"""Real public-code regeneration and synthetic project context; no DATA/QC."""
import ast
import copy
import dataclasses
import inspect
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from scripts import arv2_r327_available_history_projection as m

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


def fail(code,operation):
    with pytest.raises(m.Refused) as caught:operation()
    assert m.finite(caught.value)==code


@pytest.fixture(scope='module')
def supplied():
    folder=ROOT/'research/analyst_revisions_v2_qc'
    public={name:(folder/name).read_bytes() for name in m.previous.PUBLIC_SOURCE_PINS}
    addons=tuple((name,(folder/name).read_bytes()) for name in m.common.ADDON_NAMES)
    vendor={'schema':m.vendor.fmt.SCHEMA+'-QC-context','runtime_project_id':123,
        'manifest_pin':dict(m.previous.AR_MANIFEST_PIN),'catalog_pin':dict(m.previous.AR_CATALOG_PIN),
        'object_key_prefix':'123/arv2/r326-common/'+m.previous.AR_MANIFEST_PIN['sha256']+'/',
        'AP_fact_sha256':m.vendor.fmt.AP_FACT_SHA256,'AP_authentication_sha256':m.vendor.fmt.AP_AUTH_SHA256}
    patch=(ROOT/'scripts'/m.PATCHER_NAME).read_bytes()
    return {'public_sources':public,'addon_source_pairs':addons,
        'quote_patcher_source_bytes':(ROOT/'scripts/arv2_newrule_quote_execution_projection.py').read_bytes(),
        'common_patcher_source_bytes':(ROOT/'scripts/arv2_r298_common_price_projection.py').read_bytes(),
        'available_source_pairs':tuple((name,(folder/name).read_bytes()) for name in m.AVAILABLE_NAMES),
        'period_source_bytes':(ROOT/'scripts/arv2_r327_available_history_period.py').read_bytes(),
        'patcher_source_bytes':patch,'expected_patcher_sha256':m.sha(patch),
        'runtime_project_id':123,'native_source_context':m.native.source_context(),'vendor_source_context':vendor}


def prepare(supplied,**changes):
    arguments=dict(supplied);arguments.update(changes);return m.prepare(**arguments)


def public_batch():
    """Real public-code specification with synthetic unverified project123."""
    arguments=supplied.__wrapped__();return prepare(arguments)


@pytest.fixture(scope='module')
def batch(supplied):return prepare(supplied)


def test_actual_public_sources_make_all_six_new_period_cells_and_no_grants(batch):
    record=batch.to_record()
    assert record['schema']==m.SCHEMA and record['cell_count']==6
    assert record['cell_order']==[[6,0],[6,100],[6,200],[8,0],[8,100],[8,200]]
    assert record['evaluation_first']=='2021-11-01' and record['first_reference_close']=='2021-10-29'
    assert record['engine_start_session']=='2021-09-01'
    assert record['evaluation_last']=='2026-10-13' and record['starting_cash']=='1000000'
    assert record['initial_state']=='new_epoch_empty_positions_and_orders_USD1000000'
    assert record['research_epoch_id']==m.period.RESEARCH_EPOCH_ID
    assert record['period_sha256']==m.period.make_period(m.plain.bridge.frozen.october._sessions())['period_sha256']
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    assert record['runtime_project_currently_verified'] is False
    assert record['native_book_point_coverage_proven'] is False
    assert m.validate_batch_record(record)==record


def test_all19_source_files_equal_except_Main_and_six_profiles_distinct(batch):
    records=[spec.to_record() for spec in batch.specs]
    files=[tuple((name,raw) for name,raw in spec.source_pairs if name!='main.py') for spec in batch.specs]
    assert len(files[0])==18 and all(value==files[0] for value in files)
    assert all(len(spec.source_pairs)==19 for spec in batch.specs)
    for key in ('profile_sha256','strategy_profile_sha256'):
        assert len({row[key] for row in records})==6
    assert len({dict(spec.source_pairs)['main.py'] for spec in batch.specs})==6
    assert all(m.common.DRIVER_NAME not in dict(spec.source_pairs) for spec in batch.specs)
    assert all(m.common.BASE_NAME in dict(spec.source_pairs) for spec in batch.specs)


def test_old_c7_base_is_provenance_and_new_cloud_pin_is_actual_distinct_bytes(batch):
    for spec in batch.specs:
        record=spec.to_record();files=dict(spec.source_pairs)
        assert m.sha(files[m.common.BASE_NAME])==m.common.runtime.FROZEN_BASE_SHA256
        assert record['frozen_quote_base_sha256']==m.common.runtime.FROZEN_BASE_SHA256
        assert record['available_history_quote_base_pin']==m.pin(files[m.BASE_NAME])
        assert record['available_history_quote_base_pin']['sha256']!=record['frozen_quote_base_sha256']
        profile=m.runtime.validate_profile(json.loads(spec.profile_bytes))
        assert profile['source_pins'][m.BASE_NAME]==m.sha(files[m.BASE_NAME])
        assert profile['strategy_profile']['source_pins']==profile['source_pins']


def test_all_quote_cash_fee_fill_methods_exact_AST_and_missing_marks_stops_unchanged(batch,supplied):
    files=dict(batch.specs[0].source_pairs)
    old=ast.parse(files[m.common.BASE_NAME]);new=ast.parse(files[m.BASE_NAME])
    old_driver=m._node(old,'NewruleComparisonDriver',ast.ClassDef)
    new_driver=m._node(new,'NewruleComparisonDriver',ast.ClassDef)
    for name in m._QUOTE_METHODS:
        assert m._dump(m._node(old_driver,name))==m._dump(m._node(new_driver,name))
    assert [m._dump(node) for node in old_driver.bases]==[m._dump(node) for node in new_driver.bases]
    for name,raw in supplied['addon_source_pairs'][:-1]:
        assert files[name]==m.common._cloud_source(raw,name)
    assert files['newrule_common_price_format.py']==dict(supplied['addon_source_pairs'])['newrule_common_price_format.py']
    assert files[m.DRIVER_NAME]==dict(supplied['available_source_pairs'])[m.DRIVER_NAME]
    assert 'common_price_missing' in files['newrule_common_price_qc_runtime.py'].decode() or b'missing' in files['newrule_common_price_qc_runtime.py']


@pytest.mark.parametrize('size,arm',m.CELL_ORDER)
def test_generated_cloud_profile_is_exact_new_period_and_preserves_economics(batch,size,arm):
    spec=batch.specs[m.CELL_ORDER.index((size,arm))];profile=m.runtime.validate_profile(json.loads(spec.profile_bytes))
    strategy=profile['strategy_profile'];files=dict(spec.source_pairs)
    namespace={'__name__':'synthetic_W5_cloud_base'}
    exec(compile(files[m.BASE_NAME],m.BASE_NAME,'exec'),namespace)
    actual=namespace['make_profile'](m.plain.bridge.frozen.october._sessions(),package_sha256=strategy['package_sha256'],
        lineage_sha256=strategy['lineage_sha256'],universe_count=size,ar_percent=arm,source_pins=strategy['source_pins'])
    assert actual==strategy
    assert len(strategy['evaluation_sessions'])==1242 and len(strategy['decision_sessions'])==259
    assert strategy['gross_target']=='0.98' and strategy['aggregate_stock_target_cap']=='0.098'
    assert strategy['fee_bps']=='10' and strategy['slippage_model_bps']=='0'
    assert strategy['execution_policy']==m.quote.POLICY
    assert strategy['initial_state']=='new_epoch_empty_positions_and_orders_USD1000000'
    assert strategy['first_reference_close']=='2021-10-29'
    assert strategy['candidate_id']==f'arv2-r327-{size}-ar{arm}-2021Nov01-2026Oct13-v1-quote-aware-v1'
    assert callable(namespace['NewruleComparisonDriver']._quote_snapshot)
    assert not hasattr(m.base.NewruleComparisonDriver,'_quote_snapshot')


def test_Main_retains_two_month_callback_warmup_and_explicit_import_with_existing_cash_and_order_callbacks(batch):
    for spec in batch.specs:
        tree=ast.parse(dict(spec.source_pairs)['main.py']);profile=json.loads(spec.profile_bytes)
        imports=[node for node in tree.body if isinstance(node,ast.ImportFrom) and node.module==m.DRIVER_NAME[:-3]]
        assert len(imports)==1 and imports[0].names[0].name=='CommonPriceComparisonDriver'
        start=next(node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='set_start_date')
        assert [ast.literal_eval(node) for node in start.args]==[2021,9,1]
        source=ast.unparse(tree)
        assert 'self.settings.seed_initial_prices = False' in source
        assert f'self.project_id != {profile["runtime_project_id"]}' in source
        assert 'self.live_mode is not False' in source
        assert 'quote_bar_type=QuoteBar' in source and 'fee_model_factory=lambda: NewruleTenBpsFeeModel(self._driver)' in source
        assert 'set_cash(STARTING_CASH)' in source
        m._profile_main_join(spec.source_pairs,profile)


def test_warmup_callbacks_cannot_enter_strategy_orders_reference_or_valuation_paths(batch):
    profile=json.loads(batch.specs[0].profile_bytes)['strategy_profile']
    namespace={'__name__':'synthetic_W5_warmup_base'}
    exec(compile(dict(batch.specs[0].source_pairs)[m.BASE_NAME],m.BASE_NAME,'exec'),namespace)
    def denied(*_,**__):pytest.fail('warmup reached strategy/reference/valuation operation')
    for day in ('2021-09-01','2021-10-01','2021-10-29'):
        fake=NS(_require_initialized=lambda:None,_common_guard=lambda:None,
            _now=lambda:datetime.fromisoformat(day+'T09:31:00'),_decision_set=frozenset(profile['decision_sessions']),
            _evaluation_sessions=tuple(profile['evaluation_sessions']),_submit_market=denied,
            _reference_prices=denied,_current_holding_census=denied,_portfolio_cash=denied,_portfolio_equity=denied,
            _common_source=NS(session_close=denied))
        driver=namespace['NewruleComparisonDriver']
        assert driver.on_before_open(fake) is driver.on_after_open(fake) is None
        assert m.runtime.CommonPriceComparisonDriver.on_after_close(fake) is None
    assert profile['evaluation_sessions'][0]=='2021-11-01' and profile['decision_sessions'][0]=='2021-11-01'
    assert profile['sizing_nav'].startswith('exact_prior_NYSE_after_close_NAV;first_2021Nov01_new_epoch_STARTING_CASH')


def test_source_manifest_pins_cover_each_cell_complete_generated_code(batch):
    record=batch.to_record()
    for cell,spec in zip(record['cells'],batch.specs,strict=True):
        manifest={'schema':m.SCHEMA+'-source-manifest','runtime_project_id':record['runtime_project_id'],
            'profile_sha256':cell['common_profile_sha256'],'source_files':spec.to_record()['source_files']}
        assert cell['source_manifest_pin']==m.pin(m.canonical(manifest))
        assert cell['projection_pin']==m.pin(spec.record_bytes) and cell['profile_pin']==m.pin(spec.profile_bytes)


@pytest.mark.parametrize('source',('old_public','old_addon','new_base','new_common','period','quote_patcher','common_patcher','new_patcher'))
def test_every_supplied_public_source_pin_is_required_before_generation(supplied,source):
    args=dict(supplied)
    if source=='old_public':
        args['public_sources']=dict(args['public_sources']);args['public_sources'][m.common.BASE_NAME]+=b'\n'
    elif source=='old_addon':args['addon_source_pairs']=tuple((name,raw+b'\n' if i==0 else raw) for i,(name,raw) in enumerate(args['addon_source_pairs']))
    elif source in ('new_base','new_common'):
        target=m.BASE_NAME if source=='new_base' else m.DRIVER_NAME
        args['available_source_pairs']=tuple((name,raw+b'\n' if name==target else raw) for name,raw in args['available_source_pairs'])
    else:
        field={'period':'period_source_bytes','quote_patcher':'quote_patcher_source_bytes','common_patcher':'common_patcher_source_bytes','new_patcher':'patcher_source_bytes'}[source]
        args[field]+=b'\n'
    fail('source_pin',lambda:m.prepare(**args))


def test_declared_host_delta_rejects_extra_economic_change_even_with_prospective_raw_pin(batch,supplied):
    host=dict(supplied['available_source_pairs'])[m.BASE_NAME].replace(b'FEE_RATE = Decimal("0.001")',b'FEE_RATE = Decimal("0.002")')
    fail('base_delta',lambda:m._period_base(supplied['public_sources'][m.common.BASE_NAME],host,
        dict(batch.specs[0].source_pairs)[m.common.BASE_NAME]))


@pytest.mark.parametrize('issue',('missing_cell','reorder','duplicate_main','different_nonmain','schema','project_bool','cell_bool','grant','manifest','base_pin','period','cold_start','old_warmup'))
def test_closed_batch_refuses_mixed_cells_changed_geometry_or_false_authority(batch,issue):
    record=copy.deepcopy(batch.to_record())
    if issue=='missing_cell':record['cells'].pop()
    elif issue=='reorder':record['cells'][0],record['cells'][1]=record['cells'][1],record['cells'][0]
    elif issue=='duplicate_main':record['cells'][1]['main_pin']=record['cells'][0]['main_pin']
    elif issue=='different_nonmain':record['cells'][1]['source_files'][0]['content_sha256']='f'*64
    elif issue=='schema':record['schema']=m.previous.SCHEMA
    elif issue=='project_bool':record['runtime_project_id']=True
    elif issue=='cell_bool':record['cells'][0]['universe_count']=True
    elif issue=='grant':record['backtest_created']=True
    elif issue=='manifest':record['cells'][0]['source_manifest_pin']['sha256']='f'*64
    elif issue=='base_pin':record['available_history_quote_base_pin']['sha256']=record['frozen_quote_base_sha256']
    elif issue=='cold_start':record['engine_start_session']='2021-11-01'
    elif issue=='old_warmup':record['engine_start_session']='2020-11-01'
    else:record['period_sha256']='f'*64
    fail('period' if issue=='period' else 'batch',lambda:m.validate_batch_record(record))


def test_frozen_specification_hashes_detect_mutation(batch):
    wrong=dataclasses.replace(batch,record_bytes=batch.record_bytes+b' ')
    fail('batch',wrong.to_record)
    spec=batch.specs[0];wrong=dataclasses.replace(spec,profile_bytes=spec.profile_bytes+b' ')
    fail('projection',wrong.to_record)


@pytest.mark.parametrize('entry',(None,{},'private synthetic row',[],{'byte_count':1,'sha256':'a'*64}))
@pytest.mark.parametrize('target',('shared','cell_sources'))
def test_malformed_metadata_entries_refuse_before_key_indexing(batch,entry,target):
    record=copy.deepcopy(batch.to_record())
    if target=='shared':record['shared_non_main_source_files'][0]=entry
    else:record['cells'][0]['source_files'][0]=entry
    fail('batch',lambda:m.validate_batch_record(record))


def test_profile_and_source_prefixes_do_not_normalize_old_period_results(batch):
    profile=json.loads(batch.specs[0].profile_bytes)
    assert profile['schema']==m.runtime.SCHEMA and profile['strategy_profile']['schema']==m.base.SCHEMA
    assert m.runtime.META_STATISTIC=='ARV2_AVAILABLE_COMMON_META'
    assert m.runtime.MONTHLY_STATISTIC=='ARV2_AVAILABLE_COMMON_MONTHLY'
    assert profile['candidate_id'].endswith('-common-RAW-W5-v1')
    assert m.profile_record()['CAGR'].startswith('new_Nov1_capital_epoch')


def test_public_generator_has_no_operation_callback_or_old_module_mutation():
    source=inspect.getsource(m)
    for text in ('def run(', 'def main(', 'open(', 'read_bytes(', 'write_bytes(', 'load_key(', 'setattr(', 'sys.modules', 'requests.'):
        assert text not in source
    assert m.finite(RuntimeError('private synthetic values'))=='unknown'
