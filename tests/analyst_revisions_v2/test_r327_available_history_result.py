"""Public-code W5 envelopes and six-cell synthetic jobs; no DATA/QC access."""
import copy
import json

import pytest
from scripts import arv2_r327_available_history_result as m
from tests.analyst_revisions_v2 import test_r327_available_history_projection as projection_fixture
from tests.analyst_revisions_v2 import test_r327_available_history_runtime as aggregate_fixture


def refused(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


def pin(raw):return {'byte_count':len(raw),'sha256':m.sha(raw)}


@pytest.fixture(scope='module')
def family():
    batch=projection_fixture.public_batch();record=batch.to_record()
    axis=m.projection.plain.bridge.frozen.october._sessions()
    baseline,_=aggregate_fixture.result_fixture(axis)
    rows=[];profiles=[];bindings=[];entries=[]
    for index,spec in enumerate(batch.specs):
        profile=json.loads(spec.profile_bytes);cell=record['cells'][index]
        meta=json.loads(baseline[m.runtime.META_STATISTIC]);monthly=json.loads(baseline[m.runtime.MONTHLY_STATISTIC])
        meta.update(candidate_id=profile['candidate_id'],profile_sha256=profile['profile_sha256'],
            package_sha256=profile['package_sha256'],lineage_sha256=profile['lineage_sha256'])
        for field in ('universe_count','ar_percent'):
            if field in meta:meta[field]=profile[field]
        source=aggregate_fixture.old_common_tests.common_result(profile)
        source['schema']=m.runtime.RESULT_SCHEMA+'-source';meta['common_price']=source
        monthly.update(candidate_id=profile['candidate_id'],profile_sha256=profile['profile_sha256'])
        statistics={m.runtime.META_STATISTIC:m.canonical(meta).decode('ascii'),
            m.runtime.MONTHLY_STATISTIC:m.canonical(monthly).decode('ascii')}
        binding={'project_id':profile['runtime_project_id'],'backtest_id':format(index+1,'032x'),
            'name':'Synthetic-W5-'+str(cell['universe_count'])+'-AR'+str(cell['ar_percent']),
            'compile_id':'compile-'+str(index),'source_manifest_sha256':cell['source_manifest_pin']['sha256'],
            'common_profile_sha256':profile['profile_sha256'],'run_scope_tag':'R327-SYNTHETIC-'+str(index),
            'research_epoch_id':record['research_epoch_id'],'period_sha256':record['period_sha256'],
            'universe_count':cell['universe_count'],'ar_percent':cell['ar_percent'],
            'public_batch_sha256':batch.batch_sha256,'projection_sha256':cell['projection_sha256']}
        response={'success':True,'errors':[],'backtest':{'projectId':binding['project_id'],
            'backtestId':binding['backtest_id'],'name':binding['name'],'compileId':binding['compile_id'],
            'status':'Completed.','statistics':statistics}}
        selected,selected_pin=m.select_response(response,expected_run_binding=binding,
            expected_profile=profile,expected_public_cell=cell)
        entries.append({'selected_bytes':m.canonical(selected),'selected_pin':selected_pin,'actual_reader_exit':0,
            'launch_binding_bytes':None,'expected_launch_binding_pin':None})
        rows.append({'profile':profile,'binding':binding,'response':response,'cell':cell})
        profiles.append(profile);bindings.append(binding)
    return {'batch_bytes':batch.record_bytes,'batch_pin':pin(batch.record_bytes),'batch':record,
        'rows':rows,'profiles':profiles,'bindings':bindings,'entries':entries}


@pytest.fixture
def case(family):return copy.deepcopy(family['rows'][0])


def select(case,response=None,**extra):
    return m.select_response(case['response'] if response is None else response,
        expected_run_binding=case['binding'],expected_profile=case['profile'],expected_public_cell=case['cell'],**extra)


def checked(case,raw,selected_pin,**extra):
    return m.validate_selected(raw,expected_selected_pin=selected_pin,expected_run_binding=case['binding'],
        expected_profile=case['profile'],expected_public_cell=case['cell'],actual_reader_exit=0,**extra)


def joined(family,**changes):
    arguments={'expected_batch_bytes':family['batch_bytes'],'expected_batch_pin':family['batch_pin'],
        'expected_run_bindings':family['bindings'],'expected_profiles':family['profiles'],'actual_family_reader_exit':0}
    arguments.update(changes);return m.validate_family(family['entries'],**arguments)


def rewrite_entry(family,index,mutate):
    selected=json.loads(family['entries'][index]['selected_bytes']);mutate(selected)
    raw=m.canonical(selected);family['entries'][index].update(selected_bytes=raw,selected_pin=pin(raw))


def test_all_six_real_public_projections_join_new_statistics(family):
    value=joined(family);record=value['family']
    assert record['cell_order']==[[6,0],[6,100],[6,200],[8,0],[8,100],[8,200]]
    assert record['runtime_project_id']==123 and record['period_sha256']==m.PERIOD_SHA256
    assert record['engine_start_session']=='2021-09-01' and record['evaluation_first']=='2021-11-01'
    assert record['evaluation_last']=='2026-10-13' and record['first_reference_close']=='2021-10-29'
    assert record['performance_metric_scope']=='custom_Nov1_capital_epoch_only_not_QC_engine_warmup_period'
    assert record['cell_count']==6 and record['technical_selected_results_complete'] is True
    assert record['public_batch_pin']==family['batch_pin'] and len(value['results'])==6
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    for item in value['results']:
        meta=item['aggregate']['meta']
        assert meta['schema']==m.runtime.RESULT_SCHEMA and meta['split_unit_history_calls']==259
        assert meta['evaluation_session_count']==1242 and meta['raw_reference_history_calls']==0
        assert item['aggregate']['monthly']['months'][0][0].startswith('2021-11')
        assert len(item['aggregate']['monthly']['months'])==60
    value['family']['cells'][0]['binding']['name']='changed'
    assert family['bindings'][0]['name']!='changed'


class Unreadable:
    def __iter__(self):raise AssertionError('ignored private field traversed')
    def __repr__(self):raise AssertionError('ignored private field rendered')
    def __str__(self):raise AssertionError('ignored private field rendered')


def test_ignore_chart_order_trade_and_other_statistics_without_traversal(case):
    response=copy.deepcopy(case['response'])
    for name in ('charts','orders','trades','rollingWindow','totalPerformance','rawPrices'):
        response['backtest'][name]=Unreadable()
    response['privateUnknown']=Unreadable();response['backtest']['statistics']['Unknown licensed rows']=Unreadable()
    assert select(case,response)==select(case)


@pytest.mark.parametrize('issue,code',[
    ('success','response_success'),('errors','response_errors'),('errors_type','response_errors'),
    ('project','response_identity'),('project_bool','response_identity'),('job','response_identity'),
    ('name','response_identity'),('status','response_terminal'),('status_without_dot','response_terminal'),
    ('compile','response_compile'),('compile_null','response_compile')])
def test_actual_response_success_zero_errors_and_exact_job_terminal(case,issue,code):
    response=copy.deepcopy(case['response']);row=response['backtest']
    if issue=='success':response['success']=1
    elif issue=='errors':response['errors']=['DO-NOT-OUTPUT']
    elif issue=='errors_type':response['errors']={}
    elif issue=='project':row['projectId']+=1
    elif issue=='project_bool':row['projectId']=True
    elif issue=='job':row['backtestId']='f'*32
    elif issue=='name':row['name']+='-other'
    elif issue=='status':row['status']='Runtime Error'
    elif issue=='status_without_dot':row['status']='Completed'
    elif issue=='compile':row['compileId']='different'
    else:row['compileId']=None
    refused(code,lambda:select(case,response))


def test_missing_compile_requires_closed_external_launch_bytes(case):
    response=copy.deepcopy(case['response']);del response['backtest']['compileId']
    refused('launch_required',lambda:select(case,response))
    launch=m.canonical({'schema':m.LAUNCH_SCHEMA,'binding':case['binding']})
    arguments={'launch_binding_bytes':launch,'expected_launch_binding_pin':pin(launch)}
    selected,selected_pin=select(case,response,**arguments)
    assert selected['compile_binding_source']=='launch_only'
    assert checked(case,m.canonical(selected),selected_pin,**arguments)['aggregate']['meta']['decision_count']==259
    refused('launch_required',lambda:checked(case,m.canonical(selected),selected_pin))


@pytest.mark.parametrize('value',[2,-9,None,True,False,'0'])
def test_actual_exit_precedes_all_selected_input_access(value):
    refused('actual_exit',lambda:m.validate_selected(Unreadable(),expected_selected_pin=Unreadable(),
        expected_run_binding=Unreadable(),expected_profile=Unreadable(),expected_public_cell=Unreadable(),actual_reader_exit=value))


@pytest.mark.parametrize('issue,code',[
    ('old_schema','selected_shape'),('success_flag','selected_shape'),('error_count_bool','selected_shape'),
    ('error_count','selected_shape'),('admission','selected_shape'),('period','selected_binding'),
    ('batch','selected_binding'),('source_manifest','selected_binding'),('aggregate_hash','aggregate'),
    ('old_statistics','statistics')])
def test_repinning_selected_bytes_never_repairs_epoch_job_or_result(case,issue,code):
    selected,_=select(case)
    if issue=='old_schema':selected['schema']='arv2-r298-common-price-selected-result-v1'
    elif issue=='success_flag':selected['response_success']=1
    elif issue=='error_count_bool':selected['response_error_count']=False
    elif issue=='error_count':selected['response_error_count']=1
    elif issue=='admission':selected['source_admission_granted']=True
    elif issue=='period':selected['binding']['period_sha256']='0'*64
    elif issue=='batch':selected['binding']['public_batch_sha256']='0'*64
    elif issue=='source_manifest':selected['binding']['source_manifest_sha256']='0'*64
    elif issue=='aggregate_hash':selected['aggregate_sha256']='0'*64
    else:selected['statistics']={'ARV2_COMMON_PRICE_META':'{}','ARV2_COMMON_PRICE_MONTHLY':'{}'}
    raw=m.canonical(selected);refused(code,lambda:checked(case,raw,pin(raw)))


@pytest.mark.parametrize('issue',('profile_pin','manifest','descriptor','projection','cell_arm'))
def test_public_cell_and_expected_profile_source_join(case,issue):
    if issue=='profile_pin':case['cell']['profile_pin']['sha256']='0'*64
    elif issue=='manifest':case['cell']['source_manifest_pin']['sha256']='0'*64
    elif issue=='descriptor':case['cell']['source_files'][1]['content_sha256']='0'*64
    elif issue=='projection':case['cell']['projection_sha256']='0'*64
    else:case['cell']['ar_percent']=100
    refused('public_cell',lambda:select(case))


def test_old_2021_profile_is_not_renamed_into_new_epoch(case):
    old=aggregate_fixture.old_common_tests.result_fixture()[1]
    refused('profile',lambda:m.validate_run_binding(case['binding'],expected_profile=old,expected_public_cell=case['cell']))


@pytest.mark.parametrize('value',[2,-9,None,True])
def test_family_actual_exit_precedes_even_batch_access(value):
    refused('actual_exit',lambda:m.validate_family(Unreadable(),expected_batch_bytes=Unreadable(),
        expected_batch_pin=Unreadable(),expected_run_bindings=Unreadable(),expected_profiles=Unreadable(),actual_family_reader_exit=value))


def test_batch_bytes_authenticate_before_parse(family):
    refused('batch',lambda:joined(family,expected_batch_bytes=b'{"private":"do-not-parse"}'))


@pytest.mark.parametrize('engine_start',['2021-11-01','2020-11-01'])
def test_cold_or_old_engine_start_cannot_relabel_custom_period(family,engine_start):
    value=copy.deepcopy(family);value['batch']['engine_start_session']=engine_start
    value['batch_bytes']=m.canonical(value['batch']);value['batch_pin']=pin(value['batch_bytes'])
    refused('batch',lambda:joined(value))


def test_missing_or_reordered_family_cell_refuses(family):
    value=copy.deepcopy(family);value['entries'].pop()
    refused('family',lambda:joined(value))
    value=copy.deepcopy(family);value['entries'][0],value['entries'][1]=value['entries'][1],value['entries'][0]
    refused('selected_binding',lambda:joined(value))


@pytest.mark.parametrize('field',['backtest_id','compile_id','name','run_scope_tag'])
def test_family_job_reuse_refuses_even_rebound_selected_bytes(family,field):
    value=copy.deepcopy(family);value['bindings'][1][field]=value['bindings'][0][field]
    def mutate(selected):
        selected['binding'][field]=value['bindings'][1][field]
        if field=='compile_id':selected['response_compile_id']=value['bindings'][1][field]
    rewrite_entry(value,1,mutate)
    refused('family_jobs',lambda:joined(value))


def test_any_one_reader_nonzero_refuses_family(family):
    value=copy.deepcopy(family);value['entries'][4]['actual_reader_exit']=2
    refused('actual_exit',lambda:joined(value))


def _rebind_batch_and_selected(family):
    family['batch_bytes']=m.canonical(family['batch']);family['batch_pin']=pin(family['batch_bytes'])
    for index,binding in enumerate(family['bindings']):
        binding['public_batch_sha256']=family['batch_pin']['sha256']
        rewrite_entry(family,index,lambda selected,index=index:selected.update(binding=copy.deepcopy(family['bindings'][index])))


def test_family_shared_economics_checked_beyond_rehashed_metadata(family):
    value=copy.deepcopy(family);index=5;profile=value['profiles'][index]
    strategy=profile['strategy_profile'];strategy['gross_target']='0.97'
    strategy['profile_sha256']=m.runtime.digest({key:child for key,child in strategy.items() if key!='profile_sha256'})
    profile['strategy_profile_sha256']=strategy['profile_sha256']
    profile['profile_sha256']=m.runtime.digest({key:child for key,child in profile.items() if key!='profile_sha256'})
    m.runtime.validate_profile(profile)
    cell=value['batch']['cells'][index]
    cell.update(common_profile_sha256=profile['profile_sha256'],strategy_profile_sha256=profile['strategy_profile_sha256'],profile_pin=pin(m.canonical(profile)))
    manifest={'schema':m.BATCH_SCHEMA+'-source-manifest','runtime_project_id':profile['runtime_project_id'],
        'profile_sha256':profile['profile_sha256'],'source_files':cell['source_files']}
    cell['source_manifest_pin']=pin(m.canonical(manifest))
    value['bindings'][index].update(common_profile_sha256=profile['profile_sha256'],source_manifest_sha256=cell['source_manifest_pin']['sha256'])
    _rebind_batch_and_selected(value)
    refused('family_economics',lambda:joined(value))


def test_all_six_resolution_and_fund_identity_proofs_must_agree(family):
    value=copy.deepcopy(family)
    def mutate(selected):
        meta=json.loads(selected['statistics'][m.runtime.META_STATISTIC])
        meta['common_price']['fresh_resolution_sha256']='e'*64
        selected['statistics'][m.runtime.META_STATISTIC]=m.canonical(meta).decode('ascii')
        aggregate=m.runtime.validate_result_statistics(selected['statistics'],expected_profile=value['profiles'][5])
        selected['aggregate_sha256']=m.sha(m.canonical(aggregate))
    rewrite_entry(value,5,mutate)
    refused('family_scope',lambda:joined(value))


def test_profile_inert_no_source_QC_or_trading_authority():
    record=m.profile_record()
    assert record['new_W5_profile_schema']==m.runtime.SCHEMA
    assert record['statistics']==['ARV2_AVAILABLE_COMMON_META','ARV2_AVAILABLE_COMMON_MONTHLY']
    assert record['period_sha256']==m.PERIOD_SHA256 and record['same_project_for_six_cells'] is True
    assert record['engine_start_session']=='2021-09-01' and record['evaluation_first']=='2021-11-01'
    assert all(record[key] is False for key in m.FALSE_FLAGS)
