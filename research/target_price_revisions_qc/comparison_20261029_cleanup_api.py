"""Bounded owner cleanup: metadata inventory, exact lane archive reads, one delete.

No import/preparation performs I/O. Eleven old IDs are public-record membership,
not deletion permission. Nine historical/mixed Completed projects and the new
five are deletion-protected. Two candidates still need fresh source/job archives,
actual ownership/activity/library checks and derived eligibility. There is no
ObjectStore, source write, compile, job launch, cancellation or restore endpoint.
REST deletion has no promised rollback/CAS; its acknowledgement needs a separately
claimed exact readback. All raw artifacts stay private; source/notebook bytes are
hashed and archived only, never executed or included in the returned projection.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

from . import comparison_20261029_projects as projects, extended_operations as ops, extended_evidence as e

LANE,BRANCH=ops.LANE,ops.BRANCH
MODULE='research/target_price_revisions_qc/comparison_20261029_cleanup_api.py'
PROJECTS_MODULE=projects.MODULE
REQUIRED_SOURCES=projects.REQUIRED_SOURCES|frozenset((MODULE,))
PRIVATE_ROOT=ops.PRIVATE_PARENT/'TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1'/'cleanup-20261029'
ARTIFACT_ROOT=LANE/'artifacts/target_price_qc_recovery_20261028'
OWNER_SHA256='9e18992045573478e564b4fff454c714443533daa07de24dcbc043a785a24fad'
REGISTRY={'name':'TPR-CMP28-R107-PROJECT-BINDINGS-001.json','bytes':3573,
    'sha256':'154e8ff056eb776f070fd73922b724367e634b1b37d4052b70a464601d0c94f1'}
# Sole public record §§68.7.1,71.3/71.6,72.3/72.5,75.19/75.21.
OLD_IDS=frozenset((37524929,37539994,37540034,37540080,37540122,37540166,
    37547067,37600675,37600676,37650453,37650980))
PROTECTED_IDS=frozenset((38609822,38609834,38609836,38609837,38609840))
DELETE_CANDIDATES=frozenset((37540166,37650453))
MEMBERSHIP_SHA256='f3ded2bbc4978c919c612669292ae480ce4144a88f1ca1148a991786fa3d3c6e'
VERIFICATION_BASIS={37540166:'sole_lane_record_68.7.2_QC6_REMX_zero_selection_zero_trade'}
VERIFICATION_JOB_IDS={37540166:frozenset(('b4f867f657b98fa29a070be9f7942693',))}
PHASES=frozenset(('inventory','lane_sources','lane_jobs','lane_job','delete','delete_readback'))
MAX_RESPONSE=2*1024*1024
MAX_JOBS=1000
TERMINAL=frozenset(('Completed','Completed.','Runtime Error','RuntimeError','Error','Stopped','Cancelled','Canceled'))
COMPLETED=frozenset(('Completed','Completed.'))


class CleanupRefusal(ValueError):pass
class CleanupCancelled(KeyboardInterrupt):
    def __init__(self,report):
        self.report=_clone(report);super().__init__('cleanup cancelled; no automatic retry')
class CleanupFatal(BaseException):
    def __init__(self,report):
        self.report=_clone(report);super().__init__('cleanup stopped; no automatic retry')


def _fail():raise CleanupRefusal('bounded lane cleanup refused; no automatic retry') from None
_sha,_canonical,_clone=projects._sha,projects._canonical,projects._clone
_publish,_native_request=projects._publish,projects._native_request
_hash,_name,_integer,_instant,_closed=projects._hash,projects._name,projects._integer,projects._instant,projects._closed


def _descriptor(value,maximum=MAX_RESPONSE):
    _closed(value,{'name','bytes','sha256'});_name(value['name']);_hash(value['sha256'])
    count=_integer(value['bytes'],1,maximum)
    return {'name':value['name'],'bytes':count,'sha256':value['sha256']}


def prepare_plan(*,operation_id,git_head,source_hashes,owner_instruction_sha256,
        created_utc,expires_utc,phase,registry_file=None,project_id=None,job_id=None,
        page_start=0,archive_index=None,criteria_file=None,delete_result=None,seconds=40,mode='production'):
    """Pure ONE-request plan. All descriptors are basenames in fixed private roots.

    registry/archive/criteria and their indexed raw captures live in ARTIFACT_ROOT;
    delete_result is a previous safe .result.json in this adapter's PRIVATE_ROOT.
    inventory never grants a project write or proves account-wide completeness.
    """
    try:
        _name(operation_id)
        if len(operation_id)>76:_fail()
        _hash(git_head,40);_hash(owner_instruction_sha256)
        if phase not in PHASES or mode not in ('production','offline-fixture'):_fail()
        if mode=='production' and owner_instruction_sha256!=OWNER_SHA256:_fail()
        issued,expires=_instant(created_utc),_instant(expires_utc)
        if not 0<(expires-issued).total_seconds()<=600:_fail()
        _integer(seconds,1,60)
        if seconds>(expires-issued).total_seconds():_fail()
        if type(source_hashes) is not dict or set(source_hashes)!=REQUIRED_SOURCES:_fail()
        for digest in source_hashes.values():_hash(digest)
        registry_file=dict(REGISTRY) if registry_file is None else registry_file
        _descriptor(registry_file,128*1024)
        if mode=='production' and registry_file!=REGISTRY:_fail()
        if phase=='inventory':
            if project_id is not None or job_id is not None:_fail()
            _integer(page_start,0,9900)
            if page_start%100:_fail()
        else:
            if _integer(project_id) not in OLD_IDS or project_id in PROTECTED_IDS or page_start!=0:_fail()
            if phase=='lane_job':
                if type(job_id) is not str or re.fullmatch('[a-f0-9]{32}',job_id) is None:_fail()
            elif job_id is not None:_fail()
        if phase=='delete':
            if project_id not in DELETE_CANDIDATES:_fail()
            _descriptor(archive_index,128*1024);_descriptor(criteria_file,64*1024)
        elif archive_index is not None or criteria_file is not None:_fail()
        if phase=='delete_readback':
            if project_id not in DELETE_CANDIDATES:_fail()
            _descriptor(delete_result,MAX_RESPONSE)
            if not delete_result['name'].endswith('.result.json'):_fail()
        elif delete_result is not None:_fail()
        return _clone(dict(schema='tpr-cmp29-cleanup-plan-v1',operation_id=operation_id,git_head=git_head,
            source_hashes=source_hashes,owner_instruction_sha256=owner_instruction_sha256,
            created_utc=created_utc,expires_utc=expires_utc,phase=phase,registry_file=registry_file,
            project_id=project_id,job_id=job_id,page_start=page_start,archive_index=archive_index,
            criteria_file=criteria_file,delete_result=delete_result,seconds=seconds,mode=mode,automatic_retry=False))
    except CleanupRefusal:raise
    except Exception:_fail()


def _validated(plan):
    _closed(plan,{'schema','operation_id','git_head','source_hashes','owner_instruction_sha256','created_utc',
        'expires_utc','phase','registry_file','project_id','job_id','page_start','archive_index','criteria_file',
        'delete_result','seconds','mode','automatic_retry'})
    args={key:value for key,value in plan.items() if key not in {'schema','automatic_retry'}}
    if _canonical(plan)!=_canonical(prepare_plan(**args)):_fail()
    return _clone(plan)


def _guard(plan):
    if Path.cwd()!=LANE or Path.cwd().resolve()!=LANE:_fail()
    def git(*args):return subprocess.run(['git',*args],cwd=LANE,capture_output=True,check=True,timeout=10).stdout
    if (git('rev-parse','--show-toplevel').decode().strip()!=str(LANE)
            or git('branch','--show-current').decode().strip()!=BRANCH
            or git('rev-parse','HEAD').decode().strip()!=plan['git_head']):_fail()
    git('status','--short')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE_ROOT)],cwd=LANE,capture_output=True,timeout=10).returncode:_fail()
    if (Path(__file__)!=LANE/MODULE or Path(projects.__file__)!=LANE/PROJECTS_MODULE
            or Path(ops.__file__)!=LANE/'research/target_price_revisions_qc/extended_operations.py'
            or Path(e.__file__)!=LANE/'research/target_price_revisions_qc/extended_evidence.py'):_fail()
    for name,digest in plan['source_hashes'].items():
        path=LANE/name
        if path.resolve()!=path or path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_RESPONSE:_fail()
        raw=path.read_bytes()
        if _sha(raw)!=digest or git('show',plan['git_head']+':'+name)!=raw:_fail()


def _body(raw):
    body=e.parse_json(raw)
    if type(body) is not dict or body.get('success') is not True or body.get('errors') not in (None,[]):_fail()
    return body


def _returned(body,project):
    if 'projectId' in body and _integer(body['projectId'])!=project:_fail()


def _inventory(raw):
    body=_body(raw);rows=body.get('projects')
    if type(rows) is not list or len(rows)>100:_fail()
    result=[];seen=set()
    for row in rows:
        if type(row) is not dict:_fail()
        pid=_integer(row.get('projectId'))
        if pid in seen:_fail()
        seen.add(pid);name=row.get('name');org=row.get('organizationId');libraries=row.get('libraries')
        if type(name) is not str or not 1<=len(name)<=200:_fail()
        dependencies=None
        if type(libraries) is list and len(libraries)<=100:
            dependencies=[]
            for library in libraries:
                if type(library) is not dict:_fail()
                dependencies.append(_integer(library.get('projectId')))
            if len(dependencies)!=len(set(dependencies)):_fail()
        result.append({'project_id':pid,'name':name,'owner':row.get('owner') if type(row.get('owner')) is bool else None,
            'organization_sha256':_sha(org.encode()) if type(org) is str else None,'library_project_ids':dependencies})
    return result


def project_source_inventory(raw,*,project_id):
    """Pure hash projection of exact own-source bytes; never execute notebooks."""
    body=_body(raw);_returned(body,project_id);files=body.get('files')
    if type(files) is not list or not 0<len(files)<=100:_fail()
    result={}
    for row in files:
        if type(row) is not dict:_fail()
        _returned(row,project_id);name=row.get('name');content=row.get('content')
        if (type(name) is not str or not 1<=len(name)<=200 or name in result or type(content) is not str):_fail()
        raw_content=content.encode('utf-8')
        result[name]={'bytes':len(raw_content),'sha256':_sha(raw_content)}
    return result


def project_job_census(raw,*,project_id):
    """Pure native list status projection; status does not invent completedbool."""
    body=_body(raw);_returned(body,project_id);jobs=body.get('backtests')
    if type(jobs) is not list or len(jobs)>MAX_JOBS or _integer(body.get('count'),0,MAX_JOBS)!=len(jobs):_fail()
    result=[];seen=set()
    for row in jobs:
        if type(row) is not dict:_fail()
        _returned(row,project_id);job=row.get('backtestId');status=row.get('status')
        if type(job) is not str or re.fullmatch('[a-f0-9]{32}',job) is None or job in seen:_fail()
        seen.add(job)
        result.append({'backtest_id':job,'status':status if type(status) is str and status in TERMINAL else 'nonterminal_or_unknown'})
    return sorted(result,key=lambda row:row['backtest_id'])


def _job(raw,project,job):
    body=_body(raw);_returned(body,project);row=body.get('backtest')
    if type(row) is not dict:_fail()
    _returned(row,project)
    if row.get('backtestId')!=job or type(row.get('completed')) is not bool:_fail()
    status=row.get('status');statistics=row.get('statistics');orders=None
    if type(statistics) is dict:
        value=statistics.get('Total Orders')
        if type(value) is str and re.fullmatch(r'(0|[1-9][0-9]{0,8})',value):orders=int(value)
        elif type(value) in (int,e.JsonNumber):
            try:orders=_integer(value,0,10**9-1)
            except Exception:pass
    return {'backtest_id':job,'status':status if type(status) is str and status in TERMINAL else 'nonterminal_or_unknown',
        'completed':row['completed'],'total_orders':orders}


def _fresh(body,plan):
    elapsed=(_instant(plan['created_utc'])-_instant(body['created_utc'])).total_seconds()
    if not 0<=elapsed<=600:_fail()


def _delete_evidence(plan,registry,load):
    index=load('archive-index',plan['archive_index']);criteria=load('criteria',plan['criteria_file'])
    index=e.parse_json(index);criteria=e.parse_json(criteria);project=plan['project_id']
    _closed(index,{'schema','project_id','created_utc','owner_instruction_sha256','registry_sha256',
        'inventory_pages','sources','jobs','job_results','input_dependency_project_ids'})
    _closed(criteria,{'schema','project_id','created_utc','owner_instruction_sha256','registry_sha256',
        'archive_index_sha256','basis','source_inventory_sha256','job_census_sha256'})
    for body,schema in ((index,'tpr-cmp29-cleanup-archive-index-v1'),(criteria,'tpr-cmp29-cleanup-criteria-v1')):
        if (body['schema']!=schema or _integer(body['project_id'])!=project
                or body['owner_instruction_sha256']!=plan['owner_instruction_sha256']
                or body['registry_sha256']!=plan['registry_file']['sha256']):_fail()
        _fresh(body,plan)
    if criteria['archive_index_sha256']!=plan['archive_index']['sha256']:_fail()
    dependencies=index['input_dependency_project_ids']
    if type(dependencies) is not list or dependencies:_fail()
    pages=index['inventory_pages']
    if type(pages) is not list or not 1<=len(pages)<=100:_fail()
    all_projects={};target=None
    for ordinal,page in enumerate(pages):
        _closed(page,{'start','response'})
        if _integer(page['start'],0,9900)!=ordinal*100:_fail()
        raw=load('inventory-'+str(ordinal),page['response']);rows=_inventory(raw)
        if ordinal<len(pages)-1 and len(rows)!=100 or ordinal==len(pages)-1 and len(rows)>=100:_fail()
        body=_body(raw)
        for original,safe in zip(body['projects'],rows):
            pid=safe['project_id']
            if pid in all_projects or safe['library_project_ids'] is None:_fail()
            all_projects[pid]=safe
            if project in safe['library_project_ids']:_fail()
            if pid==project:target=original
    if (type(target) is not dict or _integer(target.get('ownerId'))!=registry['owner_id']
            or target.get('owner') is not True or target.get('organizationId')!=registry['organization_id']
            or target.get('codeRunning') is not False or 'lastLiveDeployment' not in target
            or target['lastLiveDeployment'] is not None or all_projects[project]['library_project_ids']):_fail()
    source_raw=load('sources',index['sources']);sources=project_source_inventory(source_raw,project_id=project)
    jobs_raw=load('jobs',index['jobs']);jobs=project_job_census(jobs_raw,project_id=project)
    source_hash=_sha(_canonical(sources));jobs_hash=_sha(_canonical(jobs))
    if criteria['source_inventory_sha256']!=source_hash or criteria['job_census_sha256']!=jobs_hash:_fail()
    if any(row['status'] not in TERMINAL for row in jobs):_fail()
    records=index['job_results']
    if type(records) is not dict or set(records)!={row['backtest_id'] for row in jobs}:_fail()
    completed=[]
    for ordinal,row in enumerate(jobs):
        actual=_job(load('job-'+str(ordinal),records[row['backtest_id']]),project,row['backtest_id'])
        if actual['status']!=row['status'] or actual['completed'] is not True:_fail()
        if actual['status'] in COMPLETED:
            completed.append(actual)
    basis=criteria['basis']
    if basis=='no_completed_backtest':
        if completed:_fail()
    elif basis=='verification_only':
        if (project not in VERIFICATION_BASIS or any(row['backtest_id'] not in VERIFICATION_JOB_IDS[project]
                or row['total_orders']!=0 for row in completed)):_fail()
    else:_fail()
    return {'basis':basis,'source_inventory_sha256':source_hash,'job_census_sha256':jobs_hash,
        'archived_sources':len(sources),'archived_jobs':len(jobs),'completed_jobs':len(completed),
        'observed_reverse_library_dependencies':0,'input_dependencies_in_scoped_root_review':0,
        'public_verification_basis':VERIFICATION_BASIS.get(project) if basis=='verification_only' else None,
        'dependency_backend_completeness_independently_attested':False}


def _execute(plan,root,input_root,*,transport,guard,clock,monotonic):
    plan=_validated(plan);frozen=_canonical(plan);started=monotonic();previous=None
    if (plan['mode']=='production' and (root!=PRIVATE_ROOT or input_root!=ARTIFACT_ROOT
            or transport is not _native_request or guard is not _guard or clock is not _utcnow or monotonic is not time.monotonic)
            or plan['mode']=='offline-fixture' and (root.is_relative_to(LANE) or input_root.is_relative_to(LANE)
                or transport is _native_request)):_fail()
    def check():
        nonlocal previous
        guard(plan);now,tick=clock(),monotonic()
        if (type(now) is not datetime or now.utcoffset()!=timedelta(0)
                or not _instant(plan['created_utc'])<=now<_instant(plan['expires_utc'])
                or type(tick) not in (int,float) or not 0<=tick-started<600
                or previous is not None and (now<previous[0] or tick<previous[1]) or _canonical(plan)!=frozen):_fail()
        previous=now,tick
    check()
    if root.resolve()!=root or input_root.resolve()!=input_root:_fail()
    if plan['mode']=='production':
        for path in (ops.PRIVATE_PARENT,PRIVATE_ROOT.parent,PRIVATE_ROOT):
            path.mkdir(mode=0o700,exist_ok=True);ops._custody(path.lstat(),True)
    else:root.mkdir(mode=0o700,exist_ok=True);ops._custody(root.lstat(),True)
    operation=plan['operation_id'];phase=plan['phase'];project=plan['project_id'];lock=None;failure=None
    report={'schema':'tpr-cmp29-cleanup-result-v1','operation_id':operation,'phase':phase,'project_id':project,
        'git_head':plan['git_head'],'source_hashes':plan['source_hashes'],'owner_instruction_sha256':plan['owner_instruction_sha256'],
        'registry_sha256':plan['registry_file']['sha256'],'plan_sha256':_sha(frozen),'status':'failed_or_uncertain',
        'input_claims':[],'request_claim':None,'endpoint':None,'request_attempted':False,'http_status':None,
        'raw_response':None,'projection':None,'delete_attempted':False,'delete_outcome_unknown':False,
        'receipt_published':False,'lock_cleanup_complete':False,'observed_utc':None,'automatic_retry':False,
        'actual_delete_readback_required':phase=='delete','atomic_remote_compare_and_swap_proven':False,
        'backend_rollback_proven':False,'object_store_deleted':False,'financial_results_accepted':False}
    _publish(root,operation+'.operation.spent.json',frozen)
    try:
        lock=os.open(root/'cleanup.lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        ops._custody(os.fstat(lock));os.write(lock,_canonical({'operation_id':operation}));os.fsync(lock)
        read_count=0
        def load(label,descriptor,output=False):
            nonlocal read_count
            descriptor=_descriptor(descriptor);read_count+=1
            if read_count>1206:_fail()
            check();claim=_publish(root,operation+'.read-'+str(read_count)+'.spent.json',_canonical({'label':label,'descriptor':descriptor}))
            report['input_claims'].append(claim)
            check();raw=ops.read_private(root if output else input_root,descriptor['name'],MAX_RESPONSE);check()
            if len(raw)!=_integer(descriptor['bytes']) or _sha(raw)!=descriptor['sha256']:_fail()
            return raw
        registry_raw=load('registry',plan['registry_file'])
        registry=projects.validate_bindings(registry_raw,expected_sha256=plan['registry_file']['sha256'])
        if (registry['adapter_source_sha256']!=plan['source_hashes'][PROJECTS_MODULE]
                or {row['project_id'] for row in registry['projects'].values()}!=PROTECTED_IDS):_fail()
        owner=registry['owner_id'];endpoint=None;payload=None
        if phase=='inventory':endpoint,payload='projects/read',{'start':plan['page_start'],'end':plan['page_start']+100}
        elif phase=='lane_sources':endpoint,payload='files/read',{'projectId':project}
        elif phase=='lane_jobs':endpoint,payload='backtests/list',{'projectId':project,'includeStatistics':True}
        elif phase=='lane_job':endpoint,payload='backtests/read',{'projectId':project,'backtestId':plan['job_id']}
        elif phase=='delete':
            report['eligibility']=_delete_evidence(plan,registry,load)
            check();_publish(root,'project.'+str(project)+'.delete.spent.json',_canonical({'project_id':project,
                'plan_sha256':report['plan_sha256'],'archive_index':plan['archive_index'],'criteria_file':plan['criteria_file'],
                'owner_instruction_sha256':plan['owner_instruction_sha256']}))
            endpoint,payload='projects/delete',{'projectId':project}
        else:
            prior=json.loads(load('delete-result',plan['delete_result'],True).decode('ascii'),object_pairs_hook=projects._pairs)
            if (type(prior) is not dict or prior.get('schema')!='tpr-cmp29-cleanup-result-v1' or prior.get('phase')!='delete'
                    or prior.get('project_id')!=project or prior.get('delete_attempted') is not True
                    or prior.get('owner_instruction_sha256')!=plan['owner_instruction_sha256']
                    or prior.get('registry_sha256')!=plan['registry_file']['sha256']):_fail()
            endpoint,payload='projects/read',{'projectId':project}
        report['endpoint']=endpoint
        check();report['request_claim']=_publish(root,operation+'.request.spent.json',_canonical({'endpoint':endpoint,
            'payload_sha256':_sha(_canonical(payload)),'seconds':plan['seconds'],'max_response_bytes':MAX_RESPONSE,'plan_sha256':report['plan_sha256']}))
        check();report.update(request_attempted=True,delete_attempted=phase=='delete',delete_outcome_unknown=phase=='delete')
        raw,status,token,uid=transport(endpoint,_canonical(payload),plan['seconds'],MAX_RESPONSE,owner)
        check()
        if _integer(uid)!=owner or type(status) is not int or not 100<=status<=599 or type(raw) is not bytes or not 0<len(raw)<=MAX_RESPONSE:_fail()
        report['http_status']=status;e.project_wire(raw,credential=token)
        report['raw_response']=_publish(root,operation+'.response.raw',raw)
        if status!=200:_fail()
        body=_body(raw)
        if phase=='inventory':report['projection']={'projects':_inventory(raw),'page_start':plan['page_start'],
            'page_end':plan['page_start']+100,'returned_count':len(body['projects']),
            'short_page_observed':len(body['projects'])<100,'complete_account_inventory_independently_attested':False}
        elif phase=='lane_sources':
            source=project_source_inventory(raw,project_id=project)
            report['projection']={'source_inventory':source,'source_inventory_sha256':_sha(_canonical(source))}
        elif phase=='lane_jobs':
            jobs=project_job_census(raw,project_id=project)
            report['projection']={'jobs':jobs,'returned_count':len(jobs),'job_census_sha256':_sha(_canonical(jobs)),
                'completed_bools_inferred':False}
        elif phase=='lane_job':report['projection']=_job(raw,project,plan['job_id'])
        elif phase=='delete':
            _returned(body,project);report['delete_outcome_unknown']=False
            report['projection']={'delete_acknowledged':True,'readback_performed':False}
        else:
            rows=body.get('projects')
            if type(rows) is not list or len(rows)>1:_fail()
            if not rows:observation='no_project_returned'
            else:
                row=rows[0]
                if (type(row) is not dict or _integer(row.get('projectId'))!=project or row.get('owner') is not True
                        or _integer(row.get('ownerId'))!=owner or row.get('organizationId')!=registry['organization_id']
                        or type(row.get('name')) is not str):_fail()
                observation='recycle_bin_observed' if row['name'].startswith('Recycle Bin/') else 'project_still_active'
            report['projection']={'readback_observation':observation,'backend_permanent_deletion_proven':False}
        check();report['status']='delete_acknowledged_readback_required' if phase=='delete' else 'completed'
    except BaseException as error:failure=error
    finally:
        if lock is not None:
            try:
                current=os.stat(root/'cleanup.lock',follow_symlinks=False);owned=os.fstat(lock)
                if (current.st_dev,current.st_ino)!=(owned.st_dev,owned.st_ino):_fail()
                os.unlink(root/'cleanup.lock');os.close(lock);lock=None;report['lock_cleanup_complete']=True
            except BaseException as error:failure=projects._stop(failure,error)
            finally:
                if lock is not None:
                    try:os.close(lock)
                    except BaseException as error:failure=projects._stop(failure,error)
        if failure is not None:
            report['status']='cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed_or_uncertain'
            report['delete_outcome_unknown']=report['delete_attempted']
        try:report['observed_utc']=clock().isoformat()
        except BaseException as error:
            failure=projects._stop(failure,error)
            report['status']='cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed_or_uncertain'
        report['receipt_published']=True;receipt=None
        try:receipt=_publish(root,operation+'.result.json',_canonical(report))
        except BaseException as error:
            report['receipt_published']=False;failure=projects._stop(failure,error)
            report['status']='cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed_or_uncertain'
    if isinstance(failure,KeyboardInterrupt):raise CleanupCancelled(report) from None
    if failure is not None and not isinstance(failure,Exception):raise CleanupFatal(report) from None
    return {**_clone(report),'receipt':receipt}


def _utcnow():return datetime.now(timezone.utc)
def execute_plan(plan):
    try:
        if type(plan) is not dict or plan.get('mode')!='production':_fail()
        return _execute(plan,PRIVATE_ROOT,ARTIFACT_ROOT,transport=_native_request,guard=_guard,clock=_utcnow,monotonic=time.monotonic)
    except (CleanupCancelled,CleanupFatal):raise
    except Exception:_fail()


def _execute_fixture(plan,root,input_root,*,transport,clock,guard=lambda _:None,monotonic=lambda:0.0):
    if plan.get('mode')!='offline-fixture':_fail()
    return _execute(plan,root,input_root,transport=transport,clock=clock,guard=guard,monotonic=monotonic)
