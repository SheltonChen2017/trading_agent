"""Five reserved owner projects: source-bound one-shot metadata/create adapter.

No import or pure preparation performs I/O. Project privacy is QC's documented
private default plus observed owner/org/collaborators, not a nonexistent API
privacy attestation. Every native call and prerequisite read has a fresh durable
claim. A create name is permanently spent before credentials: uncertain delivery
can only be reconciled by reads, never retried. No source/job/store/share actions.
Official endpoints and limits on the published privacy schema:
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/project-management/create-project
https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/project-management/read-project
https://www.quantconnect.com/docs/v2/cloud-platform/security-and-ip
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import time

from . import extended_operations as ops, extended_evidence as e

LANE, BRANCH = ops.LANE, ops.BRANCH
MODULE = 'research/target_price_revisions_qc/comparison_20261029_projects.py'
REQUIRED_SOURCES = frozenset((MODULE, 'research/target_price_revisions_qc/extended_operations.py',
    'research/target_price_revisions_qc/extended_evidence.py', 'research/__init__.py',
    'research/target_price_revisions_qc/__init__.py'))
ROUND_ID = 'TPR-CMP28-R107-20261029A'
ARMS = ('OFF', 'TPR050', 'TPR100', 'TPR200LONG', 'PURE')
RESERVED_NAMES = {arm: ROUND_ID + '-' + arm for arm in ARMS}
OLD_PROJECT = 37650980
HISTORICAL_PROJECTS = frozenset((37650980, 37650453))
PRIVATE_ROOT = ops.PRIVATE_PARENT / 'TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1' / 'projects-20261029A'
MAX_RESPONSE, MAX_RESULT, MAX_LIST = 2*1024*1024, 128*1024, 100
PRIVACY_BASIS = 'documented_private_default_and_observed_collaborators'
PHASES = frozenset(('baseline', 'create', 'read', 'collaborators', 'reconcile'))


class ProjectRefusal(ValueError): pass
class ProjectCancelled(KeyboardInterrupt):
    def __init__(self, report):
        self.report = _clone(report)
        super().__init__('five-project operation cancelled; no automatic retry')
class ProjectFatal(BaseException):
    def __init__(self, report):
        self.report = _clone(report)
        super().__init__('five-project operation stopped; no automatic retry')


def _fail(): raise ProjectRefusal('five-project scope refused; no automatic retry') from None
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
def _clone(value): return json.loads(_canonical(value))
def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys): _fail()
def _hash(value, size=64):
    if type(value) is not str or re.fullmatch('[a-f0-9]{'+str(size)+'}', value) is None or set(value)=={'0'}: _fail()
    return value
def _name(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,119}', value) is None: _fail()
    return value
def _integer(value, minimum=1, maximum=2**63-1):
    if type(value) is e.JsonNumber and value.fraction().denominator == 1: value=int(value.fraction())
    if type(value) is not int or not minimum <= value <= maximum: _fail()
    return value
def _instant(value):
    if type(value) is not str or len(value)>40: _fail()
    result=datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset()!=timedelta(0): _fail()
    return result

def _descriptor(value):
    _closed(value, {'name','bytes','sha256'})
    _name(value['name']); _integer(value['bytes'], 1, MAX_RESULT); _hash(value['sha256'])
    if not value['name'].endswith('.result.json'): _fail()
    return value


def prepare_plan(*, operation_id, git_head, source_hashes, owner_instruction_sha256,
        created_utc, expires_utc, phase, arm=None, baseline=None, prior=None,
        page_start=0, page_end=100, seconds=30, mode='production'):
    """Pure one-request plan; dependent IDs come from exact private receipts.

    baseline: old37650980 owned-project metadata. create: one fixed arm/name.
    read: create or successful reconciliation receipt. collaborators: exact read
    receipt. reconcile: an unknown create receipt, one bounded metadata page.
    Caller must retain the returned result descriptor for the next fresh plan.
    """
    try:
        _name(operation_id); _hash(git_head,40); _hash(owner_instruction_sha256)
        if len(operation_id)>80: _fail()
        if phase not in PHASES or mode not in ('production','offline-fixture'): _fail()
        issued,expires=_instant(created_utc),_instant(expires_utc)
        if not 0 < (expires-issued).total_seconds() <= 600: _fail()
        _integer(seconds,1,40)
        if seconds>(expires-issued).total_seconds(): _fail()
        if type(source_hashes) is not dict or set(source_hashes)!=REQUIRED_SOURCES: _fail()
        for digest in source_hashes.values(): _hash(digest)
        if phase=='baseline':
            if arm is not None or baseline is not None or prior is not None: _fail()
        else:
            if type(arm) is not str or arm not in RESERVED_NAMES: _fail()
            _descriptor(baseline)
            if phase=='create':
                if prior is not None: _fail()
            else: _descriptor(prior)
        _integer(page_start,0,900); _integer(page_end,1,1000)
        if page_start%100 or page_end!=page_start+100 or phase!='reconcile' and (page_start,page_end)!=(0,100): _fail()
        result=dict(schema='tpr-cmp28-project-plan-v1',round_id=ROUND_ID,operation_id=operation_id,
            git_head=git_head,source_hashes=source_hashes,owner_instruction_sha256=owner_instruction_sha256,
            created_utc=created_utc,expires_utc=expires_utc,phase=phase,arm=arm,baseline=baseline,prior=prior,
            page_start=page_start,page_end=page_end,seconds=seconds,mode=mode,automatic_retry=False)
        return _clone(result)
    except ProjectRefusal: raise
    except Exception: _fail()


def _validated(plan):
    _closed(plan, {'schema','round_id','operation_id','git_head','source_hashes','owner_instruction_sha256',
        'created_utc','expires_utc','phase','arm','baseline','prior','page_start','page_end','seconds','mode','automatic_retry'})
    args={key:value for key,value in plan.items() if key not in {'schema','round_id','automatic_retry'}}
    if _canonical(prepare_plan(**args))!=_canonical(plan): _fail()
    return _clone(plan)


def _guard(plan):
    if Path.cwd()!=LANE or Path.cwd().resolve()!=LANE: _fail()
    def git(*args): return subprocess.run(['git',*args],cwd=LANE,capture_output=True,timeout=10,check=True).stdout
    if (git('rev-parse','--show-toplevel').decode().strip()!=str(LANE)
            or git('branch','--show-current').decode().strip()!=BRANCH
            or git('rev-parse','HEAD').decode().strip()!=plan['git_head']): _fail()
    git('status','--short')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE_ROOT)],cwd=LANE,capture_output=True,timeout=10).returncode: _fail()
    if (Path(__file__)!=LANE/MODULE or Path(ops.__file__)!=LANE/'research/target_price_revisions_qc/extended_operations.py'
            or Path(e.__file__)!=LANE/'research/target_price_revisions_qc/extended_evidence.py'): _fail()
    for name,digest in plan['source_hashes'].items():
        path=LANE/name
        if path.resolve()!=path or path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_RESPONSE: _fail()
        raw=path.read_bytes()
        if _sha(raw)!=digest or git('show',plan['git_head']+':'+name)!=raw: _fail()


def _publish(root,name,raw):
    _name(name)
    if type(raw) is not bytes or not 0<len(raw)<=MAX_RESPONSE: _fail()
    directory=fd=None
    try:
        directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);ops._custody(os.fstat(directory),True)
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        ops._custody(os.fstat(fd));offset=0
        while offset<len(raw):
            count=os.write(fd,raw[offset:])
            if count<=0: _fail()
            offset+=count
        os.fsync(fd);os.close(fd);fd=None;os.fsync(directory)
    finally:
        if fd is not None: os.close(fd)
        if directory is not None: os.close(directory)
    return {'name':name,'bytes':len(raw),'sha256':_sha(raw)}


def _native_request(endpoint,raw,seconds,maximum,expected_owner):
    # One HTTPS POST only: no SDK retry, redirect, cookie session, or token log.
    connection=None
    with ops.wall_deadline(seconds):
        user,token=ops.credential();uid=_integer(int(user))
        if expected_owner is not None and uid!=expected_owner: _fail()
        stamp=str(int(time.time()));signed=hashlib.sha256((token+':'+stamp).encode()).hexdigest()
        authorization=base64.b64encode((user+':'+signed).encode()).decode()
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.keylog_filename=None
        context.check_hostname=True;context.verify_mode=ssl.CERT_REQUIRED;context.load_default_certs()
        try:
            connection=http.client.HTTPSConnection('www.quantconnect.com',timeout=seconds,context=context)
            connection.request('POST','/api/v2/'+endpoint,body=raw,headers={'Authorization':'Basic '+authorization,
                'Timestamp':stamp,'Content-Type':'application/json'})
            response=connection.getresponse()
            return response.read(maximum+1),response.status,token,uid
        finally:
            if connection is not None: connection.close()


def _collaborators(rows,owner):
    if type(rows) is not list or len(rows)>100: _fail()
    safe=[];nonowner=0;seen=set()
    for row in rows:
        if type(row) is not dict: _fail()
        uid=_integer(row.get('uid'));owned=row.get('owner')
        if (type(owned) is not bool or row.get('permission') not in ('read','write')
                or type(row.get('liveControl')) is not bool or uid in seen): _fail()
        seen.add(uid);nonowner+=not (uid==owner and owned is True)
        safe.append({'uid':uid,'owner':owned,'permission':row['permission'],'liveControl':row['liveControl']})
    if nonowner: _fail()
    return {'collaborator_count':len(rows),'nonowner_collaborator_count':nonowner,
        'collaborators_sha256':_sha(_canonical(sorted(safe,key=lambda item:item['uid'])))}


def _metadata(row,*,owner,org=None,arm=None,project=None):
    if type(row) is not dict: _fail()
    pid=_integer(row.get('projectId'));oid=_integer(row.get('ownerId'))
    organization=row.get('organizationId');name=row.get('name')
    if (type(organization) is not str or re.fullmatch('[a-f0-9]{32}',organization) is None
            or oid!=owner or row.get('owner') is not True or row.get('language')!='Py'
            or type(name) is not str or not 1<=len(name)<=200
            or org is not None and organization!=org
            or project is not None and pid!=project): _fail()
    if arm is not None and (name!=RESERVED_NAMES[arm] or pid in HISTORICAL_PROJECTS): _fail()
    explicit=False
    for key,private_value in (('isPublic',False),('public',False),('isPrivate',True),('private',True),('shared',False)):
        if key in row:
            explicit=True
            if row[key] is not private_value: _fail()
    created=row.get('created');created_utc=None
    if created is not None:
        if type(created) is not str or not 1<=len(created)<=80: _fail()
        try:
            parsed=datetime.fromisoformat(created)
            if parsed.tzinfo is not None: created_utc=parsed.astimezone(timezone.utc).isoformat()
        except ValueError: pass
    result={'project_id':pid,'name':name,'organization_id':organization,'owner_id':oid,'language':'Py',
        'created_utc':created_utc,'created_value_sha256':_sha(_canonical(created)),
        'explicit_privacy_flag_observed':explicit}
    return {**result,**_collaborators(row.get('collaborators'),owner)}


REPORT_KEYS = frozenset(('schema round_id operation_id git_head source_hashes owner_instruction_sha256 phase arm '
    'plan_sha256 created_utc observed_utc status request http_status endpoint payload payload_sha256 request_claim '
    'baseline prior input_read_claims raw_response metadata collaboration create_attempted '
    'unknown_create automatic_retry receipt_published lock_cleanup_complete privacy_basis '
    'independent_native_origin_attested').split())


def _report(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_RESULT: _fail()
    body=json.loads(raw.decode('ascii'),object_pairs_hook=_pairs,parse_float=lambda _: _fail(),parse_constant=lambda _: _fail())
    _closed(body,REPORT_KEYS)
    if (body['schema']!='tpr-cmp28-project-result-v1' or body['round_id']!=ROUND_ID
            or body['phase'] not in PHASES or body['privacy_basis']!=PRIVACY_BASIS
            or body['automatic_retry'] is not False or body['independent_native_origin_attested'] is not False): _fail()
    return body


def _pairs(items):
    result={}
    for key,value in items:
        if key in result: _fail()
        result[key]=value
    return result


def _same_context(report,plan):
    if (report['git_head']!=plan['git_head'] or report['source_hashes']!=plan['source_hashes']
            or report['owner_instruction_sha256']!=plan['owner_instruction_sha256']
            or report['round_id']!=ROUND_ID): _fail()
    elapsed=(_instant(plan['created_utc'])-_instant(report['observed_utc'])).total_seconds()
    if not 0<=elapsed<=3600: _fail()


def _stop(first,second):
    if (first is None or isinstance(second,KeyboardInterrupt)
            or isinstance(first,Exception) and not isinstance(second,Exception)): return second
    return first


def _execute(plan,root,*,transport,guard,clock,monotonic):
    plan=_validated(plan);frozen=_canonical(plan);started=monotonic();previous=None
    if (plan['mode']=='production' and (root!=PRIVATE_ROOT or transport is not _native_request
            or guard is not _guard or clock is not _utcnow or monotonic is not time.monotonic)
            or plan['mode']=='offline-fixture' and (root==PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)): _fail()
    def check():
        nonlocal previous
        guard(plan);now,tick=clock(),monotonic()
        if (type(now) is not datetime or now.utcoffset()!=timedelta(0)
                or not _instant(plan['created_utc'])<=now<_instant(plan['expires_utc'])
                or type(tick) not in (int,float) or not 0<=tick-started<600
                or previous is not None and (now<previous[0] or tick<previous[1])
                or _canonical(plan)!=frozen): _fail()
        previous=now,tick
    check()
    if root.resolve()!=root: _fail()
    if plan['mode']=='production':
        for path in (ops.PRIVATE_PARENT,PRIVATE_ROOT.parent,PRIVATE_ROOT):
            path.mkdir(mode=0o700,exist_ok=True);ops._custody(path.lstat(),True)
    else: root.mkdir(mode=0o700,exist_ok=True);ops._custody(root.lstat(),True)
    operation=plan['operation_id'];phase=plan['phase'];arm=plan['arm'];lock=None;failure=None
    report=dict(schema='tpr-cmp28-project-result-v1',round_id=ROUND_ID,operation_id=operation,
        git_head=plan['git_head'],source_hashes=plan['source_hashes'],owner_instruction_sha256=plan['owner_instruction_sha256'],
        phase=phase,arm=arm,plan_sha256=_sha(frozen),created_utc=plan['created_utc'],observed_utc=None,
        status='failed_or_uncertain',request=False,http_status=None,endpoint=None,payload=None,payload_sha256=None,request_claim=None,
        baseline=plan['baseline'],prior=plan['prior'],input_read_claims=[],raw_response=None,metadata=None,collaboration=None,
        create_attempted=False,unknown_create=False,automatic_retry=False,receipt_published=False,
        lock_cleanup_complete=False,privacy_basis=PRIVACY_BASIS,independent_native_origin_attested=False)
    _publish(root,operation+'.operation.spent.json',frozen)
    try:
        lock=os.open(root/'five-projects.lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        ops._custody(os.fstat(lock));os.write(lock,_canonical({'operation_id':operation}));os.fsync(lock)
        directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
        def load(label,descriptor):
            check();claim=_publish(root,operation+'.'+label+'-read.spent.json',_canonical(descriptor))
            report['input_read_claims'].append(claim)
            check();raw=ops.read_private(root,descriptor['name'],MAX_RESULT);check()
            if len(raw)!=descriptor['bytes'] or _sha(raw)!=descriptor['sha256']: _fail()
            body=_report(raw);_same_context(body,plan);return body
        base=None;prior=None;owner=None;organization=None
        if phase!='baseline':
            base=load('baseline',plan['baseline'])
            if (base['phase']!='baseline' or base['status']!='completed' or base['metadata'] is None
                    or base['metadata']['project_id']!=OLD_PROJECT): _fail()
            owner=base['metadata']['owner_id'];organization=base['metadata']['organization_id']
            if phase!='create':
                prior=load('prior',plan['prior'])
                if prior['arm']!=arm: _fail()
        if phase=='baseline':endpoint,payload='projects/read',{'projectId':OLD_PROJECT}
        elif phase=='create':endpoint,payload='projects/create',{'name':RESERVED_NAMES[arm],'language':'Py','organizationId':organization}
        elif phase=='reconcile':
            if prior['phase']!='create' or prior['unknown_create'] is not True or prior['create_attempted'] is not True: _fail()
            endpoint,payload='projects/read',{'start':plan['page_start'],'end':plan['page_end']}
        else:
            if (prior['status']!='completed' or prior['phase'] not in (('create','reconcile') if phase=='read' else ('read',))
                    or type(prior['metadata']) is not dict): _fail()
            metadata=prior['metadata']
            if (metadata['name']!=RESERVED_NAMES[arm] or metadata['organization_id']!=organization
                    or metadata['owner_id']!=owner or metadata['project_id'] in HISTORICAL_PROJECTS): _fail()
            endpoint='projects/read' if phase=='read' else 'projects/collaboration/read'
            payload={'projectId':metadata['project_id']}
        report.update(endpoint=endpoint,payload=payload,payload_sha256=_sha(_canonical(payload)))
        if phase=='create':
            check();_publish(root,'name.'+arm+'.create.spent.json',_canonical({'round_id':ROUND_ID,'arm':arm,
                'name':RESERVED_NAMES[arm],'operation_id':operation,'plan_sha256':report['plan_sha256'],
                'organization_id':organization,'owner_id':owner,'baseline':plan['baseline']}))
        check();report['request_claim']=_publish(root,operation+'.request.spent.json',_canonical({
            'endpoint':endpoint,'payload_sha256':report['payload_sha256'],'seconds':plan['seconds'],
            'max_response_bytes':MAX_RESPONSE,'plan_sha256':report['plan_sha256']}))
        check();report.update(request=True,create_attempted=phase=='create',unknown_create=phase=='create')
        raw,status,token,authenticated_owner=transport(endpoint,_canonical(payload),plan['seconds'],MAX_RESPONSE,owner)
        check();authenticated_owner=_integer(authenticated_owner)
        if owner is not None and authenticated_owner!=owner: _fail()
        if (type(raw) is not bytes or not 0<len(raw)<=MAX_RESPONSE or type(status) is not int or not 100<=status<=599): _fail()
        report['http_status']=status
        e.project_wire(raw,credential=token);body=e.parse_json(raw)
        report['raw_response']=_publish(root,operation+'.response.raw',raw)
        if status!=200 or type(body) is not dict or body.get('success') is not True or body.get('errors') not in (None,[]): _fail()
        if phase=='collaborators':
            if 'projectId' in body and _integer(body['projectId'])!=payload['projectId']: _fail()
            if body.get('userPermissions')!='write': _fail()
            report['collaboration']=_collaborators(body.get('collaborators'),owner)
            report['metadata']=prior['metadata']
        else:
            rows=body.get('projects')
            if type(rows) is not list or len(rows)>(MAX_LIST if phase=='reconcile' else 1): _fail()
            if phase=='reconcile':
                matches=[row for row in rows if type(row) is dict and row.get('name')==RESERVED_NAMES[arm]]
                if len(matches)>1: _fail()
                if not matches:
                    report['status']='reconciliation_not_observed';rows=[]
                else:rows=matches
            elif len(rows)!=1: _fail()
            if rows:
                report['metadata']=_metadata(rows[0],owner=authenticated_owner,org=organization,arm=arm,
                    project=OLD_PROJECT if phase=='baseline' else payload.get('projectId'))
                if phase in ('create','reconcile'):
                    earliest=_instant(prior['created_utc'] if phase=='reconcile' else plan['created_utc'])-timedelta(seconds=60)
                    observed=report['metadata']['created_utc']
                    if observed is not None and not earliest<=_instant(observed)<=clock()+timedelta(seconds=60): _fail()
                    if phase=='reconcile' and observed is None: report['status']='reconciliation_creation_time_unproved'
        if report['status'] not in ('reconciliation_not_observed','reconciliation_creation_time_unproved'): report['status']='completed'
        report['unknown_create']=phase=='create' and report['status']!='completed'
        check()
    except BaseException as error: failure=error
    finally:
        if lock is not None:
            try:
                current=os.stat(root/'five-projects.lock',follow_symlinks=False);owned=os.fstat(lock)
                if (current.st_dev,current.st_ino)!=(owned.st_dev,owned.st_ino): _fail()
                os.unlink(root/'five-projects.lock');os.close(lock);lock=None
                report['lock_cleanup_complete']=True
            except BaseException as error: failure=_stop(failure,error)
            finally:
                if lock is not None:
                    try:os.close(lock)
                    except BaseException as error: failure=_stop(failure,error)
        if failure is not None:
            report['status']='cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed_or_uncertain'
            report['unknown_create']=report['create_attempted']
        try: report['observed_utc']=clock().isoformat()
        except BaseException as error:
            failure=_stop(failure,error);report['observed_utc']=None;report['status']='cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed_or_uncertain'
        report['receipt_published']=True
        try:receipt=_publish(root,operation+'.result.json',_canonical(report))
        except BaseException as error:
            report['receipt_published']=False;failure=_stop(failure,error)
            report['status']='cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed_or_uncertain'
            receipt=None
    if isinstance(failure,KeyboardInterrupt):raise ProjectCancelled(report) from None
    if failure is not None and not isinstance(failure,Exception):raise ProjectFatal(report) from None
    return {**_clone(report),'receipt':receipt}


def _utcnow():return datetime.now(timezone.utc)
def execute_plan(plan):
    """Production only. No adapter flags substitute for the actual transport."""
    try:
        if type(plan) is not dict or plan.get('mode')!='production': _fail()
        return _execute(plan,PRIVATE_ROOT,transport=_native_request,guard=_guard,clock=_utcnow,monotonic=time.monotonic)
    except (ProjectCancelled,ProjectFatal):raise
    except Exception:_fail()


def _execute_fixture(plan,root,*,transport,clock,guard=lambda _:None,monotonic=lambda:0.0):
    if plan.get('mode')!='offline-fixture': _fail()
    return _execute(plan,root,transport=transport,clock=clock,guard=guard,monotonic=monotonic)


def validate_bindings(raw,*,expected_sha256):
    """Pure registry framing only; caller's pin is not authenticated API origin."""
    try:
        if type(raw) is not bytes or not 0<len(raw)<=MAX_RESULT or _sha(raw)!=_hash(expected_sha256): _fail()
        body=json.loads(raw.decode('ascii'),object_pairs_hook=_pairs,parse_float=lambda _: _fail(),parse_constant=lambda _: _fail())
        _closed(body,{'schema','round_id','owner_instruction_sha256','git_head','adapter_source_sha256',
            'organization_id','owner_id','baseline_receipt_sha256','projects','privacy_basis',
            'explicit_privacy_flag_observed','independent_native_origin_attested'})
        if (body['schema']!='tpr-cmp28-five-project-bindings-v1' or body['round_id']!=ROUND_ID
                or body['privacy_basis']!=PRIVACY_BASIS or type(body['explicit_privacy_flag_observed']) is not bool
                or body['independent_native_origin_attested'] is not False): _fail()
        for key in ('owner_instruction_sha256','adapter_source_sha256','baseline_receipt_sha256'): _hash(body[key])
        _hash(body['git_head'],40);owner=_integer(body['owner_id']);org=body['organization_id']
        if type(org) is not str or re.fullmatch('[a-f0-9]{32}',org) is None: _fail()
        _closed(body['projects'],ARMS);seen=set();receipts=set()
        for arm,row in body['projects'].items():
            _closed(row,{'project_id','name','organization_id','owner_id','language','create_receipt_sha256',
                'read_receipt_sha256','collaboration_receipt_sha256','collaborator_count',
                'nonowner_collaborator_count','collaborators_sha256'})
            pid=_integer(row['project_id'])
            if (pid in seen or pid in HISTORICAL_PROJECTS or row['name']!=RESERVED_NAMES[arm]
                    or row['organization_id']!=org or _integer(row['owner_id'])!=owner or row['language']!='Py'
                    or _integer(row['collaborator_count'],0,1)>1 or _integer(row['nonowner_collaborator_count'],0,0)!=0): _fail()
            seen.add(pid)
            for key in ('create_receipt_sha256','read_receipt_sha256','collaboration_receipt_sha256'):
                digest=_hash(row[key])
                if digest in receipts: _fail()
                receipts.add(digest)
            _hash(row['collaborators_sha256'])
        return body
    except ProjectRefusal:raise
    except Exception:_fail()


def build_bindings(*,baseline_result_raw,project_result_raws):
    """Pure aggregate from exact retained safe results; no private read/effect."""
    try:
        base=_report(baseline_result_raw)
        if base['phase']!='baseline' or base['status']!='completed' or base['metadata']['project_id']!=OLD_PROJECT: _fail()
        _closed(project_result_raws,ARMS);projects={};explicit=False
        for arm,parts in project_result_raws.items():
            _closed(parts,{'create','read','collaborators'})
            reports={name:_report(raw) for name,raw in parts.items()}
            for name,row in reports.items():
                if (row['arm']!=arm or row['status']!='completed' or row['receipt_published'] is not True
                        or row['phase'] not in (('create','reconcile') if name=='create' else (name,))
                        or row['git_head']!=base['git_head'] or row['source_hashes']!=base['source_hashes']
                        or row['owner_instruction_sha256']!=base['owner_instruction_sha256']
                        or row['baseline']['sha256']!=_sha(baseline_result_raw)): _fail()
            created,read,collab=(reports[name] for name in ('create','read','collaborators'))
            if (read['prior']['sha256']!=_sha(parts['create']) or collab['prior']['sha256']!=_sha(parts['read'])
                    or created['metadata']!=read['metadata'] or read['metadata']!=collab['metadata']
                    or collab['collaboration']!={key:read['metadata'][key] for key in
                        ('collaborator_count','nonowner_collaborator_count','collaborators_sha256')}): _fail()
            meta=read['metadata'];explicit|=meta['explicit_privacy_flag_observed']
            projects[arm]={key:meta[key] for key in ('project_id','name','organization_id','owner_id','language',
                'collaborator_count','nonowner_collaborator_count','collaborators_sha256')}
            projects[arm].update(create_receipt_sha256=_sha(parts['create']),read_receipt_sha256=_sha(parts['read']),
                collaboration_receipt_sha256=_sha(parts['collaborators']))
        result=dict(schema='tpr-cmp28-five-project-bindings-v1',round_id=ROUND_ID,
            owner_instruction_sha256=base['owner_instruction_sha256'],git_head=base['git_head'],
            adapter_source_sha256=base['source_hashes'][MODULE],organization_id=base['metadata']['organization_id'],
            owner_id=base['metadata']['owner_id'],baseline_receipt_sha256=_sha(baseline_result_raw),projects=projects,
            privacy_basis=PRIVACY_BASIS,explicit_privacy_flag_observed=explicit,independent_native_origin_attested=False)
        raw=_canonical(result);validate_bindings(raw,expected_sha256=_sha(raw));return raw
    except ProjectRefusal:raise
    except Exception:_fail()
