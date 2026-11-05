"""Prospective complete-vocabulary routes; synthetic-only native-denied tests."""
import copy
import inspect

import pytest

from scripts import arv2_r298_sharadar_current_routes as m
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as fixture


def rows():
    return [fixture.metadata('QCOM', 1)], [
        fixture.metadata(ticker, index, fund=True) for index, ticker in enumerate(m.ETF_TICKERS, 2)]


@pytest.fixture(autouse=True)
def no_frozen_operations_or_parser(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('frozen operation/parser used')
    for module in (m.previous, m.previous.previous):
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, '_fetch', deny)
    monkeypatch.setattr(m.previous, '_route_quality', deny)
    monkeypatch.setattr(m.previous, '_routes', deny)
    monkeypatch.setattr(m.previous.composer, '_sharadar_cusips', deny)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught: callback()
    assert m.finite(caught.value) == code


def test_complete_parser_used_in_quality_metadata_and_selection_without_legacy_globals():
    stocks,funds=rows()
    funds[1]['cusips']='ABCDEF123 ABCDEF124 ABCDEF125'
    funds[4]['cusips']='ABCDEF126, ABCDEF127, ABCDEF128, ABCDEF129'
    assert m.route_quality(funds[1],'funds') is True
    assert m.route_quality(funds[4],'funds') is True
    raw=fixture.csv_bytes(m.FIELDS,funds)
    parsed,summary,permas,tickers=m.metadata(raw,'funds',16*1024*1024)
    assert summary['unsupported_or_incomplete_route_row_count']==0
    assert permas[funds[1]['permaticker']]==tickers[funds[1]['ticker']]==1
    selected=m.require_probe_routes(stocks,parsed)
    assert selected==stocks+funds and selected[2] is not funds[1]
    receipt=m.catalog(stocks,funds)
    assert receipt['probes'][2]['complete_vocabulary_token_count']==3
    assert receipt['probes'][5]['complete_vocabulary_token_count']==4
    assert receipt['cusip_census_status']=='complete' and receipt['unknown_vocabulary_row_count']==0
    assert m.validate_catalog(receipt,stocks,funds)==receipt
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    serialized=m.canonical(receipt)
    assert b'ABCDEF' not in serialized and b'QCOM' not in serialized


@pytest.mark.parametrize('mode',['same_later','cross_later','third_token'])
def test_every_token_same_or_cross_table_collision_refuses_selected_route(mode):
    stocks,funds=rows()
    if mode=='same_later':
        funds[1]['cusips']+=' ABCDEF123';funds[4]['cusips']+=' ABCDEF123'
    elif mode=='cross_later':
        stocks[0]['cusips']+=' ABCDEF123';funds[4]['cusips']+=' ABCDEF123'
    else:
        stocks[0]['cusips']+=' ABCDEF122 ABCDEF123';funds[4]['cusips']+=' ABCDEF124 ABCDEF123'
    receipt=m.catalog(stocks,funds)
    assert receipt['complete_token_collision_groups']==1
    assert any(probe['same_table_complete_token_overlap_rows'] or probe['cross_table_complete_token_overlap_rows']
        for probe in receipt['probes'])
    refused('route_collision',lambda:m.require_probe_routes(stocks,funds))


@pytest.mark.parametrize('delimiter',[',',' '])
def test_duplicate_normalized_vocabulary_never_satisfies_quality_or_route(delimiter):
    stocks,funds=rows();funds[1]['cusips']=delimiter.join(('abcdef123','ABCDEF123'))
    assert m.route_quality(funds[1],'funds') is False
    receipt=m.catalog(stocks,funds)
    assert receipt['probes'][2]['vocabulary_status']=='malformed'
    assert receipt['cusip_census_status']=='incomplete_unknown_vocabulary'
    refused('route_shape',lambda:m.require_probe_routes(stocks,funds))


@pytest.mark.parametrize('value',['ABCDEF123;ABCDEF124','000000001JUNK','ABCDEF123|ABCDEF124',''])
def test_unknown_or_missing_required_vocabulary_is_not_silently_repaired(value):
    stocks,funds=rows();funds[1]['cusips']=value
    assert m.route_quality(funds[1],'funds') is False
    refused('route_shape',lambda:m.require_probe_routes(stocks,funds))
    receipt=m.catalog(stocks,funds)
    assert receipt['probes'][2]['shape_predicates_satisfied'] is False
    assert receipt['unknown_vocabulary_row_count']==1
    assert receipt['probes'][2]['same_table_complete_token_overlap_rows'] is None


@pytest.mark.parametrize('value',['bad','', 'ABCDEF123;unrecognized'])
def test_unrelated_unknown_vocab_is_counted_unknown_not_global_no_collision(value):
    stocks,funds=rows();other=fixture.metadata('OTHER',90);other['cusips']=value;stocks.append(other)
    receipt=m.catalog(stocks,funds)
    assert receipt['cusip_census_status']=='incomplete_unknown_vocabulary'
    assert receipt['unknown_vocabulary_row_count']==1
    assert receipt['tables']['stocks']['row_count']==2
    assert len(m.require_probe_routes(stocks,funds))==9
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('role',['stocks','funds'])
def test_malformed_unrelated_row_overlapping_any_token_poisoned_for_refusal_only(role):
    stocks,funds=rows()
    stocks[0]['cusips']+=' ABCDEF123'
    other=fixture.metadata('OTHER',90,fund=role=='funds');other['cusips']='ABCDEF123;INVALID'
    (stocks if role=='stocks' else funds).append(other)
    receipt=m.catalog(stocks,funds)
    assert receipt['unknown_vocabulary_row_count']==1
    assert receipt['malformed_overlap_token_groups']==1
    assert receipt['probes'][0]['malformed_field_overlap_rows']==1
    refused('route_collision',lambda:m.require_probe_routes(stocks,funds))


@pytest.mark.parametrize('kind',['duplicate_row','same_perma','same_figi','same_ticker','cross_perma','cross_figi','cross_ticker'])
def test_row_perma_figi_and_ticker_ambiguity_cannot_be_hidden_by_distinct_tokens(kind):
    stocks,funds=rows()
    if kind=='duplicate_row':stocks.append(dict(stocks[0]))
    elif kind=='same_ticker':
        other=fixture.metadata('QCOM',90);stocks.append(other)
    elif kind=='cross_ticker':
        other=fixture.metadata('QCOM',90,fund=True);funds.append(other)
    elif kind.startswith('same_'):
        other=fixture.metadata('OTHER',90);other['permaticker' if kind=='same_perma' else 'figi']=stocks[0]['permaticker' if kind=='same_perma' else 'figi']
        stocks.append(other)
    else:
        other=fixture.metadata('OTHER',90,fund=True);other['permaticker' if kind=='cross_perma' else 'figi']=stocks[0]['permaticker' if kind=='cross_perma' else 'figi']
        funds.append(other)
    refused('route_missing_or_ambiguous' if kind in ('duplicate_row','same_ticker') else 'route_collision',
        lambda:m.require_probe_routes(stocks,funds))


@pytest.mark.parametrize('field,value', [('category','Preferred Stock'),('currency','EUR'),('exchange','UNKNOWN'),
    ('figi','bad'),('permaticker',''),('isdelisted','?'),('table','OTHER')])
def test_other_route_predicates_remain_strict(field,value):
    stocks,funds=rows();stocks[0][field]=value
    assert m.route_quality(stocks[0],'stocks') is False
    refused('table' if field=='table' else 'route_shape',lambda:m.require_probe_routes(stocks,funds))


@pytest.mark.parametrize('field,value',[('firstpricedate','2021-01-01'),('firstpricedate','bad'),
    ('lastpricedate','2020-12-30'),('lastupdated','not-a-date')])
def test_prior_date_interval_remains_exact(field,value):
    stocks,funds=rows();stocks[0][field]=value
    refused('route_interval',lambda:m.require_probe_routes(stocks,funds))


@pytest.mark.parametrize('kind',['extra_field','missing_field','field_type','field_subclass','control','surrogate','outer_space','bound'])
def test_bounded_primitive_row_contract(kind):
    class Text(str):pass
    stock=rows()[0][0]
    if kind=='extra_field':stock['extra']='raw'
    elif kind=='missing_field':del stock['cusips']
    elif kind=='field_type':stock['cusips']=None
    elif kind=='field_subclass':stock['cusips']=Text('000000001')
    elif kind=='control':stock['cusips']='000000001\t000000002'
    elif kind=='surrogate':stock['cusips']='\ud800'
    elif kind=='outer_space':stock['cusips']=' 000000001'
    else:stock['cusips']='A'*2049
    refused('row_shape',lambda:m.route_quality(stock,'stocks'))


def test_catalog_joint_rows_bytes_and_CSV_bounds(monkeypatch):
    stocks,funds=rows()
    monkeypatch.setattr(m,'MAX_CATALOG_BYTES',1)
    refused('catalog_bound',lambda:m.catalog(stocks,funds))
    refused('catalog_bound',lambda:m.metadata(b'x','stocks',True))
    refused('metadata_csv',lambda:m.metadata(b'bad header\n','stocks',65536))


def test_metadata_counts_unrelated_missing_and_bad_fields_instead_of_blessing_or_dropping():
    stocks,_=rows();other=fixture.metadata('OTHER',90)
    other.update(cusips='bad',figi='',category='Preferred Stock',lastupdated='bad')
    stocks.append(other)
    raw=fixture.csv_bytes(m.FIELDS,stocks)
    parsed,summary,_,_=m.metadata(raw,'stocks',65536)
    assert len(parsed)==2
    assert summary['unsupported_or_incomplete_route_row_count']==1
    assert summary['missing_field_counts']['figi']==1
    assert summary['invalid_nonempty_date_field_count']==1


@pytest.mark.parametrize('change',['flag','hash','count_bool','rowcount','unknown','status','probe_bool',
    'candidate','missing_hash','state','token_count','overlap_bool','overlap_bound','empty_vocabulary'])
def test_closed_supplied_receipt_rejects_impossible_or_upgraded_claims(change):
    stocks,funds=rows();receipt=m.catalog(stocks,funds);probe=receipt['probes'][0]
    if change=='flag':receipt['current_identity_admitted']=True
    elif change=='hash':receipt['metadata_rows_sha256']['stocks']='x'
    elif change=='count_bool':receipt['unknown_vocabulary_row_count']=False
    elif change=='rowcount':receipt['tables']['stocks']['row_count']=0
    elif change=='unknown':receipt['unknown_vocabulary_row_count']=1
    elif change=='status':receipt['cusip_census_status']='complete_no_collisions_proven'
    elif change=='probe_bool':probe['shape_predicates_satisfied']=1
    elif change=='candidate':probe['candidate_count']=99
    elif change=='missing_hash':probe['candidate_count']=0
    elif change=='state':probe['vocabulary_status']='admitted'
    elif change=='token_count':probe['complete_vocabulary_token_count']=0
    elif change=='overlap_bool':probe['same_table_complete_token_overlap_rows']=False
    elif change=='overlap_bound':probe['malformed_field_overlap_rows']=1
    else:probe['vocabulary_status']='missing'
    refused('receipt',lambda:m.validate_receipt(receipt))


def test_received_catalog_is_recomputed_and_returns_fresh_data():
    stocks,funds=rows();receipt=m.catalog(stocks,funds)
    changed=copy.deepcopy(stocks);changed[0]['cusips']='ABCDEF123'
    refused('receipt',lambda:m.validate_catalog(receipt,changed,funds))
    checked=m.validate_receipt(receipt);checked['tables']['stocks']['row_count']=0
    assert receipt['tables']['stocks']['row_count']==1
    assert m.validate_catalog(receipt,stocks,funds)==receipt


def test_profile_and_imports_do_not_reinterpret_original_input_or_accept_identity():
    profile=m.profile_record()
    assert profile['legacy_composer_and_evidence_unchanged'] is True
    assert profile['quality_and_selection_share_complete_parser'] is True
    assert profile['malformed_field_shape_tokens']=='refusal_only_never_admission'
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    source=inspect.getsource(m)
    assert '.observe(' not in source and '._fetch(' not in source and '_sharadar_cusips(' not in source


def test_finite_mapping_is_exact_type_only():
    class Child(m.Refused):pass
    assert m.finite(m.Refused('route_collision'))=='route_collision'
    assert m.finite(Child('route_collision'))=='unknown'
    assert m.finite(ValueError('secret'))=='unknown'
