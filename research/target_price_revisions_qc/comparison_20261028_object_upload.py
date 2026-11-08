"""Exact plain derived-packet upload, not account or arbitrary ObjectStore access.

Official routes: projects/read once for own37650980, object/properties only the
one content-addressed key, and ONE object/set multipart effect. Never list,
get/delete an object, purchase capacity, upload encoded/compressed cloud inputs,
or return market/map/factor bodies. Properties previews are never retained.
Preparation is pure. Root alone executes separately claimed native scopes.
"""
from __future__ import annotations

import base64
from datetime import datetime,timedelta,timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time

from . import comparison_20261028_api as api

ops,e=api.ops,api.e
LANE,BRANCH,PROJECT=api.LANE,api.BRANCH,37650980
MODULE='research/target_price_revisions_qc/comparison_20261028_object_upload.py'
REQUIRED_SOURCES=api.REQUIRED_SOURCES|{MODULE}
PRIVATE_ROOT=api.PRIVATE_ROOT
INPUT_ROOT=LANE/'artifacts/target_price_qc_recovery_20261028'
STUDY='TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1'
PACKET_BYTES=280105389
PACKET_SHA256='6a8f4915df539f5aee731832138e038caf6dd579b591ebe745e37b5d283e4708'
KEY=f'tpr-cmp28/inputs/{PROJECT}/{STUDY}/upload-003/{PACKET_SHA256}.json'
MAX_RESPONSE=65536
CHUNK=1024*1024
MAX_OPERATION_SECONDS=600
MAX_UPLOAD_SECONDS=300
PROPERTIES_DOCUMENTATION='https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/object-store-management/get-object-store-metadata'
UPLOAD_DOCUMENTATION='https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/object-store-management/upload-object-store-files'


def _fail():raise api.APIRefusal('exact plain-packet upload refused; no retry or overwrite') from None
def _canonical(value):return api._canonical(value)
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _clock(value):return api._clock(value)
def _failure_class(error):
    """Closed body-free classes; never copy exception messages or custom names."""
    for kind,label in ((KeyboardInterrupt,'cancelled'),(SystemExit,'system_exit'),
            (MemoryError,'memory_error'),(TimeoutError,'timeout_error'),
            (BrokenPipeError,'broken_pipe'),(ConnectionResetError,'connection_reset'),
            (ConnectionAbortedError,'connection_aborted'),(ssl.SSLError,'tls_error'),
            (http.client.HTTPException,'http_error'),(api.APIRefusal,'api_refusal'),
            (ops.Refusal,'operation_refusal'),(OSError,'os_error'),(Exception,'exception')):
        if isinstance(error,kind):return label
    return 'fatal'
def _elapsed_ms(start):
    elapsed=time.monotonic()-start
    return int(elapsed*1000) if 0<=elapsed<float('inf') else None
def _descriptor(value,maximum):
    api._closed(value,{'name','bytes','sha256'});api._identity(value['name'])
    api._integer(value['bytes'],maximum,1);api._hash(value['sha256'])
    if value['name'] in {'.','..'}:_fail()
    return api._clone(value)


def _prepare(*,action,operation_id,git_head,source_hashes,owner_instruction_sha256,
             created_utc,expires_utc,organization_binding_ref=None,packet_file=None,mode='production'):
    try:
        api._identity(operation_id)
        if not operation_id.startswith('TPR-CMP28-OBJECT-') or len(operation_id)>100:_fail()
        if type(git_head) is not str or re.fullmatch(r'[a-f0-9]{40}',git_head) is None:_fail()
        api._hash(owner_instruction_sha256)
        if action not in {'organization','upload'} or mode not in {'production','offline-fixture'}:_fail()
        if not timedelta(0)<_clock(expires_utc)-_clock(created_utc)<=timedelta(seconds=MAX_OPERATION_SECONDS):_fail()
        if type(source_hashes) is not dict or not REQUIRED_SOURCES<=set(source_hashes) or len(source_hashes)>48:_fail()
        for name,identity in source_hashes.items():
            if name not in REQUIRED_SOURCES and re.fullmatch(r'research/target_price_revisions_qc/[A-Za-z0-9_.-]+[.](py|json)',name) is None:_fail()
            api._hash(identity)
        if action=='organization':
            if organization_binding_ref is not None or packet_file is not None:_fail()
        else:
            organization_binding_ref=_descriptor(organization_binding_ref,MAX_RESPONSE)
            packet_file=_descriptor(packet_file,PACKET_BYTES)
            if packet_file['bytes']!=PACKET_BYTES or packet_file['sha256']!=PACKET_SHA256:_fail()
        return api._clone({'schema':'tpr-cmp28-object-plan-v1','action':action,'operation_id':operation_id,
            'project_id':PROJECT,'git_head':git_head,'source_hashes':source_hashes,
            'owner_instruction_sha256':owner_instruction_sha256,'created_utc':created_utc,'expires_utc':expires_utc,
            'organization_binding_ref':organization_binding_ref,'packet_file':packet_file,'mode':mode,
            'key':KEY,'packet_bytes':PACKET_BYTES,'packet_sha256':PACKET_SHA256,
            'max_local_packet_read_passes':2,'max_local_packet_bytes':2*PACKET_BYTES,
            'max_upload_effects':1,'max_response_bytes_each':MAX_RESPONSE,'max_upload_phase_seconds':MAX_UPLOAD_SECONDS,
            'automatic_retry':False,'object_listing':False,'object_download':False,'object_delete':False,
            'encoded_or_compressed_cloud_input':False,'market_trading_authorized':False})
    except api.APIRefusal:raise
    except Exception:_fail()


def prepare_metadata_plan(**arguments):return _prepare(action='organization',**arguments)
def prepare_upload_plan(**arguments):return _prepare(action='upload',**arguments)
def _validate(plan):
    required={'schema','action','operation_id','project_id','git_head','source_hashes','owner_instruction_sha256',
        'created_utc','expires_utc','organization_binding_ref','packet_file','mode','key','packet_bytes','packet_sha256',
        'max_local_packet_read_passes','max_local_packet_bytes','max_upload_effects','max_response_bytes_each',
        'max_upload_phase_seconds','automatic_retry','object_listing','object_download','object_delete',
        'encoded_or_compressed_cloud_input','market_trading_authorized'}
    api._closed(plan,required)
    keys=('action','operation_id','git_head','source_hashes','owner_instruction_sha256','created_utc','expires_utc',
        'organization_binding_ref','packet_file','mode')
    if _canonical(plan)!=_canonical(_prepare(**{key:plan[key] for key in keys})):_fail()
    return api._clone(plan)


def _guard(plan):
    api._guard(plan)
    if Path(__file__)!=LANE/MODULE or Path(__file__).resolve()!=LANE/MODULE:_fail()


def _cleanup(closers):
    original=sys.exception();failure=original
    for close in closers:
        try:close()
        except BaseException as error:failure=api._retain_stop(failure,error)
    if failure is not None and failure is not original:raise failure


def _connection(seconds):
    user,token=ops.credential();stamp=str(int(time.time()))
    signed=hashlib.sha256((token+':'+stamp).encode()).hexdigest()
    authorization=base64.b64encode((user+':'+signed).encode()).decode()
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.keylog_filename=None
    context.check_hostname=True;context.verify_mode=ssl.CERT_REQUIRED;context.load_default_certs()
    return http.client.HTTPSConnection('www.quantconnect.com',timeout=seconds,context=context),{
        'Authorization':'Basic '+authorization,'Timestamp':stamp},token


def _native_json(endpoint,payload):
    if endpoint not in {'projects/read','object/properties'}:_fail()
    connection=None
    with ops.wall_deadline(30):
        try:
            connection,headers,token=_connection(30);headers['Content-Type']='application/json'
            connection.request('POST','/api/v2/'+endpoint,body=_canonical(payload),headers=headers)
            response=connection.getresponse()
            return response.read(MAX_RESPONSE+1),response.status,token
        finally:
            _cleanup([connection.close] if connection is not None else [])


def multipart_parts(organization,key):
    """Pure exact multipart framing; the binary packet is streamed separately."""
    if type(organization) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,100}',organization) is None or key!=KEY:_fail()
    boundary='tpr-cmp28-plain-'+PACKET_SHA256[:32]
    prefix=b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode()
        for name,value in (('organizationId',organization),('key',key)))
    prefix+=(f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="{PACKET_SHA256}.json"\r\n'
        'Content-Type: application/json\r\n\r\n').encode()
    suffix=f'\r\n--{boundary}--\r\n'.encode()
    return prefix,suffix,'multipart/form-data; boundary='+boundary


def _native_upload(organization,key,descriptor,check,claim,report):
    """Claimed two-pass fd read; completed sends are local returns, not server ACKs."""
    directory=file=connection=None
    begin=datetime.now(timezone.utc);first_tick=previous_tick=time.monotonic();previous=begin
    for name in ('packet_hash_read_bytes','packet_stream_read_bytes','completed_send_bytes','completed_packet_send_bytes'):
        report.setdefault(name,0)
    report['completed_send_bytes_is_server_ack']=False
    report['phase']='upload_phase_start'
    def within_phase():
        nonlocal previous,previous_tick
        now,tick=datetime.now(timezone.utc),time.monotonic()
        if (now<previous or tick<previous_tick or now>=_clock(report['expires_utc'])
                or not 0<=(now-begin).total_seconds()<MAX_UPLOAD_SECONDS or not 0<=tick-first_tick<MAX_UPLOAD_SECONDS):
            report['phase']='upload_phase_budget_guard';_fail()
        previous,previous_tick=now,tick
    try:
      with ops.wall_deadline(MAX_UPLOAD_SECONDS):
        try:
            report['phase']='packet_read_claim'
            claim('read');check()
            report['phase']='packet_open'
            if INPUT_ROOT.resolve()!=INPUT_ROOT:_fail()
            directory=os.open(INPUT_ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);ops._custody(os.fstat(directory),True)
            file=os.open(descriptor['name'],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            before=os.fstat(file);ops._custody(before)
            if before.st_size!=PACKET_BYTES:_fail()
            digest=hashlib.sha256();md5=hashlib.md5();count=0
            while count<PACKET_BYTES:
                report['phase']='packet_hash_read'
                within_phase();part=os.read(file,min(CHUNK,PACKET_BYTES-count))
                if not part:_fail()
                report['packet_hash_read_bytes']+=len(part);report['local_packet_bytes_read']+=len(part)
                digest.update(part);md5.update(part);count+=len(part)
            report['phase']='packet_hash_verify'
            if digest.hexdigest()!=PACKET_SHA256:_fail()
            middle=os.fstat(file)
            if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(middle.st_dev,middle.st_ino,middle.st_size,middle.st_mtime_ns):_fail()
            os.lseek(file,0,os.SEEK_SET);check()
            prefix,suffix,content_type=multipart_parts(organization,key)
            report['multipart_body_bytes']=len(prefix)+PACKET_BYTES+len(suffix)
            report['phase']='object_write_claim'
            claim('effect');check()
            report['phase']='upload_connect'
            connection,headers,token=_connection(MAX_UPLOAD_SECONDS)
            connection.putrequest('POST','/api/v2/object/set')
            for name,value in {**headers,'Content-Type':content_type,'Content-Length':str(report['multipart_body_bytes'])}.items():
                connection.putheader(name,value)
            report['upload_attempted']=True;report['object_created']=None
            report['phase']='upload_headers'
            connection.endheaders()
            report['phase']='upload_prefix_send'
            connection.send(prefix);report['completed_send_bytes']+=len(prefix)
            streamed=hashlib.sha256();count=0
            while count<PACKET_BYTES:
                report['phase']='packet_stream_read'
                within_phase();part=os.read(file,min(CHUNK,PACKET_BYTES-count))
                if not part:_fail()
                report['local_packet_bytes_read']+=len(part)
                report['packet_stream_read_bytes']+=len(part)
                report['phase']='packet_stream_send'
                connection.send(part)
                report['completed_send_bytes']+=len(part);report['completed_packet_send_bytes']+=len(part)
                streamed.update(part);count+=len(part)
            report['phase']='packet_stream_verify'
            after=os.fstat(file)
            if (streamed.hexdigest()!=PACKET_SHA256 or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
                    !=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):_fail()
            check();report['phase']='upload_suffix_send'
            connection.send(suffix);report['completed_send_bytes']+=len(suffix)
            report['phase']='upload_response_headers'
            response=connection.getresponse()
            report['phase']='upload_response_read'
            raw=response.read(MAX_RESPONSE+1)
            report['phase']='upload_response_received'
            return raw,response.status,token,md5.hexdigest()
        finally:
            if sys.exception() is None:report['phase']='upload_cleanup'
            _cleanup(([connection.close] if connection is not None else [])
                +([lambda:os.close(file)] if file is not None else [])
                +([lambda:os.close(directory)] if directory is not None else []))
    except BaseException as error:
        report['failure_phase']=report['phase'];report['failure_class']=_failure_class(error)
        raise
    finally:report['upload_phase_elapsed_ms']=_elapsed_ms(first_tick)


def _body(raw,status,token):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_RESPONSE or type(status) is not int or not 100<=status<=599:_fail()
    if type(token) is not str or re.fullmatch(r'[!-~]{1,256}',token) is None:_fail()
    body=e.project_wire(raw,credential=token)['projection']
    if type(body) is not dict:_fail()
    return body


def properties_projection(raw,status,token,key):
    """Never retain preview/error bodies; unknown absence is NOT permission."""
    if key!=KEY:_fail()
    body=_body(raw,status,token);metadata=body.get('metadata');errors=body.get('errors',[])
    result={'wire_sha256':_sha(raw),'wire_bytes':len(raw),'http_status':status,
        'classification':'unknown_refused','size':None,'md5':None,'preview_withheld':False}
    if type(metadata) is dict:
        if metadata.get('key')!=key:_fail()
        result['classification']='present_refused'
        if 'size' in metadata:result['size']=api._integer(metadata['size'],2**63-1)
        value=metadata.get('md5')
        if type(value) is str and re.fullmatch(r'[a-fA-F0-9]{32}',value):result['md5']=value.lower()
        result['preview_withheld']='preview' in metadata
    elif status==200 and body.get('success') is True and 'metadata' in body and metadata is None and errors==[]:
        result['classification']='explicit_absence'
    elif (status==200 and set(body)=={'errors','success'} and body['success'] is False
            and body['errors']==['File not found '+key]):
        result['classification']='explicit_absence'
    return result


def _execute(plan,*,root,guard,json_transport,upload_transport,clock):
    plan=_validate(plan)
    if (plan['mode']=='production' and (root!=PRIVATE_ROOT or guard is not _guard or json_transport is not _native_json
            or upload_transport is not _native_upload or clock is not _now)
            or plan['mode']=='offline-fixture' and (root==PRIVATE_ROOT or root.is_relative_to(LANE)
                or json_transport is _native_json or upload_transport is _native_upload)):_fail()
    frozen=_canonical(plan);previous=None
    first_tick=previous_tick=time.monotonic()
    def check():
        nonlocal previous,previous_tick
        guard(plan);now=clock();tick=time.monotonic()
        if (type(now) is not datetime or now.utcoffset()!=timedelta(0)
                or not _clock(plan['created_utc'])<=now<_clock(plan['expires_utc'])
                or previous is not None and now<previous or _canonical(plan)!=frozen
                or tick<previous_tick or not 0<=tick-first_tick<MAX_OPERATION_SECONDS):_fail()
        previous,previous_tick=now,tick
    check()
    if root.resolve()!=root:_fail()
    if plan['mode']=='production':
        for path in (ops.PRIVATE_PARENT,PRIVATE_ROOT.parent,PRIVATE_ROOT):path.mkdir(mode=0o700,exist_ok=True);ops._custody(path.lstat(),True)
    else:root.mkdir(mode=0o700,exist_ok=True);ops._custody(root.lstat(),True)
    operation=plan['operation_id'];stop=None
    report={'schema':'tpr-cmp28-object-result-v1','operation_id':operation,'action':plan['action'],
        'project_id':PROJECT,'plan_sha256':_sha(frozen),'status':'failed_or_uncertain','key':KEY,
        'expires_utc':plan['expires_utc'],
        'organization_id_sha256':None,'organization_binding':None,'properties_before':None,'properties_after':None,
        'packet_sha256':PACKET_SHA256,'packet_bytes':PACKET_BYTES,'local_packet_bytes_read':0,
        'packet_hash_read_bytes':0,'packet_stream_read_bytes':0,'completed_send_bytes':0,'completed_packet_send_bytes':0,
        'completed_send_bytes_is_server_ack':False,'upload_phase_elapsed_ms':None,'operation_elapsed_ms':None,
        'failure_phase':None,'failure_class':None,'phase':'operation_claim',
        'max_upload_phase_seconds':MAX_UPLOAD_SECONDS,'max_operation_seconds':MAX_OPERATION_SECONDS,
        'multipart_body_bytes':None,'upload_attempted':False,'upload_response_success':False,'object_created':False,
        'metadata_size_verified':False,'server_md5_matches_local':False,'receipt_published':False,'object_write_claim':None,
        'object_listing':False,'object_download':False,'object_delete':False,'automatic_retry':False,
        'no_atomic_absence_and_put_guarantee':True,'source_inputs_admitted':False,
        'native_custody_independently_proven':False,'market_trading_authorized':False,'new_jobs':0,'new_looks':0}
    api._publish(root,operation+'.operation.spent.json',frozen)
    try:
        if plan['action']=='organization':
            report['phase']='project_metadata_claim'
            api._publish(root,operation+'.project-read.spent.json',_canonical({'projectId':PROJECT,'max_requests':1}))
            report['phase']='project_metadata_read'
            check();raw,status,token=json_transport('projects/read',{'projectId':PROJECT});check()
            report['phase']='project_metadata_verify'
            body=_body(raw,status,token);rows=body.get('projects')
            if status!=200 or body.get('success') is not True or type(rows) is not list or len(rows)!=1:_fail()
            row=rows[0]
            if type(row) is not dict or api._integer(row.get('projectId'),PROJECT)!=PROJECT or row.get('owner') is not True:_fail()
            organization=row.get('organizationId')
            if type(organization) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,100}',organization) is None:_fail()
            binding={'schema':'tpr-cmp28-own-organization-binding-v1','project_id':PROJECT,'organization_id':organization,
                'organization_id_sha256':_sha(organization.encode()),'source_hashes':plan['source_hashes'],
                'metadata_operation':operation,'wire_sha256':_sha(raw),'created_utc':clock().isoformat()}
            report['organization_binding']=api._publish(root,operation+'.organization.json',_canonical(binding))
            report['organization_id_sha256']=binding['organization_id_sha256'];report['status']='completed_metadata'
        else:
            report['phase']='organization_binding_read'
            descriptor=plan['organization_binding_ref']
            api._publish(root,operation+'.organization-read.spent.json',_canonical(descriptor))
            check();raw=ops.read_private(root,descriptor['name'],MAX_RESPONSE);check()
            if len(raw)!=descriptor['bytes'] or _sha(raw)!=descriptor['sha256']:_fail()
            binding=api._parse(raw)
            api._closed(binding,{'schema','project_id','organization_id','organization_id_sha256','source_hashes',
                'metadata_operation','wire_sha256','created_utc'})
            if (binding['schema']!='tpr-cmp28-own-organization-binding-v1' or binding['project_id']!=PROJECT
                    or binding['source_hashes']!=plan['source_hashes']
                    or not timedelta(0)<=clock()-_clock(binding['created_utc'])<=timedelta(minutes=30)):_fail()
            organization=binding['organization_id'];multipart_parts(organization,KEY)
            if _sha(organization.encode())!=binding['organization_id_sha256']:_fail()
            report['organization_id_sha256']=binding['organization_id_sha256']
            payload={'organizationId':organization,'key':KEY}
            report['phase']='properties_before_claim'
            api._publish(root,operation+'.properties-before.spent.json',_canonical({'payload_sha256':_sha(_canonical(payload)),'key':KEY}))
            report['phase']='properties_before_read'
            check();raw,status,token=json_transport('object/properties',payload);check()
            report['phase']='properties_before_verify'
            report['properties_before']=properties_projection(raw,status,token,KEY)
            if report['properties_before']['classification']!='explicit_absence':_fail()
            api._publish(root,operation+'.upload.spent.json',_canonical({'key':KEY,'packet':plan['packet_file'],
                'organization_id_sha256':report['organization_id_sha256'],'max_effects':1,'max_seconds':MAX_UPLOAD_SECONDS}))
            def read_claim(action):
                if action=='read':
                    api._publish(root,operation+'.packet-read.spent.json',_canonical({'input_root':str(INPUT_ROOT),
                        'packet':plan['packet_file'],'max_passes':2,'max_bytes':2*PACKET_BYTES}))
                elif action=='effect':
                    key_sha256=_sha(KEY.encode())
                    report['object_write_claim']=api._publish(root,'object-key.'+key_sha256+'.write.spent.json',
                        _canonical({'operation_id':operation,'key':KEY,'key_sha256':key_sha256,
                            'packet_sha256':PACKET_SHA256,'max_effects':1}))
                else:_fail()
            report['phase']='upload_transport'
            check();raw,status,token,local_md5=upload_transport(organization,KEY,plan['packet_file'],check,read_claim,report);check()
            report['phase']='upload_response_verify'
            body=_body(raw,status,token)
            if status!=200 or body.get('success') is not True:_fail()
            report['upload_response_success']=True;report['object_created']=True
            report['phase']='properties_after_claim'
            api._publish(root,operation+'.properties-after.spent.json',_canonical({'payload_sha256':_sha(_canonical(payload)),'key':KEY}))
            report['phase']='properties_after_read'
            check();raw,status,token=json_transport('object/properties',payload);check()
            report['phase']='properties_after_verify'
            report['properties_after']=properties_projection(raw,status,token,KEY)
            metadata=report['properties_after']
            if metadata['classification']!='present_refused' or metadata['size']!=PACKET_BYTES:_fail()
            report['metadata_size_verified']=True
            report['server_md5_matches_local']=metadata['md5'] is not None and metadata['md5']==local_md5
            report['status']='completed_upload_metadata_verified'
        report['phase']='completed'
    except BaseException as error:
        stop=error
        if report['failure_phase'] is None:
            report['failure_phase']=report['phase'];report['failure_class']=_failure_class(error)
    report['operation_elapsed_ms']=_elapsed_ms(first_tick)
    report['status']='cancelled' if isinstance(stop,KeyboardInterrupt) else report['status']
    report['receipt_published']=True
    try:report['receipt']=api._publish(root,operation+'.result.json',_canonical(report))
    except BaseException as error:
        report['receipt_published']=False;stop=api._retain_stop(stop,error)
        report['status']='cancelled' if isinstance(stop,KeyboardInterrupt) else 'failed_or_uncertain'
    if isinstance(stop,KeyboardInterrupt):raise api.APICancelled(report) from None
    if stop is not None and not isinstance(stop,Exception):raise api.APIFatal(report) from None
    return api._clone(report)


def _now():return datetime.now(timezone.utc)
def _production(plan,action):
    try:
        if type(plan) is not dict or plan.get('action')!=action or plan.get('mode')!='production':_fail()
        return _execute(plan,root=PRIVATE_ROOT,guard=_guard,json_transport=_native_json,upload_transport=_native_upload,clock=_now)
    except (api.APICancelled,api.APIFatal):raise
    except Exception:_fail()
def execute_metadata_plan(plan):return _production(plan,'organization')
def execute_upload_plan(plan):return _production(plan,'upload')
def _execute_fixture(plan,root,*,json_transport,upload_transport,clock):
    if plan.get('mode')!='offline-fixture':_fail()
    return _execute(plan,root=root,guard=lambda _:None,json_transport=json_transport,upload_transport=upload_transport,clock=clock)
