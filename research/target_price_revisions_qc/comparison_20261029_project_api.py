"""Registered five-arm project research API successor; imports perform no I/O.

Pure preparation freezes exact payloads/hashes and committed producer sources.
Production execution has an actual authenticated HTTPS transport, never an
adapter flag. Every request/private payload read is claimed before credentials
or effect. Preserve all existing cloud extras through separate before/after
inventory comparison; this module never deletes files or writes notebooks.
Compilation/backtests spend fresh identities, and uncertain delivery forbids
automatic continuation. Raw responses remain owner-only private artifacts.
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
import stat
import subprocess
import time

from . import extended_operations as ops, extended_evidence as e
from . import comparison_20261028_api as predecessor, comparison_20261029_projects as projects

LANE, BRANCH = ops.LANE, ops.BRANCH
MODULE = 'research/target_price_revisions_qc/comparison_20261029_project_api.py'
PROJECTS_MODULE = 'research/target_price_revisions_qc/comparison_20261029_projects.py'
REQUIRED_SOURCES = predecessor.REQUIRED_SOURCES | frozenset((MODULE, PROJECTS_MODULE))
PRIVATE_ROOT = ops.PRIVATE_PARENT / 'TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1' / 'project-api-20261029'
PROJECT_KEYS = {'cap_off':'OFF','cap_tilt_50':'TPR050','cap_tilt_100':'TPR100',
    'cap_tilt_200':'TPR200LONG','pure_tpr':'PURE'}
ENDPOINTS = frozenset(('files/read','files/create','files/update','compile/create','compile/read',
    'backtests/create','backtests/read','backtests/list','backtests/read/log','backtests/orders/read',
    'backtests/chart/read'))
MUTATIONS = frozenset(('files/create','files/update','compile/create','backtests/create'))
WRITE_FILES = frozenset(('main.py','extended_core.py','cap_tilt.py','cap_observer.py','extended_construction.py',
    'extended_loader.py','extended_compressed_store.py','extended_runtime_successor.py',
    'extended_algorithm_successor.py','comparison_20261028.py','comparison_20261028_algorithm.py',
    'comparison_20261028_config.py','comparison_20261028_events.py',
    'comparison_20261028_multi_algorithm.py','comparison_20261028_signal_native.py','raw_revision.py',
    'comparison_20261028_accounting_runtime.py'))
MAX_REQUESTS, MAX_BODY, MAX_RESPONSE, MAX_TOTAL = 64, 1024*1024, 4*1024*1024, 32*1024*1024
_HASH = re.compile(r'[a-f0-9]{64}')
_ID = re.compile(r'[A-Za-z0-9_.-]{1,160}')


# Reuse project-agnostic exact JSON, O_EXCL/fsync custody and real TLS transport.
APIRefusal, APICancelled, APIFatal = predecessor.APIRefusal, predecessor.APICancelled, predecessor.APIFatal
_fail, _sha, _canonical, _clone = predecessor._fail, predecessor._sha, predecessor._canonical, predecessor._clone
_hash, _identity, _integer, _clock = predecessor._hash, predecessor._identity, predecessor._integer, predecessor._clock
_closed, _retain_stop, _parse = predecessor._closed, predecessor._retain_stop, predecessor._parse
_publish, _native_request, _utcnow = predecessor._publish, predecessor._native_request, predecessor._utcnow


def _project_binding(raw, expected_sha256, arm, config_sha256, attempt):
    if type(raw) is not bytes or not 0 < len(raw) <= 64*1024 or type(arm) is not str or arm not in PROJECT_KEYS:
        _fail()
    _hash(expected_sha256); _hash(config_sha256); _integer(attempt, 2**31-1, 1)
    registry = projects.validate_bindings(raw, expected_sha256=expected_sha256)
    return registry, PROJECT_KEYS[arm], registry['projects'][PROJECT_KEYS[arm]]['project_id']


def _payload(endpoint, payload, allowed, project):
    if type(payload) is not dict or _integer(payload.get('projectId'),project)!=project: _fail()
    keys={'projectId'}
    if endpoint in {'files/create','files/update'}:
        keys|={'name','content'}
        name=payload.get('name'); content=payload.get('content')
        if (type(name) is not str or name not in allowed or name not in WRITE_FILES
                or type(content) is not str or not 0<len(content.encode())<=60000
                or _sha(content.encode())!=allowed[name]): _fail()
    elif endpoint in {'compile/read','backtests/create'}:
        keys.add('compileId'); _identity(payload.get('compileId'))
        if endpoint=='backtests/create': keys.add('backtestName'); _identity(payload.get('backtestName'))
    elif endpoint=='backtests/chart/read':
        # Official ReadBacktestChart: JSON POST, UTC Unix seconds and point
        # count. This sole own-account chart/window is not a NAV census or
        # financial acceptance; loading responses are never retried here.
        # https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/charts
        keys|={'backtestId','name','start','end','count'}
        _identity(payload.get('backtestId'))
        if (payload.get('name')!='EXT26 Account NAV'
                or _integer(payload.get('start'),ops.CHART_START)!=ops.CHART_START
                or _integer(payload.get('end'),ops.CHART_END)!=ops.CHART_END
                or _integer(payload.get('count'),ops.CHART_COUNT)!=ops.CHART_COUNT): _fail()
    elif endpoint in {'backtests/read','backtests/read/log','backtests/orders/read'}:
        keys.add('backtestId'); _identity(payload.get('backtestId'))
        if endpoint!='backtests/read':
            keys|={'start','end'}
            start=_integer(payload.get('start'),50000); end=_integer(payload.get('end'),50200)
            # Official order range is strictly less than 100; logs retain their separate 200-line bound.
            if not start<end<=start+(200 if endpoint=='backtests/read/log' else 99): _fail()
            if endpoint=='backtests/read/log':
                keys.add('query'); query=payload.get('query')
                if type(query) is not str or re.fullmatch(r'[A-Za-z0-9 _.-]{0,80}',query) is None: _fail()
    _closed(payload,keys)


def prepare_plan(*, project_bindings_raw, expected_project_bindings_sha256, arm,
                 candidate_config_sha256, candidate_attempt,
                 operation_id, git_head, source_hashes, owner_instruction_sha256,
                 created_utc, expires_utc, requests, allowed_source_hashes=None,
                 attempt_id=None, reserved_look_id=None, max_total_response_bytes=MAX_TOTAL,
                 mode='production'):
    """Pure exact plan. Request fields: id/endpoint/payload/payload_file/hash/limits.

    Each request has ``id, endpoint, payload, payload_file, payload_sha256,
    max_response_bytes, seconds``; files/read may additionally require an exact
    ``source_inventory_sha256``. Upload operations require this precondition
    on their first and last reads, preserving all extras. QC has no atomic
    compare-and-swap: a residual remote race remains between API calls.
    Choose one payload form:
    inline dict, or same-private-root descriptor ``name, bytes, sha256``.
    The registry is supplied evidence framed by the pinned pure project adapter;
    this function does not authenticate its native receipts or assert privacy.
    Candidate config/attempt metadata is bound, not proof of deployed economics.
    Private payload bytes are NOT opened here. Dependent returned IDs require
    a new plan, not an automatic retry. No claim/attempt/job is created here.
    """
    try:
        registry, project_key, project = _project_binding(project_bindings_raw,
            expected_project_bindings_sha256, arm, candidate_config_sha256, candidate_attempt)
        _identity(operation_id)
        if not operation_id.startswith('TPR-CMP29-API-') or len(operation_id)>100: _fail()
        if type(git_head) is not str or re.fullmatch(r'[a-f0-9]{40}',git_head) is None: _fail()
        _hash(owner_instruction_sha256)
        if mode not in {'production','offline-fixture'}: _fail()
        issued,expires=_clock(created_utc),_clock(expires_utc)
        if not timedelta(0)<expires-issued<=timedelta(seconds=600): _fail()
        if type(source_hashes) is not dict or not REQUIRED_SOURCES<=set(source_hashes) or len(source_hashes)>48: _fail()
        if (registry['owner_instruction_sha256'] != owner_instruction_sha256
                or registry['adapter_source_sha256'] != source_hashes.get(PROJECTS_MODULE)):
            _fail()
        for name,identity in source_hashes.items():
            if (name not in REQUIRED_SOURCES and name!='research/target_price_revisions_development/raw_revision.py'
                    and re.fullmatch(r'research/target_price_revisions_qc/[A-Za-z0-9_.-]+[.](py|json)',name) is None): _fail()
            _hash(identity)
        allowed={} if allowed_source_hashes is None else allowed_source_hashes
        if type(allowed) is not dict or not set(allowed)<=WRITE_FILES or len(allowed)>24: _fail()
        for identity in allowed.values(): _hash(identity)
        if type(requests) is not list or not 1<=len(requests)<=MAX_REQUESTS: _fail()
        total=seconds=0; ids=set(); mutations=False; compiles=launches=writes=0; write_names=set()
        for row in requests:
            required={'id','endpoint','payload','payload_file','payload_sha256','max_response_bytes','seconds'}
            if type(row) is not dict or not required<=set(row) or set(row)-required-{'source_inventory_sha256'}:_fail()
            name=_identity(row['id'])
            if len(name)>64 or name in ids or row['endpoint'] not in ENDPOINTS: _fail()
            ids.add(name); _hash(row['payload_sha256'])
            if 'source_inventory_sha256' in row:
                if row['endpoint']!='files/read':_fail()
                _hash(row['source_inventory_sha256'])
            if len(operation_id+'.'+name+'.payload-read.spent.json')>160: _fail()
            total+=_integer(row['max_response_bytes'],MAX_RESPONSE,1)
            seconds+=_integer(row['seconds'],40,1)
            if (row['payload'] is None)==(row['payload_file'] is None): _fail()
            if row['payload'] is not None:
                wire=_canonical(row['payload'])
                if not 0<len(wire)<=MAX_BODY or _sha(wire)!=row['payload_sha256']: _fail()
                _payload(row['endpoint'],row['payload'],allowed,project)
                if row['endpoint'] in {'files/create','files/update'}:
                    file=row['payload']['name']
                    if file in write_names:_fail()
                    write_names.add(file)
            else:
                descriptor=row['payload_file']; _closed(descriptor,{'name','bytes','sha256'})
                _identity(descriptor['name']); _integer(descriptor['bytes'],MAX_BODY,1)
                if descriptor['name'] in {'.','..'} or not descriptor['name'].startswith('payload.'): _fail()
                if _hash(descriptor['sha256'])!=row['payload_sha256']: _fail()
            mutations|=row['endpoint'] in MUTATIONS
            compiles+=row['endpoint']=='compile/create'; launches+=row['endpoint']=='backtests/create'
            writes+=row['endpoint'] in {'files/create','files/update'}
        if compiles>1 or launches>1: _fail()
        if writes and any(row['endpoint']!='files/read' or 'source_inventory_sha256' not in row
                          for row in (requests[0],requests[-1])):_fail()
        if total>_integer(max_total_response_bytes,MAX_TOTAL,1) or seconds>(expires-issued).total_seconds(): _fail()
        if mutations:
            _identity(attempt_id); _identity(reserved_look_id)
        elif attempt_id is not None or reserved_look_id is not None: _fail()
        candidate_binding=_sha(_canonical({'schema':'tpr-cmp29-project-candidate-binding-v1',
            'project_bindings_sha256':expected_project_bindings_sha256,'project_id':project,
            'project_registration_key':project_key,'arm':arm,
            'candidate_config_sha256':candidate_config_sha256,'candidate_attempt':candidate_attempt}))
        plan={'schema':'tpr-cmp29-project-api-plan-v1','operation_id':operation_id,'git_head':git_head,
            'project_id':project,'project_registration_key':project_key,
            'project_bindings_json':project_bindings_raw.decode('utf-8'),
            'project_bindings_sha256':expected_project_bindings_sha256,
            'arm':arm,'candidate_config_sha256':candidate_config_sha256,
            'candidate_attempt':candidate_attempt,'candidate_binding_sha256':candidate_binding,'source_hashes':source_hashes,'owner_instruction_sha256':owner_instruction_sha256,
            'created_utc':created_utc,'expires_utc':expires_utc,'requests':requests,'allowed_source_hashes':allowed,
            'attempt_id':attempt_id,'reserved_look_id':reserved_look_id,'max_total_response_bytes':max_total_response_bytes,
            'mode':mode,'automatic_retry':False,'market_trading_authorized':False}
        raw=_canonical(plan)
        if len(raw)>4*MAX_BODY: _fail()
        return _clone(plan)
    except APIRefusal: raise
    except Exception: _fail()


def _validated(plan):
    _closed(plan,{'schema','operation_id','git_head','project_id','project_registration_key',
        'project_bindings_json','project_bindings_sha256','arm','candidate_config_sha256','candidate_attempt','candidate_binding_sha256',
        'source_hashes','owner_instruction_sha256','created_utc','expires_utc','requests',
        'allowed_source_hashes','attempt_id','reserved_look_id','max_total_response_bytes','mode',
        'automatic_retry','market_trading_authorized'})
    excluded={'schema','project_id','project_registration_key','project_bindings_json','project_bindings_sha256',
        'automatic_retry','market_trading_authorized','candidate_binding_sha256'}
    args={key:plan[key] for key in plan if key not in excluded}
    if type(plan['project_bindings_json']) is not str: _fail()
    args.update(project_bindings_raw=plan['project_bindings_json'].encode('utf-8'),
        expected_project_bindings_sha256=plan['project_bindings_sha256'])
    if _canonical(plan)!=_canonical(prepare_plan(**args)): _fail()
    return _clone(plan)


def _guard(plan):
    if Path.cwd()!=LANE or Path.cwd().resolve()!=LANE: _fail()
    def git(*args):return subprocess.run(['git',*args],cwd=LANE,capture_output=True,timeout=10,check=True).stdout
    if (git('rev-parse','--show-toplevel').decode().strip()!=str(LANE)
            or git('branch','--show-current').decode().strip()!=BRANCH
            or git('rev-parse','HEAD').decode().strip()!=plan['git_head']): _fail()
    git('status','--short')
    if subprocess.run(['git','check-ignore','-q',str(PRIVATE_ROOT)],cwd=LANE,capture_output=True,timeout=10).returncode: _fail()
    if (Path(__file__)!=LANE/MODULE or Path(ops.__file__)!=LANE/'research/target_price_revisions_qc/extended_operations.py'
            or Path(e.__file__)!=LANE/'research/target_price_revisions_qc/extended_evidence.py'
            or Path(predecessor.__file__)!=LANE/predecessor.MODULE
            or Path(projects.__file__)!=LANE/PROJECTS_MODULE): _fail()
    for name,identity in plan['source_hashes'].items():
        path=LANE/name
        if path.resolve()!=path or path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BODY: _fail()
        raw=path.read_bytes()
        if _sha(raw)!=identity or git('show',plan['git_head']+':'+name)!=raw: _fail()


def _execute(plan,root,*,transport,guard,clock,monotonic):
    plan=_validated(plan)
    project=plan['project_id']
    if (plan['mode']=='production' and (root!=PRIVATE_ROOT or transport is not _native_request
            or guard is not _guard or clock is not _utcnow or monotonic is not time.monotonic)
            or plan['mode']=='offline-fixture' and (root==PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)): _fail()
    frozen=_canonical(plan); started=monotonic();previous_now=previous_tick=None
    def check():
        nonlocal previous_now,previous_tick
        guard(plan); now,tick=clock(),monotonic()
        if (type(now) is not datetime or now.utcoffset()!=timedelta(0)
                or not _clock(plan['created_utc'])<=now<_clock(plan['expires_utc'])
                or type(tick) not in (int,float) or not 0<=tick-started<600
                or previous_now is not None and now<previous_now
                or previous_tick is not None and tick<previous_tick or _canonical(plan)!=frozen): _fail()
        previous_now,previous_tick=now,tick
    check()
    if root.resolve()!=root: _fail()
    if plan['mode']=='production':
        for path in (ops.PRIVATE_PARENT,PRIVATE_ROOT.parent,PRIVATE_ROOT):
            path.mkdir(mode=0o700,exist_ok=True);ops._custody(path.lstat(),True)
    else:root.mkdir(mode=0o700,exist_ok=True);ops._custody(root.lstat(),True)
    operation=plan['operation_id'];lock=None;stop=None
    report={'schema':'tpr-cmp29-project-api-result-v1','operation_id':operation,'project_id':project,
        'arm':plan['arm'],'project_registration_key':plan['project_registration_key'],
        'project_bindings_sha256':plan['project_bindings_sha256'],
        'candidate_config_sha256':plan['candidate_config_sha256'],'candidate_attempt':plan['candidate_attempt'],
        'candidate_binding_sha256':plan['candidate_binding_sha256'],
        'plan_sha256':_sha(frozen),'status':'failed_or_uncertain','requests':[],
        'attempt_id':plan['attempt_id'],'reserved_look_id':plan['reserved_look_id'],
        'compile_requests_attempted':0,'observed_new_backtest_ids':[],'actual_new_backtests':0,
        'new_observed_looks':0,
        'new_observed_looks_semantics':'returned_native_job_ids_not_financial_outcome_looks',
        'financial_outcome_looks_count':None,
        'project_registry_framing_verified':True,'project_native_custody_independently_attested':False,
        'response_bytes':0,'receipt_published':False,'lock_cleanup_complete':False,
        'automatic_retry':False,'market_trading_authorized':False,'economics_accepted':False,
        'atomic_remote_compare_and_swap_proven':False}
    # A previously spent operation refuses before even taking a new lock.
    _publish(root,operation+'.operation.spent.json',frozen)
    try:
        lock=os.open(root/'comparison-api.lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        ops._custody(os.fstat(lock));os.write(lock,_canonical({'operation_id':operation}));os.fsync(lock)
        written_names=set()
        for request in plan['requests']:
            check(); prefix=operation+'.'+request['id']
            row={'id':request['id'],'endpoint':request['endpoint'],'status':'failed_or_unknown',
                'request_claim':None,'payload_read_claim':None,'raw_response':None,'projection':None,
                'http_status':None,'compile_id':None,'compile_state':None,'backtest_id':None,
                'backtest_status':None,'backtest_completed':None,'source_inventory':None,
                'source_inventory_sha256':None,'listed_backtests_count':None}
            report['requests'].append(row)
            row['request_claim']=_publish(root,prefix+'.request.spent.json',_canonical({
                'plan_sha256':report['plan_sha256'],'request':request,'attempt_id':plan['attempt_id'],
                'reserved_look_id':plan['reserved_look_id']}))
            if request['payload_file'] is not None:
                descriptor=request['payload_file']
                row['payload_read_claim']=_publish(root,prefix+'.payload-read.spent.json',_canonical(descriptor))
                check();raw=ops.read_private(root,descriptor['name'],MAX_BODY);check()
                if len(raw)!=descriptor['bytes'] or _sha(raw)!=descriptor['sha256']: _fail()
                payload=_parse(raw)
            else:payload=request['payload'];raw=_canonical(payload)
            if _sha(raw)!=request['payload_sha256']: _fail()
            _payload(request['endpoint'],payload,plan['allowed_source_hashes'],project);check()
            if request['endpoint'] in {'files/create','files/update'}:
                if payload['name'] in written_names:_fail()
                written_names.add(payload['name'])
            if request['endpoint']=='compile/create':report['compile_requests_attempted']+=1
            if request['endpoint']=='backtests/create':report['actual_new_backtests']=None
            returned,status,token=transport(request['endpoint'],raw,request['seconds'],request['max_response_bytes'])
            if (type(returned) is not bytes or not 0<len(returned)<=request['max_response_bytes']
                    or report['response_bytes']+len(returned)>plan['max_total_response_bytes']
                    or type(status) is not int or not 100<=status<=599
                    or type(token) is not str or re.fullmatch(r'[!-~]{1,256}',token) is None): _fail()
            report['response_bytes']+=len(returned);row['http_status']=status
            projected=e.project_wire(returned,credential=token)  # Secret refusal precedes raw retention.
            row['raw_response']=_publish(root,prefix+'.response.raw',returned)
            row['projection']=_publish(root,prefix+'.projection.json',e.canonical(projected))
            body=projected['projection']
            if status!=200 or type(body) is not dict or body.get('success') is not True:_fail()
            if 'projectId' in body and _integer(body['projectId'],project)!=project:_fail()
            if request['endpoint'] in {'compile/create','compile/read'}:
                row['compile_id']=_identity(body.get('compileId'))
                if request['endpoint']=='compile/read' and row['compile_id']!=payload['compileId']:_fail()
                state=body.get('state')
                if type(state) is not str or re.fullmatch(r'[A-Za-z ]{1,40}',state) is None:_fail()
                row['compile_state']=state
            if request['endpoint']=='files/read':
                files=body.get('files')
                if type(files) is not list or len(files)>25:_fail()
                inventory={}
                for file in files:
                    if (type(file) is not dict or type(file.get('name')) is not str
                            or re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}',file['name']) is None
                            or file['name'] in inventory or type(file.get('content')) is not str):_fail()
                    if 'projectId' in file and _integer(file['projectId'],project)!=project:_fail()
                    content=file['content'].encode()
                    inventory[file['name']]={'bytes':len(content),'sha256':_sha(content)}
                row['source_inventory']=inventory
                row['source_inventory_sha256']=_sha(_canonical(inventory))
                if ('source_inventory_sha256' in request
                        and row['source_inventory_sha256']!=request['source_inventory_sha256']):_fail()
            if request['endpoint']=='backtests/create':
                job=body.get('backtest')
                if type(job) is not dict:_fail()
                row['backtest_id']=_identity(job.get('backtestId'))
                if 'projectId' in job and _integer(job['projectId'],project)!=project:_fail()
                report['observed_new_backtest_ids'].append(row['backtest_id'])
                report['actual_new_backtests']=len(report['observed_new_backtest_ids'])
                report['new_observed_looks']=len(report['observed_new_backtest_ids'])
            if request['endpoint'] in {'backtests/read','backtests/read/log','backtests/orders/read','backtests/chart/read'}:
                ops._returned_identity(body,project,payload['backtestId'])
            if request['endpoint']=='backtests/chart/read':
                chart=body.get('chart')
                if chart is not None:
                    if type(chart) is not dict or chart.get('name')!='EXT26 Account NAV':_fail()
                elif body.get('status')!='loading':_fail()
            if request['endpoint']=='backtests/read':
                job=body.get('backtest')
                if (type(job) is not dict or job.get('backtestId')!=payload['backtestId']
                        or type(job.get('completed')) is not bool):_fail()
                status_name=job.get('status')
                known={'Completed','Completed.','Runtime Error','RuntimeError','Error','Stopped','Cancelled',
                    'Running','In Queue','InQueue','Queued','Initializing','Loading','In Progress...'}
                row['backtest_status']=status_name if type(status_name) is str and status_name in known else 'unrecognized_status'
                row['backtest_completed']=job['completed'];row['backtest_id']=payload['backtestId']
            if request['endpoint']=='backtests/list':
                jobs=body.get('backtests')
                if type(jobs) is not list or len(jobs)>1000:_fail()
                for job in jobs:
                    if type(job) is not dict:_fail()
                    if 'projectId' in job and _integer(job['projectId'],project)!=project:_fail()
                row['listed_backtests_count']=len(jobs)
            row['status']='succeeded';check()
        report['status']='completed'
    except BaseException as error:stop=error
    finally:
        if lock is not None:
            try:
                current=os.stat(root/'comparison-api.lock',follow_symlinks=False);owned=os.fstat(lock)
                if (current.st_dev,current.st_ino)!=(owned.st_dev,owned.st_ino):_fail()
                os.unlink(root/'comparison-api.lock');os.close(lock);lock=None
                report['lock_cleanup_complete']=True
            except BaseException as error:
                stop=_retain_stop(stop,error)
            finally:
                if lock is not None:
                    try:os.close(lock)
                    except BaseException as error:
                        stop=_retain_stop(stop,error)
        if stop is not None:report['status']='cancelled' if isinstance(stop,KeyboardInterrupt) else 'failed_or_uncertain'
        report['receipt_published']=True
        try:report['receipt']=_publish(root,operation+'.result.json',_canonical(report))
        except BaseException as error:
            report['receipt_published']=False
            stop=_retain_stop(stop,error)
            report['status']='cancelled' if isinstance(stop,KeyboardInterrupt) else 'failed_or_uncertain'
    if isinstance(stop,KeyboardInterrupt):raise APICancelled(report) from None
    if stop is not None and not isinstance(stop,Exception):raise APIFatal(report) from None
    return _clone(report)


def execute_plan(plan):
    """Production only: fixed root, native TLS transport, clocks and source guard."""
    try:
        if type(plan) is not dict or plan.get('mode')!='production':_fail()
        return _execute(plan,PRIVATE_ROOT,transport=_native_request,guard=_guard,clock=_utcnow,monotonic=time.monotonic)
    except (APICancelled,APIFatal):raise
    except Exception:_fail()


def _execute_fixture(plan,root,*,transport,clock,guard=lambda _:None,monotonic=lambda:0.0):
    if plan.get('mode')!='offline-fixture':_fail()
    return _execute(plan,root,transport=transport,guard=guard,clock=clock,monotonic=monotonic)
