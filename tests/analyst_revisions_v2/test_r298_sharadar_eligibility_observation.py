"""S six-request pure provider boundary; synthetic responses, native denial."""
import copy
import csv
import io
import json
import pickle
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import arv2_r298_sharadar_eligibility_observation as m

KEY = 'synthetic-SECRET+/"1234'


def csv_bytes(fields, rows):
    stream = io.StringIO(newline=''); writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(fields)
    for row in rows: writer.writerow([row[key] for key in fields])
    return stream.getvalue().encode('utf-8')


def metadata(ticker, index, *, fund=False):
    return dict(zip(m.META_FIELDS, ('funds' if fund else 'stocks', ticker, str(1000 + index),
        'NYSEARCA' if fund else 'NASDAQ', 'N', 'ETF' if fund else 'Domestic Common Stock',
        f'{index:09d}', f'BBG{index:09d}', 'USD', '2000-01-01', '2026-10-26', '2026-10-25'), strict=True))


def payloads():
    """Public synthetic factory shared with caller tests; no licensed bytes."""
    stock = metadata('QCOM', 1)
    funds = [metadata(ticker, index, fund=True) for index, ticker in enumerate(m.ETF_TICKERS, 2)]
    def status(table): return m.canonical({'table': table, 'name': table + '.csv.zip',
        'size': 1000000, 'sizeLabel': '1.0 MB', 'modified': '2026-10-25T00:00:00+00:00'})
    def price(row): return {'ticker': row['ticker'], 'date': m.REFERENCE_SESSION,
        'closeunadj': '12.50', 'lastupdated': '2026-10-25'}
    return dict(zip(m.CAPTURE_NAMES, (csv_bytes(m.META_FIELDS, [stock]), csv_bytes(m.META_FIELDS, funds),
        status('stocks'), status('funds'), csv_bytes(m.PRICE_FIELDS, [price(stock)]),
        csv_bytes(m.PRICE_FIELDS, [price(row) for row in funds])), strict=True))


def rows(raw): return list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))


@pytest.fixture(autouse=True)
def no_old_fetch_or_observe(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('spent O operation')
    monkeypatch.setattr(m.previous, 'observe', deny)
    monkeypatch.setattr(m.previous, '_fetch', deny)


@pytest.fixture
def transport(monkeypatch):
    state = NS(captures=payloads(), calls=[], events=[], bodies=[], responses=[],
        statuses=[200] * 6, headers={}, mutation=None, request_failure=False)
    session = m.configure_owned_session(requests.Session())
    def get(self, url, **kwargs):
        index = len(state.calls); state.calls.append((url, copy.deepcopy(kwargs)))
        if state.request_failure: raise RuntimeError(KEY)
        response = requests.Response(); response.status_code = state.statuses[index]
        response.request = self.prepare_request(requests.Request('GET', url, params=kwargs['params'], headers=kwargs['headers']))
        response.url = response.request.url; response.history = []
        response.headers.update(state.headers); response.closed = False
        raw = state.captures[m.CAPTURE_NAMES[index]]
        def content(chunk_size):
            state.bodies.append(index)
            yield raw
        def close(): response.closed = True
        response.iter_content, response.close = content, close
        if state.mutation: state.mutation(self, response, index)
        state.responses.append(response)
        return response
    monkeypatch.setattr(requests.Session, 'get', get)
    state.session = session
    state.journal = lambda marker, event: state.events.append((marker, copy.deepcopy(event)))
    return state


def observe(transport):
    return m.observe(session=transport.session, api_key=KEY, journal=transport.journal, deadline=time.monotonic() + 30)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught: callback()
    assert m.finite(caught.value) == code


def test_exact_six_requests_real_fetch_and_private_capture(transport):
    receipt, private = observe(transport)
    assert receipt['application_dispatch_attempts'] == 6 and receipt['http_statuses'] == [200] * 6
    assert receipt['provider_request_count'] is None and all(receipt[key] is False for key in m.FALSE_FLAGS)
    assert receipt['early_prices']['stocks']['observed_row_count'] == 1
    assert receipt['early_prices']['funds']['observed_row_count'] == 8
    assert len(transport.calls) == 6 and transport.bodies == list(range(6))
    assert all(response.closed for response in transport.responses)
    for index, (url, kwargs) in enumerate(transport.calls):
        path, query = m._query(m.ROLES[index])
        assert url == m.BASE + path and kwargs['params'] == {**query, 'api_key': KEY}
        assert kwargs['verify'] is kwargs['stream'] is True and kwargs['allow_redirects'] is False
        assert kwargs['headers'] == {'Accept-Encoding': 'identity'} and 0 < kwargs['timeout'] <= 30
    assert private.bytes_by_name() == transport.captures
    assert m.validate_capture(receipt, private.bytes_by_name()) == receipt
    assert m.capture_pins(receipt) == receipt['capture_pins']
    assert m.validate_events(receipt, [event for _, event in transport.events])
    raw = m.canonical(receipt)
    assert KEY.encode() not in raw and b'QCOM' not in raw and b'SPY' not in raw and b'12.50' not in raw
    assert 'QCOM' not in repr(private)
    with pytest.raises(TypeError): pickle.dumps(private)


def test_frozen_public_eight_symbols_and_no_metadata_date_filters():
    assert m.ETF_TICKERS == m.targets.UNIVERSES == ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE', 'XLI', 'XLF')
    for role in m.ROLES[:2]:
        _, query = m._query(role)
        assert 'from' not in query and 'to' not in query and query['limit'] == '100000'
    assert m._query('funds_early')[1]['ticker'] == ','.join(m.ETF_TICKERS)


def test_zero_prices_is_observed_absence_not_entitlement_or_input(transport):
    transport.captures[m.CAPTURE_NAMES[4]] = csv_bytes(m.PRICE_FIELDS, [])
    transport.captures[m.CAPTURE_NAMES[5]] = csv_bytes(m.PRICE_FIELDS, [])
    receipt, _ = observe(transport)
    assert receipt['early_prices']['stocks']['missing_symbol_count'] == 1
    assert receipt['early_prices']['funds']['missing_symbol_count'] == 8
    assert receipt['paid_tier_proven'] is receipt['strategy_price_admitted'] is False


@pytest.mark.parametrize('index', range(6))
@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_failed_http_status_is_journaled_no_failed_body_or_retry(transport, index, status):
    transport.statuses[index] = status
    refused('http_status', lambda: observe(transport))
    assert len(transport.calls) == index + 1 and transport.bodies == list(range(index))
    assert transport.events[-1][1]['http_status'] == status


@pytest.mark.parametrize('status', [True, None, '403', 600])
def test_invalid_http_status_is_unknown_not_zero(transport, status):
    transport.statuses[0] = status
    refused('http_status_unavailable', lambda: observe(transport))
    assert transport.events[-1][1]['http_status'] is None and transport.bodies == []


def test_unrelated_missing_metadata_is_counted_not_blanket_refused(transport):
    other = metadata('OTHER', 90)
    for name in ('figi', 'cusips', 'exchange', 'category', 'currency'): other[name] = ''
    original = rows(transport.captures[m.CAPTURE_NAMES[0]])
    transport.captures[m.CAPTURE_NAMES[0]] = csv_bytes(m.META_FIELDS, original + [other])
    result, _ = observe(transport)
    assert result['metadata']['stocks']['unsupported_or_incomplete_route_row_count'] == 1
    assert result['metadata']['stocks']['missing_field_counts']['figi'] == 1


@pytest.mark.parametrize('kind', ['perma', 'ticker', 'figi', 'cusip', 'malformed_cusip', 'cross'])
def test_used_route_collisions_stop_before_status_or_price(transport, kind):
    original = rows(transport.captures[m.CAPTURE_NAMES[0]])
    extra = metadata('OTHER', 90)
    if kind == 'perma': extra['permaticker'] = original[0]['permaticker']
    elif kind == 'ticker': extra['ticker'] = 'QCOM'
    elif kind == 'figi': extra['figi'] = original[0]['figi']
    elif kind in ('cusip', 'malformed_cusip'): extra['cusips'] = original[0]['cusips'] + (';bad' if kind == 'malformed_cusip' else '')
    elif kind == 'cross':
        other = rows(transport.captures[m.CAPTURE_NAMES[1]]); other[0]['permaticker'] = original[0]['permaticker']
        transport.captures[m.CAPTURE_NAMES[1]] = csv_bytes(m.META_FIELDS, other)
    if kind != 'cross': transport.captures[m.CAPTURE_NAMES[0]] = csv_bytes(m.META_FIELDS, original + [extra])
    with pytest.raises(m.Refused): observe(transport)
    assert len(transport.calls) == 2


@pytest.mark.parametrize('field,value', [('currency','EUR'),('category','Preferred Stock'),('figi',''),
    ('cusips',''),('exchange','UNKNOWN'),('firstpricedate','2021-01-01')])
def test_used_probe_metadata_must_be_eligible_before_early_price_request(transport, field, value):
    stock = rows(transport.captures[m.CAPTURE_NAMES[0]]); stock[0][field] = value
    transport.captures[m.CAPTURE_NAMES[0]] = csv_bytes(m.META_FIELDS, stock)
    with pytest.raises(m.Refused): observe(transport)
    assert len(transport.calls) == 2


@pytest.mark.parametrize('field,value', [('table','SEP'),('name','other.zip'),('size',True),('size',0),
    ('modified','2026-10-25T00:00:00'),('modified','bad'),('extra','private')])
def test_status_closed_primary_documented_shape(transport, field, value):
    status = json.loads(transport.captures[m.CAPTURE_NAMES[2]]); status[field] = value
    transport.captures[m.CAPTURE_NAMES[2]] = m.canonical(status)
    refused('status_json', lambda: observe(transport))
    assert len(transport.calls) == 3


@pytest.mark.parametrize('value', ['0','-1','NaN','Infinity','1e99999'])
def test_prices_positive_finite_and_bounded(transport, value):
    price = rows(transport.captures[m.CAPTURE_NAMES[4]]); price[0]['closeunadj'] = value
    transport.captures[m.CAPTURE_NAMES[4]] = csv_bytes(m.PRICE_FIELDS, price)
    if value == '1e99999':
        # Decimal is finite even at this exponent. The financial format alone
        # imposes no economic ceiling; it remains non-admitted private evidence.
        result, _ = observe(transport); assert result['strategy_price_admitted'] is False
    else: refused('price_value', lambda: observe(transport))


@pytest.mark.parametrize('kind', ['ticker','date','duplicate'])
def test_price_exact_symbols_session_and_unique_census(transport, kind):
    price = rows(transport.captures[m.CAPTURE_NAMES[4]])
    if kind == 'ticker': price[0]['ticker'] = 'OTHER'
    elif kind == 'date': price[0]['date'] = '2021-01-04'
    else: price.append(dict(price[0]))
    transport.captures[m.CAPTURE_NAMES[4]] = csv_bytes(m.PRICE_FIELDS, price)
    refused('price_identity', lambda: observe(transport))


@pytest.mark.parametrize('kind', ['raw','csv_quotes','json_unicode','header'])
def test_secret_echo_is_rejected_before_private_capture(transport, kind):
    if kind == 'header': transport.headers['Debug'] = KEY
    elif kind in ('raw','csv_quotes'):
        stock = rows(transport.captures[m.CAPTURE_NAMES[0]])
        other = metadata('OTHER', 90); other['category'] = KEY
        transport.captures[m.CAPTURE_NAMES[0]] = csv_bytes(m.META_FIELDS, stock + [other])
        if kind == 'raw': transport.captures[m.CAPTURE_NAMES[0]] += KEY.encode()
    else:
        status = json.loads(transport.captures[m.CAPTURE_NAMES[2]]); status['sizeLabel'] = KEY
        raw = m.canonical(status)
        encoded = ''.join('\\u%04x' % ord(char) for char in KEY).encode()
        transport.captures[m.CAPTURE_NAMES[2]] = raw.replace(json.dumps(KEY).encode(), b'"' + encoded + b'"')
    refused('credential_echo', lambda: observe(transport))


def test_metadata_limit_refused_not_silent_truncated_census(transport, monkeypatch):
    monkeypatch.setattr(m, 'MAX_ROWS', 1)
    refused('metadata_limit', lambda: observe(transport))
    assert len(transport.calls) == 1


@pytest.mark.parametrize('kind,code', [('encoding','csv_encoding'),('header','csv_header'),
    ('row','csv_row_shape'),('field','csv_field_shape')])
def test_finite_csv_failures_distinguish_safe_schema_causes(transport, kind, code):
    raw = transport.captures[m.CAPTURE_NAMES[0]]
    if kind == 'encoding': raw = b'\xff'
    elif kind == 'header': raw = raw.replace(b'permaticker', b'othercolumn')
    elif kind == 'row': raw += b'only-one-cell\n'
    else:
        stock = rows(raw); stock[0]['category'] = 'x' * 2049
        raw = csv_bytes(m.META_FIELDS, stock)
    transport.captures[m.CAPTURE_NAMES[0]] = raw
    refused(code, lambda: observe(transport))
    assert len(transport.calls) == 1


@pytest.mark.parametrize('change', ['stock0','fund0','duplicate','missing_count','bool_status','pin','flag','extra'])
def test_supplied_receipt_crosscensus_and_false_flags(transport, change):
    receipt, _ = observe(transport)
    if change == 'stock0': receipt['metadata']['stocks']['row_count'] = 0
    elif change == 'fund0': receipt['metadata']['funds']['row_count'] = 0
    elif change == 'duplicate': receipt['metadata']['stocks']['duplicate_ticker_count'] = 1
    elif change == 'missing_count': receipt['early_prices']['funds']['missing_symbol_count'] = 1
    elif change == 'bool_status': receipt['http_statuses'][0] = True
    elif change == 'pin': receipt['capture_pins'][m.CAPTURE_NAMES[0]]['sha256'] = 'notsha'
    elif change == 'flag': receipt['strategy_price_admitted'] = True
    else: receipt['raw_route'] = 'PRIVATE'
    refused('receipt', lambda: m.validate_receipt(receipt))


def test_capture_and_event_both_source_bound(transport):
    receipt, opaque = observe(transport); captures = opaque.bytes_by_name()
    captures[m.CAPTURE_NAMES[4]] += b'\n'
    with pytest.raises(m.Refused): m.validate_capture(receipt, captures)
    events = [value for _, value in transport.events]; events[1]['application_attempt'] = True
    with pytest.raises(m.Refused): m.validate_events(receipt, events)


def test_unowned_environment_session_and_deadline_refuse_without_contact(transport):
    transport.session.trust_env = True
    refused('session', lambda: observe(transport))
    assert transport.calls == []
    transport.session.trust_env = False
    with pytest.raises(m.Refused):
        m.observe(session=transport.session, api_key=KEY, journal=transport.journal, deadline=time.monotonic()-1)
    assert transport.calls == []
