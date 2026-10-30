"""Synthetic QC-local reader; no actual source book, host DATA or operations."""
import copy
import inspect
import json
import pickle
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_native_price_book_runtime as m
from tests.analyst_revisions_v2 import test_r298_native_price_source_diagnostic as fixture


def refused(code,operation):
    with pytest.raises(m.Refused) as caught:operation()
    assert m.finite(caught.value)==code
    assert 'PRIVATE' not in str(caught.value)


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('old prepare/History/publication or actual DATA forbidden')
    monkeypatch.setattr(m.native.NativePriceSourceDiagnostic,'prepare',denied)
    monkeypatch.setattr(m.native.NativePriceSourceDiagnostic,'_capture',denied)
    monkeypatch.setattr(m.publication.SpecificSourceBookNamespace,'publish',denied)
    monkeypatch.setattr(fixture.History,'__getitem__',denied)


@pytest.fixture
def case(monkeypatch):
    source=fixture.scenario.__wrapped__(monkeypatch)
    source.algorithm.project_id=40000001
    driver=source.driver()
    driver.deadline=m.clock.monotonic()+100
    package,rows,axis,sessions=driver._package()
    resolution=driver._resolve_with_census(rows)
    selected=sorted(rows[:5],key=m.digest)
    records=[]
    for ordinal,row in enumerate(selected):
        symbol=resolution.symbol_for_security(row['security_id'])
        fact=m.native._native(symbol)
        cells={index:'123.45' for index in range(len(source.grid)) if not (ordinal==0 and index==1)}
        stats={'status':'complete','call_invoked':True,'batch_count':len(cells),'payload_count':len(cells),
            'invalid_row_counts':{},'duplicate_payload_count':0}
        records.append((row,symbol,fact,(stats,cells,set(cells),set())))
    summary,book=driver._finish(resolution=resolution,selected=selected,schedule=source.grid,
        records=records,static_collisions=0,identity_phase='observed')
    raw=object.__getattribute__(book,'_raw')
    scope=m.publication.make_scope(m.SOURCE_PROJECT_ID,m.digest(source.spec),'SYNTHETIC-READER')
    key=str(m.SOURCE_PROJECT_ID)+'/arv2/r326-native/'+m.digest(scope)+'/'+book.sha256
    publication={'schema':m.publication.ATTEMPT_SCHEMA,'scope_sha256':m.digest(scope),
        'source_specification_sha256':m.digest(source.spec),'attempt_consumed':True,'phase':'complete',
        'failure_code':None,'object_key':key,'book_byte_count':len(raw),'book_sha256':book.sha256,
        'source_summary_sha256':m.digest(summary),'known_absent_observed':True,'save_returned_true':True,
        'readback_equal':True,'publication_API_checks_complete':True,**m.publication.FALSE_FLAGS}
    context={'schema':m.CONTEXT_SCHEMA,'source_fact_sha256':'a'*64,'source_project_id':m.SOURCE_PROJECT_ID,
        'source_backtest_id':'b'*32,'source_projection_sha256':'c'*64,'source_profile_sha256':'d'*64,
        'scope':scope,'specification':source.spec,'source_summary':summary,'publication':publication}
    # Synthetic-only process patch of fixed constants. No public API accepts
    # replacement pins, and production remains bound to the literal AK source.
    monkeypatch.setattr(m,'SOURCE_CONTEXT_SHA256',m.digest(context))
    monkeypatch.setattr(m,'SOURCE_SUMMARY_SHA256',m.digest(summary))
    monkeypatch.setattr(m,'SOURCE_PUBLICATION_SHA256',m.digest(publication))
    monkeypatch.setattr(m,'SOURCE_BOOK_BYTES',len(raw))
    monkeypatch.setattr(m,'SOURCE_BOOK_SHA256',book.sha256)
    monkeypatch.setattr(m,'_SOURCE_CONTEXT_JSON',m.canonical(context).decode())
    class Store:
        def __init__(self):self.calls=[];self.raw=raw;self.fail=False
        def read_bytes(self,key):
            self.calls.append(key)
            if self.fail:raise RuntimeError('PRIVATE-CACHED-ERROR')
            return self.raw
        def contains_key(self,*args):raise AssertionError('no census or existence probe')
        def save_bytes(self,*args):raise AssertionError('no write')
    store=Store();source.algorithm.object_store=store
    def reader():
        return m.SpecificNativePriceBook(source.algorithm,frozen_source_context=m.source_context(),
            expected_context_sha256=m.SOURCE_CONTEXT_SHA256,frozen_runtime_project_id=40000001,
            benchmark_symbol=source.etfs['SPY'],etf_symbols=source.etfs,trade_bar_type=fixture.Bar,
            daily_resolution='Daily',raw_normalization='RAW')
    return NS(source=source,driver=driver,summary=summary,book=book,raw=raw,context=context,
        selected=selected,store=store,key=key,reader=reader)


def test_inert_constructor_then_one_fresh_full_identity_pass_and_exact_QC_read(case):
    reader=case.reader()
    assert case.store.calls==[] and case.source.history.calls==[]
    receipt=reader.authenticate_once()
    assert case.store.calls==[case.key] and case.source.history.calls==[]
    assert receipt['fresh_input_binding_count']==7 and receipt['fresh_selected_native_identity_checked_count']==5
    assert receipt['fresh_duplicate_SID_count']==receipt['fresh_own_ETF_collision_count']==0
    assert receipt['fresh_own_ETF_count']==8 and all(receipt[key] is False for key in m.FALSE_FLAGS)
    assert len(case.source.forwards)==14  # Seven fixture-source + seven fresh consumer observations.
    assert len(case.source.loads)==2
    assert len(case.source.adds)==5
    assert reader.price(dict(case.selected[1]),case.source.grid[0]['session'])==Decimal('123.45')
    assert type(reader.price(dict(case.selected[1]),case.source.grid[0]['session'])) is Decimal
    assert reader.symbol_for_binding(dict(case.selected[1])) is case.source.symbols[case.selected[1]['composite_figi']]
    refused('once',reader.authenticate_once)
    assert case.store.calls==[case.key]


def test_missing_native_cell_stops_without_other_source_date_fallback_or_new_History(case):
    reader=case.reader();reader.authenticate_once()
    refused('absent',lambda:reader.price(dict(case.selected[0]),case.source.grid[1]['session']))
    assert case.store.calls==[case.key] and case.source.history.calls==[]
    refused('session',lambda:reader.price(dict(case.selected[0]),'2021-01-05'))


def test_source_and_fresh_current_mapped_labels_may_differ_with_same_full_identity(case):
    row=case.selected[1];symbol=case.source.symbols[row['composite_figi']]
    before=m.native._native(symbol);symbol.value='SYNTHETICHIST'
    assert m.stable_native_identity(before)==m.stable_native_identity(m.native._native(symbol))
    reader=case.reader();receipt=reader.authenticate_once()
    assert reader.price(dict(row),case.source.grid[0]['session'])==Decimal('123.45')
    assert receipt['fresh_input_binding_count']==7 and case.source.history.calls==[]


def test_initial_add_security_may_return_current_mapped_Symbol_with_same_SID(case):
    row=case.selected[1];target=case.source.symbols[row['composite_figi']]
    original_add=case.source.algorithm.add_security
    def add(symbol,*args):
        security=original_add(symbol,*args)
        if symbol is target:
            mapped=fixture.Symbol('SYNTHETICMAPPED',str(symbol.id))
            security.symbol=mapped
            for config in security.subscriptions:config.symbol=mapped
            # The synthetic dict lacks LEAN SecurityManager's SID-based lookup.
            case.source.securities[mapped]=security
        return security
    case.source.algorithm.add_security=add
    reader=case.reader();reader.authenticate_once()
    assert reader.price(dict(row),case.source.grid[0]['session'])==Decimal('123.45')
    assert case.source.history.calls==[] and len(case.source.adds)==5


def test_later_same_SID_mapped_security_label_is_observational(case):
    row=case.selected[1];symbol=case.source.symbols[row['composite_figi']]
    reader=case.reader();reader.authenticate_once()
    case.source.securities[symbol].symbol=fixture.Symbol('SYNTHETICMAPPED',str(symbol.id))
    assert reader.price(dict(row),case.source.grid[0]['session'])==Decimal('123.45')


@pytest.mark.parametrize('field',['sid','kind','market','sid_date','malformed_display'])
def test_same_display_does_not_waive_any_stable_identity_field(case,field):
    row=case.selected[1];symbol=case.source.symbols[row['composite_figi']]
    reader=case.reader();reader.authenticate_once()
    changed=fixture.Symbol(symbol.value,str(symbol.id))
    if field=='sid':changed.id.text='CHANGED 123'
    elif field=='kind':changed.security_type='Option'
    elif field=='market':changed.id.market='canada'
    elif field=='sid_date':changed.id.date=datetime(2011,1,1)
    else:changed.value='malformed value'
    case.source.securities[symbol].symbol=changed
    with pytest.raises(m.Refused):reader.price(dict(row),case.source.grid[0]['session'])


def test_future_close_guard_is_independent_of_calendar_accessor(case):
    reader=case.reader();reader.authenticate_once()
    session=case.source.grid[-1]['session']
    case.source.algorithm.time=datetime(2021,1,4,9,20)
    close=reader.session_close(session)
    assert close.tzinfo is not None and close.hour==16 and close.year==2026
    refused('future_session',lambda:reader.price(dict(case.selected[1]),session))
    session=case.source.grid[1]['session']
    case.source.algorithm.time=datetime(2021,1,4,15,59)
    refused('future_session',lambda:reader.price(dict(case.selected[1]),session))
    case.source.algorithm.time=datetime(2021,1,4,16,0)
    assert reader.price(dict(case.selected[1]),session)==Decimal('123.45')


@pytest.mark.parametrize('mode',['live','project','orders','holding'])
def test_authentication_precedes_every_strategy_order_or_holding_and_checks_project(case,mode):
    reader=case.reader()
    if mode=='live':case.source.algorithm.live_mode=True
    elif mode=='project':case.source.algorithm.project_id+=1
    elif mode=='orders':case.source.algorithm.transactions.get_orders=lambda:[NS()]
    else:case.source.algorithm.portfolio={'synthetic':NS(quantity=1)}
    refused('settings' if mode=='live' else 'project' if mode=='project' else 'orders',reader.authenticate_once)
    assert case.store.calls==[]
    refused('once',reader.authenticate_once)


def test_orders_holdings_and_additional_quote_subscriptions_are_allowed_after_binding(case):
    reader=case.reader();reader.authenticate_once()
    case.source.algorithm.transactions.get_orders=lambda:[NS()]
    case.source.algorithm.portfolio={'synthetic':NS(quantity=3)}
    symbol=reader.symbol_for_binding(dict(case.selected[1]))
    case.source.securities[symbol].subscriptions.append(NS(type=NS(FullName='QuoteAwareStrategyMinute')))
    assert reader.price(dict(case.selected[1]),case.source.grid[0]['session'])==Decimal('123.45')


@pytest.mark.parametrize('mode',['forward_sid','reverse','unavailable','duplicate_unselected','own_ETF_unselected','currency','conversion','calendar'])
def test_fresh_full_catalog_and_selected_native_identity_fail_before_book_read(case,mode):
    reader=case.reader()
    chosen=case.selected[0];figi=chosen['composite_figi'];symbol=case.source.symbols[figi]
    if mode=='forward_sid':symbol.id.text='OTHER 999'
    elif mode=='reverse':case.source.reverse_changes[figi]='BBG999999999'
    elif mode=='unavailable':case.source.unavailable.add(figi)
    elif mode=='duplicate_unselected':
        case.source.forward_changes[case.source.rows[-1]['composite_figi']]=case.source.symbols[case.source.rows[-2]['composite_figi']]
    elif mode=='own_ETF_unselected':case.source.forward_changes[case.source.rows[-1]['composite_figi']]=case.source.etfs['SPY']
    elif mode=='currency':case.source.securities[symbol].quote_currency.symbol='CAD'
    elif mode=='conversion':case.source.securities[symbol].quote_currency.conversion_rate=Decimal('1.01')
    else:case.source.hours.shift=timedelta(minutes=1)
    with pytest.raises(m.Refused):reader.authenticate_once()
    assert case.store.calls==[] and case.source.history.calls==[]


@pytest.mark.parametrize('mode',['read_exception','same_size_other_bytes','short','wrong_type'])
def test_QC_read_unknown_or_wrong_fixed_bytes_are_terminal_before_lookup(case,mode):
    reader=case.reader()
    if mode=='read_exception':case.store.fail=True
    elif mode=='same_size_other_bytes':case.store.raw=b'x'*len(case.raw)
    elif mode=='short':case.store.raw=case.raw[:-1]
    else:case.store.raw=bytearray(case.raw)
    with pytest.raises(m.Refused):reader.authenticate_once()
    assert case.store.calls==[case.key]
    refused('state',lambda:reader.price(dict(case.selected[0]),case.source.grid[0]['session']))
    refused('once',reader.authenticate_once)


def test_fixed_production_byte_pin_refuses_before_JSON(monkeypatch):
    monkeypatch.setattr(m,'_parse_supplied_book',lambda *_:(_ for _ in ()).throw(AssertionError('no JSON')))
    refused('source_bytes',lambda:m._parse_fixed_book(b'not the AK source book',m.source_context()))


@pytest.mark.parametrize('mode',['original','scope','calendar','census','selected_native','extra','price'])
def test_pure_closed_book_parser_retains_full_record_predicates_even_with_rehashed_synthetic_frame(case,mode):
    record=json.loads(case.raw);summary=copy.deepcopy(case.summary)
    if mode=='original':record['selected'][0]['original_binding']['source_row_sha256']='f'*64
    elif mode=='scope':record['specification_sha256']='f'*64
    elif mode=='calendar':record['session_schedule'][0]['close_utc']='2020-12-31T20:59:00+00:00'
    elif mode=='census':record['forward_sid_census'][0]['binding_ordinal']=1
    elif mode=='selected_native':record['selected'][0]['native']['sid']='WRONG 123'
    elif mode=='extra':record['raw_export']=[]
    else:record['selected'][0]['raw_USD_closes'][0][1]='0'
    raw=m.canonical(record);summary.update(private_book_byte_count=len(raw),private_book_sha256=m.digest(record))
    context=copy.deepcopy(case.context);context['source_summary']=summary
    with pytest.raises(m.Refused):m._parse_supplied_book(raw,context)


@pytest.mark.parametrize('mode',['binding_changed','foreign_binding','currency','raw','native_sid','project','live'])
def test_every_lookup_checks_exact_original_and_current_native_currency_RAW_project(case,mode):
    reader=case.reader();reader.authenticate_once();binding=dict(case.selected[1])
    symbol=reader.symbol_for_binding(binding)
    if mode=='binding_changed':binding['identity_evidence_sha256']='f'*64
    elif mode=='foreign_binding':binding=dict(case.source.rows[-1])
    elif mode=='currency':case.source.securities[symbol].quote_currency.symbol='CAD'
    elif mode=='raw':case.source.securities[symbol].data_normalization_mode='Adjusted'
    elif mode=='native_sid':symbol.id.text='ALTERED 123'
    elif mode=='project':case.source.algorithm.project_id+=1
    else:case.source.algorithm.live_mode=True
    with pytest.raises(m.Refused):reader.price(binding,case.source.grid[0]['session'])
    assert len(case.store.calls)==1


def test_no_raw_serializer_metadata_receipt_is_independent_and_lookup_count_is_bounded(case,monkeypatch):
    reader=case.reader();reader.authenticate_once()
    assert '123.45' not in repr(reader) and 'RAW data redacted' in repr(reader)
    with pytest.raises(TypeError):pickle.dumps(reader)
    receipt=reader.receipt();receipt['source_book_sha256']='f'*64
    assert reader.receipt()['source_book_sha256']==m.SOURCE_BOOK_SHA256
    monkeypatch.setattr(m,'MAX_LOOKUPS',1)
    reader.price(dict(case.selected[1]),case.source.grid[0]['session'])
    refused('lookup_bound',lambda:reader.price(dict(case.selected[1]),case.source.grid[0]['session']))
    assert not any(hasattr(reader,name) for name in ('raw','serialize','private_record','to_json','save','export'))


def test_production_source_context_is_exact_closed_and_profile_has_no_grant():
    context=m.source_context()
    assert m.digest(context)==m.SOURCE_CONTEXT_SHA256
    assert context['publication']['book_sha256']==m.SOURCE_BOOK_SHA256
    context['publication']['book_sha256']='f'*64
    refused('context',lambda:m.validate_source_context(context))
    assert all(m.profile_record()[key] is False for key in m.FALSE_FLAGS)
    source=inspect.getsource(m)
    assert '._capture(' not in source and '.prepare(' not in source and '.publish(' not in source
    assert '.history[' not in source and 'save_bytes(' not in source
