"""Synthetic ten-field named metadata only; no actual stat or input access."""
import ast
import copy
import hashlib
import inspect
from pathlib import Path
import stat
import sys

import pytest

from scripts import arv2_r338_input_shape as m

UID=918273645
NONCE='7654abcd'*8


def metadata(spec):
    leaf=spec['kind']!='directory'
    mode=spec['required_mode'] if spec['required_mode'] is not None else 0o755
    return (1,100+spec['path_index'],(stat.S_IFREG if leaf else stat.S_IFDIR)|mode,
        UID,345,1 if leaf else 2,spec['exact_bytes'] or 1024,123456789000,123456789001,0)


def rows():
    return [{'path_index':spec['path_index'],'path':spec['path'],
        'first_metadata':metadata(spec),'second_metadata':metadata(spec),
        'first_status':'observed','second_status':'observed'} for spec in m.scope()]


def run(value=None,**kwargs):
    options={'uid':UID,'transport_nonce':NONCE};options.update(kwargs)
    return m.inspect_metadata(rows() if value is None else value,**options)


def refused(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def change(value,index,field,new,endpoint='first'):
    info=list(value[index][endpoint+'_metadata']);info[field]=new
    value[index][endpoint+'_metadata']=tuple(info)


def test_all_static_policy_shapes_pass_without_source_or_all_component_claim():
    summary,private=run()
    assert summary==m.validate_summary(summary)
    assert summary['diagnostic_complete'] is True
    assert summary['all_observed_policy_passed'] is summary['all_metadata_endpoints_equal'] is True
    assert summary['earliest_shape_index'] is summary['first_unavailable_index'] is summary['first_changed_index'] is None
    assert len(summary['rows'])==len(m.scope())<=64
    assert summary['private_evidence_pin']==m.pin(m.canonical(private))
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert 'expected_uid' not in summary and 'transport_nonce' not in summary
    raw=m.canonical(summary)
    assert str(UID).encode() not in raw and NONCE.encode() not in raw
    assert b'first_metadata' not in raw and b'second_metadata' not in raw
    assert 'assistant.dispatch_fence' not in sys.modules


def test_scope_matches_actual_used_public_input_constants_and_first_hold_order():
    from scripts import arv2_r338_quarantine_input as source
    paths=[]
    for leaf in (source.PACKAGE/'transport-manifest.json',source.LINEAGE):
        for path in (*reversed(leaf.parents),leaf):
            if path not in paths:paths.append(path)
    assert [row['path'] for row in m.scope()]==list(map(str,paths))
    assert len([row for row in m.scope() if row['kind']!='directory'])==2
    assert str(m.ROOT)==str(source.ROOT) and str(m.PACKAGE)==str(source.PACKAGE) and str(m.LINEAGE)==str(source.LINEAGE)
    raw=Path('scripts/arv2_r338_quarantine_input.py').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==m.INPUT_SOURCE_SHA256
    assert m.FIELDS==source.FIELDS and m.MAX_LEAF_BYTES==source.MAX_LEAF_BYTES and m.MAX_LINEAGE_BYTES==source.MAX_LINEAGE_BYTES
    assert m.SOURCE_ACTIVATION_BYTES==source.SOURCE_ACTIVATION['byte_count']


@pytest.mark.parametrize('kind',['kind','owner','flags','mode','single_link','positive_size','maximum_size','exact_size'])
def test_independent_failure_predicates_and_earliest_shape(kind):
    plan=m.scope();index=next(row['path_index'] for row in plan if row['kind']=='source_activation')
    value=rows();spec=plan[index]
    if kind=='kind':change(value,index,2,stat.S_IFLNK|0o600)
    elif kind=='owner':change(value,index,3,UID+1)
    elif kind=='flags':change(value,index,9,stat.UF_IMMUTABLE)
    elif kind=='mode':change(value,index,2,stat.S_IFREG|0o644)
    elif kind=='single_link':change(value,index,5,2)
    elif kind=='positive_size':change(value,index,6,0)
    elif kind=='maximum_size':change(value,index,6,spec['maximum_bytes']+1)
    else:change(value,index,6,spec['exact_bytes']+1)
    summary,_=run(value)
    endpoint=summary['rows'][index]['first']
    assert endpoint['predicates'][kind] is False and kind in endpoint['failed_predicates']
    assert summary['earliest_shape_index']==index and summary['shape_failure_path_count']==1
    assert summary['all_observed_policy_passed'] is False


def test_multiple_policy_failures_all_retained_even_after_kind_and_earlier_ancestor_mode_failure():
    plan=m.scope();root=next(row['path_index'] for row in plan if row['path']==str(m.ROOT))
    leaf=next(row['path_index'] for row in plan if row['kind']=='source_activation')
    value=rows();change(value,root,2,stat.S_IFDIR|0o700)
    change(value,leaf,2,stat.S_IFLNK|0o777);change(value,leaf,3,UID+1)
    change(value,leaf,9,stat.UF_IMMUTABLE);change(value,leaf,5,2);change(value,leaf,6,0)
    summary,_=run(value)
    assert summary['earliest_shape_index']==root and summary['shape_failure_path_count']==2
    assert set(summary['rows'][leaf]['first']['failed_predicates'])=={
        'kind','owner','flags','mode','single_link','positive_size','exact_size'}
    assert summary['rows'][leaf]['first']['predicates']['maximum_size'] is True


@pytest.mark.parametrize('index',range(len(m.scope())))
@pytest.mark.parametrize('variant',['valid','kind','owner','flags','mode','links','size'])
def test_projection_policy_acceptance_matches_actual_used_guard_without_constructor_IO(monkeypatch,index,variant):
    from scripts import arv2_r338_quarantine_input as source
    monkeypatch.setattr(source.os,'getuid',lambda:UID)
    spec=m.scope()[index];info=list(metadata(spec))
    if variant=='kind':info[2]=stat.S_IFLNK|stat.S_IMODE(info[2])
    elif variant=='owner':info[3]=UID+1
    elif variant=='flags':info[9]=stat.UF_IMMUTABLE
    elif variant=='mode':info[2]=stat.S_IFMT(info[2])|0o777
    elif variant=='links':info[5]=2
    elif variant=='size':info[6]=0
    info=tuple(info)
    expected=None if spec['kind']=='directory' else {'maximum':spec['maximum_bytes'],'byte_count':spec['exact_bytes']}
    actual=source._InputGuard.__new__(source._InputGuard)
    try:actual._policy(Path(spec['path']),info,expected);accepted=True
    except source.Refused as error:
        assert source.finite(error)=='shape';accepted=False
    value=rows();value[index]['first_metadata']=info
    summary,_=run(value)
    assert summary['rows'][index]['first']['policy_passed'] is accepted


@pytest.mark.parametrize('field',range(10))
def test_all_ten_tuple_fields_participate_in_endpoint_equality(field):
    value=rows();index=len(value)-1
    change(value,index,field,value[index]['second_metadata'][field]+1,'second')
    summary,private=run(value)
    assert summary['first_changed_index']==index and summary['changed_path_count']==1
    assert summary['rows'][index]['metadata_equal'] is False
    assert private['rows'][index]['first_metadata']!=private['rows'][index]['second_metadata']


@pytest.mark.parametrize('bad',[(),(1,)*9,(1,)*11,[1]*10,(1,1,1,1,1,1,1,1,1,True),
    (1,1,1,1,1,1,1,1,1,-1),(1,1,1,1,1,1,1,1,1,None)])
def test_full_metadata_tuple_schema_is_strict(bad):
    value=rows();value[0]['first_metadata']=bad
    refused('metadata',lambda:run(value))


@pytest.mark.parametrize('status',['not_found','permission_denied','not_directory','blocked_ancestor','unavailable'])
def test_missing_named_metadata_is_finite_unknown_diagnostic_not_policy_pass(status):
    value=rows();value[-1].update(first_metadata=None,first_status=status)
    summary,_=run(value)
    assert summary['first_unavailable_index']==len(value)-1 and summary['unavailable_path_count']==1
    assert summary['rows'][-1]['first']['policy_passed'] is None
    assert summary['all_observed_policy_passed'] is False and summary['all_metadata_endpoints_equal'] is False
    assert summary['earliest_shape_index'] is None


def test_observed_symlink_never_claims_held_or_all_component_nofollow():
    value=rows();root=next(row['path_index'] for row in m.scope() if row['path']==str(m.ROOT))
    change(value,root,2,stat.S_IFLNK|0o755)
    for index in range(root+1,len(value)):
        value[index].update(first_metadata=None,first_status='blocked_ancestor',second_metadata=None,second_status='blocked_ancestor')
    summary,_=run(value)
    assert summary['earliest_shape_index']==root and summary['rows'][root]['first']['observed_kind']=='symlink'
    assert summary['all_component_nofollow_proven'] is summary['held_descriptor_identity_proven'] is False


@pytest.mark.parametrize('kind',['order','missing','extra','path','bool_index','status','metadata_status','unknown_field'])
def test_observation_scope_is_closed_exact_static_inventory(kind):
    value=rows()
    if kind=='order':value.reverse()
    elif kind=='missing':value.pop()
    elif kind=='extra':value.append(value[-1])
    elif kind=='path':value[-1]['path']='/Volumes/NOT-AUTHORIZED'
    elif kind=='bool_index':value[0]['path_index']=False
    elif kind=='status':value[-1]['first_status']='RAW-ERROR'
    elif kind=='metadata_status':value[-1]['first_status']='unavailable'
    else:value[-1]['private_extra']='NEVER-PUBLIC'
    with pytest.raises(m.Refused):run(value)


@pytest.mark.parametrize('uid',[True,-1,None,'918273645'])
def test_uid_is_typed_caller_observation_not_authority_flag(uid):
    refused('uid',lambda:run(uid=uid))


@pytest.mark.parametrize('nonce',[None,True,b'a'*64,'','a'*63,'A'*64,'g'*64])
def test_nonce_is_exact_private_transport_field(nonce):
    refused('transport_nonce',lambda:run(transport_nonce=nonce))


def test_fresh_private_nonce_changes_only_private_evidence_pin():
    first,private_first=run();second,private_second=run(transport_nonce='abcd7654'*8)
    assert first['private_evidence_pin']!=second['private_evidence_pin']
    assert {k:v for k,v in first.items() if k!='private_evidence_pin'}=={k:v for k,v in second.items() if k!='private_evidence_pin'}
    assert {k:v for k,v in private_first.items() if k!='transport_nonce'}=={k:v for k,v in private_second.items() if k!='transport_nonce'}
    assert m.canonical(private_first)!=m.canonical(private_second)


@pytest.mark.parametrize('change',['bool_count','first_shape','mode_relation','owner_relation','predicate_type','unknown','equality','false_claim','nonce_public'])
def test_public_summary_validation_rejects_inconsistent_or_leaking_metadata(change):
    summary,_=run();row=summary['rows'][-1]
    if change=='bool_count':summary['changed_path_count']=False
    elif change=='first_shape':summary['earliest_shape_index']=0
    elif change=='mode_relation':row['first']['mode']='0644'
    elif change=='owner_relation':row['first']['owner_match']=False
    elif change=='predicate_type':row['first']['predicates']['kind']=1
    elif change=='unknown':row['first']['flags_class']='RAW_PRIVATE_FLAG'
    elif change=='equality':row['metadata_equal']=None
    elif change=='false_claim':summary['source_bytes_authenticated']=True
    else:summary['transport_nonce']=NONCE
    refused('output',lambda:m.validate_summary(summary))


def test_private_transport_bound_and_exact_no_IO_import_call_boundary(monkeypatch):
    monkeypatch.setattr(m,'MAX_PRIVATE_BYTES',1)
    refused('private_bound',lambda:run())
    tree=ast.parse(inspect.getsource(m))
    assert all(alias.name in ('hashlib','json','re','stat') for node in ast.walk(tree)
        if isinstance(node,ast.Import) for alias in node.names)
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            assert not isinstance(node.func,ast.Name) or node.func.id not in ('open','exec','eval','compile','__import__')
            assert not isinstance(node.func,ast.Attribute) or node.func.attr not in (
                'stat','lstat','fstat','open','read_bytes','read_text','write_bytes','resolve','listdir','getuid','snapshot')
