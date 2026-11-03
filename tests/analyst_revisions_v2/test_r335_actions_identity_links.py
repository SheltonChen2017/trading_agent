"""Synthetic retained-byte action metadata links; no actual DATA/network/USB/QC."""
import ast
import copy
from contextlib import ExitStack
import csv
from datetime import date,timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import pytest
from scripts import inspect_arv2_r335_actions_identity_links as m
from scripts import arv2_r335_sharadar_actions_v2 as observer


def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, profile_sha256='c' * 64)


def refuse(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


class Security:
    @staticmethod
    def snapshot(fd): return {'acl_empty': True, 'xattrs': {}}


def fixture_control(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    lane = artifacts / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', lane / 'firstrate/R335-A')
    return lane


def test_symlink_output_ancestor_refuses_before_any_own_claim(tmp_path, monkeypatch):
    lane = fixture_control(tmp_path, monkeypatch)
    other = tmp_path / 'other'; other.mkdir()
    (lane / 'firstrate').symlink_to(other, target_is_directory=True)
    with pytest.raises((OSError, m.Refused)): m.Store(Security).__enter__()
    assert not (other / 'R335-A').exists()


def test_late_output_mutation_is_refused_and_evidence_retained(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'claim.json').write_bytes(b'changed')
            store.verify()
    assert (m.CONTROL / 'claim.json').read_bytes() == b'changed'


def test_unexpected_owned_control_leaf_is_not_absorbed_by_later_own_write(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'unexpected').write_bytes(b'synthetic')
            refuse('control', lambda: store.write('report.json', b'{}'))
    assert (m.CONTROL / 'unexpected').read_bytes() == b'synthetic'
    assert not (m.CONTROL / 'report.json').exists()


def test_cli_unknown_argument_never_echoes_supplied_value():
    result = subprocess.run([sys.executable, '-I', '-B', str(m.SOURCE), 'launch', '--SYNTHETIC-SECRET-ARG'],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 2 and not result.stderr
    assert b'SYNTHETIC-SECRET' not in result.stdout
    assert json.loads(result.stdout)['failure_code'] == 'arguments'


def test_dynamic_output_security_mismatch_is_not_ignored(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    class Changing(Security):
        changed=False
        @staticmethod
        def snapshot(fd):return {'synthetic_security_state':Changing.changed}
    with pytest.raises(m.Refused):
        with m.Store(Changing) as store:
            store.write('claim.json',b'{}');Changing.changed=True;store.verify()


def test_original_held_named_file_rejects_byte_pin_symlink_and_late_replacement(tmp_path):
    source = tmp_path / 'source'; source.write_bytes(b'synthetic')
    deadline = time.monotonic() + 299
    with m.HeldFile(source, maximum=100, expected=m.pin(b'synthetic'), deadline=deadline) as held:
        assert held.read() == b'synthetic'
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, expected=m.pin(b'other'), deadline=deadline) as held: held.read()
    link = tmp_path / 'link'; link.symlink_to(source)
    with pytest.raises(OSError):
        with m.HeldFile(link, maximum=100, deadline=deadline): pass
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, deadline=deadline) as held:
            source.write_bytes(b'changed!'); held.verify()


@pytest.mark.parametrize('field,value', [('expected_head', 'a' * 39), ('expected_head', True),
    ('caller_sha256', 'x' * 64), ('profile_sha256', None), ('caller_sha256', 'b' * 65)])
def test_arguments_refuse_malformed_bindings(field, value):
    value_args = args(); setattr(value_args, field, value)
    refuse('arguments', lambda: m.binding(value_args))


def test_binding_accepts_exact_source_run_pins_only():
    assert m.binding(args()) == {'schema': m.SCHEMA, 'expected_head': 'a' * 40,
        'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64}


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'not-json', b''])
def test_json_refuses_duplicates_constants_and_malformed(raw):
    with pytest.raises(m.Refused): m.parse(raw, 100)


def csv_bytes(rows):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(observer.FIELDS)
    for row in rows:writer.writerow([row[key] for key in observer.FIELDS])
    return stream.getvalue().encode()


@pytest.fixture
def scenario(monkeypatch):
    cases=[];wholes=[]
    for ordinal,(count,first) in enumerate(m.GEOMETRY):
        original={'ticker':'S'+str(ordinal),'relatedtickers':'DO NOT PARSE','name':'Synthetic café'}
        original.update({'field'+str(index):'' for index in range(28-len(original))})
        raw=(json.dumps(original,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
        binding={'diagnostic_current_ticker':'S'+str(ordinal),'source_row_sha256':m.sha(raw)}
        whole=m.sha(m.canonical(binding));wholes.append(whole)
        current={key:'' for key in m.META_FIELDS};current['ticker']='C'+str(ordinal) if ordinal<4 else 'S4'
        source_leads=[('binding.diagnostic_current_ticker',None,binding['diagnostic_current_ticker']),('original_row.ticker',None,original['ticker']),
            ('current_candidate_rows.ticker',0,current['ticker'])]
        leads=[{'field_origin':origin,'current_row_ordinal':index,'token':token,'token_supported':True,
            'listing_matches':[],'metadata_only_not_identity_or_price_coverage':True} for origin,index,token in source_leads]
        required=[(date.fromisoformat(first)+timedelta(days=index)).isoformat() for index in range(count-1)]+[m.LAST]
        cases.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'binding':binding,'original_row':original,
            'current_candidate_rows':[current],'metadata_leads':leads,'optional_relatedtickers_raw':original['relatedtickers'],
            'relatedtickers_parse_state':'retained_unparsed','required_sessions':required,'potential_reference_sessions':[],
            'candidates':[{'candidate_ordinal':0,'gap_geometry':{'missing_required_sessions':required[:3]}}],
            'no_candidate_gap':{'missing_required_sessions':[]},'source_assignment_changed':False,'original_metadata_hash_rechecked':True})
    monkeypatch.setattr(m,'EXPECTED_WHOLES',tuple(wholes))
    metadata={'schema':m.F_SCHEMA,'input_DATA_pins':{'identity':{'relative_path':'inherited-only',**m.I_DATA_PIN}},
        'retained_E_observation':{},'cases':cases,**m.F_FLAGS}
    rows=[{'date':'2024-01-02','action':'split','ticker':'S0','name':'Synthetic issuer','value':'1',
        'contraticker':'AA, BB' if index<9 else 'COUNTER','contraname':'Synthetic counterparty'} for index in range(33)]
    def values():
        projected=m.derive_plan(metadata,observer)
        original={**projected,'schema':'arv2-r335-sharadar-actions-v1-plan'}
        monkeypatch.setitem(m.DATA_PLAN,'plan',{'relative_path':m.DATA_PLAN['plan']['relative_path'],**m.pin(m.canonical(original))})
        body=csv_bytes(rows)
        transport={'schema':'arv2-r335-sharadar-actions-v1-private-transport','plan_sha256':m.sha(m.canonical(original)),
            'request_ordinal':0,'role':'ticker_union','query_token':','.join(original['explicit_tokens']),
            'http_status':200,'body_pin':m.pin(body),'CSV_validation_complete':False}
        return metadata,original,body,transport
    return NS(metadata=metadata,rows=rows,values=values)


def result_value(scenario):
    public,private=m.inspect_links(*scenario.values(),observer)
    return {'schema':m.SCHEMA,'complete':True,'inspection':public,'private_pin':m.pin(m.canonical(private)),
        'all_four_DATA_authenticated':True,'source_guard_normal_return':True,'source_receipt_sha256':'a'*64,
        'retained_H_observation_sha256':m.sha(m.canonical(m.H_OBSERVATION)),**m.FALSE_FLAGS},private


def test_retained_subset_v2_parse_preserves_all_rows_opaque_text_and_original_failure(scenario):
    result,private=result_value(scenario);public=result['inspection']
    assert m.validate_result(result)==result and public['source_row_count']==33
    assert len(private['all_original_rows'])==33 and public['parse_counts']['repeated_primary_key_row_count']==31
    assert public['opaque_nonempty_contraticker_source_row_count']==9
    assert public['literal_counterparty_metadata_lead_source_row_count']==24
    assert public['admitted_alias_count']==public['ticker_change_search_lead_count']==0
    assert private['all_original_rows'][0]['opaque_contraticker_verbatim']=='AA, BB'
    assert private['all_original_rows'][0]['literal_counterparty_metadata_lead'] is None
    assert private['all_original_rows'][9]['literal_counterparty_metadata_lead']=='COUNTER'
    assert all(event['alias_admitted'] is event['same_security_or_share_class_proven'] is False for event in private['all_original_rows'])
    assert public['current_vintage_subset_only'] is True and public['complete_ACTIONS_history_proven'] is False
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert not any(token in m.canonical(public) for token in (b'S0',b'COUNTER',b'AA, BB',b'2024-01-02',b'Synthetic issuer'))


def test_schema_projection_changes_no_tokens_source_pins_lineage_or_transport(scenario):
    result,private=result_value(scenario)
    original,projected=private['original_G_plan'],private['projected_v2_plan']
    assert original['schema'].endswith('v1-plan') and projected['schema'].endswith('v2-plan')
    assert {key:value for key,value in original.items() if key!='schema'}=={key:value for key,value in projected.items() if key!='schema'}
    assert private['original_G_transport']['plan_sha256']==m.sha(m.canonical(original))
    assert result['v2_producer_invoked'] is result['G_request_plan_completed'] is result['remaining_G_query_authority_granted'] is False


def test_all_shared_primary_token_owners_are_retained_and_links_are_not_distinct_rows(scenario):
    target=scenario.metadata['cases'][1];target['current_candidate_rows'][0]['ticker']='S0'
    target['metadata_leads'][2]['token']='S0'
    extra={key:'' for key in m.META_FIELDS};extra['ticker']='EXTRA'
    target['current_candidate_rows'].append(extra)
    target['metadata_leads'].append({'field_origin':'current_candidate_rows.ticker','current_row_ordinal':1,'token':'EXTRA',
        'token_supported':True,'listing_matches':[],'metadata_only_not_identity_or_price_coverage':True})
    result,private=result_value(scenario);public=result['inspection']
    assert public['distinct_matched_source_row_count']==33 and public['case_event_link_count']==66
    assert public['shared_primary_ticker_source_row_count']==33 and public['shared_primary_ticker_event_link_count']==66
    assert [case['event_link_count'] for case in public['cases']]==[33,33,0,0,0]
    assert all(event['primary_owner_case_ordinals']==[0,1] for event in private['all_original_rows'])


def test_known_family_map_is_minimal_unknowns_and_counterparty_metadata_do_not_become_aliases(scenario):
    scenario.rows[9]['action']='tickerchangefrom'
    scenario.rows[10]['action']='acquisitioncash'
    result,private=result_value(scenario);public=result['inspection']
    assert m.DOCUMENTED_TICKER_CHANGE_CODES==()
    assert public['source_action_family_counts']['unknown']==1
    assert public['source_action_family_counts']['acquisition_consideration']==1
    assert private['all_original_rows'][9]['row']['action']=='tickerchangefrom'
    assert private['all_original_rows'][9]['literal_counterparty_metadata_lead']=='COUNTER'
    assert all(event['ticker_change_search_lead'] is None for event in private['all_original_rows'])
    assert result['synthetic_cash_created'] is result['corporate_action_semantics_applied'] is False


def test_same_primary_key_conflicting_values_survive_without_overwrite(scenario):
    scenario.rows[1]['value']='2'
    result,private=result_value(scenario)
    assert result['inspection']['parse_counts']['conflicting_value_primary_key_count']==1
    assert [event['row']['value'] for event in private['all_original_rows'][:2]]==['1','2']
    assert len(private['all_original_rows'])==33


def test_interval_and_gap_links_do_not_repair_prices_or_apply_actions(scenario):
    first=m.GEOMETRY[0][1]
    for row in scenario.rows:row['date']=first
    result,private=result_value(scenario);case=result['inspection']['cases'][0]
    assert case['required_window_relation_link_counts']['at_first_required']==33
    assert case['candidate_missing_interval_link_counts']['at_missing_interval_first']==33
    assert case['event_on_recorded_missing_date_link_count']==33
    assert result['price_input_admitted'] is result['source_assignment_changed'] is False
    assert private['cases'][0]['event_links'][0]['candidate_gap_links'][0]['event_on_recorded_missing_date'] is True


@pytest.mark.parametrize('change',['schema','tokens','lineage','source_pin','query','status_bool','body_pin','ordinal_bool'])
def test_source_plan_projection_and_original_transport_mismatches_refuse(scenario,change):
    metadata,original,body,transport=scenario.values()
    if change=='schema':original['schema']='other'
    elif change=='tokens':original['explicit_tokens'][0]='OTHER'
    elif change=='lineage':original['binding_lineage_sha256']='0'*64
    elif change=='source_pin':original['F_DATA_pin']['sha256']='0'*64
    elif change=='query':transport['query_token']='OTHER'
    elif change=='status_bool':transport['http_status']=True
    elif change=='body_pin':transport['body_pin']['sha256']='0'*64
    else:transport['request_ordinal']=False
    with pytest.raises((m.Refused,observer.Refused)):m.inspect_links(metadata,original,body,transport,observer)


@pytest.mark.parametrize('change',['id','bool_count','alias','search','family_sum','family_relation','shared_relation','scope_complete','row_count','extra'])
def test_public_counts_cannot_disclose_ids_forge_relationships_or_admit_aliases(scenario,change):
    value,_=result_value(scenario);public=value['inspection']
    if change=='id':public['ticker']='SECRET'
    elif change=='bool_count':public['cases'][0]['event_link_count']=True
    elif change=='alias':public['admitted_alias_count']=1
    elif change=='search':public['ticker_change_search_lead_count']=1
    elif change=='family_sum':public['source_action_family_counts']['split']-=1
    elif change=='family_relation':public['cases'][0]['action_family_link_counts'].update(split=0,unknown=33)
    elif change=='shared_relation':public['shared_primary_ticker_source_row_count']=1
    elif change=='scope_complete':public['complete_ACTIONS_history_proven']=True
    elif change=='row_count':public['parse_counts']['primary_key_count']=0
    else:public['event_date']='2024-01-02'
    refuse('output',lambda:m.validate_result(value))


def test_actual_exit_and_report_pin_remain_mandatory(scenario):
    value,_=result_value(scenario);report={'binding':m.binding(args()),'result':value}
    packet={**report,'report_pin':m.pin(m.canonical(report))};raw=m.canonical(packet)+b'\n'
    assert m.validate_envelope(raw,0,args())==packet
    for actual in (2,None,True,-9):refuse('child_failure',lambda:m.validate_envelope(raw,actual,args()))
    packet['report_pin']['sha256']='0'*64
    refuse('output',lambda:m.validate_envelope(m.canonical(packet)+b'\n',0,args()))


def test_exact_four_DATA_policy_no_H_DATA_controls_provider_or_original_producer_execution():
    assert all(m.sha((m.ROOT/name).read_bytes())==pin for name,pin in m.SOURCE_PINS.items())
    assert set(m.DATA_PLAN)=={'metadata','plan','body','transport'}
    policy=m.native_profile();profile=m.profile_record()
    assert '(deny network*)' in policy and '/Library/Keychains' in policy and '(subpath "/Volumes")' in policy
    assert 'R335-20261103-H' not in policy and 'R335-20261103-G/claim.json' not in policy and 'R335-20261103-G/report.json' not in policy
    assert all(item['relative_path'] in policy for item in m.DATA_PLAN.values())
    assert profile['documented_ticker_change_codes']==[] and len(profile['known_action_families'])==9
    tree=ast.parse(m.SOURCE.read_bytes());attrs={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not attrs&{'observe','load_key','Session','history','market_order','set_holdings'}


def test_native_worker_claims_before_exact_four_DATA_and_closes_before_output(scenario,tmp_path,monkeypatch):
    metadata,original,body,transport=scenario.values()
    raw={'metadata':m.canonical(metadata),'plan':m.canonical(original),'body':body,'transport':m.canonical(transport)}
    # Synthetic frame lengths are source-fixture bounds, not production pins.
    for role in ('plan','transport'):monkeypatch.setitem(m.DATA_PLAN,role,{'relative_path':m.DATA_PLAN[role]['relative_path'],**m.pin(raw[role])})
    events=[];inside=False
    class Guard:
        def __init__(self,plan,**kwargs):assert plan==m.DATA_PLAN
        def __enter__(self):
            nonlocal inside
            assert events==[('write','claim.json')];inside=True;events.append(('enter',None));return self
        def read_all_once(self):events.append(('read',tuple(raw)));return raw
        def verify(self):events.append(('verify',None))
        def receipt(self):return {'synthetic':True}
        def __exit__(self,*args):
            nonlocal inside
            inside=False;events.append(('normal_return',None))
    class Store:
        def __init__(self,security):assert security is Security
        def __enter__(self):return self
        def write(self,name,value):
            assert not inside;events.append(('write',name));return m.pin(value)
        def __exit__(self,*args):pass
    monkeypatch.setattr(m,'preflight',lambda *args:None)
    monkeypatch.setattr(m,'bootstrap',lambda *args:{'security':Security,'guard':NS(FixedDataGuard=Guard),'observer':observer})
    monkeypatch.setattr(m,'Store',Store)
    chosen=args();read,write=os.pipe();chosen.intent_fd=read
    os.write(write,m.canonical(m.binding(chosen)));os.close(write)
    packet=m.worker(chosen,time.monotonic()+299)
    assert m.validate_result(packet['result'])==packet['result']
    assert [value for event,value in events if event=='read']==[('metadata','plan','body','transport')]
    assert events.index(('normal_return',None))<events.index(('write','private-diagnosis.json'))
    assert packet['result']['v2_producer_invoked'] is False


def test_source_held_v2_bootstrap_does_not_execute_old_callers_or_H_DATA():
    root=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
    code="""from scripts import inspect_arv2_r335_actions_identity_links as m
from contextlib import ExitStack
import time,sys
with ExitStack() as held:
 modules=m.bootstrap('validate',held,time.monotonic()+299)
 assert set(modules)=={'security','observer'}
 assert modules['observer'].SCHEMA=='arv2-r335-sharadar-actions-v2'
 assert modules['observer'].__spec__.loader is None
 assert 'scripts.run_arv2_r335_sharadar_actions' not in sys.modules
 assert 'scripts.inspect_arv2_r335_sharadar_scope' not in sys.modules
 assert 'scripts.arv2_keychain_connections' not in sys.modules
"""
    result=subprocess.run([sys.executable,'-I','-B','-c',"import sys;sys.path.insert(0,"+repr(str(root))+");"+code],
        cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0 and not result.stdout and not result.stderr


def test_F_lineage_derivation_is_byte_semantic_clone_of_used_G_pure_helper():
    path=m.ROOT/'scripts/run_arv2_r335_sharadar_actions.py'
    raw=path.read_bytes();assert m.sha(raw)=='2d23cfef4e3fb3fb890ef5f8868457de8c4bb402672fa08f6dcc618b57525df4'
    old,new=ast.parse(raw),ast.parse(m.SOURCE.read_bytes())
    get=lambda tree,name:next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
    assert ast.dump(get(old,'derive_plan'),include_attributes=False)==ast.dump(get(new,'derive_plan'),include_attributes=False)
    frozen=(m.ROOT/'scripts/inspect_arv2_r335_sharadar_scope.py').read_bytes()
    assert m.sha(frozen)=='6b989a7de0241074c9dd8582d30683324ef04b7c294a6ce6d3ae325706b5326a'
    baseline=ast.parse(frozen)
    for name in ('HeldFile','Store','preflight','parent','validate_envelope','validate_parent_output','main'):
        assert ast.dump(get(baseline,name),include_attributes=False)==ast.dump(get(new,name),include_attributes=False)


@pytest.mark.parametrize('change',['conflict_without_duplicate','counterparty_without_owner_links'])
def test_public_conflict_and_literal_lead_counts_require_possible_source_relations(scenario,change):
    value,_=result_value(scenario);public=value['inspection']
    if change=='conflict_without_duplicate':
        public['parse_counts'].update(primary_key_count=33,repeated_primary_key_row_count=0,conflicting_value_primary_key_count=1)
    else:
        for case in public['cases']:case['literal_counterparty_metadata_lead_link_count']=0
    refuse('output',lambda:m.validate_result(value))


def test_self_consistent_retained_plan_cannot_replace_F_binding_lineage(scenario,monkeypatch):
    metadata,original,body,transport=scenario.values()
    original['binding_lineage_sha256']='0'*64
    transport['plan_sha256']=m.sha(m.canonical(original))
    monkeypatch.setitem(m.DATA_PLAN,'plan',{'relative_path':m.DATA_PLAN['plan']['relative_path'],**m.pin(m.canonical(original))})
    refuse('plan',lambda:m.inspect_links(metadata,original,body,transport,observer))
