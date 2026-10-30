"""Synthetic projects/metadata only; no credentials, native calls or accounts."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import stat
import sys

import pytest

from research.target_price_revisions_qc import comparison_20261029_projects as p
from research.target_price_revisions_qc import extended_operations as _custody_ops

NOW=datetime(2026,10,29,10,tzinfo=timezone.utc)
OWNER=42
ORG='a'*32
TOKEN='SYNTHETIC-SECRET-NEVER-RETAIN'
ROOT=Path(__file__).resolve().parents[2]

MAC_CUSTODY_REASON = (
    "Owner-selected Mac-only native custody (TPR-CR25-003): POSIX no-follow/UID/mode/directory-fsync "
    "custody is not Windows custody evidence"
)


@pytest.fixture(autouse=True)
def mac_only_native_custody(monkeypatch):
    """TPR-CR33-003: skip exactly where execution reaches POSIX private custody off the Mac.

    Portable plan, builder and refusal checks keep running on every host.
    """
    if sys.platform != "darwin":
        def custody(*_args, **_kwargs):
            pytest.skip(MAC_CUSTODY_REASON)
        monkeypatch.setattr(_custody_ops, "_custody", custody)



@pytest.fixture(autouse=True)
def deny_native(monkeypatch):
    def deny(*_args,**_kwargs):raise AssertionError('actual credential/network/subprocess forbidden')
    monkeypatch.setattr(p.ops,'credential',deny)
    monkeypatch.setattr(p.http.client,'HTTPSConnection',deny)
    monkeypatch.setattr(p.subprocess,'run',deny)


def plan(operation='baseline',phase='baseline',**changes):
    at=changes.pop('at',NOW)
    args=dict(operation_id='TPR107-SYNTHETIC-'+operation,git_head='b'*40,
        source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in p.REQUIRED_SOURCES},
        owner_instruction_sha256='c'*64,created_utc=at.isoformat(),expires_utc=(at+timedelta(seconds=600)).isoformat(),
        phase=phase,mode='offline-fixture')
    args.update(changes);return p.prepare_plan(**args)


def metadata(pid=p.OLD_PROJECT,arm=None,**changes):
    row=dict(projectId=pid,organizationId=ORG,name='Existing Own OFF' if arm is None else p.RESERVED_NAMES[arm],
        ownerId=OWNER,owner=True,language='Py',created=NOW.isoformat(),collaborators=[])
    row.update(changes);return row


def response(body,status=200,token=TOKEN,owner=OWNER):return p._canonical(body),status,token,owner

def run(tmp_path,prepared,transport,**changes):
    return p._execute_fixture(prepared,tmp_path/'projects',transport=transport,
        clock=lambda:datetime.fromisoformat(prepared['created_utc'])+timedelta(seconds=1),**changes)


def read_result(tmp_path,result):return (tmp_path/'projects'/result['receipt']['name']).read_bytes()


def baseline(tmp_path):
    prepared=plan()
    result=run(tmp_path,prepared,lambda *_:response({'success':True,'projects':[metadata()]}))
    assert result['status']=='completed';return result


def next_plan(phase,arm,base,prior=None,operation=None):
    return plan(operation or phase+'-'+arm,phase,arm=arm,baseline=base['receipt'],
        prior=None if prior is None else prior['receipt'],at=datetime.fromisoformat((prior or base)['observed_utc'])+timedelta(seconds=1))


def project_chain(tmp_path,arm='OFF',pid=400001,base=None,created_override=None):
    base=baseline(tmp_path) if base is None else base
    body=metadata(pid,arm)
    if created_override is not None:body['created']=created_override
    created=run(tmp_path,next_plan('create',arm,base),lambda *_:response({'success':True,'projects':[body]}))
    read=run(tmp_path,next_plan('read',arm,base,created),lambda *_:response({'success':True,'projects':[body]}))
    collaborators=run(tmp_path,next_plan('collaborators',arm,base,read),lambda *_:response({
        'success':True,'collaborators':[],'userPermissions':'write','userLiveControl':True}))
    assert created['status']==read['status']==collaborators['status']=='completed'
    return base,created,read,collaborators


def registry(tmp_path):
    base=baseline(tmp_path);parts={}
    for index,arm in enumerate(p.ARMS):
        _,created,read,collab=project_chain(tmp_path,arm,400001+index,base)
        parts[arm]={'create':read_result(tmp_path,created),'read':read_result(tmp_path,read),
            'collaborators':read_result(tmp_path,collab)}
    raw=p.build_bindings(baseline_result_raw=read_result(tmp_path,base),project_result_raws=parts)
    return raw,parts,base


def test_baseline_auth_owner_and_name_claims_precede_one_create_effect(tmp_path):
    base=baseline(tmp_path);prepared=next_plan('create','OFF',base);calls=[];root=tmp_path/'projects'
    def transport(endpoint,raw,seconds,maximum,expected_owner):
        calls.append(endpoint)
        assert endpoint=='projects/create' and expected_owner==OWNER
        assert json.loads(raw)=={'name':p.RESERVED_NAMES['OFF'],'language':'Py','organizationId':ORG}
        assert (root/'name.OFF.create.spent.json').exists()
        for suffix in ('.operation.spent.json','.baseline-read.spent.json','.request.spent.json'):
            assert (root/(prepared['operation_id']+suffix)).exists()
        return response({'success':True,'projects':[metadata(400001,'OFF')]})
    out=run(tmp_path,prepared,transport)
    assert out['status']=='completed' and calls==['projects/create'] and out['unknown_create'] is False
    assert out['metadata']['project_id']==400001 and out['privacy_basis']==p.PRIVACY_BASIS
    assert out['independent_native_origin_attested'] is out['automatic_retry'] is False
    for item in root.iterdir():
        assert stat.S_IMODE(item.stat().st_mode)==0o600
        assert TOKEN.encode() not in item.read_bytes()
    assert stat.S_IMODE(root.stat().st_mode)==0o700


def test_full_five_actual_phase_chains_form_only_closed_framing_registry(tmp_path):
    raw,_,_=registry(tmp_path);body=p.validate_bindings(raw,expected_sha256=p._sha(raw))
    assert body['round_id']==p.ROUND_ID and len({x['project_id'] for x in body['projects'].values()})==5
    assert body['owner_id']==OWNER and body['organization_id']==ORG
    assert body['adapter_source_sha256']==p._sha((ROOT/p.MODULE).read_bytes())
    assert body['explicit_privacy_flag_observed'] is body['independent_native_origin_attested'] is False
    assert body['privacy_basis']=='documented_private_default_and_observed_collaborators'
    assert not {'private','isPublic','native_permission','orders_authorized'}&set(body)


@pytest.mark.parametrize('fault',['timeout','500','malformed','owner','two_projects','duplicate_name','secret','unknown_status'])
def test_create_unknown_outcome_spends_name_and_never_retries(tmp_path,fault):
    base=baseline(tmp_path);prepared=next_plan('create','OFF',base);calls=[]
    def transport(*_):
        calls.append('call')
        if fault=='timeout':raise TimeoutError('PRIVATE-ERROR')
        if fault=='500':return response({'success':False,'errors':['PRIVATE-ERROR']},500)
        if fault=='malformed':return b'not-json',200,TOKEN,OWNER
        if fault=='owner':return response({'success':True,'projects':[metadata(400001,'OFF',ownerId=43)]})
        if fault=='two_projects':return response({'success':True,'projects':[metadata(400001,'OFF'),metadata(400002,'OFF')]})
        if fault=='duplicate_name':return response({'success':False,'errors':['already exists']})
        if fault=='secret':return response({'success':True,'projects':[metadata(400001,'OFF')],'echo':TOKEN})
        return response({'success':None})
    out=run(tmp_path,prepared,transport)
    assert out['status']=='failed_or_uncertain' and out['unknown_create'] is True and calls==['call']
    assert out['receipt_published'] and 'PRIVATE-ERROR' not in json.dumps(out)
    retry=next_plan('create','OFF',base,operation='different-create-OFF')
    again=run(tmp_path,retry,transport)
    assert again['status']=='failed_or_uncertain' and again['request'] is False and calls==['call']
    if fault=='500':assert out['raw_response'] is not None and out['http_status']==500
    if fault=='secret':assert out['raw_response'] is None


def test_unknown_create_can_only_reconcile_reserved_name_then_exact_read(tmp_path):
    base=baseline(tmp_path)
    def uncertain(*_):raise TimeoutError('PRIVATE-ERROR')
    unknown=run(tmp_path,next_plan('create','OFF',base),uncertain)
    prepared=next_plan('reconcile','OFF',base,unknown)
    calls=[]
    def listing(endpoint,raw,*_):
        calls.append(endpoint);assert json.loads(raw)=={'start':0,'end':100}
        return response({'success':True,'projects':[metadata(800001,'OFF'),metadata(800002,'PURE')]})
    reconciled=run(tmp_path,prepared,listing)
    assert reconciled['status']=='completed' and reconciled['metadata']['project_id']==800001 and calls==['projects/read']
    exact=run(tmp_path,next_plan('read','OFF',base,reconciled),lambda _,raw,*rest:response({
        'success':True,'projects':[metadata(json.loads(raw)['projectId'],'OFF')]}))
    assert exact['status']=='completed'


@pytest.mark.parametrize('rows,expected',[([], 'reconciliation_not_observed'),([metadata(800001,'OFF'),metadata(800002,'OFF')],'failed_or_uncertain')])
def test_reconcile_missing_or_duplicate_does_not_repeat_create(tmp_path,rows,expected):
    base=baseline(tmp_path)
    unknown=run(tmp_path,next_plan('create','OFF',base),lambda *_:response({'success':False},500))
    out=run(tmp_path,next_plan('reconcile','OFF',base,unknown),lambda *_:response({'success':True,'projects':rows}))
    assert out['status']==expected and out['create_attempted'] is False


@pytest.mark.parametrize('created',[None,'2026-10-29T10:00:00','opaque-native-timestamp'])
def test_missing_or_naive_created_is_retained_unknown_without_timezone_invention(tmp_path,created):
    base=baseline(tmp_path);body=metadata(400001,'OFF',created=created)
    out=run(tmp_path,next_plan('create','OFF',base),lambda *_:response({'success':True,'projects':[body]}))
    assert out['status']=='completed' and out['metadata']['created_utc'] is None
    assert out['metadata']['created_value_sha256']==p._sha(p._canonical(created))


def test_unknown_create_reconciliation_never_invents_utc_for_naive_creation(tmp_path):
    base=baseline(tmp_path)
    unknown=run(tmp_path,next_plan('create','OFF',base),lambda *_:response({'success':False},500))
    out=run(tmp_path,next_plan('reconcile','OFF',base,unknown),lambda *_:response({
        'success':True,'projects':[metadata(800001,'OFF',created='2026-10-29T10:00:00')]}))
    assert out['status']=='reconciliation_creation_time_unproved' and out['metadata']['created_utc'] is None
    child=run(tmp_path,next_plan('read','OFF',base,out),lambda *_:pytest.fail('unproved identity must not read'))
    assert child['status']=='failed_or_uncertain' and child['request'] is False


@pytest.mark.parametrize('changes',[{'owner':False},{'ownerId':43},{'organizationId':'d'*32},{'projectId':p.OLD_PROJECT},
    {'language':'C#'},{'name':'foreign'},{'isPublic':True},{'private':False},{'shared':True},{'isPublic':'false'}])
def test_foreign_or_explicit_public_create_metadata_never_registers(tmp_path,changes):
    base=baseline(tmp_path)
    out=run(tmp_path,next_plan('create','OFF',base),lambda *_:response({'success':True,'projects':[metadata(400001,'OFF',**changes)]}))
    assert out['status']=='failed_or_uncertain' and out['metadata'] is None and out['unknown_create'] is True


def test_owner_only_collaborator_schema_is_observed_without_pii_projection(tmp_path):
    row={'uid':OWNER,'owner':True,'permission':'write','liveControl':False,'email':'PRIVATE-EMAIL','bio':'PRIVATE-BIO'}
    base=run(tmp_path,plan(),lambda *_:response({'success':True,'projects':[metadata(collaborators=[row])]}))
    assert base['status']=='completed' and base['metadata']['collaborator_count']==1
    assert 'PRIVATE-EMAIL' not in json.dumps(base) and 'PRIVATE-BIO' not in json.dumps(base)


@pytest.mark.parametrize('row',[{'uid':43,'owner':False,'permission':'read','liveControl':False},
    {'uid':None,'owner':False,'permission':'read','liveControl':False},
    {'uid':OWNER,'owner':True,'permission':'unknown','liveControl':False},
    {'uid':OWNER,'owner':True,'permission':'write','liveControl':None}])
def test_nonowner_entire_org_and_unknown_collaborators_refuse(tmp_path,row):
    base=baseline(tmp_path)
    out=run(tmp_path,next_plan('create','OFF',base),lambda *_:response({'success':True,'projects':[metadata(400001,'OFF',collaborators=[row])]}))
    assert out['status']=='failed_or_uncertain' and out['metadata'] is None


def test_actual_private_valued_extra_flag_is_observed_but_not_origin_or_privacy_attestation(tmp_path):
    base=baseline(tmp_path)
    out=run(tmp_path,next_plan('create','OFF',base),lambda *_:response({'success':True,'projects':[metadata(400001,'OFF',isPublic=False)]}))
    assert out['status']=='completed' and out['metadata']['explicit_privacy_flag_observed'] is True
    assert out['independent_native_origin_attested'] is False


@pytest.mark.parametrize('fault',['cross_arm','old_id','wrong_owner','duplicate_id','false_count','owner_bool','receipt_reuse','public_authority','new_arm','wrong_pin'])
def test_registry_refuses_cross_project_aliases_types_receipts_or_authority(tmp_path,fault):
    raw,_,_=registry(tmp_path);body=json.loads(raw)
    row=body['projects']['OFF']
    if fault=='cross_arm':row['name']=p.RESERVED_NAMES['PURE']
    elif fault=='old_id':row['project_id']=p.OLD_PROJECT
    elif fault=='wrong_owner':row['owner_id']=43
    elif fault=='duplicate_id':row['project_id']=body['projects']['PURE']['project_id']
    elif fault=='false_count':row['nonowner_collaborator_count']=False
    elif fault=='owner_bool':body['owner_id']=1;row['owner_id']=True
    elif fault=='receipt_reuse':row['create_receipt_sha256']=row['read_receipt_sha256']
    elif fault=='public_authority':body['independent_native_origin_attested']=True
    elif fault=='new_arm':body['projects']['OTHER']=row
    wire=p._canonical(body)
    with pytest.raises(p.ProjectRefusal):p.validate_bindings(wire,expected_sha256='d'*64 if fault=='wrong_pin' else p._sha(wire))


def test_build_registry_refuses_unlinked_phase_receipts(tmp_path):
    _,parts,base=registry(tmp_path)
    row=json.loads(parts['OFF']['read']);row['prior']['sha256']='e'*64
    parts['OFF']['read']=p._canonical(row)
    with pytest.raises(p.ProjectRefusal):p.build_bindings(baseline_result_raw=read_result(tmp_path,base),project_result_raws=parts)


@pytest.mark.parametrize('fault',['missing','hash','symlink','stale','wrong_source','wrong_arm'])
def test_prerequisite_receipt_denies_before_credentials_or_request(tmp_path,fault):
    base=baseline(tmp_path);descriptor=dict(base['receipt'])
    if fault=='missing':descriptor['name']='missing.result.json'
    elif fault=='hash':descriptor['sha256']='d'*64
    elif fault=='symlink':
        path=tmp_path/'projects'/'alias.result.json';path.symlink_to(descriptor['name']);descriptor['name']=path.name
    elif fault in ('wrong_source','wrong_arm'):
        body=json.loads(read_result(tmp_path,base));body['source_hashes'][p.MODULE]='d'*64
        target=tmp_path/'projects'/'changed.result.json';target.write_bytes(p._canonical(body));target.chmod(0o600)
        descriptor={'name':target.name,'bytes':target.stat().st_size,'sha256':p._sha(target.read_bytes())}
    at=NOW+timedelta(seconds=4000) if fault=='stale' else NOW+timedelta(seconds=2)
    out=run(tmp_path,plan('bad-create','create',arm='OFF',baseline=descriptor,at=at),lambda *_:pytest.fail('no request'))
    assert out['status']=='failed_or_uncertain' and out['request'] is False and not out['create_attempted']


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_nonordinary_native_stop_is_body_free_and_name_remains_spent(tmp_path,kind):
    base=baseline(tmp_path)
    class Fatal(BaseException):pass
    def stop(*_):raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-ERROR')
    with pytest.raises(p.ProjectCancelled if kind=='cancel' else p.ProjectFatal) as caught:
        run(tmp_path,next_plan('create','OFF',base),stop)
    assert 'PRIVATE-ERROR' not in str(caught.value) and caught.value.report['unknown_create'] is True
    assert caught.value.report['receipt_published'] is True
    assert (tmp_path/'projects'/'name.OFF.create.spent.json').exists()


def test_guard_change_after_request_never_accepts_a_result_or_retries(tmp_path):
    base=baseline(tmp_path);calls=[];changed=False
    def guard(_):
        if changed:raise p.ProjectRefusal('scope changed')
    def transport(*_):
        nonlocal changed
        changed=True;calls.append('once');return response({'success':True,'projects':[metadata(400001,'OFF')]})
    out=run(tmp_path,next_plan('create','OFF',base),transport,guard=guard)
    assert out['status']=='failed_or_uncertain' and out['unknown_create'] is True and calls==['once']


@pytest.mark.parametrize('changes',[{'phase':'files/update'},{'arm':'FOREIGN'},{'seconds':True},
    {'page_start':1,'page_end':101},{'page_start':0,'page_end':1000},{'mode':'native-marker'}])
def test_closed_plan_cannot_widen_endpoint_arm_page_or_authority(changes):
    with pytest.raises(p.ProjectRefusal):plan(**changes)


@pytest.mark.parametrize('privacy_changes',[{}, {'isPublic':True,'shared':True}])
def test_old_baseline_null_uid_is_qualified_owner_org_only_metadata(tmp_path,privacy_changes):
    known={'uid':OWNER,'owner':True,'permission':'write','liveControl':False}
    unknown={'uid':None,'owner':False,'permission':'read','liveControl':False}
    out=run(tmp_path,plan(),lambda *_:response({'success':True,'projects':[metadata(collaborators=[known,unknown],**privacy_changes)]}))
    assert out['status']=='completed'
    assert out['privacy_basis']=='baseline_owner_org_metadata_only'
    assert out['metadata']['collaborator_count']==2
    assert out['metadata']['nonowner_collaborator_count']==1
    assert out['metadata']['unclassified_collaborator_count']==1
    assert out['metadata']['known_nonowner_collaborator_count']==0
    assert out['metadata']['old_project_privacy_clean_verified'] is False
    assert out['metadata']['old_project_write_authorized'] is False
    assert out['metadata']['nonowner_count_includes_unclassified'] is True
    assert out['metadata']['collaborators_sha256']==p._sha(p.e.canonical(p.e.parse_json(p._canonical([known,unknown]))))
    assert out['endpoint']=='projects/read' and out['payload']=={'projectId':p.OLD_PROJECT}


@pytest.mark.parametrize('phase',['create','read','collaborators'])
def test_identical_null_uid_in_new_project_phase_still_refuses(tmp_path,phase):
    base=baseline(tmp_path)
    unknown={'uid':None,'owner':False,'permission':'read','liveControl':False}
    newmeta=metadata(400001,'OFF',collaborators=[unknown])
    if phase=='create':
        prepared=next_plan('create','OFF',base)
    else:
        created=run(tmp_path,next_plan('create','OFF',base),lambda *_:response({'success':True,'projects':[metadata(400001,'OFF')]}))
        if phase=='read':prepared=next_plan('read','OFF',base,created)
        else:
            read=run(tmp_path,next_plan('read','OFF',base,created),lambda *_:response({'success':True,'projects':[metadata(400001,'OFF')]}))
            prepared=next_plan('collaborators','OFF',base,read)
    body={'success':True,'collaborators':[unknown],'userPermissions':'write'} if phase=='collaborators' else {'success':True,'projects':[newmeta]}
    out=run(tmp_path,prepared,lambda *_:response(body))
    assert out['status']=='failed_or_uncertain'
    assert out['metadata'] is None and out['collaboration'] is None
