"""Synthetic cleanup metadata/source/job archives; no native/private account I/O."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import stat

import pytest

from research.target_price_revisions_qc import comparison_20261029_cleanup_api as m

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime(2026,10,29,12,tzinfo=timezone.utc)
OWNER=42
ORG='a'*32
TOKEN='SYNTHETIC-SECRET-NEVER-RETAIN'
PROJECT=37540166
JOB='1'*32


@pytest.fixture(autouse=True)
def no_actual(monkeypatch):
    def deny(*_args,**_kwargs):raise AssertionError('actual credential/network/subprocess forbidden')
    monkeypatch.setattr(m.ops,'credential',deny)
    monkeypatch.setattr(m.projects.http.client,'HTTPSConnection',deny)
    monkeypatch.setattr(m.subprocess,'run',deny)


def store(root,name,body):
    root.mkdir(mode=0o700,exist_ok=True)
    raw=body if type(body) is bytes else m._canonical(body)
    path=root/name
    with path.open('xb') as stream:stream.write(raw)
    path.chmod(0o600)
    return {'name':name,'bytes':len(raw),'sha256':m._sha(raw)}


def fixture_registry(root):
    rows={}
    for arm,pid in zip(m.projects.ARMS,sorted(m.PROTECTED_IDS)):
        rows[arm]=dict(project_id=pid,name=m.projects.RESERVED_NAMES[arm],organization_id=ORG,owner_id=OWNER,
            language='Py',create_receipt_sha256=m._sha((arm+'create').encode()),
            read_receipt_sha256=m._sha((arm+'read').encode()),collaboration_receipt_sha256=m._sha((arm+'collab').encode()),
            collaborator_count=1,nonowner_collaborator_count=0,collaborators_sha256='d'*64)
    body=dict(schema='tpr-cmp28-five-project-bindings-v1',round_id=m.projects.ROUND_ID,
        owner_instruction_sha256='c'*64,git_head='b'*40,adapter_source_sha256=m._sha((ROOT/m.PROJECTS_MODULE).read_bytes()),
        organization_id=ORG,owner_id=OWNER,baseline_receipt_sha256='e'*64,projects=rows,
        privacy_basis=m.projects.PRIVACY_BASIS,explicit_privacy_flag_observed=False,independent_native_origin_attested=False)
    return store(root,m.REGISTRY['name'],body)


def plan(registry,phase='inventory',operation='inventory',**changes):
    args=dict(operation_id='TPR107-CLEANUP-SYNTHETIC-'+operation,git_head='b'*40,
        source_hashes={name:m._sha((ROOT/name).read_bytes()) for name in m.REQUIRED_SOURCES},
        owner_instruction_sha256=m.OWNER_SHA256,created_utc=(NOW+timedelta(seconds=30)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=600)).isoformat(),phase=phase,registry_file=registry,mode='offline-fixture')
    args.update(changes);return m.prepare_plan(**args)


def run(tmp_path,prepared,transport,**changes):
    return m._execute_fixture(prepared,tmp_path/'cleanup',tmp_path/'inputs',transport=transport,
        clock=lambda:NOW+timedelta(seconds=31),**changes)


def response(body,status=200,token=TOKEN,owner=OWNER):return m._canonical(body),status,token,owner


def project(pid=PROJECT,**changes):
    row=dict(projectId=pid,name='Retained TargetPrice Test',ownerId=OWNER,owner=True,organizationId=ORG,
        libraries=[],codeRunning=False,lastLiveDeployment=None,description='PRIVATE-DESCRIPTION',email='PRIVATE-EMAIL')
    row.update(changes);return row


def archived(tmp_path,*,pid=PROJECT,status='Runtime Error',orders='0',basis='no_completed_backtest',
        meta_changes=None,inventory_extra=None,jobs=None,input_dependencies=None,job_changes=None):
    root=tmp_path/'inputs';registry=fixture_registry(root)
    rows=[project(pid,**(meta_changes or {})),*(inventory_extra or [])]
    inventory=store(root,'inventory.raw',{'success':True,'projects':rows})
    source_raw=m._canonical({'success':True,'projectId':pid,'files':[{'name':'main.py','content':'# PRIVATE-SOURCE-BODY\n'},
        {'name':'research.ipynb','content':'{"cells":["raise SystemExit(99)"]}'}]})
    sources=store(root,'sources.raw',source_raw)
    list_rows=[{'backtestId':JOB,'status':status}] if jobs is None else jobs
    jobs_raw=m._canonical({'success':True,'projectId':pid,'backtests':list_rows,'count':len(list_rows)})
    jobs_descriptor=store(root,'jobs.raw',jobs_raw);details={}
    for row in list_rows:
        body=dict(backtestId=row['backtestId'],status=row['status'],completed=row['status'] in m.COMPLETED,
            statistics={} if orders is None else {'Total Orders':orders})
        body.update(job_changes or {})
        details[row['backtestId']]=store(root,'job-'+row['backtestId']+'.raw',{'success':True,'projectId':pid,'backtest':body})
    index=dict(schema='tpr-cmp29-cleanup-archive-index-v1',project_id=pid,created_utc=(NOW+timedelta(seconds=10)).isoformat(),
        owner_instruction_sha256=m.OWNER_SHA256,registry_sha256=registry['sha256'],
        inventory_pages=[{'start':0,'response':inventory}],sources=sources,jobs=jobs_descriptor,job_results=details,
        input_dependency_project_ids=[] if input_dependencies is None else input_dependencies)
    archive=store(root,'archive.json',index)
    criteria=dict(schema='tpr-cmp29-cleanup-criteria-v1',project_id=pid,created_utc=(NOW+timedelta(seconds=11)).isoformat(),
        owner_instruction_sha256=m.OWNER_SHA256,registry_sha256=registry['sha256'],archive_index_sha256=archive['sha256'],
        basis=basis,source_inventory_sha256=m._sha(m._canonical(m.project_source_inventory(source_raw,project_id=pid))),
        job_census_sha256=m._sha(m._canonical(m.project_job_census(jobs_raw,project_id=pid))))
    criteria_file=store(root,'criteria.json',criteria)
    return registry,archive,criteria_file,index,criteria


def delete_plan(registry,index,criteria,**changes):
    return plan(registry,'delete','delete',project_id=PROJECT,archive_index=index,criteria_file=criteria,**changes)


def test_public_record_membership_is_pinned_and_not_deletion_authority():
    body={'schema':'tpr-public-record-project-membership-v1','source_head':'bb2220174fb69acba098d9ec9c8959ed6c412b7b',
        'old_project_ids':sorted(m.OLD_IDS),'protected_project_ids':sorted(m.PROTECTED_IDS)}
    assert len(m.OLD_IDS)==11 and m._sha(m._canonical(body))==m.MEMBERSHIP_SHA256
    assert m.DELETE_CANDIDATES=={37540166,37650453} and 37650980 not in m.DELETE_CANDIDATES


def test_inventory_reads_all_account_metadata_without_admitting_names_or_writes(tmp_path):
    registry=fixture_registry(tmp_path/'inputs');prepared=plan(registry,page_start=100);calls=[]
    def transport(endpoint,raw,seconds,maximum,owner):
        calls.append(endpoint)
        assert endpoint=='projects/read' and json.loads(raw)=={'start':100,'end':200}
        assert owner==OWNER and maximum==2*1024*1024
        assert (tmp_path/'cleanup'/(prepared['operation_id']+'.request.spent.json')).exists()
        return response({'success':True,'projects':[project(1111,owner=False),project(38609822)]})
    out=run(tmp_path,prepared,transport);text=json.dumps(out)
    assert out['status']=='completed' and calls==['projects/read']
    assert [row['project_id'] for row in out['projection']['projects']]==[1111,38609822]
    assert out['projection']['short_page_observed'] is True
    assert out['projection']['complete_account_inventory_independently_attested'] is False
    assert not any(value in text for value in ('PRIVATE-DESCRIPTION','PRIVATE-EMAIL',ORG,TOKEN))


@pytest.mark.parametrize('phase',['lane_sources','lane_jobs','lane_job','delete','delete_readback'])
@pytest.mark.parametrize('pid',[38609822,38609834,38609836,38609837,38609840,99999999])
def test_all_new_five_and_foreign_ids_are_denied_for_exact_cleanup_stages(tmp_path,phase,pid):
    registry=fixture_registry(tmp_path/'inputs')
    with pytest.raises(m.CleanupRefusal):plan(registry,phase,project_id=pid,job_id=JOB if phase=='lane_job' else None)


def test_no_completed_candidate_requires_real_archives_and_claims_before_delete(tmp_path):
    registry,index,criteria,*_=archived(tmp_path);prepared=delete_plan(registry,index,criteria);calls=[]
    def transport(endpoint,raw,*_):
        calls.append(endpoint);root=tmp_path/'cleanup'
        assert endpoint=='projects/delete' and json.loads(raw)=={'projectId':PROJECT}
        assert (root/('project.'+str(PROJECT)+'.delete.spent.json')).exists()
        assert len(list(root.glob(prepared['operation_id']+'.read-*.spent.json')))==7
        return response({'success':True})
    out=run(tmp_path,prepared,transport)
    assert out['status']=='delete_acknowledged_readback_required' and calls==['projects/delete']
    assert out['eligibility']['completed_jobs']==0 and out['eligibility']['archived_jobs']==1
    assert out['actual_delete_readback_required'] is True
    assert out['backend_rollback_proven'] is out['atomic_remote_compare_and_swap_proven'] is False
    assert out['object_store_deleted'] is out['financial_results_accepted'] is False
    assert 'PRIVATE-SOURCE-BODY' not in json.dumps(out) and 'SystemExit' not in json.dumps(out)
    for item in (tmp_path/'cleanup').iterdir():assert stat.S_IMODE(item.stat().st_mode)==0o600


def test_documented_verification_candidate_needs_actual_zero_order_completed_details(tmp_path):
    registry,index,criteria,*_=archived(tmp_path,status='Completed.',basis='verification_only',orders='0')
    out=run(tmp_path,delete_plan(registry,index,criteria),lambda *_:response({'success':True}))
    assert out['status']=='delete_acknowledged_readback_required' and out['eligibility']['completed_jobs']==1
    assert out['eligibility']['public_verification_basis']==m.VERIFICATION_BASIS[PROJECT]


@pytest.mark.parametrize('fault',['completed','nonzero_orders','unknown_orders','nonterminal','missing_completed',
    'code_running','unknown_code','live','missing_live','library','reverse_library','input_dependency',
    'foreign_owner','foreign_org','stale','tamper','criteria_marker'])
def test_delete_refuses_missing_or_conflicting_native_evidence_before_effect(tmp_path,fault):
    kwargs={}
    if fault=='completed':kwargs.update(status='Completed.',basis='no_completed_backtest')
    elif fault=='nonzero_orders':kwargs.update(status='Completed.',basis='verification_only',orders='1')
    elif fault=='unknown_orders':kwargs.update(status='Completed.',basis='verification_only',orders=None)
    elif fault=='nonterminal':kwargs['status']='In Progress...'
    elif fault=='missing_completed':kwargs['job_changes']={'completed':None}
    elif fault=='code_running':kwargs['meta_changes']={'codeRunning':True}
    elif fault=='unknown_code':kwargs['meta_changes']={'codeRunning':None}
    elif fault=='live':kwargs['meta_changes']={'lastLiveDeployment':'2020-01-01T00:00:00Z'}
    elif fault=='missing_live':kwargs['meta_changes']={'lastLiveDeployment':'unknown'}
    elif fault=='library':kwargs['meta_changes']={'libraries':[{'projectId':1234}]}
    elif fault=='reverse_library':kwargs['inventory_extra']=[project(9999,libraries=[{'projectId':PROJECT}])]
    elif fault=='input_dependency':kwargs['input_dependencies']=[38609822]
    elif fault=='foreign_owner':kwargs['meta_changes']={'ownerId':43}
    elif fault=='foreign_org':kwargs['meta_changes']={'organizationId':'f'*32}
    registry,index,criteria,index_body,criteria_body=archived(tmp_path,**kwargs)
    if fault in ('stale','criteria_marker'):
        if fault=='stale':criteria_body['created_utc']=(NOW-timedelta(seconds=900)).isoformat()
        else:criteria_body['eligible']=True
        criteria=store(tmp_path/'inputs','changed-criteria.json',criteria_body)
    if fault=='tamper':index={**index,'sha256':'f'*64}
    out=run(tmp_path,delete_plan(registry,index,criteria),lambda *_:pytest.fail('invalid evidence must not delete'))
    assert out['status']=='failed_or_uncertain' and out['request_attempted'] is False and out['delete_attempted'] is False
    assert not (tmp_path/'cleanup'/('project.'+str(PROJECT)+'.delete.spent.json')).exists()


@pytest.mark.parametrize('pid',sorted(m.OLD_IDS-m.DELETE_CANDIDATES))
def test_completed_or_mixed_historical_projects_are_always_delete_protected(tmp_path,pid):
    registry=fixture_registry(tmp_path/'inputs')
    with pytest.raises(m.CleanupRefusal):plan(registry,'delete',project_id=pid)


@pytest.mark.parametrize('fault',['timeout','500','secret'])
def test_unknown_delete_is_retained_without_retry_and_spends_exact_project(tmp_path,fault):
    registry,index,criteria,*_=archived(tmp_path);prepared=delete_plan(registry,index,criteria);calls=[]
    def transport(*_):
        calls.append('once')
        if fault=='timeout':raise TimeoutError('PRIVATE-ERROR')
        return response({'success':False,'errors':[TOKEN if fault=='secret' else 'PRIVATE-ERROR']},500)
    out=run(tmp_path,prepared,transport)
    assert out['status']=='failed_or_uncertain' and out['delete_outcome_unknown'] is True and calls==['once']
    second=delete_plan(registry,index,criteria,operation_id='TPR107-CLEANUP-SYNTHETIC-delete-second')
    again=run(tmp_path,second,transport)
    assert again['request_attempted'] is False and calls==['once']
    if fault=='500':assert out['raw_response'] is not None and out['http_status']==500
    if fault=='secret':assert out['raw_response'] is None
    assert TOKEN not in json.dumps(out) and 'PRIVATE-ERROR' not in json.dumps(out)


@pytest.mark.parametrize('state',['recycle','still_active','not_returned'])
def test_delete_ack_requires_separate_exact_readback_without_permanent_deletion_claim(tmp_path,state):
    registry,index,criteria,*_=archived(tmp_path)
    deleted=run(tmp_path,delete_plan(registry,index,criteria),lambda *_:response({'success':True}))
    prepared=plan(registry,'delete_readback','readback',project_id=PROJECT,delete_result=deleted['receipt'])
    rows=[] if state=='not_returned' else [project(name='Recycle Bin/TargetPrice' if state=='recycle' else 'TargetPrice')]
    def transport(endpoint,raw,*_):
        assert endpoint=='projects/read' and json.loads(raw)=={'projectId':PROJECT}
        return response({'success':True,'projects':rows})
    out=run(tmp_path,prepared,transport)
    expected={'recycle':'recycle_bin_observed','still_active':'project_still_active','not_returned':'no_project_returned'}[state]
    assert out['status']=='completed' and out['projection']['readback_observation']==expected
    assert out['projection']['backend_permanent_deletion_proven'] is False


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_cancellation_and_fatal_priority_are_body_free_and_preserve_spent_delete(tmp_path,kind):
    registry,index,criteria,*_=archived(tmp_path)
    class Fatal(BaseException):pass
    def transport(*_):raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-ERROR')
    with pytest.raises(m.CleanupCancelled if kind=='cancel' else m.CleanupFatal) as caught:
        run(tmp_path,delete_plan(registry,index,criteria),transport)
    assert 'PRIVATE-ERROR' not in str(caught.value) and caught.value.report['delete_outcome_unknown'] is True
    assert caught.value.report['receipt_published'] is True


def test_unknown_registry_or_auth_owner_denies_before_data_acceptance(tmp_path):
    registry=fixture_registry(tmp_path/'inputs');registry['sha256']='f'*64
    out=run(tmp_path,plan(registry),lambda *_:pytest.fail('no credentials or call'))
    assert out['status']=='failed_or_uncertain' and out['request_attempted'] is False


def test_archive_completeness_cannot_be_asserted_at_a_full_100_row_page(tmp_path):
    registry,index,criteria,body,criterion=archived(tmp_path)
    rows=[project(PROJECT),*[project(1000+n) for n in range(99)]]
    page=store(tmp_path/'inputs','full-page.raw',{'success':True,'projects':rows})
    body['inventory_pages']=[{'start':0,'response':page}]
    index=store(tmp_path/'inputs','full-index.json',body)
    criterion['archive_index_sha256']=index['sha256'];criteria=store(tmp_path/'inputs','full-criteria.json',criterion)
    out=run(tmp_path,delete_plan(registry,index,criteria),lambda *_:pytest.fail('full page is not complete inventory'))
    assert out['request_attempted'] is False


@pytest.mark.parametrize('changes',[{'phase':'object/delete'},{'page_start':1},{'page_start':10000},
    {'seconds':61},{'project_id':PROJECT},{'mode':'source-marker'}])
def test_plan_cannot_widen_page_endpoint_seconds_or_marker_authority(tmp_path,changes):
    registry=fixture_registry(tmp_path/'inputs')
    with pytest.raises(m.CleanupRefusal):plan(registry,**changes)


def test_final_clock_fatal_cannot_leave_completed_status_or_private_body(tmp_path):
    registry=fixture_registry(tmp_path/'inputs');prepared=plan(registry);after=False;post_calls=0
    class Fatal(BaseException):pass
    def clock():
        nonlocal post_calls
        if after:
            post_calls+=1
            if post_calls==3:raise Fatal('PRIVATE-ERROR')
        return NOW+timedelta(seconds=31)
    def transport(*_):
        nonlocal after
        after=True;return response({'success':True,'projects':[]})
    with pytest.raises(m.CleanupFatal) as caught:
        m._execute_fixture(prepared,tmp_path/'cleanup',tmp_path/'inputs',transport=transport,clock=clock)
    assert caught.value.report['status']=='failed_or_uncertain'
    assert caught.value.report['receipt_published'] is True and 'PRIVATE-ERROR' not in str(caught.value)
