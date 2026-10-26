"""Synthetic injected provider boundary; no source, credential or network use."""
import copy
import csv
import io
import pickle
import time
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import pytest
import requests

from scripts import arv2_r298_sharadar_reference_observation as m


KEY = 'synthetic-SECRET+/"1234'


def csv_bytes(fields, row=None):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n'); writer.writerow(fields)
    if row is not None: writer.writerow(row)
    return stream.getvalue().encode()


@pytest.fixture
def packet():
    return {'permaticker': '123456', 'expected_composite_figi': 'BBG000000001',
        'exchange_mic': 'XNAS', 'original_cusips': ('123456789',)}


@pytest.fixture
def transport(monkeypatch):
    state = NS(calls=[], events=[], bodies=[], responses=[], mutation=None,
        metadata=['SEP', 'SYNTHX', '123456', 'NASDAQ', 'N', 'Domestic Common Stock',
            '123456789', 'BBG000000001', 'USD', '2000-01-01', '2026-10-24', '2026-10-25'],
        price=['SYNTHX', '2022-10-21', '12.50', '2026-10-25'], statuses=[200, 200],
        headers={}, chunks=None, fail=None, close_failure=False, raw_meta=None, raw_price=None)
    session = m.configure_owned_session(requests.Session())
    def get(self, url, **kwargs):
        index = len(state.calls)
        state.calls.append((url, copy.deepcopy(kwargs)))
        if state.fail == 'request': raise RuntimeError(KEY)
        response = requests.Response(); response.status_code = state.statuses[index]
        response.request = self.prepare_request(requests.Request('GET', url,
            params=kwargs['params'], headers=kwargs['headers']))
        response.url = response.request.url; response.history = []
        response.headers.update(state.headers)
        response.closed = False
        payload = (state.raw_meta if state.raw_meta is not None else csv_bytes(m.META_FIELDS, state.metadata)) if index == 0 else (
            state.raw_price if state.raw_price is not None else csv_bytes(m.PRICE_FIELDS, state.price))
        def content(chunk_size):
            state.bodies.append(index)
            if state.fail == 'body': raise AssertionError('failed body must remain unread')
            if state.chunks is not None: yield from state.chunks
            else: yield payload
        def close():
            response.closed = True
            if state.close_failure: raise RuntimeError(KEY)
        response.iter_content, response.close = content, close
        state.responses.append(response)
        if state.mutation is not None: state.mutation(self, response, index)
        return response
    monkeypatch.setattr(requests.Session, 'get', get)
    state.session = session
    def journal(marker, event): state.events.append((marker, copy.deepcopy(event)))
    state.journal = journal
    return state


def observe(packet, transport, **kwargs):
    return m.observe(packet, session=transport.session, api_key=KEY,
        journal=transport.journal, deadline=time.monotonic() + 30, **kwargs)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught: callback()
    assert m.finite(caught.value) == code


def test_two_fixed_requests_success_and_closed_events(packet, transport):
    receipt, opaque = observe(packet, transport)
    assert receipt['status'] == 'vendor_row_observed' and receipt['price_row_count'] == 1
    assert receipt['application_dispatch_attempts'] == 2 and receipt['http_statuses'] == [200, 200]
    assert receipt['provider_request_count'] is None
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    assert len(transport.calls) == 2 and transport.bodies == [0, 1]
    assert all(response.closed for response in transport.responses)
    for index, (url, kwargs) in enumerate(transport.calls):
        assert url == m.BASE + ('/v1.0/data/tickers' if index == 0 else '/v1.0/data/stocks')
        assert kwargs['allow_redirects'] is False and kwargs['stream'] is True and kwargs['verify'] is True
        assert kwargs['headers'] == {'Accept-Encoding': 'identity'} and 0 < kwargs['timeout'] <= 30
        query = kwargs['params']; assert query['api_key'] == KEY and query['limit'] == '2' and query['skip'] == '0'
        assert query['format'] == 'csv'
        if index == 0:
            assert query['table'] == 'stocks' and query['permaticker'] == packet['permaticker']
            assert query['fields'] == ','.join(m.META_FIELDS) and 'from' not in query and 'to' not in query
        else:
            assert query['ticker'] == 'SYNTHX' and query['from'] == query['to'] == '2022-10-21'
            assert query['fields'] == ','.join(m.PRICE_FIELDS)
    events = [event for marker, event in transport.events]
    assert [marker for marker, event in transport.events] == ['metadata-intent', 'metadata-status', 'price-intent', 'price-status']
    assert m.validate_events(receipt, events) == events
    raw_meta, raw_price = opaque.bytes_pair()
    assert m.validate_capture(packet, receipt, raw_meta, raw_price) == receipt
    assert m.capture_pins(receipt) == {'metadata.csv': {'byte_count': len(raw_meta), 'sha256': m.sha(raw_meta)},
        'price.csv': {'byte_count': len(raw_price), 'sha256': m.sha(raw_price)}}
    assert KEY not in repr(opaque) and 'SYNTHX' not in repr(opaque)
    with pytest.raises(TypeError): pickle.dumps(opaque)


def test_zero_price_rows_is_valid_absence_not_price_admission(packet, transport):
    transport.price = None
    receipt, opaque = observe(packet, transport)
    assert receipt['status'] == 'vendor_row_absent' and receipt['price_row_count'] == 0
    assert receipt['unadjusted_close_positive_finite'] is False
    assert m.validate_capture(packet, receipt, *opaque.bytes_pair()) == receipt


@pytest.mark.parametrize('status', [401, 403, 429, 500, 599])
def test_failed_numeric_status_journaled_before_body_and_closed(packet, transport, status):
    transport.statuses[0] = status; transport.fail = 'body'; transport.close_failure = True
    refused('http_status', lambda: observe(packet, transport))
    assert transport.bodies == [] and len(transport.calls) == 1 and transport.responses[0].closed
    assert transport.events[-1][1]['http_status'] == status


@pytest.mark.parametrize('status', [True, False, 99, 600, '403', None])
def test_unusable_numeric_status_is_unknown_not_zero(packet, transport, status):
    transport.statuses[0] = status; transport.fail = 'body'
    refused('http_status_unavailable', lambda: observe(packet, transport))
    assert transport.bodies == [] and transport.events[-1][1]['http_status'] is None
    assert transport.events[-1][1]['http_status_state'] == 'unavailable'


@pytest.mark.parametrize('form', ['literal', 'quoted', 'plus', 'lower_percent', 'json', 'header'])
def test_credential_echo_never_returns_private_payload(packet, transport, form):
    variants = {'literal': KEY.encode(), 'quoted': quote(KEY, safe='').encode(),
        'plus': quote_plus(KEY, safe='').encode(), 'lower_percent': quote(KEY, safe='').lower().replace('synthetic-secret', 'synthetic-SECRET').encode(),
        'json': m.json.dumps(KEY)[1:-1].encode()}
    if form == 'header': transport.headers = {'X-Provider-Debug': KEY}
    else: transport.raw_meta = csv_bytes(m.META_FIELDS, transport.metadata) + variants[form]
    refused('credential_echo', lambda: observe(packet, transport))
    assert len(transport.calls) == 1 and transport.responses[0].closed
    if form == 'header': assert transport.bodies == []


@pytest.mark.parametrize('field,value,code', [('table','SF1','metadata_identity'),
    ('permaticker','654321','metadata_identity'), ('figi','BBG000000002','metadata_identity'),
    ('exchange','NYSE','metadata_identity'), ('category','ETF','metadata_identity'),
    ('cusips','987654321','metadata_identity'), ('currency','EUR','metadata_currency'),
    ('firstpricedate','2022-10-22','metadata_interval'), ('lastpricedate','2022-10-20','metadata_interval'),
    ('lastupdated','2026-99-25','metadata_interval'), ('ticker','BAD/TICKER','metadata_identity'),
    ('isdelisted','UNKNOWN','metadata_identity')])
def test_metadata_identity_and_coverage_before_price_dispatch(packet, transport, field, value, code):
    transport.metadata[m.META_FIELDS.index(field)] = value
    refused(code, lambda: observe(packet, transport))
    assert len(transport.calls) == 1 and len(transport.events) == 2


@pytest.mark.parametrize('field,value,code', [('ticker','OTHER','price_identity'),
    ('date','2022-10-20','price_identity'), ('lastupdated','bad','price_identity'),
    ('closeunadj','NaN','price_value'), ('closeunadj','Infinity','price_value'),
    ('closeunadj','0','price_value'), ('closeunadj','-2','price_value'), ('closeunadj','1,234','price_value')])
def test_exact_unadjusted_price_or_finite_refusal(packet, transport, field, value, code):
    transport.price[m.PRICE_FIELDS.index(field)] = value
    refused(code, lambda: observe(packet, transport))
    assert len(transport.calls) == 2 and all(response.closed for response in transport.responses)


@pytest.mark.parametrize('role,kind,code', [('metadata','empty','metadata_census'),
    ('metadata','two','metadata_census'), ('price','two','price_census'),
    ('metadata','header','csv'), ('price','adjusted','csv'), ('metadata','invalid_utf8','csv'),
    ('metadata','nul','csv'), ('price','whitespace','csv')])
def test_csv_strict_shape_no_ambiguous_or_adjusted_rows(packet, transport, role, kind, code):
    fields = m.META_FIELDS if role == 'metadata' else m.PRICE_FIELDS
    row = transport.metadata if role == 'metadata' else transport.price
    raw = csv_bytes(fields, row)
    if kind == 'empty': raw = csv_bytes(fields)
    elif kind == 'two': raw += csv_bytes(fields, row).split(b'\n', 1)[1]
    elif kind == 'header': raw = raw.replace(b'table,', b'table,table,', 1)
    elif kind == 'adjusted': raw = raw.replace(b'closeunadj', b'close')
    elif kind == 'invalid_utf8': raw += b'\xff'
    elif kind == 'nul': raw += b'\x00'
    elif kind == 'whitespace': raw = raw.replace(b'12.50', b' 12.50')
    setattr(transport, 'raw_meta' if role == 'metadata' else 'raw_price', raw)
    refused(code, lambda: observe(packet, transport))


@pytest.mark.parametrize('kind', ['trust_env','verify','auth','proxy','header','hook','retry','instance_callable'])
def test_unsafe_session_refuses_before_any_intent(packet, transport, kind):
    session = transport.session
    if kind == 'trust_env': session.trust_env = True
    elif kind == 'verify': session.verify = False
    elif kind == 'auth': session.auth = ('synthetic', 'synthetic')
    elif kind == 'proxy': session.proxies['https'] = 'http://synthetic.invalid'
    elif kind == 'header': session.headers['Authorization'] = 'synthetic'
    elif kind == 'hook': session.hooks['response'] = []
    elif kind == 'retry': session.adapters['https://'].max_retries = m.HTTPAdapter(max_retries=1).max_retries
    else: session.get = lambda *args, **kwargs: None
    refused('session', lambda: observe(packet, transport))
    assert transport.calls == transport.events == []


@pytest.mark.parametrize('kind', ['host','path','query','body','header','redirect','response_url','compression','length','chunk','oversize','short'])
def test_response_identity_and_bounds_do_not_return_bytes(packet, transport, kind):
    expected = 'prepared_identity' if kind in ('host','path','query','body','header') else {
        'compression':'response_encoding','length':'response_bound','chunk':'response_stream',
        'oversize':'response_bound','short':'response_bound'}.get(kind, 'response_identity')
    def mutate(session, response, index):
        if kind == 'host': response.request.url = response.request.url.replace('api.sharadar.com', 'example.invalid')
        elif kind == 'path': response.request.url = response.request.url.replace('/data/tickers','/data/stocks')
        elif kind == 'query': response.request.url += '&extra=1'
        elif kind == 'body': response.request.body = b'body'
        elif kind == 'header': response.request.headers['X-Extra'] = 'value'
        elif kind == 'redirect': response.history = [requests.Response()]
        elif kind == 'response_url': response.url += '&extra=1'
    transport.mutation = mutate
    if kind == 'compression': transport.headers['Content-Encoding'] = 'gzip'
    elif kind == 'length': transport.headers['Content-Length'] = str(m.MAX_META + 1)
    elif kind == 'chunk': transport.chunks = ['not-bytes']
    elif kind == 'oversize': transport.chunks = [b'x' * (m.MAX_META + 1)]
    elif kind == 'short': transport.headers['Content-Length'] = '1'
    refused(expected, lambda: observe(packet, transport))
    assert transport.responses[0].closed and len(transport.calls) == 1


def test_packet_changed_during_transport_refuses_without_price_call(packet, transport):
    def mutate(session, response, index): packet['permaticker'] = '654321'
    transport.mutation = mutate
    refused('changed', lambda: observe(packet, transport))
    assert len(transport.calls) == 1


def test_request_throw_retains_only_finite_status_unknown(packet, transport):
    transport.fail = 'request'
    refused('request_failed', lambda: observe(packet, transport))
    assert len(transport.events) == 2 and transport.events[-1][1]['http_status'] is None
    assert KEY not in repr(transport.events)


def test_pre_send_deadline_or_journal_failure_never_claims_wire_zero(packet, transport, monkeypatch):
    now = time.monotonic()
    def journal(marker, event):
        transport.events.append((marker,event)); monkeypatch.setattr(m.time, 'monotonic', lambda: now + 100)
    transport.journal = journal
    refused('request_failed', lambda: observe(packet, transport))
    assert transport.calls == [] and len(transport.events) == 2
    assert transport.events[-1][1]['http_status'] is None
    monkeypatch.setattr(m.time, 'monotonic', lambda: now)
    transport.events.clear()
    def fail(marker, event):
        transport.events.append((marker,event)); raise RuntimeError(KEY)
    transport.journal = fail
    refused('journal', lambda: observe(packet, transport))
    assert transport.calls == [] and len(transport.events) == 1


@pytest.mark.parametrize('kind', ['flag','boolcount','statuses','hash','extra','zero_bytes','count_status'])
def test_receipt_closed_types_and_events_cross_binding(packet, transport, kind):
    receipt, opaque = observe(packet, transport); bad = copy.deepcopy(receipt)
    if kind == 'flag': bad['strategy_price_admitted'] = True
    elif kind == 'boolcount': bad['application_dispatch_attempts'] = True
    elif kind == 'statuses': bad['http_statuses'] = [200, True]
    elif kind == 'hash': bad['price_csv_sha256'] = 'G' * 64
    elif kind == 'extra': bad['raw_route'] = 'synthetic'
    elif kind == 'zero_bytes': bad['price_csv_byte_count'] = 0
    else: bad['price_row_count'] = 0
    refused('receipt', lambda: m.validate_receipt(bad))
    events = [event for marker,event in transport.events]
    events[3]['http_status'] = 403
    refused('event', lambda: m.validate_events(receipt, events))
    meta, price = opaque.bytes_pair()
    refused('receipt', lambda: m.validate_capture(packet, receipt, meta, price.replace(b'12.50',b'12.51')))


def test_pure_capture_validation_has_no_request_or_key_access(packet, transport, monkeypatch):
    receipt, opaque = observe(packet, transport)
    def denied(*args, **kwargs): pytest.fail('pure validator made operation')
    monkeypatch.setattr(requests.Session, 'get', denied)
    monkeypatch.setattr(m.source, '_api_key', denied)
    assert m.validate_capture(packet, receipt, *opaque.bytes_pair()) == receipt
    assert m.finite(ValueError(KEY)) == 'unknown'
    class Subclass(m.Refused): pass
    assert m.finite(Subclass('credential')) == 'unknown'
    assert m.finite(m.Refused(KEY)) == 'unknown'
    profile = m.profile_record()
    assert profile['maximum_application_dispatch_attempts'] == 2 and profile['provider_request_count'] is None
    assert profile['metadata_from_or_to_filter'] is False and profile['retries'] == 0


def test_prepare_identity_refuses_before_application_intent(packet, transport, monkeypatch):
    original = requests.Session.prepare_request
    def changed(self, request):
        result = original(self, request); result.url += '&extra=1'; return result
    monkeypatch.setattr(requests.Session, 'prepare_request', changed)
    refused('prepared_identity', lambda: observe(packet, transport))
    assert transport.calls == transport.events == []
