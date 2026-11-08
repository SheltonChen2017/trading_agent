"""Synthetic child-project custody; no account, private packet or native I/O."""
import ast
from copy import deepcopy
import hashlib
import json
from datetime import datetime,time,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import comparison_20261029_project_probe as p
from research.target_price_revisions_qc import comparison_20261029_projects as registry

PROJECT=49010001

def sha(raw):return hashlib.sha256(raw).hexdigest()

@pytest.fixture
def source():
    return {n:Path(n).read_bytes() for n in {p.PRIOR_MODULE,p.REGISTRY_MODULE}|{p.PREFIX+n for n in p.SOURCE_ARGUMENTS.values()}}

@pytest.fixture
def bindings():
    return {'schema':'tpr-cmp28-five-project-bindings-v1','round_id':registry.ROUND_ID,
        'owner_instruction_sha256':'b'*64,'git_head':'a'*40,
        'adapter_source_sha256':sha(Path(registry.MODULE).read_bytes()),
        'organization_id':'d'*32,'owner_id':12345,'baseline_receipt_sha256':'e'*64,
        'privacy_basis':registry.PRIVACY_BASIS,'explicit_privacy_flag_observed':False,
        'independent_native_origin_attested':False,
        'projects':{arm:{'project_id':PROJECT+i,'name':registry.RESERVED_NAMES[arm],
            'organization_id':'d'*32,'owner_id':12345,'language':'Py',
            'create_receipt_sha256':sha((arm+'create').encode()),
            'read_receipt_sha256':sha((arm+'read').encode()),
            'collaboration_receipt_sha256':sha((arm+'collaborators').encode()),
            'collaborator_count':0,'nonowner_collaborator_count':0,'collaborators_sha256':sha(b'[]')}
            for i,arm in enumerate(registry.ARMS)}}

def build(source,bindings,**kw):
    raw=registry._canonical(bindings)
    return p.build_project_probe(public_sources=source,project_bindings_raw=raw,
        expected_project_bindings_sha256=sha(raw),
        operation_id='TPR-CMP28-MARK-PROBE-ISOLATED-SYNTHETIC-009',git_head='a'*40,**kw)

def literal(raw,name):
    nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.Assign) and len(n.targets)==1
           and isinstance(n.targets[0],ast.Name) and n.targets[0].id==name]
    assert len(nodes)==1
    return ast.literal_eval(nodes[0].value)

def methods(raw):
    main=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='Main')
    return {n.name:n for n in main.body if isinstance(n,ast.FunctionDef)}

def test_only_child_checks_rebound_parent_key_and_evidence_stay_old(source,bindings):
    raw,report_raw=build(source,bindings);report=json.loads(report_raw)
    cfg=json.loads(literal(raw,'PROBE_CONFIG_JSON'))
    assert report['child_project_id']==cfg['child_project_id']==PROJECT
    assert cfg['binding']['project_id']==37650980
    assert '/37650980/12dd4732ba5d9d8f57950beb2a371c79/' in cfg['binding']['key']
    assert literal(raw,'PROJECT')==37650980
    assert sha(raw)==report['main_sha256'] and sha(literal(raw,'PROBE_CONFIG_JSON').encode())==report['config_sha256']
    assert report['financial_recovery_proven'] is report['same_session_correction_proven'] is False
    assert cfg['public_identity_export'] is False and cfg['private_identity_label_max_bytes']==64
    compile(ast.parse(raw),'main.py','exec')
    previous,_=p.prior.build_extended_mark_probe(**{key:source[p.PREFIX+name] for key,name in p.SOURCE_ARGUMENTS.items()},
        operation_id='TPR-CMP28-MARK-PROBE-ISOLATED-SYNTHETIC-009',git_head='a'*40)
    before,after=methods(previous),methods(raw)
    for name in ('_effect','_tick_config_bound','_register_parent','_history','_regular_window','_record_error','on_data'):
        assert ast.dump(before[name])==ast.dump(after[name]),name
    assert raw.startswith(source[p.PREFIX+'comparison_20261028_mark_read.py']+b'\n')
    assert raw.count(b"private_target_identity_label")==1

def test_actual_child_guard_accepts_only_new_off_id_and_preserves_parent_job_refusal(source,bindings):
    raw,_=build(source,bindings);cfg=json.loads(literal(raw,'PROBE_CONFIG_JSON'));nodes=methods(raw)
    namespace={'json':json,'re':__import__('re'),'_sha':sha,'PROBE_CONFIG':cfg,
        'PROBE_CONFIG_JSON':literal(raw,'PROBE_CONFIG_JSON'),'PROBE_CONFIG_SHA256':literal(raw,'PROBE_CONFIG_SHA256'),
        'ProbeRefusal':type('ProbeRefusal',(ValueError,),{}),'time':time,'timezone':timezone,'NY':ZoneInfo('America/New_York')}
    tree=ast.Module(body=[nodes['_tick_config_bound'],nodes['_bound']],type_ignores=[])
    exec(compile(tree,'synthetic_child_guards','exec'),namespace)
    class Algo:
        _tick_config_bound=namespace['_tick_config_bound'];_bound=namespace['_bound']
        live_mode=False;project_id=PROJECT;algorithm_id='f'*32
        time=datetime(2021,2,12,16,1);utc_time=datetime(2021,2,12,21,1)
        _child_job=None;_report={}
        _tick_config_json=namespace['PROBE_CONFIG_JSON'];_tick_config_sha256=namespace['PROBE_CONFIG_SHA256']
        def get_locked(self):return True
    algo=Algo();algo._bound()
    assert algo._child_job=='f'*32 and algo._report['actual_child_job_id']=='f'*32
    for other in (37650980,37650453,PROJECT+1,False):
        algo.project_id=other
        with pytest.raises(ValueError):algo._bound()
    algo.project_id=PROJECT;algo.algorithm_id=cfg['binding']['job_id']
    with pytest.raises(ValueError):algo._bound()
    algo.algorithm_id='f'*32;algo._tick_config_sha256='0'*64
    with pytest.raises(ValueError):algo._bound()

@pytest.mark.parametrize('mutation',['duplicate','old_project','foreign_org','wrong_name','nonowner','public_claim','forged_adapter'])
def test_registry_faults_fail_before_render(source,bindings,mutation):
    row=bindings['projects']['OFF']
    if mutation=='duplicate':row['project_id']=bindings['projects']['PURE']['project_id']
    elif mutation=='old_project':row['project_id']=37650980
    elif mutation=='foreign_org':row['organization_id']='c'*32
    elif mutation=='wrong_name':row['name']='unrelated'
    elif mutation=='nonowner':row['nonowner_collaborator_count']=1
    elif mutation=='public_claim':bindings['independent_native_origin_attested']=True
    else:bindings['adapter_source_sha256']='7'*64
    with pytest.raises(p.ProjectProbeRefusal):build(source,bindings)

@pytest.mark.parametrize('name',[p.PRIOR_MODULE,p.REGISTRY_MODULE,*[p.PREFIX+n for n in p.SOURCE_ARGUMENTS.values()]])
def test_source_corruption_refuses(source,bindings,name):
    source[name]+=b'\n'
    with pytest.raises(p.ProjectProbeRefusal):build(source,bindings)

@pytest.mark.parametrize('value',['TEST','A'*64,'A.B_9-','A'*65,'A B','é','',False,None])
def test_private_native_label_executes_only_bound_read_and_rejects_invalid_framing(source,bindings,value):
    raw,_=build(source,bindings)
    probe=methods(raw)['_probe'];blocks=[]
    for node in ast.walk(probe):
        body=getattr(node,'body',None)
        if not isinstance(body,list):continue
        for i,item in enumerate(body):
            if (isinstance(item,ast.Assign) and len(item.targets)==1
                    and isinstance(item.targets[0],ast.Name) and item.targets[0].id=='label'):
                blocks.append(body[i:i+3])
    assert len(blocks)==1 and len(blocks[0])==3
    effects=[];report={}
    def effect(phase,call):
        effects.append(phase);assert phase=='private_identity_label'
        return call()
    namespace={'self':SimpleNamespace(_effect=effect,_report=report),'symbol':SimpleNamespace(value=value),
        're':__import__('re'),'ProbeRefusal':type('ProbeRefusal',(ValueError,),{})}
    code=compile(ast.Module(body=blocks[0],type_ignores=[]),'bounded_private_label','exec')
    good=type(value) is str and 1<=len(value)<=64 and all(c.isascii() and (c.isalnum() or c in '_.-') for c in value)
    if good:
        exec(code,namespace)
        assert report=={'private_target_identity_label':value}
    else:
        with pytest.raises(ValueError):exec(code,namespace)
        assert report=={}
    assert effects==['private_identity_label']
