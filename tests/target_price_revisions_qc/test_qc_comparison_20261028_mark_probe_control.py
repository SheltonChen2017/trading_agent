"""Pure source edits + synthetic controls/subscription metadata; no actual IO."""
from copy import deepcopy
from datetime import datetime
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import comparison_20261028_mark_probe_control as c
from research.target_price_revisions_qc import comparison_20261028_mark_read as reader
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe as old

PREFIX=Path('research/target_price_revisions_qc')


@pytest.fixture
def sources():return dict(base_probe_source=(PREFIX/'comparison_20261028_mark_probe.py').read_bytes(),
    helper_source=(PREFIX/'comparison_20261028_mark_read.py').read_bytes(),producer_source=(PREFIX/'comparison_20261028_algorithm.py').read_bytes())


def build(sources,**changes):
    args=dict(sources,operation_id='TPR-CMP28-MARK-PROBE-CONTROL-SYNTHETIC-002',git_head='a'*40,failure_session='2021-02-10')
    args.update(changes);return c.build_mark_probe_control(**args)


def test_plain_single_main_uses_exact_pins_and_enumerated_readable_source_edits(sources):
    raw,report=build(sources);report=json.loads(report);tree=ast.parse(raw);compile(tree,'<control>','exec')
    assert raw.startswith(sources['helper_source']+b'\n') and len(raw)==report['main_bytes']<=60000
    assert hashlib.sha256(raw).hexdigest()==report['main_sha256'] and report['max_history_calls']==4
    assert report['max_native_exact_symbol_registrations']==report['max_registration_config_reads']==1
    assert report['max_total_history_rows']==2004 and len(report['source_edits'])==7
    methods={n.name:n for n in next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Main').body if isinstance(n,ast.FunctionDef)}
    calls=[n for n in ast.walk(methods['_register_parent']) if isinstance(n,ast.Attribute)]
    assert any(n.attr=='add_security' for n in calls) and not any(n.attr=='add_equity' for n in calls)
    names={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not names & {'set_holdings','market_order','market_on_open_order','liquidate','save_bytes','download','set_market_price'}
    assert report['target_data_gap_proven'] is report['one_of_five_economic_arms'] is report['native_permission'] is False


@pytest.mark.parametrize('name',['base_probe_source','helper_source','producer_source'])
def test_all_three_public_sources_refuse_one_byte_drift(sources,name):
    sources[name]+=b'\n'
    with pytest.raises(c.ControlledProbeRefusal):build(sources)


@pytest.mark.parametrize('session',[None,'2021-02-09','2026-10-09',True])
def test_control_scope_is_exact_known_failed_session(sources,session):
    with pytest.raises(c.ControlledProbeRefusal):build(sources,failure_session=session)


@pytest.fixture
def native(sources,monkeypatch):
    original=old.native.__wrapped__({name:sources[name] for name in ('helper_source','producer_source')},monkeypatch)
    raw,_=build(sources);module=ModuleType('synthetic_control_probe');exec(compile(raw,'<synthetic-control>','exec'),module.__dict__)
    config=deepcopy(module.PROBE_CONFIG);config['binding']=original.module.PROBE_CONFIG['binding'];config['pointer']=original.module.PROBE_CONFIG['pointer']
    module.PROBE_CONFIG=config;module.PROBE_CONFIG_JSON=reader._canonical(config).decode();module.PROBE_CONFIG_SHA256=hashlib.sha256(module.PROBE_CONFIG_JSON.encode()).hexdigest()
    algo=module.Main();algo.__dict__.update(original.algo.__dict__)
    original.algo=algo;original.module=module
    api=sys.modules['AlgorithmImports'];api.TickType=NS(TRADE='trade',QUOTE='quote');module.TickType=api.TickType
    class NativeSecurity:
        def __init__(self,symbol):self.symbol=symbol
    class NativeConfig:
        def __init__(self,symbol):
            self.symbol=symbol;self.is_internal_feed=False;self.data_normalization_mode='raw';self.resolution='minute';self.tick_type='trade'
            self.type=NS(FullName='QuantConnect.Data.Market.TradeBar');self.fill_data_forward=False;self.extended_market_hours=False
            self.is_custom_data=False;self.exchange_time_zone=NS(id='America/New_York')
    securities=ModuleType('QuantConnect.Securities');securities.Security=NativeSecurity
    data=ModuleType('QuantConnect.Data');data.SubscriptionDataConfig=NativeConfig
    system=ModuleType('System');system.Object=NS(ReferenceEquals=lambda left,right:left is right)
    for mod in (securities,data,system):monkeypatch.setitem(sys.modules,mod.__name__,mod)
    state=NS(events=[],rows={},registered=None,configs=[],on_add=lambda:None,on_configs=lambda:None,registration_failure=False,
        untyped_security=False,wrong_security=False,hook=lambda *_:None,history=[],yielded=0)
    store=algo.object_store;store.hook=lambda stage:state.events.append(stage)
    class Registry:
        def __getitem__(self,symbol):assert state.registered.symbol.id==symbol.id;return state.registered
    algo.securities=Registry()
    def add_security(symbol,**options):
        state.events.append('add_security');state.on_add()
        assert isinstance(symbol,old.Symbol)
        assert options==dict(resolution='minute',fill_forward=False,extended_market_hours=False,data_normalization_mode='raw')
        if state.registration_failure:raise AttributeError('PRIVATE-REGISTER-ERROR')
        chosen=old.Symbol(old.SID('WRONG X123ABC'),'WRONG') if state.wrong_security else symbol
        value=NativeSecurity(chosen);state.registered=value
        if not state.configs:state.configs=[NativeConfig(symbol)]
        return NS(symbol=chosen) if state.untyped_security else value
    algo.add_security=add_security
    def configs(symbol,internal):
        state.events.append('configs');state.on_configs();assert internal is True;return state.configs
    algo.subscription_manager=NS(subscription_data_config_service=NS(get_subscription_data_configs=configs))
    class History:
        def __getitem__(self,kind):
            assert kind is old.Bar
            def request(symbol,start,end,resolution,**options):
                label=('control_' if symbol.id==algo._clock.id else '')+resolution
                state.events.append(label);state.history.append((label,symbol,options));state.hook(label)
                assert start==datetime(2021,2,10) and end==datetime(2021,2,10,16,1)
                assert options==dict(fill_forward=False,extended_market_hours=False,data_normalization_mode='raw')
                def rows():
                    for row in state.rows.get(label,[]):state.yielded+=1;yield row
                return rows()
            return request
    algo.history=History()
    def initialize():
        algo.initialize()
        target=old.Symbol(old.SID(original.body['security_id']),'PRIVATE.SID')
        def bar(symbol,price='50',volume='100'):
            row=old.Bar(symbol,datetime(2021,2,10,16),price);row.volume=volume;return row
        state.rows={'control_minute':[bar(algo._clock,'600','100000')],'control_daily':[bar(algo._clock,'600','100000')],
            'minute':[bar(target)],'daily':[bar(target)]}
        algo.algorithm_id='c'*32;original.state.locked=True
    original.control=state;original.initialize=initialize;original.NativeConfig=NativeConfig
    return original


def result(case):
    case.algo.on_end_of_algorithm();raw=case.logs[-1]
    assert raw.startswith('CMP28_MARK_PROBE_RESULT ') and 'PRIVATE.SID' not in raw and '2021-02-10T' not in raw
    assert 'PRIVATE-REGISTER-ERROR' not in raw and '"volume"' not in raw and '"price"' not in raw
    return json.loads(raw.split(' ',1)[1])


def test_positive_controls_then_genuine_exact_registration_then_target_with_safe_volume_counts(native):
    native.initialize();assert not native.algo.object_store.calls and not native.control.history
    native.algo._probe();out=result(native)
    assert native.control.events==['contains','read','control_minute','control_daily','add_security','configs','minute','daily']
    assert out['status']=='completed_controlled_diagnostic' and out['control_request_path_status']=='positive_controls_observed'
    assert out['native_exact_subscription']['verified'] is True and out['native_exact_subscription']['add_security_calls']==1
    assert out['history_calls']==4 and out['minute_daily_close_price_parity'] is True
    for label in ('control_minute','control_daily','minute','daily'):
        assert out[label]['positive_volume_rows']==out[label]['nonnegative_volume_rows']==1
        assert out[label]['all_volume_nonnegative'] is True
    assert out['target_data_gap_proven'] is out['strategy_accepted'] is False


@pytest.mark.parametrize('mode',['empty','zero_volume','negative_volume'])
def test_unproved_positive_control_path_never_becomes_data_gap_claim(native,mode):
    native.initialize()
    for label in ('control_minute','control_daily'):
        if mode=='empty':native.control.rows[label]=[]
        else:native.control.rows[label][0].volume='0' if mode=='zero_volume' else '-1'
    native.algo._probe();out=result(native)
    assert out['control_request_path_status']==out['status']=='request_path_unproved'
    assert out['target_data_gap_proven'] is False and out['history_calls']==4
    if mode=='negative_volume':assert out['control_daily']['all_volume_nonnegative'] is False


def test_positive_controls_and_registered_target_empty_are_observations_not_asserted_data_gap(native):
    native.initialize();native.control.rows['minute']=[];native.control.rows['daily']=[]
    native.algo._probe();out=result(native)
    assert out['control_request_path_status']=='positive_controls_observed' and out['native_exact_subscription']['verified'] is True
    assert out['minute']['rows']==out['daily']['rows']==0 and out['minute_daily_close_price_parity'] is None
    assert out['target_data_gap_proven'] is False


@pytest.mark.parametrize('mode',['raise','untyped','wrong_sid','config_untyped','adjusted','fillforward','extended','custom','wrong_type','wrong_zone'])
def test_controls_survive_registration_or_actual_config_refusal_and_no_target_query_occurs(native,mode):
    native.initialize()
    target=old.Symbol(old.SID(native.body['security_id']),'PRIVATE.SID')
    config=native.NativeConfig(target)
    if mode=='raise':native.control.registration_failure=True
    elif mode=='untyped':native.control.untyped_security=True
    elif mode=='wrong_sid':native.control.wrong_security=True
    elif mode=='config_untyped':native.control.configs=[NS(**vars(config))]
    else:
        if mode=='adjusted':config.data_normalization_mode='adjusted'
        elif mode=='fillforward':config.fill_data_forward=True
        elif mode=='extended':config.extended_market_hours=True
        elif mode=='custom':config.is_custom_data=True
        elif mode=='wrong_type':config.type=NS(FullName='OtherType')
        elif mode=='wrong_zone':config.exchange_time_zone=NS(id='UTC')
        native.control.configs=[config]
    native.algo._probe();out=result(native)
    assert out['control_minute']['rows']==out['control_daily']['rows']==1
    assert out['native_exact_subscription']['verified'] is False and out['history_calls']==2
    assert [label for label,_,_ in native.control.history]==['control_minute','control_daily']


@pytest.mark.parametrize('phase',['add','configs'])
def test_registration_custody_drift_refuses_after_effect_without_any_target_history(native,phase):
    native.initialize()
    changed=lambda:setattr(native.algo,'algorithm_id','d'*32)
    if phase=='add':native.control.on_add=changed
    else:native.control.on_configs=changed
    native.algo._probe();out=result(native)
    assert out['status']=='runtime_custody_changed' and out['history_calls']==2 and out['end_runtime_custody'] is False
    assert out['actual_child_job_id']=='c'*32
    assert out['native_exact_subscription']['verified'] is False


def test_actual_config_enumeration_is_bounded_and_refuses_oversized_result(native):
    native.initialize()
    target=old.Symbol(old.SID(native.body['security_id']),'PRIVATE.SID')
    observed=[]
    def unbounded():
        while True:
            observed.append(None)
            yield native.NativeConfig(target)
    native.control.configs=unbounded()
    native.algo._probe();out=result(native)
    assert len(observed)==65 and out['native_exact_subscription']['verified'] is False
    assert out['status']=='native_exact_subscription_config_unproved' and out['history_calls']==2


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_registration_nonordinary_stops_are_body_free_and_never_query_parent_history(native,kind):
    native.initialize()
    class Fatal(BaseException):pass
    def stop():raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-REGISTRATION-STOP')
    native.control.on_add=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ProbeStopped) as error:native.algo._probe()
    assert 'PRIVATE-REGISTRATION-STOP' not in str(error.value) and len(native.control.history)==2


def test_four_call_and_per_stream_row_bounds_are_hard_and_duplicate_callback_has_no_effect(native):
    native.initialize()
    for label in ('control_minute','minute'):native.control.rows[label]*=1001
    for label in ('control_daily','daily'):native.control.rows[label]*=3
    native.algo._probe();out=result(native)
    assert out['history_calls']==4 and native.control.yielded==2004
    assert all(out[label]['row_bound_reached_result_may_be_incomplete'] for label in ('control_minute','control_daily','minute','daily'))
    before=list(native.control.events);native.algo._probe();assert native.control.events==before


def test_known_exact_raw_quote_companion_allows_only_typed_trade_history_and_reports_safe_counts(native):
    native.initialize()
    target=old.Symbol(old.SID(native.body['security_id']),'PRIVATE.SID')
    trade=native.NativeConfig(target);quote=native.NativeConfig(target)
    quote.tick_type='quote';quote.type=NS(FullName='QuantConnect.Data.Market.QuoteBar')
    native.control.configs=[trade,quote]
    native.algo._probe();out=result(native);proof=out['native_exact_subscription']
    assert proof['verified'] is True and proof['external_config_count']==2
    assert proof['regular_nonfillforward_raw_minute_trade_configs']==1
    assert proof['regular_nonfillforward_raw_minute_quote_configs']==1
    assert proof['unrecognized_external_config_count']==0 and out['history_calls']==4
    assert proof['native_config_kind_counts']=={'trade_bar':1,'quote_bar':1,'other_native':0,'untyped':0}
    assert proof['config_rows_examined']==2
    assert [label for label,_,_ in native.control.history]==['control_minute','control_daily','minute','daily']
    assert out['minute_daily_close_price_parity'] is True and out['target_data_gap_proven'] is False


@pytest.mark.parametrize('fault',['foreign_sid','adjusted','fillforward','extended','custom','zone',
    'resolution','wrong_type','wrong_tick','duplicate_quote','duplicate_trade','no_trade','untyped'])
def test_quote_companion_is_explicitly_validated_and_never_ignored_if_unsafe(native,fault):
    native.initialize();target=old.Symbol(old.SID(native.body['security_id']),'PRIVATE.SID')
    trade=native.NativeConfig(target);quote=native.NativeConfig(target)
    quote.tick_type='quote';quote.type=NS(FullName='QuantConnect.Data.Market.QuoteBar')
    configs=[trade,quote]
    if fault=='foreign_sid':quote.symbol=old.Symbol(old.SID('FOREIGN X123ABC'),'PRIVATE.FOREIGN')
    elif fault=='adjusted':quote.data_normalization_mode='adjusted'
    elif fault=='fillforward':quote.fill_data_forward=True
    elif fault=='extended':quote.extended_market_hours=True
    elif fault=='custom':quote.is_custom_data=True
    elif fault=='zone':quote.exchange_time_zone=NS(id='UTC')
    elif fault=='resolution':quote.resolution='daily'
    elif fault=='wrong_type':quote.type=NS(FullName='Unknown.PRIVATE.TYPE')
    elif fault=='wrong_tick':quote.tick_type='trade'
    elif fault=='duplicate_quote':configs.append(quote)
    elif fault=='duplicate_trade':configs.append(trade)
    elif fault=='no_trade':configs=[quote]
    else:configs[1]=NS(**vars(quote))
    native.control.configs=configs;native.algo._probe();out=result(native)
    assert out['native_exact_subscription']['verified'] is False
    kinds=out['native_exact_subscription']['native_config_kind_counts']
    assert sum(kinds.values())==len(configs) and out['native_exact_subscription']['config_rows_examined']==len(configs)
    assert out['history_calls']==2 and out['status']=='native_exact_subscription_config_unproved'
    assert out['target_data_gap_proven'] is False
    assert all(label.startswith('control_') for label,_,_ in native.control.history)
    assert 'PRIVATE.FOREIGN' not in native.logs[-1] and 'Unknown.PRIVATE.TYPE' not in native.logs[-1]
