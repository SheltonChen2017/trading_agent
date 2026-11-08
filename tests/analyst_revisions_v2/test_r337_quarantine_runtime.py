"""R337 synthetic source/driver/profile/result and preserved quote-accounting checks.

Run under native network, artifact, USB, Keychain and security-exec denial.
Only public source and synthetic data are used; no old operational protocol.
"""
import ast
import copy
import inspect
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MethodType, SimpleNamespace as NS

import pytest
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_common_price as price
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_runtime as m
from research.analyst_revisions_v2_qc import newrule_common_price_qc_runtime as oldprice
from research.analyst_revisions_v2_qc import newrule_available_history_common_price_runtime as oldcommon
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from tests.analyst_revisions_v2 import test_r337_quarantine_targets as target_fixture
from tests.analyst_revisions_v2 import test_r298_native_price_source_diagnostic as native_fixture
from tests.analyst_revisions_v2 import test_r327_available_history_runtime as result_fixture
from scripts import arv2_newrule_quote_execution_projection as quote
from scripts import arv2_r327_available_history_projection as w5

D=Decimal


def refused(code, operation, module=m):
    with pytest.raises(module.Refused) as caught: operation()
    assert module.finite(caught.value)==code
    assert 'SYNTHETIC_PRIVATE' not in str(caught.value)


@pytest.fixture(scope='module')
def axis(): return october._sessions()


def profile(axis,count=6,arm=0):
    strategy=m.make_strategy_profile(axis, package_sha256=price.native.PACKAGE_SHA256,
        lineage_sha256=m.LINEAGE_SHA256, universe_count=count, ar_percent=arm,
        source_pins={'source.py':'a'*64}, quarantine_catalog_sha256='b'*64)
    return m.make_profile(strategy,runtime_project_id=123,vendor_source_context_sha256='c'*64,
        quarantine_catalog_sha256='b'*64,source_pins={'source.py':'a'*64})


@pytest.mark.parametrize('count,arm',[(6,0),(6,100),(6,200),(8,0),(8,100),(8,200)])
def test_all_six_new_profiles_bind_one_epoch_exact_window_and_quarantine(axis,count,arm):
    value=profile(axis,count,arm)
    assert m.validate_profile(value)==value
    assert value['candidate_id']==f'arv2-r337-{count}-ar{arm}-W5-five-case-quarantine-v1'
    strategy=value['strategy_profile']
    assert value['research_epoch_id']==strategy['research_epoch_id']==m.quarantine.RESEARCH_EPOCH_ID
    assert len(strategy['evaluation_sessions'])==1242 and len(strategy['decision_sessions'])==259
    assert strategy['initial_state']=='new_epoch_empty_positions_and_orders_USD1000000'
    assert strategy['native_price_book_initialized'] is False
    assert strategy['gross_target']=='0.98' and strategy['aggregate_stock_target_cap']=='0.098'
    assert all(value[k] is False for k in m.FALSE_FLAGS)
    assert 'native_source_context_sha256' not in value


@pytest.mark.parametrize('field,value', [('gross_target','0.99'),('fee_bps','0'),
    ('research_epoch_id','old'),('quarantined_binding_count',True),
    ('maximum_reference_history_calls',400),('primary_view','different'),
    ('whole_shares',1),('quarantine_timing','before_ranking'),('native_price_book_initialized',0),
    ('candidate_id','old'),('source_admission_granted',True)])
def test_rehashing_changed_economics_or_old_epoch_does_not_make_new_profile(axis,field,value):
    candidate=profile(axis)['strategy_profile'];candidate[field]=value
    candidate['profile_sha256']=m.digest({k:v for k,v in candidate.items() if k!='profile_sha256'})
    refused('profile',lambda:m.make_profile(candidate,runtime_project_id=123,
        vendor_source_context_sha256='c'*64,quarantine_catalog_sha256='b'*64,source_pins={'source.py':'a'*64}))


class Bridge:
    def __init__(self,rows,symbols,axis,catalog,pin):
        self.rows,self.symbols,self.axis,self.catalog,self.pin=rows,symbols,axis,catalog,pin
        self.close_error=None;self.close_attempts=0
    def receipt(self):
        return {'quarantine_epoch':price.RESEARCH_EPOCH_ID,'quarantine_catalog_sha256':self.pin,
            'fresh_binding_stream_sha256':price.native.BINDING_STREAM_SHA256,
            'fresh_input_binding_count':price.native.EXPECTED_BINDINGS,
            'native_price_book_initialized':False,'native_price_book_reads':0}
    def symbol_for_binding(self,row):return self.symbols[row['security_id']]
    def session_close(self,session):
        self.close_attempts+=1
        if self.close_error is not None:raise self.close_error
        return datetime.fromisoformat(session).replace(hour=16,tzinfo=price.NY)
    def no_orders(self):return True


class Vendor:
    def __init__(self,bridge,funds):
        self._native=bridge;self.symbols=bridge.symbols;self.funds=funds
        self.auths=0;self.calls=[];self.fail=False;self.conditional=set()
        self.auth_error=self.price_error=self.identity_error=None;self.identity_attempts=0
    def authenticate_once(self):
        self.auths+=1
        if self.auth_error is not None:raise self.auth_error
        if self.fail:raise ValueError('SYNTHETIC_PRIVATE')
    def receipt(self):return {'schema':'synthetic-vendor','pin':'d'*64}
    def symbol_for_binding(self,row):
        self.identity_attempts+=1
        if self.identity_error is not None:raise self.identity_error
        if row['security_id'] in self.conditional:raise ValueError('SYNTHETIC_PRIVATE')
        return self.symbols[row['security_id']]
    def symbol_for_fund(self,row):
        assert row['schema']==price.FUND_SCHEMA
        return self.funds[row['ticker']]
    def price(self,row,session):
        self.calls.append((row,session))
        if self.price_error is not None:raise self.price_error
        return D(100)


@pytest.fixture
def source_case(monkeypatch):
    rows,catalog,pin=target_fixture.policy.__wrapped__(monkeypatch)
    axis=('2020-12-31','2021-01-04','2026-10-13')
    monkeypatch.setattr(price.native,'EXPECTED_BINDINGS',len(rows))
    monkeypatch.setattr(price.native,'EXPECTED_AXIS_COUNT',len(axis))
    monkeypatch.setattr(price.native,'AXIS_SHA256',price.digest(list(axis)))
    monkeypatch.setattr(price.native,'BINDING_STREAM_SHA256',m.quarantine.ORIGINAL_BINDING_STREAM_SHA256)
    symbols={row['security_id']:native_fixture.Symbol('SYN'+str(i),'stock-'+str(i)) for i,row in enumerate(rows)}
    funds={ticker:native_fixture.Symbol(ticker,'fund-'+ticker) for ticker in price.native.UNIVERSES}
    bridge=Bridge(rows,symbols,axis,catalog,pin);vendor=Vendor(bridge,funds)
    monkeypatch.setattr(price,'_provider_types',lambda:(Bridge,Vendor))
    kwargs=dict(stock_bindings=rows,own_fund_contracts=price.fund_contracts(),session_axis=axis,
        quarantine_catalog=catalog,expected_quarantine_catalog_sha256=pin)
    source=price.SpecificQuarantinePriceBook(bridge,vendor,**kwargs);source.authenticate_once()
    return NS(rows=rows,catalog=catalog,pin=pin,axis=axis,symbols=symbols,funds=funds,
        bridge=bridge,vendor=vendor,source=source,kwargs=kwargs)


def test_vendor_only_source_authenticates_genuine_catalog_then_never_native_prices(source_case):
    c=source_case;identity=c.rows[-1]['security_id']
    assert c.source.price(identity,'2021-01-04',runtime_symbol=c.symbols[identity])==100
    assert c.source.price('own-etf-SPY','2021-01-04',runtime_symbol=c.funds['SPY'])==100
    receipt=c.source.receipt()
    assert c.vendor.auths==1 and len(c.vendor.calls)==2
    assert receipt['native_price_book_initialized'] is False and receipt['native_price_book_reads']==0
    assert all(v==0 for k,v in receipt['lookup_counts'].items() if k.startswith('native_'))
    assert all(v==2 for k,v in receipt['lookup_counts'].items() if k.startswith('vendor_'))
    refused('once',c.source.authenticate_once,price)


@pytest.mark.parametrize('which',range(5))
def test_exact_five_source_denial_precedes_vendor_symbol_or_price(source_case,which):
    c=source_case;identity=c.rows[which]['security_id']
    refused('quarantine',lambda:c.source.require_identity(identity),price)
    refused('quarantine',lambda:c.source.price(identity,'2021-01-04',runtime_symbol=c.symbols[identity]),price)
    assert c.vendor.calls==[]


def test_conditional_unavailable_unknown_and_missing_are_hard_stops_not_new_quarantine(source_case):
    c=source_case;identity=c.rows[-1]['security_id'];c.vendor.conditional.add(identity)
    refused('identity',lambda:c.source.require_identity(identity),price)
    refused('identity',lambda:c.source.require_identity('unknown'),price)
    assert c.vendor.calls==[]


@pytest.mark.parametrize('mode',['new_bridge','new_vendor','class_method','instance_method','bound_method'])
def test_original_concrete_provider_objects_and_method_identities_stay_bound(source_case,monkeypatch,mode):
    c=source_case
    if mode=='new_bridge':c.source._bridge=Bridge(c.rows,c.symbols,c.axis,c.catalog,c.pin)
    elif mode=='new_vendor':c.source._vendor=Vendor(c.bridge,c.funds)
    elif mode=='class_method':monkeypatch.setattr(Vendor,'price',lambda *a:D(1))
    elif mode=='instance_method':c.vendor.price=lambda *a:D(1)
    else:c.vendor.price=MethodType(lambda *a:D(1),c.vendor)
    with pytest.raises(price.Refused):c.source.receipt()


def test_reference_and_actual_close_use_vendor_RAW_cash_and_whole_holdings(source_case):
    c=source_case;identity=c.rows[-1]['security_id'];ledger=price.QuarantinePriceLedger(c.source)
    symbols={identity:c.symbols[identity]};holdings={identity:2}
    refs=ledger.reference_prices('2020-12-31',(identity,),holdings,symbols,
        now=datetime(2021,1,4,9,20,tzinfo=price.NY))
    assert refs=={identity:D(100)}
    nav,gross=ledger.observe_close('2021-01-04',cash='800',holdings=holdings,runtime_symbols=symbols,
        now=datetime(2021,1,4,16,1,tzinfo=price.NY),engine_nav='99999999')
    assert nav==1000 and gross==D('.2')
    assert ledger.summary()['unique_close_count']==1
    refused('repeated_close',lambda:ledger.observe_close('2021-01-04',cash='801',holdings=holdings,
        runtime_symbols=symbols,now=datetime(2021,1,4,16,1,tzinfo=price.NY)),price)


def test_original_fund_schema_unchanged_and_ledger_financial_clock_AST_exact():
    assert price.FUND_SCHEMA==oldprice.FUND_SCHEMA
    def methods(cls):return {n.name:n for n in ast.parse(inspect.getsource(cls)).body[0].body if isinstance(n,ast.FunctionDef)}
    before,after=methods(oldprice.CommonPriceLedger),methods(price.QuarantinePriceLedger)
    assert set(before)==set(after)
    for name in before.keys()-{'__init__'}:
        assert ast.dump(before[name],include_attributes=False)==ast.dump(after[name],include_attributes=False)


def _method(cls,name):return ast.parse(inspect.getsource(cls)).body[0].body[[getattr(n,'name',None) for n in ast.parse(inspect.getsource(cls)).body[0].body].index(name)]


def test_quote_methods_are_explicit_previously_frozen_projection_not_unquoted_host():
    cls=m.FiveCaseQuarantineComparisonDriver
    for name,string in (('_quote_snapshot',quote.QUOTE_METHOD),('_current_execution_price',quote.PRICE_METHOD),('fee_basis',quote.FEE_METHOD)):
        assert ast.dump(_method(cls,name),include_attributes=False)==ast.dump(ast.parse(string).body[0],include_attributes=False)
    assert not hasattr(m.base.NewruleComparisonDriver,'_quote_snapshot')
    assert m.quote_policy_fields()==w5.policy_profile_fields()
    for name in ('_freeze_fund_translation','_reference_prices','on_after_close'):
        assert ast.dump(_method(cls,name),include_attributes=False)==ast.dump(_method(oldcommon.CommonPriceComparisonDriver,name),include_attributes=False)


def _quote_case(monkeypatch):
    from tests.analyst_revisions_v2.test_quote_execution_projection import QuoteBar,TypedCache,NOW
    symbol=NS(sid='synthetic');quote_bar=QuoteBar(symbol);cached=QuoteBar(symbol)
    security=NS(symbol=symbol,price=D(120),bid_price=D(90),ask_price=D(110),cache=TypedCache(cached))
    class Bars:
        def __contains__(self,key):return key.sid=='synthetic'
        def __getitem__(self,key):return quote_bar
    driver=m.FiveCaseQuarantineComparisonDriver.__new__(m.FiveCaseQuarantineComparisonDriver)
    driver._now=lambda:NOW;driver._quote_bar_type=QuoteBar
    driver._algorithm=NS(current_slice=NS(quote_bars=Bars()),live_mode=False)
    driver._intent=None;driver._denied_ids=frozenset({'denied'});driver._common_ready=True
    driver._security_by_sid={'synthetic':'ID'};driver._security_by_etf_sid={}
    driver._price_identity=lambda identity: identity if identity!='denied' else m.require(False,'quarantine')
    monkeypatch.setattr(m.legacy,'_symbol_sid',lambda symbol,label:symbol.sid)
    return NS(driver=driver,security=security,symbol=symbol,quote=quote_bar,cached=cached,now=NOW)


def test_actual_new_driver_quotes_are_side_aware_and_engine_cache_is_unchanged(monkeypatch):
    c=_quote_case(monkeypatch)
    assert c.driver._current_execution_price(c.security,1)==110
    assert c.driver._current_execution_price(c.security,-1)==90
    assert c.security.price==120
    c.quote.is_fill_forward=True
    with pytest.raises(m.Refused,match='quote_execution_fill_forward'):c.driver._quote_snapshot(c.security)


def test_actual_new_driver_cash_bound_uses_max_ask_and_engine_price(monkeypatch):
    c=_quote_case(monkeypatch);d=c.driver;session=c.now.date().isoformat()
    d._require_initialized=lambda:None;d._decision_set={session};d._executed=set()
    d._preopen_clock_confirmations={session};d._split_records_by_session={}
    d._plans={session:{'holdings':{},'split_records':{},'quantities':{'ID':2},'sha256':'a'*64}}
    holdings={};cash=[D(230)];orders=[]
    d._algorithm.transactions=NS(get_open_orders=lambda:())
    d._current_holding_census=lambda:dict(holdings);d._current_quantity=lambda identity:holdings.get(identity,0)
    d._ensure_security=lambda identity:(c.symbol,c.security);d._portfolio_cash=lambda:cash[0]
    d._cash_underfill_count=0
    def submit(identity,quantity,session):
        orders.append(quantity);holdings[identity]=quantity;cash[0]-=D(quantity)*D(110)*D('1.001')
    d._submit_market=submit
    assert d.on_after_open()=='a'*64 and orders==[1] and d._cash_underfill_count==1


@pytest.mark.parametrize('quantity,side,expected_cash',[(2,'110','779.780'),(-2,'90','1179.820')])
def test_actual_new_driver_synchronous_quote_fee_fill_cash_reconciliation(monkeypatch,quantity,side,expected_cash):
    c=_quote_case(monkeypatch);d=c.driver;session=c.now.date().isoformat()
    d._require_initialized=lambda:None;d._status=lambda v:v
    d._order_ids=set();d._event_ids=set();d._fills=[]
    d._plans={session:{'sha256':'a'*64}}
    holdings=[0 if quantity>0 else 3];cash=[D(1000)]
    d._ensure_security=lambda identity:(c.symbol,c.security)
    d._current_quantity=lambda identity:holdings[0];d._portfolio_cash=lambda:cash[0]
    engine=NS(id=7,tag=None,symbol=c.symbol,quantity=D(quantity))
    d._algorithm.transactions=NS(get_order_by_id=lambda order_id:engine)
    def order(symbol,signed_quantity,*,asynchronous,tag):
        engine.tag=tag;fee=d.fee_basis(NS(order=engine,security=c.security))*abs(quantity)*D('.001')
        cash[0]-=D(quantity)*D(side)+fee;holdings[0]+=quantity
        event=NS(status='Filled',order_id=7,id=0,symbol=c.symbol,fill_quantity=quantity,fill_price=D(side),
            order_fee=NS(value=NS(amount=fee,currency='USD')),utc_time=c.now.astimezone(timezone.utc))
        d.on_order_event(event);return NS(status='Filled',order_id=7)
    d._algorithm.market_order=order;d._submit_market('ID',quantity,session)
    assert cash[0]==D(expected_cash) and len(d._fills)==1 and d._intent is None
    assert c.security.price==120


def test_quarantined_manual_order_is_stopped_before_engine_or_external_handler(monkeypatch):
    c=_quote_case(monkeypatch);d=c.driver;d._security_by_sid['synthetic']='denied'
    with pytest.raises(m.Refused,match='quarantine'):d.on_order_event(NS(symbol=c.symbol))
    with pytest.raises(m.Refused,match='quarantine'):d._submit_market('denied',1,'2021-01-04')


def test_quarantined_positive_holdings_stop_instead_of_imaginary_liquidation(monkeypatch):
    d=m.FiveCaseQuarantineComparisonDriver.__new__(m.FiveCaseQuarantineComparisonDriver)
    d._algorithm=NS(portfolio={native_fixture.Symbol('X','denied-native'):NS(quantity=1)})
    d._security_by_sid={'denied-native':'denied'};d._security_by_etf_sid={}
    d._denied_ids=frozenset({'denied'});d._common_ready=False
    refused('quarantine',d._current_holding_census)


def common_result(expected):
    value=result_fixture.old_common_tests.common_result({**expected,'native_source_context_sha256':'a'*64})
    value['schema']=m.RESULT_SCHEMA+'-source';value.pop('native_source_context_sha256')
    value.update({k:expected[k] for k in ('quarantine_catalog_sha256','quarantine_policy_sha256','research_epoch_id')})
    ledger=value['ledger'];ledger['schema']=price.SCHEMA+'-ledger'
    source=ledger['source_observation'];source.pop('specification_sha256');source.pop('native_receipt')
    source.update(schema=price.SCHEMA+'-source-observation',
        quarantine_catalog_sha256=expected['quarantine_catalog_sha256'],
        quarantine_policy_sha256=expected['quarantine_policy_sha256'],research_epoch_id=m.RESEARCH_EPOCH_ID,
        full_stock_binding_count=6151,bridge_receipt={'byte_count':100,'sha256':'e'*64},
        native_price_book_initialized=False,native_price_book_reads=0)
    return value


def quarantine_result(expected):
    return {'schema':m.RESULT_SCHEMA+'-quarantine','research_epoch_id':m.RESEARCH_EPOCH_ID,
        'quarantine_catalog_sha256':expected['quarantine_catalog_sha256'],
        'quarantine_policy_sha256':expected['quarantine_policy_sha256'],'decision_count':259,
        'transfer_ledger_path_sha256':'f'*64,'total_selected_sleeve_occurrence_count':0,
        'total_positive_sleeve_occurrence_count':0,'total_transferred_to_own_etf_weight':'0',
        'decisions_with_positive_transfer':0,'quarantined_target_count':0,'quarantined_order_count':0,
        'quarantined_holding_count':0,'replacement_name_promotions':0,'renormalization_performed':False,**m.FALSE_FLAGS}


def stats_fixture(axis):
    old,_=result_fixture.result_fixture(axis);expected=profile(axis)
    meta=json.loads(old[oldcommon.META_STATISTIC]);months=json.loads(old[oldcommon.MONTHLY_STATISTIC])
    meta.update(schema=m.RESULT_SCHEMA,candidate_id=expected['candidate_id'],profile_sha256=expected['profile_sha256'],
        common_price=common_result(expected),quarantine=quarantine_result(expected))
    months.update(schema=m.MONTH_SCHEMA,candidate_id=expected['candidate_id'],profile_sha256=expected['profile_sha256'])
    return {m.META_STATISTIC:m.canonical(meta).decode(),m.MONTHLY_STATISTIC:m.canonical(months).decode()},expected


def test_new_result_parser_authenticates_zero_native_vendor_only_and_transfer_ledger(axis):
    stats,expected=stats_fixture(axis);value=m.validate_result_statistics(stats,expected_profile=expected)
    assert value['meta']['quarantine']['research_epoch_id']==m.RESEARCH_EPOCH_ID
    assert value['meta']['common_price']['ledger']['source_observation']['native_price_book_initialized'] is False
    assert len(value['monthly']['months'])==60


@pytest.mark.parametrize('issue',['old_schema','old_epoch','old_profile','native_lookup','native_initialized',
    'native_read','missing_close','missing_refs','false_flag','quarantined_target','quarantined_holding',
    'quarantined_order','promoted','renormalized','bad_transfer','bool_count','no_quarantine'])
def test_result_refuses_old_run_fake_source_counts_or_quarantine_gate_violation(axis,issue):
    stats,expected=stats_fixture(axis);meta=json.loads(stats[m.META_STATISTIC]);q=meta['quarantine']
    source=meta['common_price']['ledger']['source_observation']
    if issue=='old_schema':meta['schema']=oldcommon.RESULT_SCHEMA
    elif issue=='old_epoch':q['research_epoch_id']='old'
    elif issue=='old_profile':meta['profile_sha256']='0'*64
    elif issue=='native_lookup':source['lookup_counts']['native_price_lookup_completed']=1
    elif issue=='native_initialized':source['native_price_book_initialized']=True
    elif issue=='native_read':source['native_price_book_reads']=1
    elif issue=='missing_close':meta['common_price']['ledger']['unique_close_count']-=1
    elif issue=='missing_refs':meta['common_price']['ledger']['counts']['reference_batch_completed']-=1
    elif issue=='false_flag':q['paper_or_live_ready']=True
    elif issue=='quarantined_target':q['quarantined_target_count']=1
    elif issue=='quarantined_holding':q['quarantined_holding_count']=1
    elif issue=='quarantined_order':q['quarantined_order_count']=1
    elif issue=='promoted':q['replacement_name_promotions']=1
    elif issue=='renormalized':q['renormalization_performed']=True
    elif issue=='bad_transfer':q['total_transferred_to_own_etf_weight']='0.01'
    elif issue=='bool_count':q['quarantined_target_count']=False
    else:meta.pop('quarantine')
    stats[m.META_STATISTIC]=m.canonical(meta).decode()
    with pytest.raises(m.Refused):m.validate_result_statistics(stats,expected_profile=expected)


def test_initializer_source_never_constructs_old_native_book_and_validates_real_catalog():
    text=inspect.getsource(m.FiveCaseQuarantineComparisonDriver)
    assert 'SpecificNativePriceBook' not in text and 'native_source_context' not in text
    assert 'make_quarantine_catalog(tuple(package.runtime_symbol_bindings))' in text
    assert 'resolve_preliminary_qc_figis' in text
    assert 'self._bridge.authenticate_once()' in text
    assert 'self._common_source.authenticate_once()' in text
    assert 'super().initialize()' not in text


@pytest.mark.parametrize('count,arm',[(6,0),(6,100),(6,200),(8,0),(8,100),(8,200)])
def test_actual_preopen_builds_full_books_then_transfers_before_any_price_subscription(monkeypatch,count,arm):
    import dataclasses
    rows,catalog,pin=target_fixture.policy.__wrapped__(monkeypatch)
    books=target_fixture.books(shared=True)
    books=tuple(dataclasses.replace(book,members=tuple(dataclasses.replace(member,
        economic_id=rows[i]['security_id'] if i<len(rows) else member.economic_id)
        for i,member in enumerate(book.members))) for book in books)
    denied=frozenset(row['security_id'] for row in rows[:5])
    d=m.FiveCaseQuarantineComparisonDriver.__new__(m.FiveCaseQuarantineComparisonDriver)
    session=m.START_SESSION
    d._require_initialized=lambda:None;d._now=lambda:datetime.fromisoformat(session).replace(hour=9,minute=20,tzinfo=price.NY)
    d._decision_set={session};d._plans={};d._intent=None;d._algorithm=NS(live_mode=False)
    d._books=lambda s:(books,'d'*64);d._profile={'universe_count':count,'ar_percent':arm}
    d._quarantine_catalog=catalog;d._common_profile={'quarantine_catalog_sha256':pin}
    d._denied_ids=denied;d._current_holding_census=lambda:{}
    d._session_axis=(m.base.FIRST_REFERENCE_CLOSE,session);d._session_positions={session:1}
    checked=[];subscribed=[];price_demands=[]
    def identity(value):
        assert value not in denied;checked.append(value);return value
    d._price_identity=identity
    d._prune_execution_subscriptions=lambda values:subscribed.extend(sorted(values))
    def references(previous,values):
        assert previous==m.base.FIRST_REFERENCE_CLOSE and not denied.intersection(values)
        assert set(values)<=set(checked);price_demands.extend(values);return {value:D(100) for value in values}
    d._reference_prices=references;d._order_ids=set();d._portfolio_cash=lambda:D(1000000)
    d._split_factors=lambda values,now:({value:D(1) for value in values},'e'*64)
    d._split_records_by_session={};d._portfolio_equity=lambda:D(1000000)
    d._fallback_counts={};d._quarantine_ledgers={}
    returned=d.on_before_open();plan=d._plans[session];target=plan['target']
    assert returned==target.target_sha256 and target.input_books_sha256==m.targets.book_digest(books)
    assert not denied.intersection(plan['quantities'])
    assert set(subscribed)==set(price_demands)=={identity for identity,_,_ in target.weights}
    assert d._quarantine_ledgers[session]['quarantined_target_count']==0
    assert d._quarantine_ledgers[session]['transferred_to_own_etf_weight']!='0'
    assert sum((weight for _,_,weight in target.weights),D(0))==D('.98')


def test_actual_quote_fill_and_cash_methods_AST_equal_declared_projection_and_W5_cash_bound():
    def dump(value):return ast.dump(value,include_attributes=False)
    for name in ('_submit_market','on_after_open','on_order_event'):
        expected=copy.deepcopy(_method(m.base.NewruleComparisonDriver,name))
        if name in ('_submit_market','on_after_open'):
            calls=[n for n in ast.walk(expected) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Attribute) and n.func.attr=='_current_execution_price']
            assert len(calls)==1
            calls[0].args.append(ast.Name(id='quantity',ctx=ast.Load()) if name=='_submit_market' else ast.Constant(1))
        else:
            index=next(i for i,n in enumerate(expected.body) if isinstance(n,ast.Assign)
                and isinstance(n.targets[0],ast.Tuple) and [x.id for x in n.targets[0].elts]==['quantity','price'])
            expected.body[index+1:index+1]=ast.parse('require(abs(price - Decimal(intent["fee_basis_quote"])) <= Decimal("0.0000001"), "quote_execution_fill_price")').body
        if name=='on_after_open':expected=w5._cash_bound(expected,*w5.CASH_BOUND_CHANGE)
        actual=copy.deepcopy(_method(m.FiveCaseQuarantineComparisonDriver,name))
        # The only additions to these financial methods are the explicit denials.
        if name=='_submit_market':actual.body=actual.body[2:]
        elif name=='on_order_event':actual.body=actual.body[1:]
        assert dump(actual)==dump(expected)
    for name in ('_split_factors','_books','on_data','on_splits','configure_security'):
        assert getattr(m.FiveCaseQuarantineComparisonDriver,name) is getattr(m.base.NewruleComparisonDriver,name)


def test_initializer_calls_only_new_concrete_bridge_vendor_and_ledger(monkeypatch):
    d=m.FiveCaseQuarantineComparisonDriver.__new__(m.FiveCaseQuarantineComparisonDriver)
    d._common_started=False;d._common_ready=False;d._algorithm=NS()
    d._package=NS(runtime_symbol_bindings=('all6151-synthetic-placeholder',))
    d._resolution=object();d._session_axis=('full-axis-synthetic-placeholder',)
    d._benchmark_symbol=object();d._etf_symbols={ticker:object() for ticker in price.native.UNIVERSES}
    d._raw_normalization='RAW';d._quarantine_catalog={'synthetic':True};d._vendor_context={'synthetic':True}
    d._common_profile={'runtime_project_id':123,'quarantine_catalog_sha256':'b'*64,'vendor_source_context_sha256':'c'*64}
    calls=[]
    d._initialize_genuine_strategy=lambda:calls.append('genuine-package-and-resolution') or True
    d._freeze_fund_translation=lambda:calls.append('fund-translation')
    d._common_guard=lambda:calls.append('ready-guard')
    class B:
        def __init__(self,algorithm,**kwargs):
            assert kwargs['package'] is d._package and kwargs['resolution'] is d._resolution
            assert kwargs['etf_symbols'] is d._etf_symbols;calls.append('new-bridge')
        def authenticate_once(self):calls.append('bridge-auth')
    class V:
        def __init__(self,algorithm,**kwargs):
            assert kwargs['identity_bridge'] is d._bridge and kwargs['resolution'] is d._resolution
            assert tuple(kwargs['etf_symbols'])==tuple(d._etf_symbols.values());calls.append('new-vendor')
    class S:
        def __init__(self,bridge,vendor,**kwargs):
            assert bridge is d._bridge and vendor is d._vendor_book;calls.append('vendor-only-source')
        def authenticate_once(self):calls.append('vendor-source-auth')
    monkeypatch.setattr(m.vendor_reader,'IdentityCalendarBridge',B)
    monkeypatch.setattr(m.vendor_reader,'SpecificQuarantineVendorPriceBook',V)
    monkeypatch.setattr(price,'SpecificQuarantinePriceBook',S)
    monkeypatch.setattr(price,'QuarantinePriceLedger',lambda source:calls.append('new-ledger') or object())
    assert d.initialize() is True
    assert calls==['genuine-package-and-resolution','fund-translation','new-bridge','bridge-auth','new-vendor',
        'vendor-only-source','vendor-source-auth','new-ledger','ready-guard']
    refused('once',d.initialize)


def _error(kind):
    if kind=='vendor_deadline':return price.vendor_format.Refused('deadline')
    if kind=='timeout':return TimeoutError('SYNTHETIC_PRIVATE_TIMEOUT')
    if kind=='process_timeout':return price.TimeoutExpired('SYNTHETIC_PRIVATE_COMMAND',1)
    if kind=='vendor_other':return price.vendor_format.Refused('missing')
    if kind=='unknown':return ValueError('SYNTHETIC_PRIVATE_OTHER')
    class ForeignTimeout(TimeoutError):pass
    return ForeignTimeout('SYNTHETIC_PRIVATE_SUBCLASS')


@pytest.mark.parametrize('kind,expected',[(k,'deadline') for k in ('vendor_deadline','timeout','process_timeout')]
    +[(k,'provider_authentication') for k in ('vendor_other','unknown','subclass')])
def test_vendor_auth_deadline_preserved_only_after_actual_guarded_auth_call(source_case,kind,expected):
    c=source_case;vendor=Vendor(c.bridge,c.funds);vendor.auth_error=_error(kind)
    source=price.SpecificQuarantinePriceBook(c.bridge,vendor,**c.kwargs)
    refused(expected,source.authenticate_once,price)
    assert vendor.auths==1 and source._started is True and source._ready is False
    refused('once',source.authenticate_once,price)


@pytest.mark.parametrize('kind,expected',[(k,'deadline') for k in ('vendor_deadline','timeout','process_timeout')]
    +[(k,'price_missing_or_unknown') for k in ('vendor_other','unknown','subclass')])
def test_vendor_price_deadline_preserved_after_identity_calendar_and_price_dispatch(source_case,kind,expected):
    c=source_case;identity=c.rows[-1]['security_id'];c.vendor.price_error=_error(kind)
    refused(expected,lambda:c.source.price(identity,'2021-01-04',runtime_symbol=c.symbols[identity]),price)
    counts=c.source.receipt()['lookup_counts']
    assert c.vendor.identity_attempts==1 and c.bridge.close_attempts==1 and len(c.vendor.calls)==1
    assert counts['vendor_identity_check_completed']==1
    assert counts['vendor_price_lookup_attempts']==1 and counts['vendor_price_lookup_completed']==0


@pytest.mark.parametrize('boundary',('identity','calendar'))
@pytest.mark.parametrize('kind,deadline',[('vendor_deadline',True),('timeout',True),('process_timeout',True),
    ('vendor_other',False),('unknown',False),('subclass',False)])
def test_generalized_method_wrappers_preserve_exact_deadlines_without_changing_other_categories(source_case,boundary,kind,deadline):
    c=source_case;identity=c.rows[-1]['security_id']
    if boundary=='identity':
        c.vendor.identity_error=_error(kind);call=lambda:c.source.require_identity(identity)
    else:
        c.bridge.close_error=_error(kind);call=lambda:c.source.session_close('2021-01-04')
    refused('deadline' if deadline else boundary,call,price)
    assert (c.vendor.identity_attempts if boundary=='identity' else c.bridge.close_attempts)==1
