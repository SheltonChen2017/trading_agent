"""Synthetic original ownership evidence; no actual DATA, keys, USB or QC."""
import ast
import copy
import csv
import io
import json
import os
from pathlib import Path
import time
import subprocess
import sys
from contextlib import ExitStack,contextmanager
import zipfile
from types import SimpleNamespace as NS
import pytest
from scripts import arv2_r336_original_identity_ownership as p
from scripts import inspect_arv2_r336_original_identity_ownership as m
from scripts import arv2_r336_original_ticker_security as s

def refusal(code,call):
    with pytest.raises(p.Refused) as caught:call()
    assert p.finite(caught.value)==code

def row(index,table='SF1',**changes):
    value={key:'' for key in p.REQUIRED}
    value.update(table=table,ticker='S'+str(index),permaticker=str(100+index),figi='BBG'+str(index).zfill(9),
      cusips=str(index+1).zfill(9),exchange='NASDAQ',category='Domestic Common Stock',currency='USD',
      firstpricedate='2000-01-03',lastpricedate='2026-10-13',isdelisted='N',sector='Technology',industry='Synthetic',
      name='Synthetic café',lastupdated='2026-09-13')
    value.update({'extra'+str(i):'' for i in range(28-len(value))});value.update(changes);return value

def binding(value):
    source=p.sha(p.row_bytes(value));perma=value['permaticker'];figi=value['figi'];mic='XNAS'
    # The expected original row/evidence encoding is independently constructed.
    evidence={'permaticker':perma,'composite_figi':figi,'source_table':'SF1','ticker':value['ticker'],
      'cusips':[value['cusips']],'exchange':'NASDAQ','exchange_mic':mic,'firstpricedate':'2000-01-03',
      'lastpricedate':'2026-10-13','source_row_sha256':source,
      'availability_semantics':'capture_time_current_snapshot_active_and_delisted_not_point_in_time'}
    raw=(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
    digest=p.sha(raw)
    return {'source_row_sha256':source,'security_id':'sharadar-composite-figi-'+figi,'issuer_id':'sharadar-permaticker-'+perma,
      'composite_figi':figi,'listing_id':'sharadar-listing-'+digest[:24],'diagnostic_current_ticker':value['ticker'],
      'diagnostic_exchange_mic':mic,'identity_evidence_sha256':digest}

@pytest.fixture
def scenario(monkeypatch):
    originals=[row(i) for i in range(5)];cases=[];wholes=[];rows=[]
    for ordinal,original in enumerate(originals):
        bound=binding(original);whole=p.sha(p.canonical(bound));wholes.append(whole)
        current=[{key:original[key] for key in p.CURRENT_FIELDS}]
        current[0]['table']='stocks';current[0]['figi']='BBG'+str(ordinal+50).zfill(9)
        if ordinal==0:
            current.append(dict(current[0],permaticker='999',cusips='999999999',figi=original['figi']))
        cases.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'demand':{'retained':True},
          'original_case':{'aa_stock':{'binding':bound,'original_row':original,'current_candidate_rows':current}}})
        rows.extend((original,dict(original,table='SEP',figi=current[0]['figi'])))
    monkeypatch.setattr(p,'WHOLes',tuple(wholes))
    identity={'schema':'arv2-r327-W5-identity-necessary-demand-i-v1-private','cases':cases}
    return NS(originals=originals,rows=rows,identity=identity)

def inspect(scenario):return p.inspect(scenario.rows,scenario.identity,deadline=time.monotonic()+30)

def test_cross_table_FIGI_disagreement_is_observation_not_rewrite(scenario):
    before=copy.deepcopy(scenario.identity);summary,private=inspect(scenario)
    assert summary['selected_case_count']==5 and summary['current_candidate_count']==6
    for ordinal,case in enumerate(summary['cases']):
        scopes={value['table_scope']:value for value in case['table_scopes']}
        assert scopes['fundamentals']['predicate_counts']['same_FIGI']['true']==1
        assert scopes['stocks']['predicate_counts']['same_FIGI']['false']==1
        assert scopes['stocks']['current_candidate_matrices'][0]['same_permaticker_FIGI_CUSIP_tuple']==1
        assert not case['identity_admitted']
    assert scenario.identity==before and all(summary[key] is False for key in p.FLAGS)
    assert private['cases'][0]['current_candidate_rows']==before['cases'][0]['original_case']['aa_stock']['current_candidate_rows']

def test_identical_physical_rows_are_preserved_without_admission(scenario):
    scenario.rows.append(dict(scenario.rows[0]));summary,private=inspect(scenario)
    assert summary['original_repeated_full_row_count']==1
    assert summary['cases'][0]['original_SF1_physical_match_count']==2
    scope=summary['cases'][0]['table_scopes'][0]
    assert scope['physical_row_count']==2 and scope['unique_identity_tuple_count']==1
    assert len([row for row in private['cases'][0]['original_catalog_owners'] if row['scope']=='fundamentals'])==2

def test_same_name_or_ticker_is_never_a_relationship_selector(scenario):
    unrelated=row(99,name=scenario.originals[0]['name'],ticker=scenario.originals[0]['ticker'])
    scenario.rows.append(unrelated);summary,private=inspect(scenario)
    assert summary['cases'][0]['related_original_physical_row_count']==2
    assert all(owner['row']!=unrelated for owner in private['cases'][0]['original_catalog_owners'])

def test_other_table_scope_and_poisoned_complete_token_incidence_retained(scenario):
    poison=row(99,table='UNRECOGNIZED',cusips='bad/'+scenario.originals[0]['cusips']+'/bad')
    scenario.rows.append(poison);summary,private=inspect(scenario)
    scope=summary['cases'][0]['table_scopes'][3]
    assert scope['physical_row_count']==scope['poison_owner_count']==1
    assert scope['malformed_or_missing_vocabulary_row_count']==1
    assert scope['link_counts']['original_poison_CUSIP']==1
    owner=next(item for item in private['cases'][0]['original_catalog_owners'] if item['scope']=='other')
    assert owner['complete_CUSIPs']==[] and owner['poison_CUSIPs']==[scenario.originals[0]['cusips']]

@pytest.mark.parametrize('value',[None,False,17,[],{},b'123456789'])
def test_vocabulary_rejects_nonstring_without_raw_error(value):refusal('row',lambda:p.vocabulary(value))

@pytest.mark.parametrize('value',['123456789','123456789 987654321','123456789, 987654321',' abcdefghi '])
def test_complete_vocabulary_supported_without_field_truncation(value):
    tokens,poison,state=p.vocabulary(value);assert tokens and not poison and state=='accepted'

@pytest.mark.parametrize('value',['123456789 123456789','123456789,','123456789 BAD','123456789\t987654321'])
def test_incomplete_vocabulary_never_admits_first_token(value):
    tokens,poison,state=p.vocabulary(value);assert not tokens and state!='accepted' and '123456789' in poison

@pytest.mark.parametrize('field',['source_row_sha256','security_id','issuer_id','composite_figi','listing_id',
  'diagnostic_current_ticker','diagnostic_exchange_mic','identity_evidence_sha256'])
def test_every_original_construction_binding_is_checked(scenario,field):
    value=scenario.identity['cases'][0]['original_case']['aa_stock']['binding'];value[field]='wrong'
    refusal('original_proof',lambda:p.original_proof(value,scenario.originals[0]))

@pytest.mark.parametrize('field',['permaticker','figi','ticker','cusips','exchange','firstpricedate','sector','industry','name'])
def test_full_original_row_hash_precedes_any_metadata_reinterpretation(scenario,field):
    original=dict(scenario.originals[0]);original[field]+='X'
    refusal('original_proof',lambda:p.original_proof(binding(scenario.originals[0]),original))

def test_hash_matches_frozen_composer_unicode_encoding(scenario):
    raw=p.row_bytes(scenario.originals[0]);assert b'caf\xc3\xa9' in raw and raw.endswith(b'\n')
    assert p.sha(raw)!=p.sha(p.canonical(scenario.originals[0]))

@pytest.mark.parametrize('kind',['ordinal','whole','candidate_count','source_row','source_schema'])
def test_closed_five_case_binding_scope(scenario,kind):
    if kind=='ordinal':scenario.identity['cases'][0]['case_ordinal']=True
    elif kind=='whole':scenario.identity['cases'][0]['whole_binding_sha256']='0'*64
    elif kind=='candidate_count':scenario.identity['cases'][0]['original_case']['aa_stock']['current_candidate_rows'].pop()
    elif kind=='source_row':scenario.rows.pop(0)
    else:scenario.identity['schema']='other'
    with pytest.raises(p.Refused):inspect(scenario)

def source_function(path,name):
    raw=path.read_text();tree=ast.parse(raw)
    node=next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
    return ast.dump(node,include_attributes=False)

def test_complete_token_parser_is_exact_frozen_AST_copy():
    assert source_function(Path(p.__file__),'_syntax')==source_function(m.ROOT/'scripts/arv2_r298_sharadar_cusip_syntax.py','_syntax')

@pytest.mark.parametrize('name',['_sessions','demands'])
def test_full_demand_validation_is_exact_frozen_copy(name):
    assert source_function(Path(p.__file__),name)==source_function(m.ROOT/'scripts/inspect_arv2_r335_firstrate_stock_coverage.py',name)

def test_current_original_security_guard_preserves_full_held_named_class():
    assert source_function(Path(s.__file__),'SourceGuard')==source_function(m.ROOT/'scripts/arv2_r298_reference_ticker_source_guard.py','SourceGuard')
    source=Path(s.__file__).read_text();assert 'historical' not in [node.id for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Name)]
    assert 'VINTAGE_METADATA' not in source and 'PROSPECTIVE_DEVICE' not in source

def zip_fixture(monkeypatch):
    rows=[row(i) for i in range(5)];stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
    header=list(rows[0]);writer.writerow(header)
    for value in rows:writer.writerow([value[key] for key in header])
    payload=stream.getvalue().encode();buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as zipped:zipped.writestr('synthetic.csv',payload)
    zipped=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(zipped)) as source:info=source.infolist()[0]
    manifest={'archives':[{'dataset':'tickers','archive_file':'01-tickers-years-full.zip','archive_byte_count':len(zipped),
      'archive_sha256':p.sha(zipped),'members':[{'name':'synthetic.csv','compressed_byte_count':info.compress_size,
      'uncompressed_byte_count':len(payload),'crc32':info.CRC,'content_sha256':p.sha(payload),'row_count':len(rows),'columns':header}]},{},{}]}
    raw=p.canonical(manifest);pins={'MANIFEST_PIN':p.pin(raw),'ARCHIVE_PIN':p.pin(zipped),'MEMBER_PIN':p.pin(payload),
      'HEADER_PIN':p.pin(payload.partition(b'\n')[0]+b'\n'),'COLUMNS_SHA':p.sha(p.canonical(header)),
      'ROW_STREAM_SHA':p.sha((json.dumps([p.sha(p.row_bytes(row)) for row in rows],sort_keys=True,
        separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')),'ROW_COUNT':5}
    for key,value in pins.items():monkeypatch.setattr(p,key,value)
    return raw,(p.sha(raw)+'\n').encode(),zipped,rows

def test_all_original_container_member_header_stream_bindings_parse_before_rows(monkeypatch):
    manifest,marker,archive,rows=zip_fixture(monkeypatch)
    assert p.decode_catalog(manifest,marker,archive,deadline=time.monotonic()+30)==rows

@pytest.mark.parametrize('which',['manifest','marker','archive','member','header','columns','row_stream','count'])
def test_every_archive_layer_pin_is_enforced(monkeypatch,which):
    manifest,marker,archive,_=zip_fixture(monkeypatch)
    if which=='manifest':manifest+=b' '
    elif which=='marker':marker=b'0'*64+b'\n'
    elif which=='archive':archive+=b' '
    elif which=='member':monkeypatch.setitem(p.MEMBER_PIN,'sha256','0'*64)
    elif which=='header':monkeypatch.setitem(p.HEADER_PIN,'sha256','0'*64)
    elif which=='columns':monkeypatch.setattr(p,'COLUMNS_SHA','0'*64)
    elif which=='row_stream':monkeypatch.setattr(p,'ROW_STREAM_SHA','0'*64)
    else:monkeypatch.setattr(p,'ROW_COUNT',4)
    with pytest.raises(p.Refused):p.decode_catalog(manifest,marker,archive,deadline=time.monotonic()+30)

@pytest.mark.parametrize('kind',['flag','extra','bool_count','case_order','scope','matrix','predicate','duplicate_count'])
def test_public_summary_refuses_invented_acceptance_or_inconsistent_counts(scenario,kind):
    summary,_=inspect(scenario)
    if kind=='flag':summary['identity_admitted']=True
    elif kind=='extra':summary['private_id']='NEVER'
    elif kind=='bool_count':summary['current_candidate_count']=True
    elif kind=='case_order':summary['cases'].reverse()
    elif kind=='scope':summary['cases'][0]['table_scopes'][0]['table_scope']='aliased'
    elif kind=='matrix':summary['cases'][0]['table_scopes'][0]['current_candidate_matrices'][0]['same_permaticker_FIGI_CUSIP_tuple']=999
    elif kind=='predicate':summary['cases'][0]['table_scopes'][0]['predicate_counts']['same_FIGI']['true']=999
    else:summary['original_repeated_full_row_count']=9
    refusal('output',lambda:p.validate_summary(summary))

class Security:
    @staticmethod
    def snapshot(fd):return {'acl_empty':True,'xattrs':{}}

def test_exclusive_claim_preserves_old_control_and_never_reuses_it(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir();root.chmod(0o755)
    (root/'artifacts').mkdir(mode=0o700);(root/'artifacts/analyst_revisions_v2').mkdir(mode=0o700)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',root/'artifacts/analyst_revisions_v2/recovery/M')
    with m.Store(Security) as store:store.write('claim.json',b'{}')
    with pytest.raises((m.Refused,OSError)):
        with m.Store(Security):pass
    assert (m.CONTROL/'claim.json').read_bytes()==b'{}'

def test_late_held_named_output_modification_refuses_and_preserves_bytes(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir();root.chmod(0o755)
    (root/'artifacts').mkdir(mode=0o700);(root/'artifacts/analyst_revisions_v2').mkdir(mode=0o700)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',root/'artifacts/analyst_revisions_v2/recovery/M')
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json',b'{}');(m.CONTROL/'claim.json').write_bytes(b'changed');store.verify()
    assert (m.CONTROL/'claim.json').read_bytes()==b'changed'

def test_native_policy_denies_network_USB_and_keychains_without_extra_DATA():
    policy=m.native_profile()
    assert '(deny network*)' in policy and '/Volumes' in policy
    assert '/Users/sheltonchen/Library/Keychains' in policy and '/Library/Keychains' in policy
    assert '/usr/bin/security' in policy
    assert all(str(m.ROOT/value['relative_path']) in policy for value in m.DATA_PLAN.values())
    assert len(m.DATA_PLAN)==4 and not any('ACTIONS' in value['relative_path'].upper() for value in m.DATA_PLAN.values())

def test_pure_module_has_no_filesystem_network_or_external_imports():
    tree=ast.parse(Path(p.__file__).read_text());imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom):imports.append(node.module.split('.')[0])
    assert set(imports)<={'collections','csv','datetime','hashlib','io','json','math','pathlib','re','stat','time','zipfile'}
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('open','exec','eval') for node in ast.walk(tree))

def test_parent_initializes_pinned_validator_before_child_dispatch(monkeypatch):
    events=[];monkeypatch.setattr(m,'preflight',lambda *a:events.append('preflight'))
    monkeypatch.setattr(m,'PURE_MODULE',None)
    def bootstrap(role,stack,deadline):
        assert role=='validate';events.append('pinned_validator');m.PURE_MODULE=p
    monkeypatch.setattr(m,'bootstrap',bootstrap)
    def dispatch(args):
        assert m.PURE_MODULE is p;events.append('dispatch');return 'complete'
    monkeypatch.setattr(m,'_parent_bound',dispatch)
    assert m.parent(NS())=='complete' and events==['preflight','pinned_validator','dispatch']

def test_cli_unknown_argument_is_finite_and_never_echoes_input():
    completed=subprocess.run([sys.executable,'-I','-B',str(m.SOURCE),'launch','--SYNTHETIC-PRIVATE'],cwd=m.ROOT,
      stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,
      env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert completed.returncode==2 and not completed.stderr and b'SYNTHETIC-PRIVATE' not in completed.stdout
    assert json.loads(completed.stdout)['failure_code']=='arguments'

def test_fresh_isolated_process_bootstraps_exact_closure_without_private_access():
    script="""import importlib.util,sys,time
from contextlib import ExitStack
from pathlib import Path
path=Path('scripts/inspect_arv2_r336_original_identity_ownership.py').absolute()
spec=importlib.util.spec_from_file_location('M_synthetic',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with ExitStack() as held:
    bound=module.bootstrap('worker',held,time.monotonic()+20)
    assert set(bound)=={'security','pure','guard','original_guard','anchor'}
    assert bound['anchor'].observed_fact()['private_data']==module.DATA_PLAN['identity']
    assert not any(name.startswith(('qc.','QuantConnect','AlgorithmImports','scripts.run_arv2_r298')) for name in sys.modules)
print('pinned bootstrap complete')
"""
    support=m.ROOT/'.pytest_cache/r336-ownership/tmp'
    completed=subprocess.run([sys.executable,'-I','-B','-c',script],cwd=m.ROOT,
      stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,
      env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1',
       'TMPDIR':str(support),'PYTHONPYCACHEPREFIX':str(support/'pycache')})
    assert completed.returncode==0 and not completed.stderr and completed.stdout==b'pinned bootstrap complete\n'

@pytest.mark.parametrize('exit_code',[None,True,1,2,-9])
def test_actual_child_exit_is_mandatory_even_before_parsing(exit_code):
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    with pytest.raises(m.Refused):m.validate_envelope(b'{}\n',exit_code,args)

def test_pinned_report_and_parent_actual_exit_cannot_be_fabricated(scenario,monkeypatch):
    summary,_=inspect(scenario);summary['original_catalog_row_count']=74150
    # Add unselected physical rows in the public count while preserving its
    # closed relationships. This is synthetic output validation only.
    summary['original_distinct_full_row_count']=74150;summary['original_repeated_full_row_count']=0
    monkeypatch.setattr(m,'PURE_MODULE',p)
    result={'schema':m.SCHEMA,'complete':True,'inspection':summary,'private_pin':{'byte_count':100,'sha256':'d'*64},
      'all_four_DATA_authenticated':True,'both_source_guards_normal_return':True,'source_receipt_sha256':'e'*64,**m.FALSE_FLAGS}
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    report={'binding':m.binding(args),'result':result};child={**report,'report_pin':m.pin(m.canonical(report))}
    parent={'binding':m.binding(args),'actual_child_exit':0,'output_authenticated':True,'child_stdout_pin':m.pin(m.canonical(child)+b'\n'),
      'child_stderr_byte_count':0,'outcome':child}
    assert m.validate_parent_output(m.canonical(parent)+b'\n',0,args)['result']==result
    with pytest.raises(m.Refused):m.validate_envelope(m.canonical(child)+b'\n',2,args)
    with pytest.raises(m.Refused):m.validate_parent_output(m.canonical(parent)+b'\n',2,args)
    child['report_pin']['sha256']='0'*64
    with pytest.raises(m.Refused):m.validate_envelope(m.canonical(child)+b'\n',0,args)

def test_finite_failure_packet_never_depends_on_old_price_globals(monkeypatch):
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args));packet=m.failure_packet('source_pin')
    assert m.validate_failure(packet,args)==packet and packet['attempt_reusable'] is False
    assert 'lexical_evidence' not in packet and 'parser_failure_code' not in packet

def test_launch_arms_parent_deadline_before_preflight_or_bootstrap(monkeypatch):
    args=['M','launch','--expected-head','a'*40,'--caller-sha256','b'*64,'--profile-sha256','c'*64]
    monkeypatch.setattr(sys,'argv',args);events=[];handlers=[]
    monkeypatch.setattr(m.signal,'signal',lambda sig,callback:handlers.append(callback))
    monkeypatch.setattr(m.signal,'setitimer',lambda kind,seconds:events.append(('alarm',seconds)))
    monkeypatch.setattr(m,'parent',lambda supplied:events.append(('parent',None)) or 'synthetic')
    assert m.main()=='synthetic' and events[0][0]=='alarm' and events[1][0]=='parent'
    assert 0<events[0][1]<=300
    with pytest.raises(m.Refused) as caught:handlers[0](None,None)
    assert m.finite(caught.value)=='deadline'

@pytest.mark.parametrize('late_failure',[False,True])
def test_worker_claim_precedes_all_DATA_and_both_guards_return_before_publication(monkeypatch,late_failure):
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64,intent_fd=None)
    reader,writer=os.pipe();os.write(writer,m.canonical(m.binding(args)));os.close(writer);args.intent_fd=reader
    events=[];raws={'manifest':b'manifest','marker':b'marker','archive':b'archive','identity':b'{}'}
    for key,raw in raws.items():monkeypatch.setitem(m.DATA_PLAN,key,{'relative_path':'inherited/'+key,**m.pin(raw)})
    monkeypatch.setattr(m,'preflight',lambda *a:events.append('preflight'))
    class Store:
        def __init__(self,security):pass
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def write(self,name,raw):
            if name!='claim.json':assert events.index('original_return')<len(events) and events.index('identity_return')<len(events)
            events.append('write:'+name);return m.pin(raw)
    class Original:
        LEAVES=('manifest','marker','archive')
        def __init__(self,**kwargs):pass
        def __enter__(self):events.append('original_enter');return self
        def __exit__(self,*a):
            events.append('original_return')
            if late_failure:raise m.Refused('changed')
        def read(self,name,deadline):events.append('read:'+name);return raws[name]
        def verify(self):events.append('original_verify')
    class Fixed:
        def __init__(self,*a,**k):pass
        def __enter__(self):events.append('identity_enter');return self
        def __exit__(self,*a):events.append('identity_return')
        def read_all_once(self):events.append('read:identity');return {'identity':raws['identity']}
        def verify(self):pass
        def receipt(self):return {'technical':True}
    pure=NS(demands=lambda *a:events.append('demands'),decode_catalog=lambda *a,**k:events.append('parse_catalog') or [],
      inspect=lambda *a,**k:({'original_catalog_row_count':74150},{'synthetic':True}))
    modules={'security':None,'original_guard':NS(SourceGuard=Original,LEAVES=Original.LEAVES),
      'guard':NS(FixedDataGuard=Fixed),'pure':pure,'anchor':NS(observed_fact=lambda:{'private_data':m.DATA_PLAN['identity'],
        'result':{'identity_summary':{}}})}
    monkeypatch.setattr(m,'bootstrap',lambda *a:modules);monkeypatch.setattr(m,'Store',Store)
    monkeypatch.setattr(m,'validate_result',lambda value:value)
    if late_failure:
        with pytest.raises(m.Refused):m.worker(args,time.monotonic()+30)
        assert 'write:private-diagnosis.json' not in events
    else:
        result=m.worker(args,time.monotonic()+30);assert result['result']['both_source_guards_normal_return']
    assert events.index('write:claim.json')<events.index('original_enter')<events.index('read:manifest')
    assert events.index('read:identity')<events.index('demands')<events.index('parse_catalog')

@pytest.mark.parametrize('kind',['same_FIGI','candidate_union','tuple_minimum','poison','source_row'])
def test_public_predicate_matrices_cannot_contradict_each_other(scenario,kind):
    summary,_=inspect(scenario);scope=summary['cases'][0]['table_scopes'][0]
    if kind=='same_FIGI':scope['link_counts']['original_FIGI']=0
    elif kind=='candidate_union':scope['link_counts']['candidate_permaticker']=0
    elif kind=='tuple_minimum':
        matrix=scope['current_candidate_matrices'][0];matrix['same_permaticker_FIGI_CUSIP_tuple']=1;matrix['same_nonempty_FIGI']=0
    elif kind=='poison':scope['poison_owner_count']=1
    else:scope['predicate_counts']['same_source_row']={'true':0,'false':1}
    refusal('output',lambda:p.validate_summary(summary))

@pytest.mark.parametrize('deadline',[True,None,float('nan'),float('inf'),-float('inf'),0])
def test_pure_budget_refuses_nonfinite_bool_missing_or_spent_deadline(deadline):
    refusal('deadline',lambda:p.budget(deadline))

def test_pure_budget_rejects_undeclared_extended_horizon():
    refusal('deadline',lambda:p.budget(time.monotonic()+301))

def test_complete_CUSIP_consensus_is_exact_not_only_one_way(scenario):
    summary,_=inspect(scenario);scope=summary['cases'][0]['table_scopes'][0]
    assert scope['complete_CUSIP_tuple_consensus']
    scope['complete_CUSIP_tuple_consensus']=False
    refusal('output',lambda:p.validate_summary(summary))

def test_original_stream_serialization_matches_actual_frozen_function_not_envelope_codec():
    source=(m.ROOT/'research/analyst_revisions_v2/canonical.py').read_text();tree=ast.parse(source)
    node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='canonical_json_bytes')
    namespace={'json':json,'Any':object,'CanonicalEvidenceError':ValueError}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'frozen_public_serializer','exec'),namespace)
    for value in (['a'*64,'b'*64],{'name':'café'}):
        expected=namespace['canonical_json_bytes'](value)
        assert p.original_json_bytes(value)==expected and expected.endswith(b'\n')
        assert p.sha(expected)!=p.sha(p.canonical(value))

def test_missing_original_stream_LF_is_a_real_regression(monkeypatch):
    manifest,marker,archive,_=zip_fixture(monkeypatch)
    monkeypatch.setattr(p,'original_json_bytes',p.canonical)
    refusal('row_stream',lambda:p.decode_catalog(manifest,marker,archive,deadline=time.monotonic()+30))
