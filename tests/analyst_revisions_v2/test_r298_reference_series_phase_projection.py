"""Synthetic source/clock/metadata phase adversaries, no private input or QC."""
import ast
import copy
import dataclasses
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_reference_series_phase_projection as m

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(scope='module')
def public():
    comparison = m.comparison
    research = ROOT / 'research/analyst_revisions_v2_qc'
    names = set(comparison.bridge.parent.SOURCE_PINS) | set(comparison.NEW_SOURCE_PINS) | {comparison.HOST_SOURCE_NAME}
    sources = {name: (research / name).read_bytes() for name in names}
    old = comparison.public_specification(sources=sources,
        expected_host_source_pins={comparison.HOST_SOURCE_NAME: m.sha(sources[comparison.HOST_SOURCE_NAME])})
    pairs = tuple((item.project_path, item.source_bytes) for item in old.cells[0].source_files)
    patcher = (ROOT / 'scripts' / m.PATCHER_NAME).read_bytes()
    projection = m.public_specification(pairs, patcher_source_bytes=patcher, expected_patcher_sha256=m.sha(patcher))
    return NS(pairs=pairs, patcher=patcher, projection=projection,
        profile=json.loads(projection.profile_bytes), files=dict(projection.source_pairs))


@pytest.fixture
def runtime():
    namespace = {}
    exec(compile(m._runtime(), 'synthetic series phase runtime', 'exec'), namespace)
    namespace['sid'] = lambda symbol: symbol.identity
    return namespace


class Symbol:
    def __init__(self, identity, display='SYNTHX', timestamp=None):
        self.identity, self.value = identity, display
        self.id = NS(date=timestamp or datetime(2000, 1, 1))


class Bar:
    def __init__(self, symbol, left, right, ff=False):
        self.symbol, self.time, self.end_time, self.is_fill_forward = symbol, left, right, ff
    def __getattr__(self, name):
        raise AssertionError('no OHLCV/security price access allowed')


class Quote: pass


class Batch:
    def __init__(self, symbol, bar): self.time, self.entries = bar.end_time, [(symbol, bar)]
    def items(self): return iter(self.entries)


class History:
    def __init__(self, daily=(), minute=(), post=None):
        self.daily, self.minute, self.post, self.calls = daily, minute, post, []
        self.failure = None
    def __getitem__(self, kind):
        assert kind is Bar
        if self.failure == 'lookup': raise RuntimeError('synthetic')
        def call(symbols, start, end, resolution, **kwargs):
            self.calls.append((symbols, start, end, resolution, kwargs))
            if self.failure == 'call': raise RuntimeError('synthetic')
            if resolution == 'daily': return self.daily
            return self.post if len(self.calls) == 3 and self.post is not None else self.minute
        return call


def minutes(symbol, count=390, offset=0):
    opening = datetime(2022, 10, 21, 9, 30) + timedelta(seconds=offset)
    return [Batch(symbol, Bar(symbol, opening + timedelta(minutes=i), opening + timedelta(minutes=i+1))) for i in range(count)]


def daily(symbol, shape='precise'):
    result = []
    for text in m.SERIES_SESSIONS:
        value = datetime.fromisoformat(text)
        left, right = (value + timedelta(hours=9, minutes=30), value + timedelta(hours=16)) if shape == 'precise' else (
            value, value + timedelta(days=1)) if shape == 'legacy' else (value, value + timedelta(hours=16))
        result.append(Batch(symbol, Bar(symbol, left, right)))
    return result


def security(symbol):
    config = NS(symbol=symbol, resolution='minute', fill_data_forward=False, extended_market_hours=False,
        data_normalization_mode='RAW', data_time_zone='America/New_York', exchange_time_zone='America/New_York',
        type=NS(FullName='QuantConnect.Data.Market.TradeBar'))
    value = NS(symbol=symbol, data_normalization_mode='RAW', exchange=NS(hours=NS(time_zone='America/New_York')),
        subscriptions=[config])
    value.set_data_normalization_mode = lambda mode: setattr(value, 'data_normalization_mode', mode)
    return value


def initialized(runtime, public, monkeypatch):
    symbol, spy = Symbol('synthetic-native-SID'), Symbol('synthetic-SPY-SID', 'SPY')
    history = History(daily(symbol), minutes(symbol))
    selected = {'security_id': 'synthetic-selected', 'source_row_sha256': m.SOURCE_ROW,
        'composite_figi': 'BBG000000001'}
    rows = [{'security_id': 'synthetic-' + str(i)} for i in range(6150)] + [selected]
    runtime['WITNESS'] = runtime['digest']({'schema': 'arv2-missing-reference-identity-v1',
        'security_id': selected['security_id'], 'reference_session': '2022-10-21', 'decision_session': '2022-10-24'})
    runtime['BINDING_ROW'] = runtime['digest'](selected)
    loaded = NS(package_sha256=public.profile['package_sha256'], activation_manifest_sha256='a' * 64,
        evaluator_input=NS(session_axis=m.comparison.bridge.frozen.october._sessions(),
            source_lineage_sha256s=(('security_master_admission_sha256','b' * 64),)), runtime_symbol_bindings=rows)
    loads, resolutions, probes, summaries = [], [], [], []
    def load(*args, **kwargs): loads.append(kwargs); return loaded
    def resolve(rows, **kwargs):
        resolutions.append((len(rows), kwargs))
        return NS(input_row_count=6151, resolved_count=5116, named_refusal_count=1035,
            symbol_for_security=lambda identity: symbol if identity == selected['security_id'] else None)
    monkeypatch.setattr(runtime['inputs'], 'load_accepted_risk_preliminary_package', load)
    monkeypatch.setattr(runtime['figi'], 'resolve_preliminary_qc_figis', resolve)
    monkeypatch.setattr(runtime['figi'], '_input_row', lambda row, pin: dict(row))
    def composite(value, when=None):
        probes.append((value,when))
        return selected['composite_figi'] if when is None else symbol
    selected_security, spy_security = security(symbol), security(spy)
    algorithm = NS(live_mode=False, history=history, time=datetime(2022,10,25), time_zone='America/New_York',
        transactions=NS(get_orders=lambda: ()), portfolio={}, composite_figi=composite,
        add_security=lambda *args: selected_security,
        set_summary_statistic=lambda key,text: summaries.append((key,text)))
    value = runtime['ReferenceSeriesPhaseDiagnostic'](algorithm, profile=copy.deepcopy(public.profile),
        activation_manifest_key='synthetic', activation_manifest_sha256='a' * 64, activation_manifest_byte_count=1,
        benchmark_symbol=spy, clock_security=spy_security, trade_bar_type=Bar, quote_bar_type=Quote,
        minute_resolution='minute', daily_resolution='daily', raw_normalization='RAW')
    return NS(value=value, symbol=symbol, spy=spy, selected=selected, selected_security=selected_security,
        clock_security=spy_security, history=history, summaries=summaries, loads=loads, resolutions=resolutions,
        probes=probes, loaded=loaded)


def clock(state, **kwargs):
    state.value.algorithm.time = datetime(2022,10,25,9,31)
    bar = Bar(state.spy, datetime(2022,10,25,9,30), datetime(2022,10,25,9,31), **kwargs)
    return NS(time=datetime(2022,10,25,9,31), bars={state.spy:bar})


def bound_result(state):
    value = copy.deepcopy(state.value.result)
    value['identity_sha256'], value['whole_binding_row_sha256'] = m.WITNESS, m.BINDING_ROW
    return value


def validate(value, public):
    return m.validate_result_statistics({m.META_STATISTIC:m.canonical(value).decode('ascii')}, expected_profile=public.profile)


def test_public_exact_N_preimage_two_edits_and_pure_repeat(public, monkeypatch):
    files, nfiles = public.files, dict(m._n_pairs(public.pairs, old_input=True))
    assert len(files) == 11 and len([name for name in files if files[name] != nfiles[name]]) == 2
    assert set(name for name in files if files[name] != nfiles[name]) == {'main.py',m.RUNTIME_NAME}
    assert m.sha(m.canonical(m._manifest(tuple(nfiles.items()),m.N_PROJECTION))+b'\n') == m.N_MANIFEST
    assert len(public.projection.to_record()['unchanged_cloud_files']) == 9
    assert public.profile['profile_sha256'] == m.profile_digest(public.profile)
    assert m.validate_public_projection(public.projection.record_bytes,public.projection.source_pairs,
        expected_projection_sha256=public.projection.projection_sha256,
        expected_profile_sha256=public.profile['profile_sha256'])[1] == public.profile
    def denied(*args,**kwargs): pytest.fail('pure builder made IO')
    monkeypatch.setattr(Path,'read_bytes',denied); monkeypatch.setattr(m.admission,'admit',denied)
    assert m.public_specification(public.pairs,patcher_source_bytes=public.patcher,
        expected_patcher_sha256=m.sha(public.patcher)) == public.projection
    with pytest.raises(dataclasses.FrozenInstanceError): public.projection.record_bytes=b'changed'


def test_generated_source_no_orders_prices_seed_warmup_or_alternate_subscription(public):
    main=public.files['main.py'].decode('ascii'); runtime=public.files[m.RUNTIME_NAME].decode('ascii')
    assert 'set_start_date(2022, 10, 25)' in main and 'set_end_date(2022, 10, 25)' in main
    assert 'seed_initial_prices = False' in main and 'set_warm_up' not in main and 'schedule' not in main
    assert main.count('self.add_equity(')==1 and 'on_data' in main
    assert 'set_runtime_statistic' not in runtime and 'set_summary_statistic' in runtime
    tree=ast.parse(runtime)
    forbidden={'price','close','open','high','low','volume','market_order','set_holdings','set_market_price'}
    assert not any(isinstance(node,ast.Attribute) and node.attr in forbidden for node in ast.walk(tree))
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Attribute) and node.attr=='add_security']
    assert len(calls)==1 and all(len(raw)<=64000 for raw in public.files.values())


def test_initialize_then_exact_clock_three_fixed_requests_and_single_summary_key(runtime,public,monkeypatch):
    state=initialized(runtime,public,monkeypatch); state.value.initialize()
    assert len(state.loads)==len(state.resolutions)==1 and state.resolutions[0][0]==6151
    assert len(state.history.calls)==2 and len(state.summaries)==1
    first=copy.deepcopy(state.value.result['initialize'])
    assert state.value.result['post']['status']=='pending' and state.value.result['diagnostic_complete'] is False
    assert len(state.probes)==6 and [when for _,when in state.probes if when is not None]==[datetime.fromisoformat(x) for x in m.PROBE_DATES]
    state.value.on_data(clock(state)); state.value.on_end()
    assert len(state.history.calls)==3 and len(state.summaries)==2
    assert {key for key,_ in state.summaries}=={m.META_STATISTIC}
    assert state.value.result['initialize']==first
    expected=[(datetime(2022,10,17),datetime(2022,10,25),'daily'),
        (datetime(2022,10,21,9,30),datetime(2022,10,21,16),'minute')]*1
    assert state.history.calls[0][1:4]==expected[0] and all(call[1:4]==expected[1] for call in state.history.calls[1:])
    assert all(call[0]==[state.symbol] and call[4]=={'fill_forward':False,'extended_market_hours':False,
        'data_normalization_mode':'RAW'} for call in state.history.calls)
    result=bound_result(state)
    assert validate(result,public)==result and result['diagnostic_complete'] is True
    assert result['explicit_history_calls']==3 and all(result[key] is False for key in m.FALSE_FLAGS)
    assert len(m.canonical(result))<=16384
    state.value.on_data(clock(state)); assert len(state.history.calls)==3 and len(state.summaries)==2


@pytest.mark.parametrize('shape',['precise','legacy','midnight_close'])
def test_daily_delivered_metadata_retained_before_shape_validity(runtime,public,monkeypatch,shape):
    state=initialized(runtime,public,monkeypatch); state.history.daily=daily(state.symbol,shape)
    state.value.initialize(); row=state.value.result['initialize']['daily_series']
    assert row['status']=='complete' and row['items']==6
    assert row['time_session']['2022-10-21']==row['time_session']['2022-10-24']==1
    assert row['end_session']['2022-10-24']==(0 if shape=='legacy' else 1)
    assert sum(row['valid_precise_by_session'].values())==(6 if shape=='precise' else 0)
    assert sum(row['valid_legacy_by_session'].values())==(6 if shape=='legacy' else 0)
    assert row['period']['other']==(6 if shape=='midnight_close' else 0)
    assert validate(bound_result(state),public)['post']['status']=='pending'


@pytest.mark.parametrize('initial_count,post_count',[(0,0),(0,390),(390,0),(390,390)])
def test_phase_contrasts_are_metadata_not_A19_cause(runtime,public,monkeypatch,initial_count,post_count):
    state=initialized(runtime,public,monkeypatch)
    state.history.minute=minutes(state.symbol,initial_count); state.history.post=minutes(state.symbol,post_count)
    state.value.initialize(); state.value.on_data(clock(state))
    result=validate(bound_result(state),public)
    assert result['initialize']['minute']['items']==initial_count and result['post']['minute']['items']==post_count
    assert result['diagnostic_complete'] is True and result['a19_cause_authenticated'] is False
    assert result['independent_data_completeness_proven'] is False


@pytest.mark.parametrize('change',['late','missing','fill_forward','wrong_sid','wrong_period','wrong_slice'])
def test_missing_or_bad_exact_clock_retains_immutable_Init_and_no_third_call(runtime,public,monkeypatch,change):
    state=initialized(runtime,public,monkeypatch); state.value.initialize()
    initial=copy.deepcopy(state.value.result['initialize']); data=clock(state)
    if change=='late': state.value.algorithm.time+=timedelta(minutes=1)
    elif change=='missing': data.bars={}
    elif change=='fill_forward': data.bars[state.spy].is_fill_forward=True
    elif change=='wrong_sid': data.bars[state.spy].symbol=Symbol('other')
    elif change=='wrong_period': data.bars[state.spy].time+=timedelta(seconds=1)
    else: data.time+=timedelta(seconds=1)
    with pytest.raises(RuntimeError,match='feed_(missing_clock|clock)'): state.value.on_data(data)
    assert len(state.history.calls)==2 and len(state.summaries)==2
    assert state.value.result['initialize']==initial
    result=validate(bound_result(state),public)
    assert result['diagnostic_complete'] is False and result['post']['minute'] is None


def test_no_catchup_terminal_missed_clock_refuses_after_preserving_Init(runtime,public,monkeypatch):
    state=initialized(runtime,public,monkeypatch); state.value.initialize()
    state.value.algorithm.time=datetime(2022,10,25,16)
    with pytest.raises(RuntimeError,match='feed_missing_clock'): state.value.on_end()
    result=validate(bound_result(state),public)
    assert result['post']['status']=='clock_missing' and result['summary_updates']==2
    assert len(state.history.calls)==2


@pytest.mark.parametrize('kind',['wrong_sid','fill_forward','off_grid','duplicate'])
def test_received_minute_rows_never_claim_valid_grid_without_witnesses(runtime,public,monkeypatch,kind):
    state=initialized(runtime,public,monkeypatch)
    rows=state.history.minute
    if kind=='wrong_sid': rows[0].entries[0][1].symbol=Symbol('other')
    elif kind=='fill_forward': rows[0].entries[0][1].is_fill_forward=True
    elif kind=='off_grid': rows[0].entries[0][1].time+=timedelta(seconds=1)
    else: rows[1]=rows[0]
    state.value.initialize(); result=validate(bound_result(state),public)
    assert result['initialize']['minute']['items']==390
    assert result['initialize']['minute']['minute_grid_complete'] is False


@pytest.mark.parametrize('field,value',[('fill_data_forward',True),('extended_market_hours',True),
    ('data_normalization_mode','Adjusted'),('resolution','daily'),('data_time_zone','UTC'),('exchange_time_zone','UTC'),
    ('type',NS(FullName='Other.Type'))])
def test_actual_subscription_config_mismatch_stops_before_history(runtime,public,monkeypatch,field,value):
    state=initialized(runtime,public,monkeypatch)
    setattr(state.selected_security.subscriptions[0],field,value)
    with pytest.raises(RuntimeError,match='feed_subscription'): state.value.initialize()
    assert state.history.calls==[] and state.summaries==[]


@pytest.mark.parametrize('mode',['different','unavailable','forward_fail','reverse_fail','bad_metadata'])
def test_dated_probe_never_replaces_original_native_symbol(runtime,public,monkeypatch,mode):
    state=initialized(runtime,public,monkeypatch)
    def composite(value,when=None):
        if when is None:
            if mode=='reverse_fail': raise RuntimeError('synthetic')
            return state.selected['composite_figi']
        if mode=='forward_fail': raise RuntimeError('synthetic')
        if mode=='unavailable': return None
        if mode=='bad_metadata': return NS(value='SYNTHX',id=NS(date='not_datetime'))
        return Symbol('other-SID','OTHER') if mode=='different' else state.symbol
    state.value.algorithm.composite_figi=composite
    state.value.initialize(); state.value.on_data(clock(state))
    result=validate(bound_result(state),public)
    assert all(call[0]==[state.symbol] for call in state.history.calls)
    assert result['alternate_resolved_symbol_used'] is False
    probe=result['initialize']['dated_probes'][0]
    assert probe['status']=={'different':'observed','unavailable':'unavailable','forward_fail':'forward_failed',
        'reverse_fail':'reverse_failed','bad_metadata':'metadata_failed'}[mode]
    if mode=='different': assert probe['same_native_sid'] is probe['same_native_display'] is False


def test_post_history_refusal_preserves_Init_and_emits_false_complete(runtime,public,monkeypatch):
    state=initialized(runtime,public,monkeypatch); state.value.initialize()
    initial=copy.deepcopy(state.value.result['initialize'])
    state.history.failure='call'
    with pytest.raises(RuntimeError,match='feed_result'): state.value.on_data(clock(state))
    result=validate(bound_result(state),public)
    assert result['initialize']==initial and result['post']['minute']['status']=='call_failed'
    assert result['diagnostic_complete'] is False and result['explicit_history_calls']==3
    assert len(state.summaries)==2


def test_dated_future_probe_refuses_before_resolver(runtime,public,monkeypatch):
    state=initialized(runtime,public,monkeypatch)
    state.value.native=state.value.native_metadata(state.symbol)
    with pytest.raises(RuntimeError,match='feed_clock'):
        state.value.dated_probe('BBG000000001','2022-10-26')
    assert state.probes==[]


@pytest.mark.parametrize('kind',['bool_calls','pending_complete','wrong_post_clock','alter_Init','missing_bad_subscription',
    'daily_bad_sid','daily_wrong_session','daily_bool','probe_false_equality','probe_unknown','extra','price','oversize'])
def test_receiver_rejects_inconsistent_or_forged_metadata(runtime,public,monkeypatch,kind):
    state=initialized(runtime,public,monkeypatch); state.value.initialize(); result=bound_result(state)
    if kind=='bool_calls': result['explicit_history_calls']=True
    elif kind=='pending_complete': result['diagnostic_complete']=True
    elif kind=='wrong_post_clock': result['post']['actual_clock']='2022-10-25_0931_NY_OnData'
    elif kind=='alter_Init':
        result['initialize']['resolved_count']-=1
        result['initialize']['named_refusal_count']+=1
    elif kind=='missing_bad_subscription': result['initialize']['selected_subscription']['fill_forward']=True
    elif kind=='daily_bad_sid': result['initialize']['daily_series']['sid_mismatch_count']=1
    elif kind=='daily_wrong_session': result['initialize']['daily_series']['time_session']['2022-10-21']=0
    elif kind=='daily_bool': result['initialize']['daily_series']['batches']=True
    elif kind=='probe_false_equality': result['initialize']['dated_probes'][0]['same_native_sid']=False
    elif kind=='probe_unknown': result['initialize']['dated_probes'][0]['raw_ticker']='SYNTHX'
    elif kind=='extra': result['raw_price']='secret'
    elif kind=='price': result['price_used']=True
    if kind not in ('alter_Init','extra','price','oversize'):
        result['initialize_sha256']=m.sha(m.canonical(result['initialize']))
    raw=m.canonical(result).decode('ascii')
    if kind=='oversize': raw='x'*16385
    with pytest.raises(m.Refused): m.validate_result_statistics({m.META_STATISTIC:raw},expected_profile=public.profile)


@pytest.mark.parametrize('kind',['runtime','main','legacy','other','record','profile'])
def test_projection_tampering_and_old_N_immutability(public,kind):
    pairs=public.projection.source_pairs; raw=public.projection.record_bytes
    name={'runtime':m.RUNTIME_NAME,'main':'main.py','legacy':'newrule_legacy_primitives.py',
        'other':m.comparison.bridge.INPUT_NAME}.get(kind)
    if name: pairs=tuple((key,value+b'\n' if key==name else value) for key,value in pairs)
    elif kind=='record': raw+=b'\n'
    with pytest.raises(m.Refused): m.validate_public_projection(raw,pairs,
        expected_projection_sha256=public.projection.projection_sha256,
        expected_profile_sha256='0'*64 if kind=='profile' else public.profile['profile_sha256'])
    assert m.sha((ROOT/'scripts'/m.previous.PATCHER_NAME).read_bytes())==m.N_PATCHER
