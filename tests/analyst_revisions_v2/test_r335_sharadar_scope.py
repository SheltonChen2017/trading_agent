"""Synthetic H row-scope diagnosis; network/DATA/USB/Keychains denied."""
import ast
import copy
from contextlib import ExitStack
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import pytest
from scripts import inspect_arv2_r335_sharadar_scope as m
from scripts import arv2_r335_sharadar_actions as observer


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


def plan():
    return {'schema':observer.PLAN_SCHEMA,'F_DATA_pin':dict(observer.F_DATA_PIN),'I_DATA_pin':dict(observer.I_DATA_PIN),
        'explicit_tokens':['S'+str(index) for index in range(9)],'binding_lineage_sha256':'a'*64}


def row(**changes):
    value={'date':'2024-01-02','action':'synthetic_action','ticker':'S0','name':'Synthetic issuer',
        'value':'1','contraticker':'','contraname':''};value.update(changes);return value


def csv_bytes(rows,fields=observer.FIELDS):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(fields)
    for value in rows:writer.writerow([value[key] for key in fields] if type(value) is dict else value)
    return stream.getvalue().encode('utf8')


def transport(raw,selected=None):
    selected=plan() if selected is None else selected
    return {'schema':observer.SCHEMA+'-private-transport','plan_sha256':m.sha(m.canonical(selected)),
        'request_ordinal':0,'role':'ticker_union','query_token':','.join(selected['explicit_tokens']),
        'http_status':200,'body_pin':m.pin(raw),'CSV_validation_complete':False}


def inspect(rows):
    raw=csv_bytes(rows);return m.inspect_rows(raw,plan(),transport(raw),observer)


def result_value():
    inspection,private=inspect([row(name='')])
    return {'schema':m.SCHEMA,'complete':True,'inspection':inspection,'private_pin':m.pin(m.canonical(private)),
        'retained_G_failure_sha256':m.sha(m.canonical(m.G_OBSERVATION)),
        'all_three_DATA_authenticated':True,'source_guard_normal_return':True,'source_receipt_sha256':'a'*64,**m.FALSE_FLAGS}


def test_exact_selected_source_and_only_three_G_DATA_leaves():
    assert all(m.sha((m.ROOT/name).read_bytes())==pin for name,pin in m.SOURCE_PINS.items())
    assert set(m.DATA_PLAN)=={'plan','body','transport'}
    assert sorted(item['byte_count'] for item in m.DATA_PLAN.values())==[400,443,2388]
    policy=m.native_profile();profile=m.profile_record()
    assert '(deny network*)' in policy and '(subpath "/Volumes")' in policy
    assert '/Library/Keychains' in policy and '/usr/bin/security' in policy and '[.]pyc$' in policy
    assert all(name in policy for name in ('plan-private.json','response-00.csv','transport-00.json'))
    assert 'R335-20261103-G/claim.json' not in policy and 'R335-20261103-G/report.json' not in policy
    assert 'R335-20261103-F/private-diagnosis.json' not in policy and 'identity-demand-private.json' not in policy
    assert profile['retained_G_failure_observation']['actual_parent_exit']==2
    assert profile['retained_G_failure_observation']['accepted'] is False
    assert all(profile[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('change,predicate',[({'ticker':'bad/token'},'ticker_grammar'),({'contraticker':'bad/token'},'contraticker_grammar'),
    ({'ticker':'OTHER'},'request_role_filter'),({'action':''},'action_nonempty'),({'action':'café'},'action_ascii'),
    ({'action':'a'*129},'action_length_bounded'),({'name':''},'name_nonempty')])
def test_every_frozen_scope_subpredicate_is_counted_and_reproduced_independently(change,predicate):
    public,private=inspect([row(**change)])
    assert public['first_unsupported_code']==public['frozen_parser_failure_code']=='row_scope'
    assert predicate in public['first_failed_scope_predicates']
    assert public['predicate_counts'][predicate]['fail_count']==1
    assert public['predicate_counts']['frozen_row_scope_conjunction']['fail_count']==1
    assert public['private_parsed_rows_retained'] is True and private['parsed_rows']==[row(**change)]
    assert public['scope_or_grammar_admitted'] is False and all(private[key] is False for key in m.FALSE_FLAGS)
    assert not any(key in m.canonical(public) for key in (b'SYN0',b'OTHER',b'Synthetic issuer',b'2024-01-02',b'cafe'))


def test_multiple_first_scope_failures_are_observations_not_a_unique_cause():
    public,_=inspect([row(action='',name='',contraticker='bad/token')])
    assert public['first_failed_scope_predicates']==['contraticker_grammar','action_nonempty','name_nonempty']
    assert public['first_unsupported_code']=='row_scope'


def test_later_all_row_counts_do_not_claim_original_G_reached_later_failures():
    public,private=inspect([row(name=''),row(date='2024-99-99',value='NaN'),row(date='2024-01-03',value='not-number')])
    assert public['frozen_parser_failure_code']=='row_scope' and public['record_count']==3
    assert public['predicate_counts']['name_nonempty']['fail_count']==1
    assert public['predicate_counts']['date_canonical']['fail_count']==1
    assert public['predicate_counts']['date_nondecreasing']['unexamined_count']==2
    assert public['value_class_counts']['nonfinite']==public['value_class_counts']['unparseable']==1
    assert public['original_G_processed_all_rows_proven'] is False
    assert len(private['parsed_rows'])==3


@pytest.mark.parametrize('changes,code,predicate', [({'name':' padded '},'csv','field_trim'),
    ({'name':'line\nfeed'},'csv','field_control_free'),({'name':'x'*2049},'csv','field_length_bounded'),
    ({'date':'2024-99-99'},'row_date','date_canonical'),({'date':'2020-01-02'},'row_date','date_in_window'),
    ({'value':'NaN'},'row_value','value_rule'),({'value':'1_000'},'row_value','value_rule')])
def test_shape_date_and_value_predicates_remain_separate_from_scope(changes,code,predicate):
    public,_=inspect([row(**changes)])
    assert public['first_unsupported_code']==public['frozen_parser_failure_code']==code
    assert public['predicate_counts'][predicate]['fail_count']==1
    assert public['first_failed_scope_predicates']==[]


def test_date_order_and_empty_finite_signed_value_classes():
    public,_=inspect([row(date='2024-01-03',value=''),row(date='2024-01-02',value='-1E2')])
    assert public['first_unsupported_code']=='row_date'
    assert public['predicate_counts']['date_nondecreasing']['fail_count']==1
    assert public['value_class_counts']['empty']==1 and public['value_class_counts']['finite_supported']==1


def test_unambiguous_width_is_required_before_any_private_parsed_rows_are_retained():
    malformed=['2024-01-02','action','S0']
    public,private=inspect([malformed,row()])
    assert public['all_CSV_records_unambiguous'] is False
    assert public['private_parsed_rows_retained'] is False and private['parsed_rows'] is None
    assert public['predicate_counts']['seven_fields']['fail_count']==1
    assert public['predicate_counts']['ticker_grammar']['unexamined_count']==1
    assert public['value_class_counts']['unexamined']==1
    assert public['frozen_parser_failure_code']=='csv'


@pytest.mark.parametrize('change',['role','ordinal_bool','status_bool','status','query','plan_pin','body_pin','complete','extra'])
def test_transport_and_plan_are_exactly_bound_without_replaying_G(change):
    raw=csv_bytes([row(name='')]);metadata=transport(raw)
    if change=='role':metadata['role']='contraticker_single'
    elif change=='ordinal_bool':metadata['request_ordinal']=False
    elif change=='status_bool':metadata['http_status']=True
    elif change=='status':metadata['http_status']=403
    elif change=='query':metadata['query_token']='OTHER'
    elif change=='plan_pin':metadata['plan_sha256']='0'*64
    elif change=='body_pin':metadata['body_pin']['sha256']='0'*64
    elif change=='complete':metadata['CSV_validation_complete']=True
    else:metadata['api_key']='SECRET'
    refuse('transport',lambda:m.inspect_rows(raw,plan(),metadata,observer))


@pytest.mark.parametrize('change',['bool_count','extra','scope_label','scope_conjunction','value_class','private_flag','G_accepted','guard','parser_code','date_index'])
def test_closed_public_diagnosis_cannot_forge_counts_causes_or_admission(change):
    value=result_value();public=value['inspection']
    if change=='bool_count':public['predicate_counts']['name_nonempty']['fail_count']=True
    elif change=='extra':public['raw_row']='SECRET'
    elif change=='scope_label':public['first_failed_scope_predicates']=['ticker_grammar']
    elif change=='scope_conjunction':public['predicate_counts']['frozen_row_scope_conjunction'].update(pass_count=1,fail_count=0)
    elif change=='value_class':public['value_class_counts'].update(nonfinite=1,finite_supported=0)
    elif change=='private_flag':public['private_parsed_rows_retained']=1
    elif change=='G_accepted':value['G_attempt_accepted']=True
    elif change=='guard':value['source_guard_normal_return']=False
    elif change=='parser_code':public['frozen_parser_failure_code']='row_value'
    else:public['first_failure_date_index']=0
    refuse('output',lambda:m.validate_result(value))


def test_actual_parent_exit_and_external_report_pin_required_even_for_diagnostic_result():
    value=result_value();report={'binding':m.binding(args()),'result':value}
    packet={**report,'report_pin':m.pin(m.canonical(report))};raw=m.canonical(packet)+b'\n'
    assert m.validate_envelope(raw,0,args())==packet
    for actual in (2,None,True,-9):refuse('child_failure',lambda:m.validate_envelope(raw,actual,args()))
    packet['report_pin']['sha256']='0'*64
    refuse('output',lambda:m.validate_envelope(m.canonical(packet)+b'\n',0,args()))


def test_worker_claims_before_exact_three_DATA_reads_and_waits_for_normal_guard_return(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch);raw_body=csv_bytes([row(name='')]);selected=plan();meta=transport(raw_body)
    raw={'plan':m.canonical(selected),'body':raw_body,'transport':m.canonical(meta)};events=[];inside=False
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
    assert [value for event,value in events if event=='read']==[('plan','body','transport')]
    assert events.index(('normal_return',None))<events.index(('write','private-diagnosis.json'))
    assert packet['result']['G_attempt_accepted'] is False


def test_fresh_bootstrap_never_executes_spent_G_caller_or_keychain_module():
    root=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
    code="""from scripts import inspect_arv2_r335_sharadar_scope as m
from contextlib import ExitStack
import time,sys
with ExitStack() as sources:
 modules=m.bootstrap('validate',sources,time.monotonic()+299)
 assert set(modules)=={'security','observer'}
 assert modules['observer'].__spec__.loader is None
 assert 'scripts.run_arv2_r335_sharadar_actions' not in sys.modules
 assert 'scripts.arv2_keychain_connections' not in sys.modules
"""
    result=subprocess.run([sys.executable,'-I','-B','-c',"import sys;sys.path.insert(0,"+repr(str(root))+");"+code],
        cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0 and not result.stdout and not result.stderr


@pytest.mark.parametrize('change',['profile','head','caller'])
def test_current_preflight_rejects_bad_profile_head_or_caller_before_DATA_or_imports(monkeypatch,change):
    original_flags=sys.flags
    class Flags:
        isolated=1
        def __getattr__(self,name):return getattr(original_flags,name)
    monkeypatch.setattr(sys,'flags',Flags())
    selected=args();selected.caller_sha256=m.sha(m.SOURCE.read_bytes())
    selected.profile_sha256=m.sha(m.canonical(m.profile_record()))
    if change=='profile':selected.profile_sha256='0'*64
    if change=='caller':selected.caller_sha256='0'*64
    calls=[]
    def git(command,**kwargs):
        calls.append(command)
        assert command[0]=='/usr/bin/git'
        if command[1:]==['rev-parse','--show-toplevel']:raw=str(m.ROOT).encode()+b'\n'
        elif command[1:]==['branch','--show-current']:raw=m.BRANCH.encode()+b'\n'
        elif command[1:]==['rev-parse','HEAD']:raw=(('b'*40) if change=='head' else selected.expected_head).encode()+b'\n'
        elif command[1:]==['status','--porcelain']:raw=b''
        elif command[1]=='cat-file':raw=m.SOURCE.read_bytes()
        else:raise AssertionError('unexpected synthetic git command')
        return NS(returncode=0,stderr=b'',stdout=raw)
    monkeypatch.setattr(m.subprocess,'run',git)
    refuse('git_state' if change=='head' else 'source_pin',lambda:m.preflight(selected,time.monotonic()+299))
    if change=='profile':assert calls==[]


def test_selected_source_byte_mismatch_refuses_before_any_repo_module_execution(tmp_path,monkeypatch):
    root=tmp_path/'root';(root/'scripts').mkdir(parents=True)
    (root/'scripts'/'synthetic.py').write_bytes(b'raise RuntimeError("must not execute")\n')
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'SOURCE_PINS',{'scripts/synthetic.py':'0'*64})
    with ExitStack() as sources:
        refuse('source_pin',lambda:m.bootstrap('validate',sources,time.monotonic()+299))


def test_validate_mode_requires_host_and_source_preflight_before_stdin(monkeypatch):
    calls=[]
    chosen=args();argv=[str(m.SOURCE),'validate','--expected-head',chosen.expected_head,'--caller-sha256',chosen.caller_sha256,
        '--profile-sha256',chosen.profile_sha256,'--actual-parent-exit','2']
    monkeypatch.setattr(sys,'argv',argv)
    def preflight(*args):calls.append('preflight');raise m.Refused('source_pin')
    monkeypatch.setattr(m,'preflight',preflight)
    monkeypatch.setattr(m.signal,'signal',lambda *args:None);monkeypatch.setattr(m.signal,'setitimer',lambda *args:None)
    class Forbidden:
        def read(self,*args):raise AssertionError('stdin before preflight')
    monkeypatch.setattr(sys,'stdin',NS(buffer=Forbidden()))
    refuse('source_pin',m.main)
    assert calls==['preflight']


def test_frozen_storage_and_parent_actual_exit_protocols_remain_unchanged():
    old_path=m.ROOT/'scripts/inspect_arv2_r335_firstrate_gap_metadata.py'
    old=old_path.read_bytes();assert m.sha(old)=='fd41a4d434503edc15d71d25775b520e98728a0e0d2e455c5bc03c69dabbbfa0'
    a,b=ast.parse(old),ast.parse(m.SOURCE.read_bytes())
    for name in ('HeldFile','Store','preflight','parent','validate_envelope','validate_parent_output','binding','safe_env'):
        get=lambda tree:next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
        assert ast.dump(get(a),include_attributes=False)==ast.dump(get(b),include_attributes=False)


def test_exact_frozen_parser_refusal_must_match_independent_first_failure(monkeypatch):
    raw=csv_bytes([row(name='')])
    monkeypatch.setattr(observer,'parse_response',lambda *args,**kwargs:([],{}))
    refuse('parser_reproduction',lambda:m.inspect_rows(raw,plan(),transport(raw),observer))
