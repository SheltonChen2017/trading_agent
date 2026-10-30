"""T exact public-probe matrix; synthetic transport, native denial required."""
import copy
import pickle
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import arv2_r298_sharadar_probe_metadata as m
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as fixture

KEY = fixture.KEY
csv_bytes, rows = fixture.csv_bytes, fixture.rows


def payloads():
    raw = fixture.payloads()
    return dict(zip(m.CAPTURE_NAMES, (raw['stocks-metadata.csv'], raw['funds-metadata.csv']), strict=True))


@pytest.fixture(autouse=True)
def no_previous_operations(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('spent S/O operation')
    for module in (m.previous, m.previous.previous):
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, '_fetch', deny)


@pytest.fixture
def transport(monkeypatch):
    state = NS(captures=payloads(), calls=[], events=[], bodies=[], responses=[],
        statuses=[200,200], headers={}, mutation=None)
    session = m.configure_owned_session(requests.Session())
    def get(self, url, **kwargs):
        index = len(state.calls); state.calls.append((url, copy.deepcopy(kwargs)))
        response = requests.Response(); response.status_code = state.statuses[index]
        response.request = self.prepare_request(requests.Request('GET', url, params=kwargs['params'], headers=kwargs['headers']))
        response.url = response.request.url; response.history = []; response.headers.update(state.headers)
        raw = state.captures[m.CAPTURE_NAMES[index]]; response.closed = False
        def content(chunk_size): state.bodies.append(index); yield raw
        def close(): response.closed = True
        response.iter_content, response.close = content, close
        if state.mutation: state.mutation(self, response, index)
        state.responses.append(response)
        return response
    monkeypatch.setattr(requests.Session, 'get', get)
    state.session = session
    state.journal = lambda marker,event: state.events.append((marker,copy.deepcopy(event)))
    return state


def observe(transport):
    return m.observe(session=transport.session,api_key=KEY,journal=transport.journal,deadline=time.monotonic()+30)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught: callback()
    assert m.finite(caught.value) == code


def test_two_fixed_metadata_requests_real_newfetch_and_private_buffers(transport):
    receipt, private = observe(transport)
    assert receipt['application_dispatch_attempts']==2 and receipt['http_statuses']==[200,200]
    assert receipt['provider_request_count'] is None and all(receipt[name] is False for name in m.FALSE_FLAGS)
    assert len(receipt['probes'])==9 and [row['probe_index'] for row in receipt['probes']]==list(range(9))
    for index,(url,kwargs) in enumerate(transport.calls):
        path,query=m._query(m.ROLES[index])
        assert url==m.BASE+path and kwargs['params']=={**query,'api_key':KEY}
        assert query['limit']=='100' and query['sort']=='ticker.asc' and 'from' not in query
        assert kwargs['verify'] is kwargs['stream'] is True and kwargs['allow_redirects'] is False
        assert kwargs['headers']=={'Accept-Encoding':'identity'} and 0<kwargs['timeout']<=30
    assert transport.bodies==[0,1] and all(response.closed for response in transport.responses)
    assert m.validate_capture(receipt,private.bytes_by_name())==receipt
    assert m.validate_events(receipt,[event for _,event in transport.events])
    assert m.capture_pins(receipt)==receipt['capture_pins']
    raw=m.canonical(receipt)
    assert b'QCOM' not in raw and b'SPY' not in raw and KEY.encode() not in raw
    with pytest.raises(TypeError): pickle.dumps(private)


@pytest.mark.parametrize('field,value,predicate', [('table','UNKNOWN','table_expected'),
    ('permaticker','','permaticker_format'),('figi','bad','figi_format'),
    ('cusips','','cusip_field_nonempty'),('cusips','bad','cusip_vocabulary_valid'),
    ('exchange','UNKNOWN','mic_allowed'),('category','Preferred Stock','category_expected'),
    ('currency','EUR','currency_usd'),('isdelisted','?','isdelisted_shape'),
    ('firstpricedate','invalid','first_price_date_canonical'),
    ('lastpricedate','','last_price_date_canonical'),('lastupdated','invalid','lastupdated_canonical'),
    ('firstpricedate','2021-01-01','reference_interval_contains')])
def test_exact_failed_identity_predicate_is_honest_observation_not_stop(transport,field,value,predicate):
    stock=rows(transport.captures[m.CAPTURE_NAMES[0]]);stock[0][field]=value
    transport.captures[m.CAPTURE_NAMES[0]]=csv_bytes(m.META_FIELDS,stock)
    receipt,_=observe(transport);probe=receipt['probes'][0]
    assert probe['predicates'][predicate] is False
    assert probe['failed_identity_predicate_count']>=1 and len(transport.calls)==2
    assert probe['fields'][field]['utf8_byte_count']==len(value.encode())
    assert probe['fields'][field]['value_sha256']==m.sha(m.canonical(value))
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)
    assert m.validate_capture(receipt,transport.captures)==receipt


@pytest.mark.parametrize('count',[0,2,3])
def test_missing_or_duplicate_ticker_candidates_are_explicit_unknown(transport,count):
    stock=rows(transport.captures[m.CAPTURE_NAMES[0]])
    transport.captures[m.CAPTURE_NAMES[0]]=csv_bytes(m.META_FIELDS,stock*count)
    receipt,_=observe(transport);probe=receipt['probes'][0]
    assert probe['candidate_count']==count and probe['candidate_ambiguous'] is (count>1)
    assert probe['predicates'] is probe['fields'] is None


def test_cross_route_and_same_table_collision_flags_observed_not_suppressed(transport):
    stock=rows(transport.captures[m.CAPTURE_NAMES[0]])
    other=fixture.metadata('OTHER',90);other['permaticker']=stock[0]['permaticker']
    other['cusips']=stock[0]['cusips']+';bad'
    stock.append(other);transport.captures[m.CAPTURE_NAMES[0]]=csv_bytes(m.META_FIELDS,stock)
    funds=rows(transport.captures[m.CAPTURE_NAMES[1]]);funds[0]['figi']=stock[0]['figi']
    transport.captures[m.CAPTURE_NAMES[1]]=csv_bytes(m.META_FIELDS,funds)
    receipt,_=observe(transport);probe=receipt['probes'][0]
    assert probe['predicates']['same_table_permaticker_collision'] is True
    assert probe['predicates']['same_table_cusip_collision'] is True
    assert probe['predicates']['cross_table_figi_collision'] is True
    assert receipt['unexpected_ticker_row_counts']['stocks']==1


@pytest.mark.parametrize('index',[0,1])
@pytest.mark.parametrize('status',[401,403,429,500,True,None])
def test_failed_status_retained_without_failedbody_or_retry(transport,index,status):
    transport.statuses[index]=status
    refused('http_status' if type(status) is int else 'http_status_unavailable',lambda:observe(transport))
    assert len(transport.calls)==index+1 and transport.bodies==list(range(index))
    assert transport.events[-1][1]['http_status']==(status if type(status) is int else None)


@pytest.mark.parametrize('kind',['raw','csv_quotes','header'])
def test_raw_and_decoded_secret_echo_guards_before_private_return(transport,kind):
    if kind=='header':transport.headers['Debug']=KEY
    else:
        stock=rows(transport.captures[m.CAPTURE_NAMES[0]]);stock[0]['category']=KEY
        raw=csv_bytes(m.META_FIELDS,stock)
        transport.captures[m.CAPTURE_NAMES[0]]=raw+(KEY.encode() if kind=='raw' else b'')
    refused('credential_echo',lambda:observe(transport))


@pytest.mark.parametrize('kind,code',[('UTF8','csv_encoding'),('header','csv_header'),
    ('row','csv_row_shape'),('field','csv_field_shape'),('limit','metadata_limit'),('body','response_bound')])
def test_structural_safety_still_refuses_not_quality_false(transport,kind,code):
    raw=transport.captures[m.CAPTURE_NAMES[0]]
    if kind=='UTF8':raw=b'\xff'
    elif kind=='header':raw=raw.replace(b'figi',b'other')
    elif kind=='row':raw+=b'onefield\n'
    elif kind=='field':
        stock=rows(raw);stock[0]['category']='x'*2049;raw=csv_bytes(m.META_FIELDS,stock)
    elif kind=='limit':raw=csv_bytes(m.META_FIELDS,rows(raw)*100)
    else:raw=b'x'*65537
    transport.captures[m.CAPTURE_NAMES[0]]=raw
    refused(code,lambda:observe(transport))


@pytest.mark.parametrize('change',['bool','count','field_hash','empty','predicate_currency','flags','index','extra','ambiguous'])
def test_closed_receipt_constraints_reject_forged_predicate_claims(transport,change):
    receipt,_=observe(transport);probe=receipt['probes'][0]
    if change=='bool':probe['predicates']['currency_usd']=1
    elif change=='count':probe['failed_identity_predicate_count']=99
    elif change=='field_hash':probe['fields']['currency']['value_sha256']='0'*64
    elif change=='empty':probe['fields']['currency']['utf8_byte_count']=0
    elif change=='predicate_currency':probe['predicates']['currency_usd']=False;probe['failed_identity_predicate_count']+=1
    elif change=='flags':receipt['probe_metadata_admitted']=True
    elif change=='index':probe['probe_index']=True
    elif change=='extra':probe['raw_field']='PRIVATE'
    else:probe['candidate_ambiguous']=True
    refused('predicate_receipt',lambda:m.validate_receipt(receipt))


def test_capture_and_events_recomputed_source_bound(transport):
    receipt,private=observe(transport);captures=private.bytes_by_name()
    stock=rows(captures[m.CAPTURE_NAMES[0]]);stock[0]['currency']='EUR'
    captures[m.CAPTURE_NAMES[0]]=csv_bytes(m.META_FIELDS,stock)
    refused('predicate_receipt',lambda:m.validate_capture(receipt,captures))
    events=[value for _,value in transport.events];events[1]['application_attempt']=True
    with pytest.raises(m.Refused):m.validate_events(receipt,events)


@pytest.mark.parametrize('change',['ticker_hash','ticker_length','empty_hash_nonempty','USD_length','table_length',
    'Y_length','empty_perma','empty_figi','empty_cusip','empty_exchange','empty_category','empty_first',
    'short_lastupdated','perma_collision_unknown','figi_collision_unknown','cusip_collision_unknown','ticker_collision_unknown'])
def test_predicate_matrix_cannot_claim_impossible_field_or_nullable_shapes(transport,change):
    receipt,_=observe(transport);probe=receipt['probes'][0];fields=probe['fields'];pred=probe['predicates']
    def replace(field,value):
        fields[field]={'type':'str','state':'nonempty' if value else 'empty',
            'utf8_byte_count':len(value.encode()),'value_sha256':m.sha(m.canonical(value))}
    if change=='ticker_hash':replace('ticker','OTHER')
    elif change=='ticker_length':fields['ticker']['utf8_byte_count']+=1
    elif change=='empty_hash_nonempty':fields['category']['value_sha256']=m.sha(m.canonical(''))
    elif change=='USD_length':fields['currency']['utf8_byte_count']=4
    elif change=='table_length':fields['table']['utf8_byte_count']=1
    elif change=='Y_length':fields['isdelisted']['utf8_byte_count']=2
    elif change.startswith('empty_'):
        name={'perma':'permaticker','figi':'figi','cusip':'cusips','exchange':'exchange',
            'category':'category','first':'firstpricedate'}[change[6:]]
        replace(name,'')
        if name=='cusips':pred['cusip_field_nonempty']=False
    elif change=='short_lastupdated':replace('lastupdated','1')
    else:
        name={'perma_collision_unknown':'same_table_permaticker_collision',
            'figi_collision_unknown':'cross_table_figi_collision','cusip_collision_unknown':'same_table_cusip_collision',
            'ticker_collision_unknown':'cross_table_ticker_collision'}[change]
        pred[name]=None
    probe['failed_identity_predicate_count']=sum(value is False for name,value in pred.items() if name not in m.COLLISIONS)
    probe['unknown_predicate_count']=sum(value is None for value in pred.values())
    probe['collision_predicate_count']=sum(pred[name] is True for name in m.COLLISIONS)
    refused('predicate_receipt',lambda:m.validate_receipt(receipt))


def test_missing_probe_empty_candidate_hash_is_exact(transport):
    transport.captures[m.CAPTURE_NAMES[0]]=csv_bytes(m.META_FIELDS,[])
    receipt,_=observe(transport)
    assert receipt['probes'][0]['candidate_rows_sha256']==m.sha(m.canonical([]))
    receipt['probes'][0]['candidate_rows_sha256']='0'*64
    refused('predicate_receipt',lambda:m.validate_receipt(receipt))
