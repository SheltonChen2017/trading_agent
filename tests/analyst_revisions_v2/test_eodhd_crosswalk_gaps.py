"""Synthetic complete-inventory BC diagnostics; no production DATA or contact."""
import copy
from collections import Counter, defaultdict
import hashlib
import inspect
import time
from types import SimpleNamespace as NS
import pytest
from scripts import read_arv2_r298_eodhd_crosswalk_gaps as m


def args():return NS(operation='produce',expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def figi(number):
    seed='BBG'+str(number).zfill(8);values=[int(char,36)*(1 if index%2==0 else 2) for index,char in enumerate(seed)]
    return seed+str((10-sum(number//10+number%10 for number in values)%10)%10)


def cusip(number):
    seed=str(number).zfill(8);values=[int(char)*(1 if index%2==0 else 2) for index,char in enumerate(seed)]
    return seed+str((10-sum(number//10+number%10 for number in values)%10)%10)


def isin(value,prefix='US'):
    for digit in range(10):
        candidate=prefix+value+str(digit)
        if m.crosswalk._isin(candidate):return candidate
    raise AssertionError('synthetic ISIN')


def catalog(code,kind='Common Stock'):
    return {'Code':code,'Name':'private synthetic display','Country':'US','Exchange':'NYSE','Currency':'USD','Type':kind,'Isin':None}


def mapping(symbol,f,c,ISIN=None):return {'symbol':symbol,'figi':f,'cusip':c,'isin':ISIN,'lei':None,'cik':None}


def fail(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def receipt(plan):
    return {'schema':m.guard_module.SCHEMA+'-receipt','profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(plan))),
        'files':{role:{**item,'current_metadata_sha256':'a'*64,'current_security_sha256':'b'*64} for role,item in plan.items()},
        'fresh_current_security_authenticated':True,'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
        'historical_continuity_proven':False,'continuous_integrity_proven':False}


@pytest.fixture(scope='module')
def full_case():
    context=m.source_context();summary=copy.deepcopy(context['BB_result']['crosswalk_summary'])
    admission=context['BB_result']['genuine_input_binding']['binding_contract']['security_master_admission_sha256']
    sources=[];stocks=[];funds=[];active=[];mappings=[];stream=hashlib.sha256()
    for index in range(6151):
        f,c=figi(index+1),cusip(index+100)
        role='Sharadar_RAW_full_window' if index<5636 else 'pending_native_original_identity_source' if index<5641 else 'conditional_never_potential_empty_initial_holdings_required'
        row=m.crosswalk.prices.native.figi.build_preliminary_qc_figi_binding(security_id='sharadar-composite-figi-'+f,
            issuer_id='synthetic-issuer-'+str(index),composite_figi=f,listing_id='synthetic-listing-'+str(index),
            diagnostic_current_ticker='S'+str(index),diagnostic_exchange_mic='XNYS',candidate_first_session='2020-12-31',
            candidate_last_session='2026-10-13',source_snapshot_available_at='2026-10-13T00:00:00.000000Z',
            source_row_sha256=hashlib.sha256(('source'+str(index)).encode()).hexdigest(),
            identity_evidence_sha256=hashlib.sha256(('evidence'+str(index)).encode()).hexdigest(),
            security_master_admission_sha256=admission,admitted_mapping_inventory_sha256='e'*64,admitted_mapping_count=6151)
        stream.update(m.crosswalk.prices.native.figi._canonical(row))
        sources.append({'kind':'stock','ordinal':index,'binding':row,'original_proof':'pass','owner':('stock',row['security_id'],f),
            'figi':f,'tokens':[c],'AP_role':role,'potential':index<5641})
        stocks.append({'binding_ordinal':index,'binding':row,'original_proof':'pass',
            'original_source_row_sha256':row['source_row_sha256'],'original_identity_evidence_sha256':row['identity_evidence_sha256'],
            'AP_role':role,'potential':index<5641,'source_composite_figi':f,'available_source_cusip_union':[c],
            'validated_original_cusip_tokens':[c],'qualified_current_cusip_tokens':[c]})
        code='S'+str(index);active.append(catalog(code))
        if index!=3:
            value=None if index==0 else c[:8] if index==1 else c.lstrip('0') if index==2 else c
            mappings.append(mapping(code+'.US',f,value,isin(c) if index in (0,1,2) else None))
    for ordinal,ticker in enumerate(m.crosswalk.prices.native.UNIVERSES):
        f,c=figi(90000+ordinal),cusip(90000+ordinal)
        sources.append({'kind':'fund','ordinal':ordinal,'ticker':ticker,'owner':('fund',ticker,f),'figi':f,'tokens':[c],
            'AP_role':'Sharadar_RAW_full_window','potential':True})
        funds.append({'fund_ordinal':ordinal,'ticker':ticker,'AP_role':'Sharadar_RAW_full_window','potential':True,
            'source_composite_figi':f,'available_source_cusip_union':[c],'validated_original_cusip_tokens':None,'qualified_current_cusip_tokens':[c]})
        active.append(catalog(ticker,'ETF'));mappings.append(mapping(ticker+'.US',f,c))
    indexes=m.crosswalk._indexes(active,[],mappings,sources,None)
    for item,source in zip(stocks+funds,sources,strict=True):item.update(m.crosswalk._match(source,indexes,None))
    summary['source_pins']['genuine_binding_stream_sha256']=stream.hexdigest();summary['source_fingerprint']=m.sha(m.canonical(summary['source_pins']))
    summary.update(original_proof_counts={'pass':6151,'refused':0,'unavailable':0},original_token_count=6151,
        qualified_current_token_count=6159,union_token_count=6159,provider_row_counts={'active':6159,'delisted':0,'mapping':len(mappings)},original_reporting_currency_not_usd_count=0)
    for key,table in (('stocks',stocks),('funds',funds)):
        summary['disposition_counts'][key]=dict(Counter(item['status'] for item in table))
        summary['reason_counts'][key]=dict(Counter(item['reason'] for item in table if item['reason'] is not None))
    record={'schema':m.crosswalk.PRIVATE_SCHEMA,'source_fingerprint':summary['source_fingerprint'],'stocks':stocks,'funds':funds}
    summary['private_payload_pin']=m.pin(m.canonical(record));context['BB_result']['crosswalk_summary']=summary
    return context,record,mappings,active


def test_public_BB_reconstruction_and_six_DATA_pins():
    context=m.source_context();assert context['BB_fact_sha256']==m.FACT_SHA256
    assert len(m.DATA_PLAN)==6 and sum(item['byte_count'] for item in m.DATA_PLAN.values())==40937140
    assert len(m.pins())==215 and all(m.sha((m.ROOT/name).read_bytes())==expected for name,expected in m.pins().items())


@pytest.mark.parametrize('role',('producer','validator'))
@pytest.mark.parametrize('bad',(False,True,2))
def test_actual_zero_requires_integer_zero(monkeypatch,role,bad):
    fact=m.anchor.observed_fact();fact[role]['actual_exit']=bad
    monkeypatch.setattr(m.anchor,'observed_fact',lambda:fact);monkeypatch.setattr(m,'FACT_SHA256',m.sha(m.canonical(fact)))
    fail('source_binding',m.source_context)


@pytest.mark.parametrize('issue',('summary','data_pin','report','grant','stdout','count'))
def test_prior_metadata_cannot_be_silently_refreshed(monkeypatch,issue):
    if issue=='summary':
        result=m.anchor.result_summary();result['crosswalk_summary']['union_token_count']+=1;monkeypatch.setattr(m.anchor,'result_summary',lambda:result)
    else:
        fact=m.anchor.observed_fact()
        if issue=='data_pin':fact['data_plan']['crosswalk']['sha256']='e'*64
        elif issue=='report':fact['report']['byte_count']+=1
        elif issue=='grant':fact['crosswalk_admitted']=True
        elif issue=='stdout':fact['producer']['stdout_sha256']='f'*64
        else:fact['producer']['stdout_bytes']=True
        monkeypatch.setattr(m.anchor,'observed_fact',lambda:fact)
    fail('source_binding',m.source_context)


@pytest.mark.parametrize('field,value,category',[
    ('figi',None,'null'),('figi',False,'type'),('figi','','empty'),('figi','BBG','length'),('figi','BBG00000000A','format'),
    ('cusip',None,'null'),('cusip',123,'type'),('cusip','','empty'),('cusip','12345678','length8'),('cusip','123','length_other'),('cusip','12345678A','format'),
    ('symbol',None,'null'),('symbol',{},'type'),('symbol','','empty'),('symbol','US','length'),('symbol','SYMBOL.UK','format'),('symbol','SYNTHETIC.US','valid'),
    ('isin',None,'null'),('isin',[],'type'),('isin','','empty'),('isin','US0','length'),('isin','USABCDEFGHI!','format')])
def test_identifier_field_categories_are_finite(field,value,category):assert m._field_category({field:value},field)==category


@pytest.mark.parametrize('field',('figi','cusip','symbol','isin'))
def test_missing_distinct_from_null(field):assert m._field_category({},field)=='missing'


def test_valid_and_corrupted_checksum_categories():
    for field,value in (('figi',figi(1)),('cusip',cusip(1)),('isin',isin(cusip(1)))):
        assert m._field_category({field:value},field)=='valid'
        assert m._field_category({field:value[:-1]+str((int(value[-1])+1)%10)},field)=='checksum'


def test_all_original_bindings_and_diagnostic_observations(full_case):
    context,record,mappings,active=full_case;value=m.diagnose(record,mappings,active,[],context,time.monotonic()+100)
    m.validate_diagnosis(value,context);assert value['complete_mapping_row_count']==6158 and value['funds']['source_count']==8
    assert sum(group['source_count'] for group in value['stock_groups'])==6151
    group=next(group for group in value['stock_groups'] if group['BB_reason']=='mapping_identifier_invalid');flags=group['source_observation_counts']
    assert group['source_count']==3 and flags['same_FIGI_CUSIP8_base_equal_observed']==1
    assert flags['same_FIGI_CUSIP9_leading_zero_loss_observed']==1 and flags['exact_FIGI_and_checksum_CUSIP9_pair_present']==0
    assert group['related_mapping_field_categories']['cusip']['null']==1
    isin_rows=group['same_FIGI_ISIN_source_token_row_counts']['validated_original']['US']
    assert isin_rows['raw_missing_null_or_empty']==1 and isin_rows['raw_nonempty_invalid']==2
    assert group['same_FIGI_ISIN_source_token_source_counts']['validated_original']['US']==isin_rows
    assert sum(group['same_FIGI_ISIN_source_token_row_counts']['union_only']['US'].values())==0
    raw=m.canonical(value)
    for forbidden in (record['stocks'][0]['binding']['security_id'].encode(),mappings[0]['figi'].encode(),b'private synthetic display',b'mapping_indices'):assert forbidden not in raw
    assert all(value[key] is False for key in m.FALSE_FLAGS if key!='result_cell')


@pytest.mark.parametrize('issue',('semantic_hash','stream','evidence','ordinal','tokens','indices','catalog_ref','result'))
def test_binding_and_full_reproduction_tampering_refuses(full_case,issue):
    context,record,mappings,active=full_case;record=copy.deepcopy(record);context=copy.deepcopy(context);item=record['stocks'][7]
    if issue=='semantic_hash':item['binding']['row_sha256']='e'*64
    elif issue=='stream':context['BB_result']['crosswalk_summary']['source_pins']['genuine_binding_stream_sha256']='e'*64
    elif issue=='evidence':item['original_identity_evidence_sha256']='e'*64
    elif issue=='ordinal':item['binding_ordinal']=False
    elif issue=='tokens':item['available_source_cusip_union']=[]
    elif issue=='indices':item['mapping_indices']=[len(mappings)]
    elif issue=='catalog_ref':item['catalog_references']=[{'table':'active','ordinal':len(active)}]
    else:item.update(reason='mapping_identifier_invalid',status='unresolved',route=None)
    with pytest.raises(m.Refused):m.diagnose(record,mappings,active,[],context,time.monotonic()+100)


def test_reference_budget_before_matching(full_case,monkeypatch):
    context,record,mappings,active=full_case;monkeypatch.setattr(m,'MAX_REFERENCE_VISITS',0)
    monkeypatch.setattr(m.crosswalk,'_match',lambda *_:pytest.fail('matching dispatched after exhausted budget'))
    fail('reference_budget',lambda:m.diagnose(record,mappings,active,[],context,time.monotonic()+100))


@pytest.mark.parametrize('value,state',[(None,'raw_missing_null_or_empty'),('','raw_missing_null_or_empty'),
    (' ','raw_nonempty_invalid'),('N/A','raw_nonempty_invalid'),(False,'raw_nonempty_invalid')])
def test_nonempty_raw_placeholder_is_not_absence(value,state):
    assert m._raw_cusip_state({'cusip':value},cusip(1))==state


def test_agreeing_and_conflicting_valid_raw_CUSIP_are_separate():
    assert m._raw_cusip_state({'cusip':cusip(1)},cusip(1))=='raw_agrees'
    assert m._raw_cusip_state({'cusip':cusip(2)},cusip(1))=='raw_valid_different'


def test_derived_identifier_index_sees_other_null_and_invalid_FIGI_rows(full_case):
    context,record,mappings,active=full_case;context=copy.deepcopy(context);local=record['stocks'][0]['validated_original_cusip_tokens'][0]
    extra=[mapping('DERIVED'+str(index)+'.US',f,None,isin(local)) for index,f in enumerate((figi(80000),None,'BAD'))]
    context['BB_result']['crosswalk_summary']['provider_row_counts']['mapping']+=len(extra)
    value=m.diagnose(record,mappings+extra,active,[],context,time.monotonic()+100)
    group=next(group for group in value['stock_groups'] if group['BB_reason']=='mapping_identifier_invalid')
    counts=group['all_mapping_derived_source_token_FIGI_counts']['validated_original']
    assert counts=={'same_valid_FIGI':3,'other_valid_FIGI':1,'missing_null_or_empty_FIGI':1,'nonempty_invalid_FIGI':1}
    assert group['same_FIGI_ISIN_source_token_row_counts']['validated_original']['US']['raw_missing_null_or_empty']==1


def test_related_other_FIGI_cannot_count_as_same_FIGI_ISIN_evidence(full_case):
    context,record,mappings,active=full_case;context=copy.deepcopy(context);record=copy.deepcopy(record)
    local=record['stocks'][0]['validated_original_cusip_tokens'][0]
    extra=mapping('OTHER-RELATED.US',figi(80000),local,isin(local))
    record['stocks'][0]['mapping_indices'].append(len(mappings));context['BB_result']['crosswalk_summary']['provider_row_counts']['mapping']+=1
    value=m.diagnose(record,mappings+[extra],active,[],context,time.monotonic()+100)
    group=next(group for group in value['stock_groups'] if group['BB_reason']=='mapping_identifier_invalid')
    counts=group['same_FIGI_ISIN_source_token_row_counts']['validated_original']['US']
    assert counts['raw_missing_null_or_empty']==1 and counts['raw_agrees']==0
    assert group['all_mapping_derived_source_token_FIGI_counts']['validated_original']['other_valid_FIGI']==1


def test_union_only_ISIN_match_does_not_become_original_evidence(full_case):
    context,record,mappings,active=full_case;context=copy.deepcopy(context);record=copy.deepcopy(record);mappings=copy.deepcopy(mappings)
    local=cusip(9000000);item=record['stocks'][0];item['qualified_current_cusip_tokens'].append(local)
    item['available_source_cusip_union']=sorted(item['available_source_cusip_union']+[local]);mappings[0]['isin']=isin(local)
    summary=context['BB_result']['crosswalk_summary'];summary['qualified_current_token_count']+=1;summary['union_token_count']+=1
    value=m.diagnose(record,mappings,active,[],context,time.monotonic()+100)
    group=next(group for group in value['stock_groups'] if group['BB_reason']=='mapping_identifier_invalid')
    assert group['same_FIGI_ISIN_source_token_row_counts']['union_only']['US']['raw_missing_null_or_empty']==1
    assert group['same_FIGI_ISIN_source_token_row_counts']['validated_original']['US']['raw_missing_null_or_empty']==0
    assert value['identifiers_repaired'] is value['new_route_created'] is False


def test_all_six_pins_before_parse_and_guard_normal_return(monkeypatch):
    context=m.source_context();values={role:('synthetic-'+role).encode() for role in m.DATA_PLAN};plan=copy.deepcopy(m.DATA_PLAN)
    for role in plan:plan[role].update(m.pin(values[role]))
    monkeypatch.setattr(m,'DATA_PLAN',plan);events=[];active=[False]
    class Guard:
        def __init__(self,*_,**__):pass
        def __enter__(self):active[0]=True;events.append('enter');return self
        def __exit__(self,*_):active[0]=False;events.append('normal-return')
        def read_all_once(self):events.append('all-six-pins');return values
        def verify(self):assert active[0]
        def receipt(self):return receipt(plan)
    monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    def catalog(*_):assert active[0] and events[-1]=='all-six-pins';events.append('catalog');return b'active',b'delisted',[]
    monkeypatch.setattr(m.bb,'_catalog_data',catalog);monkeypatch.setattr(m.crosswalk.catalogs,'checked_symbol_rows',lambda _:[])
    monkeypatch.setattr(m,'_decode_private',lambda *_:{'synthetic':True})
    def diagnose(*_):assert active[0];events.append('diagnose');return {'synthetic_closed':True}
    monkeypatch.setattr(m,'diagnose',diagnose);monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    result=m.construct(context,time.monotonic()+100)
    assert not active[0] and events==['enter','all-six-pins','catalog','diagnose','normal-return'] and result['source_guard_normal_return'] is True


def test_changed_byte_pin_refuses_before_JSON(monkeypatch):
    context=m.source_context()
    class Guard:
        def __init__(self,*_,**__):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read_all_once(self):return {role:b'wrong' for role in m.DATA_PLAN}
    monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard);monkeypatch.setattr(m.bb,'_catalog_data',lambda *_:pytest.fail('catalog before pins'))
    with pytest.raises(m.bb.Refused):m.construct(context,time.monotonic()+100)


def test_guard_return_failure_never_publishes_report(monkeypatch):
    monkeypatch.setattr(m,'source_context',lambda:{})
    class Store:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def write(self,name,raw,deadline):assert name!='report.json';return m.pin(raw)
    monkeypatch.setattr(m,'Store',Store)
    def construct(*_):raise m.guard_module.Refused('named_changed')
    monkeypatch.setattr(m,'construct',construct);result=m.run(args(),time.monotonic()+100)
    assert set(result)=={'failure'} and result['failure']['failure_code']=='guard_named_changed'


@pytest.fixture
def result(full_case):
    context,record,mappings,active=full_case
    value={'schema':m.SCHEMA,'diagnosis':m.diagnose(record,mappings,active,[],context,time.monotonic()+100),'source_receipt':receipt(m.DATA_PLAN),
        'source_guard_normal_return':True,'BB_fact_sha256':m.FACT_SHA256,'post_checks_complete':True,**m.FALSE_FLAGS}
    return context,value


def envelope(value):return m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':m.pin(m.canonical({**m.binding(args()),'result':value}))}})+bytes([10])


@pytest.mark.parametrize('issue',('actual','normal','admission','group_bool','count','private_field','receipt'))
def test_closed_metadata_and_actual_zero_required(result,monkeypatch,issue):
    context,value=result;value=copy.deepcopy(value);actual=0;monkeypatch.setattr(m,'source_context',lambda:context)
    if issue=='actual':actual=2
    elif issue=='normal':value['source_guard_normal_return']=False
    elif issue=='admission':value['identifiers_repaired']=True
    elif issue=='group_bool':value['diagnosis']['stock_groups'][0]['source_count']=True
    elif issue=='count':value['diagnosis']['complete_mapping_row_count']-=1
    elif issue=='private_field':value['diagnosis']['private_symbol']='must-never-print'
    else:value['source_receipt']['files']['crosswalk']['sha256']='e'*64
    with pytest.raises((m.Refused,m.guard_module.Refused)):m.validate_output(envelope(value),actual,args())


def test_closed_success_has_one_real_LF(result,monkeypatch):
    context,value=result;monkeypatch.setattr(m,'source_context',lambda:context);raw=envelope(value)
    assert raw.count(bytes([10]))==1 and m.validate_output(raw,0,args())['outcome']['result']==value
    fail('output',lambda:m.validate_output(raw[:-1]+bytes([92,110]),0,args()))


def maximum_fixed_group_envelope(value):
    """Pessimistic byte shape, not a semantically admissible count result.

    Every diagnosis integer is widened to the seven-digit reference budget;
    the actual fixed BB observation bounds the possible fifteen group keys.
    Receipt byte counts and binding/hash fields keep their exact dimensions.
    """
    def widen(node):
        if type(node) is int:return m.MAX_REFERENCE_VISITS
        if type(node) is dict:return {key:widen(child) for key,child in node.items()}
        if type(node) is list:return [widen(child) for child in node]
        return node
    value=copy.deepcopy(value);diagnosis=widen(value['diagnosis']);template=diagnosis['stock_groups'][0];groups=[]
    for prior in m.anchor.result_summary()['stock_AP_role_potential_breakdown']:
        keys=[('matched_current_crosswalk',None)] if prior['disposition_counts'].get('matched_current_crosswalk') else []
        keys.extend(('unresolved',reason) for reason in prior['unresolved_reason_counts'])
        for status,reason in keys:
            group=copy.deepcopy(template);group.update(AP_role=prior['AP_role'],potential=prior['potential'],BB_status=status,BB_reason=reason)
            groups.append(group)
    diagnosis['stock_groups']=groups;value['diagnosis']=diagnosis
    return envelope(value),len(groups)


def test_full_fixed_fifteen_group_envelope_has_room_with_widened_counters(result):
    _,value=result;maximum,groups=maximum_fixed_group_envelope(value)
    assert groups==15 and len(maximum)<m.MAX_OUTPUT


@pytest.mark.parametrize('mode',('produce','validate'))
def test_native_policy_only_six_DATA_no_genuine_or_old_controls(mode):
    policy=m.native_profile(mode);assert '(deny network*)' in policy and '(deny process-exec (literal "/usr/bin/security"))' in policy
    for item in m.DATA_PLAN.values():assert (item['relative_path'] in policy) is (mode=='produce')
    for path in (m.bb.worker.previous.PACKAGE,m.bb.worker.previous.LINEAGE):assert str(path) not in policy
    for path in ('routes-private.json','price-lineage-private.json','plan-private.json','/report.json','/claim.json'):assert path not in policy


def test_no_old_entrypoint_or_provider_route():
    source=inspect.getsource(m)
    for forbidden in ('bb.run(','bb.construct(','bb.main(','ba.run(','ba.main(','load_key(','requests.get(','.ljust('):assert forbidden not in source
    assert source.index('values=guard.read_all_once()')<source.index('active_raw,delisted_raw,mappings=')
