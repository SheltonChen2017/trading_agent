"""One prospective two-request EODHD fund history/identity diagnostic.

Only SPY metadata and six historical RAW close observations are requested.
Both successful raw bodies are privately retained before semantic analysis in
a separate credential-free network-denied worker. No strategy capture, source
fallback, QC operation, price admission or permanent identity proof follows.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlencode

import requests

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import read_arv2_r298_common_price_manifest_metadata as support
from scripts import arv2_r298_ar_source_binding as anchor
from scripts import arv2_keychain_connections as keychain

ar,ap=support.ar,support.ar.ap
admitted,environment,PYTHON=ar.admitted,ar.environment,ar.PYTHON
canonical,sha,pin,parse,metadata=ar.canonical,ar.sha,ar.pin,ar.parse,ar.metadata
SOURCE=ROOT/'scripts/run_arv2_r298_eodhd_history_diagnostic.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_history_diagnostic/R326-20261027-AU'
SCHEMA='arv2-r298-eodhd-fund-history-diagnostic-au-v1'
PARENT_SECONDS,PROVIDER_SECONDS,AUTH_SECONDS,VALIDATOR_SECONDS=120,60,30,30
MAX_BODY,MAX_FRAME,MAX_JOURNAL=65536,65536,2048
DATA_FILES=('metadata-private.json','history-private.json','requests.jsonl')
ROLES=('provider','authenticate')
DATES=('2020-12-31','2021-01-04','2021-01-05','2021-01-06','2021-01-07','2021-01-08')
EXPECTED_ISIN='US78462F1030'
HOST='https://eodhd.com'
REQUESTS=(('/api/exchange-symbol-list/US',{'fmt':'json','symbols':'SPY','delisted':'0','type':'etf'}),
    ('/api/eod/SPY.US',{'fmt':'json','from':'2020-12-31','to':'2021-01-08','period':'d','order':'a'}))
ANCHOR_FACT_SHA256='19194ca0fc562b4b0fed8331d7c6e725c3dd7cc31fada7fa519a08acc10d28b3'
ANCHOR_OUTPUT_SHA256='70e6def0fe2621965904e31fe8121c7713c5201b9b151397766f78091e7ab843'
NEW_PINS={'scripts/read_arv2_r298_common_price_manifest_metadata.py':'1cb61514eb650cd3f360dfb0f5e58c486d443cf5ec104ccda46aa8d740e7c783',
    'scripts/arv2_r298_ar_source_binding.py':'52ae31ddb440e1ecaf693d54fb6cf6d48ee377813d8614e7ce3cee5a02d68d76'}
FALSE_FLAGS={'strategy_capture':False,'fallback_source_selected':False,'price_input_admitted':False,
    'complete_strategy_price_coverage_proven':False,'permanent_identity_proven':False,'point_in_time_proven':False,
    'formal_forward_ready':False,'paper_or_live_ready':False,'QC_contact':False,'new_paid_rights':False,
    'licensed_rows_disclosed':False,'recognized_credential_encodings_retained':False,
    'physical_request_count_measured':False,'old_controls_read':False}
FINITE=frozenset(('host','arguments','environment','source_pin','source_binding','git_state','deadline','public_CA',
    'claim_spent','control_changed','control_security','control_bound','control_write','credential_handoff',
    'inherited','worker_scope','worker_packet','worker_failed','request','response','http_status','http_refused',
    'body_bound','credential_echo','journal','metadata_shape','history_shape','diagnostic_incomplete','output',
    'os_error','unknown'))|frozenset(code for code in ap.FINITE if code.startswith('transport_'))


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args=BaseException.args.__get__(error)
        return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is admitted.helpers.Deadline:return 'deadline'
    if type(error) is environment.EnvironmentRefused:return 'environment'
    if type(error) is keychain.KeychainUnavailable:return 'credential_handoff'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=PARENT_SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def source_context():
    fact,output=anchor.observed_fact(),anchor.sidecar_output()
    require(sha(canonical(fact))==ANCHOR_FACT_SHA256 and sha(canonical(output))==ANCHOR_OUTPUT_SHA256
        and fact['complete_original_payload_recovered'] is True,'source_binding')
    raw=canonical(output)+b'\n'
    for role in ('AR_producer','AR_native_validator','AS_actual'):
        observed=fact[role]
        try:ap.public_transport._actual_metadata(observed)
        except BaseException:raise Refused('source_binding') from None
        require(type(observed['actual_exit']) is int and observed['actual_exit']==0
            and observed['spawn_observed'] is True and observed['bound'] is None
            and observed['stderr_bytes']==0 and observed['stderr_sha256']==sha(b'')
            and observed['stdout_bytes']==len(raw) and observed['stdout_sha256']==sha(raw),'source_binding')
    old=SimpleNamespace(**{key:value for key,value in fact['AR_binding'].items() if key!='schema'})
    ar.validate_output(raw,0,old)
    require(all(fact[key] is False for key in ('new_operation_or_read_granted','QC_transfer_granted',
        'QC_processing_rights_granted','price_input_admitted','point_in_time_proven','formal_forward_ready','paper_or_live_ready')),'source_binding')
    return {'AR_AS_fact_sha256':ANCHOR_FACT_SHA256,'AR_output_sha256':ANCHOR_OUTPUT_SHA256,
        'AR_report_pin':fact['AR_report_pin'],'source_history_barrier_observed':True,
        'source_history_barrier_is_not_authenticated_subscription_cause':True}


def pins():
    result=support.pins()
    for name,value in NEW_PINS.items():
        require(name not in result or result[name]==value,'source_pin');result[name]=value
    return result


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),'source_context':source_context(),
        'purpose':'existing_EODHD_current_identity_and_pre2021_fund_history_availability_not_replacement_capture',
        'request_inventory':[{'ordinal':i,'endpoint':HOST+path,'parameters':params} for i,(path,params) in enumerate(REQUESTS)],
        'maximum_application_dispatches':2,'parent_seconds':PARENT_SECONDS,'provider_seconds':PROVIDER_SECONDS,
        'authentication_seconds':AUTH_SECONDS,'validator_seconds':VALIDATOR_SECONDS,'request_seconds':25,
        'maximum_body_bytes':MAX_BODY,'expected_dates':list(DATES),'RAW_field':'close','expected_public_ISIN':EXPECTED_ISIN,
        'metadata_ISIN_field':'Isin','venue_is_display_metadata_not_historical_master':True,
        'existing_keychain_service':'trading-agent-eodhd','existing_keychain_account':'eodhd','keychain_lookups':1,
        'claim_and_source_pins_complete_AR_AS_proof_before_keychain':True,
        'CA':{'path':str(ap.public_transport.CA_PATH),'byte_count':ap.public_transport.CA_BYTES,'sha256':ap.public_transport.CA_SHA256},
        'CA_held_bytes_owned_SSLContext_no_default_CA_or_client_cert':True,'HTTP_retries':0,'redirects':False,
        'failed_body_application_read':False,'HTTP200_secret_scanned_before_retention_and_separate_semantics':True,
        'recognized_encodings':'bounded_raw_URL_JSON_and_CSV_doubled_quotes_not_general_secrecy_proof',
        'provider_no_body_JSON_parse':True,'body_pins_and_original_descriptors_held_through_native_auth_return':True,
        'metadata_and_history_independent_finite_evidence_retained_even_if_identity_unresolved':True,
        'current_vintage_nonatomic_not_immutable_history':True,'parent_actual0_and_external_native_validator0_required':True,
        'ordinary_outer_independent_native_children_no_nested_outer_sandbox':True,
        'uninterruptible_IO_and_host_suspension_can_exceed_deadline':True,**FALSE_FLAGS}


def binding(args):return {'schema':SCHEMA,'expected_head':args.expected_head,
    'caller_sha256':args.caller_sha256,'profile_sha256':args.profile_sha256}


def _ca_bytes():
    try:raw=ap.public_transport._ca_bytes()
    except BaseException:raise Refused('public_CA') from None
    require(len(raw)==ap.public_transport.CA_BYTES and sha(raw)==ap.public_transport.CA_SHA256,'public_CA');return raw


def preflight(args,deadline):
    require(not admitted.v5._under_test() and sys.platform=='darwin' and os.name=='posix'
        and sys.version_info[:2]==(3,13) and Path(sys.executable)==PYTHON and Path.cwd()==ROOT
        and ROOT.resolve()==ROOT and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    ar._credential_free();environment._require_environment();source_context();_ca_bytes()
    for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],admitted.frozen.BRANCH),
            (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
        require(admitted.v5._git(command,deadline).decode('ascii').strip()==expected,'git_state')
    for name,expected in pins().items():require(sha((ROOT/name).read_bytes())==expected,'source_pin')
    require(sha(SOURCE.read_bytes())==args.caller_sha256 and sha(admitted.v5._git(
        ['cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],deadline,256*1024))==args.caller_sha256
        and sha(canonical(profile_record()))==args.profile_sha256,'source_pin');remaining(deadline)


def _security(fd):
    try:return ap.security.snapshot(fd)
    except ap.security.Refusal:raise Refused('control_security') from None


def _write(fd,raw):
    view=memoryview(raw)
    while view:
        count=os.write(fd,view);require(count>0,'control_write');view=view[count:]
    os.fsync(fd)


def _read(fd,maximum,deadline):
    info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and 0<=info.st_size<=maximum,'control_bound')
    before,snapshot=metadata(info),_security(fd);raw=bytearray()
    while len(raw)<info.st_size:
        remaining(deadline);chunk=os.pread(fd,min(65536,info.st_size-len(raw)),len(raw))
        require(chunk,'control_changed');raw.extend(chunk)
    require(metadata(os.fstat(fd))==before and _security(fd)==snapshot,'control_changed');return bytes(raw)


class Store:
    def __init__(self):
        self.fd,self.chain,self.held=None,[],{};fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for index,part in enumerate(CONTROL.parts[1:],1):
                here=Path(*CONTROL.parts[:index+1])
                if here in (CONTROL.parent,CONTROL):
                    try:os.mkdir(part,0o700,dir_fd=fd);os.fsync(fd)
                    except FileExistsError:require(here!=CONTROL,'claim_spent')
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=nxt;self.chain.append((os.fstat(fd).st_dev,os.fstat(fd).st_ino))
            self.fd,self.snapshot=fd,_security(fd);self.verify()
        except BaseException:os.close(fd);raise
    def __enter__(self):return self
    def __exit__(self,*_):
        failed=False
        for row in self.held.values():
            try:os.close(row['fd'])
            except OSError:failed=True
        try:os.close(self.fd)
        except OSError:failed=True
        require(not failed,'control_changed')
    def verify(self):
        other,chain=admitted._storage_module()._walk(CONTROL)
        try:
            info=os.fstat(other)
            require(chain==tuple(self.chain) and metadata(info)==metadata(os.fstat(self.fd))
                and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700
                and _security(self.fd)==self.snapshot and set(os.listdir(other))==set(self.held),'control_changed')
            for name,row in self.held.items():
                info=os.stat(name,dir_fd=other,follow_symlinks=False)
                require(metadata(info)==row['metadata']==metadata(os.fstat(row['fd'])) and stat.S_ISREG(info.st_mode)
                    and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and info.st_uid==os.getuid()
                    and _security(row['fd'])==row['security'],'control_changed')
        finally:os.close(other)
    def create(self,name,raw=b''):
        self.verify();require(name not in self.held and len(self.held)<16
            and (name in DATA_FILES or re.fullmatch(r'[a-z-]{1,40}\.json',name)),'control_bound')
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        self.held[name]={'fd':fd,'metadata':metadata(os.fstat(fd)),'security':_security(fd)}
        if raw:_write(fd,raw)
        os.fsync(self.fd);self.refresh((name,));return fd
    def refresh(self,names):
        for name in names:
            row=self.held[name];old,new=row['metadata'],metadata(os.fstat(row['fd']))
            require(new[:6]==old[:6] and new[9]==old[9] and new[6]>=old[6]
                and new==metadata(os.stat(name,dir_fd=self.fd,follow_symlinks=False))
                and _security(row['fd'])==row['security'],'control_changed');row['metadata']=new
        self.verify()
    def write(self,name,value):
        raw=canonical(value);require(0<len(raw)<=MAX_FRAME,'control_bound');self.create(name,raw);return pin(raw)


def native_profile(role):
    require(role in (*ROLES,'validate'),'arguments')
    value='(version 1)(allow default)'+(ap.public_transport.EGRESS if role=='provider' else '(deny network*)')
    value+=''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))'
    allowed=f'(require-not (subpath "{ROOT/".pytest_cache"}"))(require-not (literal "/dev/null"))'
    if role!='validate':allowed+=f'(require-not (subpath "{CONTROL}"))'
    value+='(deny file-write* (require-all '+allowed+'))'
    if role=='validate':return value+f'(deny file-read* (subpath "{ROOT/"artifacts"}"))'
    # Own protocol directory only, no AR/AP DATA or old controls.
    return value+ap.previous._artifact_policy([CONTROL])+f'(allow file-read* file-write* (subpath "{CONTROL}"))'


class OwnedAdapter(requests.adapters.HTTPAdapter):
    def __init__(self,ca_raw):
        require(type(ca_raw) is bytes and len(ca_raw)==ap.public_transport.CA_BYTES
            and sha(ca_raw)==ap.public_transport.CA_SHA256,'public_CA')
        self.ca_ascii=ca_raw.decode('ascii');self.context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.check_hostname=True;self.context.verify_mode=ssl.CERT_REQUIRED
        self.context.minimum_version=ssl.TLSVersion.TLSv1_2;self.context.load_verify_locations(cadata=self.ca_ascii)
        super().__init__(max_retries=0,pool_connections=1,pool_maxsize=1)
    def init_poolmanager(self,connections,maxsize,block=False,**kwargs):
        kwargs['ssl_context']=self.context;return super().init_poolmanager(connections,maxsize,block,**kwargs)
    def cert_verify(self,conn,url,verify,cert):
        require(url.startswith(HOST+'/api/') and verify is True and cert is None,'request')
        conn.cert_reqs,conn.ca_certs,conn.ca_cert_dir,conn.ca_cert_data='CERT_REQUIRED',None,None,self.ca_ascii
    def build_connection_pool_key_attributes(self,request,verify,cert=None):
        require(verify is True and cert is None and request.url.startswith(HOST+'/api/'),'request')
        host,kwargs=super().build_connection_pool_key_attributes(request,verify,cert)
        kwargs.update(ssl_context=self.context,cert_reqs='CERT_REQUIRED',ca_certs=None,ca_cert_dir=None,ca_cert_data=self.ca_ascii)
        return host,kwargs
    def proxy_manager_for(self,*args,**kwargs):raise Refused('request')


class OwnedSession(requests.Session):
    def resolve_redirects(self,*args,**kwargs):return iter(())


def _session(ca_raw):
    value=OwnedSession();value.trust_env,value.auth,value.verify,value.cert,value.max_redirects=False,None,True,None,0
    value.headers.clear();value.cookies.clear();value.proxies.clear();value.params.clear();value.adapters.clear()
    value.hooks={'response':[]};value.mount('https://',OwnedAdapter(ca_raw));return value


def _session_check(value,url):
    adapter=value.get_adapter(url)
    require(type(value) is OwnedSession and value.trust_env is False and value.auth is None and value.verify is True
        and value.cert is None and value.max_redirects==0 and not value.headers and not value.cookies
        and not value.proxies and not value.params and value.hooks=={'response':[]}
        and set(value.adapters)=={'https://'} and type(adapter) is OwnedAdapter and adapter.max_retries.total==0
        and adapter.context.check_hostname is True and adapter.context.verify_mode==ssl.CERT_REQUIRED
        and adapter.context.minimum_version>=ssl.TLSVersion.TLSv1_2
        and sha(adapter.ca_ascii.encode('ascii'))==ap.public_transport.CA_SHA256,'request')


def request_record(ordinal):
    require(type(ordinal) is int and 0<=ordinal<2,'request');path,params=REQUESTS[ordinal]
    return {'ordinal':ordinal,'endpoint':HOST+path,'parameters':dict(params)}


def _provider_state():
    return {'application_dispatch_intents':0,'completed_HTTP200_bodies':0,'current_ordinal':None,
        'HTTP_status_type':'not_observed','HTTP_status':None,'transport_failure':None,'OS_errno':None,
        'body_pins':[],'journal_pin':None,'provider_request_count':None}


def fetch(ordinal,key,state,ca_raw,deadline):
    item=request_record(ordinal);params={**item['parameters'],'api_token':key};url=item['endpoint']+'?'+urlencode(params)
    secrets=ap._secret_encodings(key)
    with _session(ca_raw) as session:
        _session_check(session,url)
        prepared=session.prepare_request(requests.Request('GET',item['endpoint'],params=params,headers={'Accept-Encoding':'identity'}))
        require(prepared.method=='GET' and prepared.url==url and prepared.body is None
            and dict(prepared.headers)=={'Accept-Encoding':'identity'} and prepared.hooks=={'response':[]},'request')
        try:
            with session.send(prepared,timeout=min(25,remaining(deadline)),allow_redirects=False,stream=True,verify=True,proxies={}) as response:
                status=response.status_code;state['HTTP_status_type']='int' if type(status) is int and 100<=status<=599 else 'other'
                require(type(status) is int and 100<=status<=599,'http_status');state['HTTP_status']=status
                require(response.url==url and response.request is prepared and not response.history,'response')
                require(status==200,'http_refused')
                _session_check(session,url);environment.require_safe_environment();headers=response.headers
                require(len(headers)<=64 and not headers.get('Set-Cookie')
                    and headers.get('Content-Encoding','identity').casefold()=='identity','response')
                for name,value in headers.items():
                    require(type(name) is str and type(value) is str and len(name)+len(value)<=8192
                        and not any(secret in (name+':'+value).encode('utf-8') for secret in secrets),'credential_echo')
                length=headers.get('Content-Length')
                require(length is None or type(length) is str and length.isdecimal() and len(length)<=6
                    and 0<int(length)<=MAX_BODY,'body_bound')
                body=bytearray()
                for chunk in response.iter_content(chunk_size=MAX_BODY):
                    remaining(deadline);require(type(chunk) is bytes and len(body)+len(chunk)<=MAX_BODY,'body_bound');body.extend(chunk)
                require(0<len(body)<=MAX_BODY and (length is None or len(body)==int(length)),'body_bound')
                require(not any(secret in body for secret in secrets),'credential_echo');return bytes(body)
        except requests.exceptions.RequestException as error:
            state['transport_failure']=ap.previous.transport_failure(error);state['OS_errno']=ap._errno(error)
            raise Refused(state['transport_failure']) from None


def _intent(fd,ordinal,deadline):
    remaining(deadline);old=metadata(os.fstat(fd));snapshot=_security(fd)
    require(stat.S_ISREG(old[2]) and old[6]<MAX_JOURNAL,'journal')
    require(os.lseek(fd,0,os.SEEK_END)==old[6],'journal')
    _write(fd,canonical({'ordinal':ordinal,'request_sha256':sha(canonical(request_record(ordinal)))})+b'\n')
    fresh=metadata(os.fstat(fd));require(fresh[:6]==old[:6] and fresh[9]==old[9]
        and fresh[6]<=MAX_JOURNAL and _security(fd)==snapshot,'journal')


def provider_observation(fds,key,state,deadline):
    ca_raw=_ca_bytes();require(all(os.fstat(fd).st_size==0 for fd in fds),'worker_scope')
    for ordinal in range(2):
        state.update(current_ordinal=ordinal,HTTP_status_type='not_observed',HTTP_status=None)
        _intent(fds[2],ordinal,deadline);state['application_dispatch_intents']+=1
        body=fetch(ordinal,key,state,ca_raw,deadline)
        require(os.fstat(fds[ordinal]).st_size==0,'worker_scope');_write(fds[ordinal],body)
        state['body_pins'].append(pin(body));state['completed_HTTP200_bodies']+=1
    state['journal_pin']=pin(_read(fds[2],MAX_JOURNAL,deadline));validate_provider(state,success=True);return state


def validate_provider(value,*,success=False):
    require(type(success) is bool,'output')
    require(type(value) is dict and set(value)==set(_provider_state())
        and all(type(value[key]) is int for key in ('application_dispatch_intents','completed_HTTP200_bodies'))
        and 0<=value['completed_HTTP200_bodies']<=value['application_dispatch_intents']<=2
        and value['current_ordinal'] in (None,0,1) and type(value['current_ordinal']) in (int,type(None))
        and value['HTTP_status_type'] in ('not_observed','int','other')
        and (value['HTTP_status'] is None or type(value['HTTP_status']) is int and 100<=value['HTTP_status']<=599)
        and (value['transport_failure'] is None or value['transport_failure'] in FINITE)
        and (value['OS_errno'] is None or type(value['OS_errno']) is int and -65535<=value['OS_errno']<=65535)
        and value['provider_request_count'] is None and type(value['body_pins']) is list
        and len(value['body_pins'])==value['completed_HTTP200_bodies'],'output')
    for item in value['body_pins']:ap._pin(item,MAX_BODY)
    require((value['HTTP_status_type']=='int') is (type(value['HTTP_status']) is int),'output')
    ordinal=value['current_ordinal'];intents=value['application_dispatch_intents'];bodies=value['completed_HTTP200_bodies']
    if ordinal is None:require(intents==bodies==0,'output')
    elif ordinal==0:require(intents<=1 and bodies<=1,'output')
    else:require(intents in (1,2) and bodies>=1,'output')
    if value['journal_pin'] is not None:ap._pin(value['journal_pin'],MAX_JOURNAL)
    if success:require(value['completed_HTTP200_bodies']==value['application_dispatch_intents']==2
        and value['current_ordinal']==1 and value['HTTP_status_type']=='int' and value['HTTP_status']==200
        and value['transport_failure'] is value['OS_errno'] is None and value['journal_pin'] is not None,'output')
    return value


def _decode(raw,code):
    require(type(raw) is bytes and 0<len(raw)<=MAX_BODY,code)
    def pairs(items):
        result={}
        for key,value in items:require(key not in result,code);result[key]=value
        return result
    def number(text):
        require(type(text) is str and len(text)<=64,code)
        try:return Decimal(text)
        except DecimalException:raise Refused(code) from None
    try:return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_float=number,parse_int=number,
        parse_constant=lambda _:(_ for _ in ()).throw(Refused(code)))
    except (ValueError,UnicodeError,RecursionError):raise Refused(code) from None


def analyse(metadata_raw,history_raw):
    value={'schema':SCHEMA+'-authentication','body_pins':[pin(metadata_raw),pin(history_raw)],
        'metadata_schema_valid':False,'metadata_row_count':None,'identity_matched':False,'identity_status':'unresolved',
        'metadata_row_sha256':None,'history_schema_valid':False,'history_row_count':None,'positive_RAW_close_count':None,
        'expected_date_coverage':False,'observed_dates_sha256':None,'RAW_close_series_sha256':None,
        'date_window_sha256':sha(canonical(list(DATES))),**FALSE_FLAGS}
    try:
        rows=_decode(metadata_raw,'metadata_shape');require(type(rows) is list and len(rows)==1,'metadata_shape')
        row=rows[0];require(type(row) is dict and set(row)=={'Code','Name','Country','Exchange','Currency','Type','Isin'}
            and all(type(row[key]) is str and 0<len(row[key])<=512 and all(32<=ord(char)<=126 for char in row[key])
                for key in ('Code','Name','Country','Exchange','Currency','Type'))
            and (row['Isin'] is None or type(row['Isin']) is str and len(row['Isin'])<=32),'metadata_shape')
        matched=(row['Code']=='SPY' and row['Type']=='ETF' and row['Currency']=='USD' and row['Isin']==EXPECTED_ISIN)
        value.update(metadata_schema_valid=True,metadata_row_count=1,identity_matched=matched,
            identity_status='matched_current_vendor_fund' if matched else 'unresolved',metadata_row_sha256=sha(canonical(row)))
    except Refused:pass
    try:
        rows=_decode(history_raw,'history_shape');require(type(rows) is list and len(rows)<=32,'history_shape')
        dates=[];closes=[]
        for row in rows:
            require(type(row) is dict and set(row)=={'date','open','high','low','close','adjusted_close','volume'}
                and type(row['date']) is str and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',row['date']),'history_shape')
            try:date.fromisoformat(row['date'])
            except ValueError:raise Refused('history_shape') from None
            close=row['close'];require(type(close) is Decimal and close.is_finite() and 0<close<=Decimal('1000000000')
                and len(close.as_tuple().digits)<=28 and close.as_tuple().exponent>=-12,'history_shape')
            dates.append(row['date']);closes.append([row['date'],format(close,'f')])
        value.update(history_schema_valid=True,history_row_count=len(rows),positive_RAW_close_count=len(rows),
            expected_date_coverage=tuple(dates)==DATES,observed_dates_sha256=sha(canonical(dates)),RAW_close_series_sha256=sha(canonical(closes)))
    except Refused:pass
    validate_authentication(value);return value


def validate_authentication(value,provider=None):
    fields={'schema','body_pins','metadata_schema_valid','metadata_row_count','identity_matched','identity_status',
        'metadata_row_sha256','history_schema_valid','history_row_count','positive_RAW_close_count','expected_date_coverage',
        'observed_dates_sha256','RAW_close_series_sha256','date_window_sha256',*FALSE_FLAGS}
    require(type(value) is dict and set(value)==fields and value['schema']==SCHEMA+'-authentication'
        and all(type(value[key]) is bool for key in ('metadata_schema_valid','identity_matched','history_schema_valid','expected_date_coverage'))
        and value['identity_status'] in ('unresolved','matched_current_vendor_fund')
        and (value['identity_status']=='matched_current_vendor_fund') is value['identity_matched']
        and value['date_window_sha256']==sha(canonical(list(DATES))) and all(value[key] is False for key in FALSE_FLAGS)
        and type(value['body_pins']) is list and len(value['body_pins'])==2,'output')
    for item in value['body_pins']:ap._pin(item,MAX_BODY)
    if provider is not None:require(value['body_pins']==provider['body_pins'],'output')
    if value['metadata_schema_valid']:
        require(type(value['metadata_row_count']) is int and value['metadata_row_count']==1 and _hash(value['metadata_row_sha256']),'output')
    else:require(value['metadata_row_count'] is value['metadata_row_sha256'] is None and value['identity_matched'] is False,'output')
    if value['history_schema_valid']:
        require(type(value['history_row_count']) is type(value['positive_RAW_close_count']) is int
            and 0<=value['history_row_count']==value['positive_RAW_close_count']<=32
            and _hash(value['observed_dates_sha256']) and _hash(value['RAW_close_series_sha256']),'output')
        if value['expected_date_coverage']:require(value['history_row_count']==6
            and value['observed_dates_sha256']==sha(canonical(list(DATES))),'output')
    else:require(value['history_row_count'] is value['positive_RAW_close_count'] is value['observed_dates_sha256']
        is value['RAW_close_series_sha256'] is None and value['expected_date_coverage'] is False,'output')
    return value


def authenticate_observation(fds,provider,deadline):
    validate_provider(provider,success=True);before=[(metadata(os.fstat(fd)),_security(fd)) for fd in fds]
    raw=[_read(fd,MAX_BODY if i<2 else MAX_JOURNAL,deadline) for i,fd in enumerate(fds)]
    require([pin(item) for item in raw[:2]]==provider['body_pins'] and pin(raw[2])==provider['journal_pin'],'journal')
    expected=b''.join(canonical({'ordinal':i,'request_sha256':sha(canonical(request_record(i)))})+b'\n' for i in range(2))
    require(raw[2]==expected,'journal');result=analyse(raw[0],raw[1])
    require([(metadata(os.fstat(fd)),_security(fd)) for fd in fds]==before,'control_changed')
    validate_authentication(result,provider);return result


def _inherited(args,role,packet,deadline):
    fds=(args.control_fd,args.claim_fd,args.intent_fd,args.started_fd,*args.data_fds)
    require(all(type(fd) is int and fd>2 for fd in fds) and len(set(fds))==len(fds)
        and len(args.data_fds)==3,'inherited')
    info=os.fstat(args.control_fd);require(metadata(info)==metadata(os.stat(CONTROL,follow_symlinks=False))
        and stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o700 and info.st_uid==os.getuid(),'inherited');_security(args.control_fd)
    for fd,name in zip(fds[1:],('claim.json',role+'-intent.json',role+'-started.json',*DATA_FILES),strict=True):
        info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600
            and info.st_uid==os.getuid() and info.st_nlink==1
            and metadata(info)==metadata(os.stat(name,dir_fd=args.control_fd,follow_symlinks=False)),'inherited');_security(fd)
    expected={**binding(args),'role':role,'input_pin':pin(packet)}
    require(_read(args.claim_fd,MAX_FRAME,deadline)==canonical(binding(args))
        and _read(args.intent_fd,MAX_FRAME,deadline)==canonical(expected) and os.fstat(args.started_fd).st_size==0,'worker_scope')
    _write(args.started_fd,canonical(expected));os.fsync(args.control_fd)


def _capture_child(command,safe,packet,inherited,seconds):
    deadline=time.monotonic()+seconds;output,errors=bytearray(),bytearray();final=None
    actual={'actual_exit':None,'spawn_observed':False,'bound':None,'stdout_bytes':0,'stdout_sha256':sha(b''),
        'stderr_bytes':0,'stderr_sha256':sha(b'')}
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env=safe,pass_fds=tuple(inherited),close_fds=True);actual['spawn_observed']=True
    try:
        process.stdin.write(packet);process.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ,'out');selector.register(process.stderr,selectors.EVENT_READ,'err')
            while selector.get_map():
                if time.monotonic()>=deadline:actual['bound']='deadline';raise Refused('deadline')
                for event,_ in selector.select(min(1,deadline-time.monotonic())):
                    chunk=os.read(event.fileobj.fileno(),65536)
                    if not chunk:selector.unregister(event.fileobj);continue
                    target=output if event.data=='out' else errors;target.extend(chunk);require(len(target)<=MAX_FRAME,'worker_packet')
        process.wait(timeout=max(.01,deadline-time.monotonic()));require(not errors and output.endswith(b'\n')
            and output.count(b'\n')==1,'worker_packet');final=parse(bytes(output[:-1]))
    except BaseException as error:final={'capture_failure':finite(error)}
    finally:
        if process.poll() is None:process.kill()
        process.wait();actual.update(actual_exit=process.returncode,stdout_bytes=len(output),stdout_sha256=sha(bytes(output)),
            stderr_bytes=len(errors),stderr_sha256=sha(bytes(errors)));process.stdout.close();process.stderr.close()
    return final,actual


def _child(args,store,role,payload,runtime,deadline,key=None):
    packet=canonical(payload);store.write(role+'-intent.json',{**binding(args),'role':role,'input_pin':pin(packet)})
    started=store.create(role+'-started.json');fds=[store.held[name]['fd'] for name in DATA_FILES]
    inherited=[store.fd,store.held['claim.json']['fd'],store.held[role+'-intent.json']['fd'],started,*fds]
    command=['/usr/bin/sandbox-exec','-p',native_profile(role),str(PYTHON),'-B',str(SOURCE),role,
        '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
        '--control-fd',str(inherited[0]),'--claim-fd',str(inherited[1]),'--intent-fd',str(inherited[2]),
        '--started-fd',str(started),'--data-fds',','.join(map(str,fds))]
    read=write=None
    try:
        if role=='provider':
            ap._secret_encodings(key);read,write=os.pipe();require(os.write(write,key.encode('ascii'))==len(key),'credential_handoff')
            os.close(write);write=None;inherited.append(read);command+=['--credential-fd',str(read)]
        final,actual=_capture_child(command,ap.capture_support._environment(runtime,None),packet,inherited,
            min(PROVIDER_SECONDS if role=='provider' else AUTH_SECONDS,remaining(deadline)))
    finally:
        if read is not None:os.close(read)
        if write is not None:os.close(write)
        store.refresh((role+'-started.json',*(DATA_FILES if role=='provider' else ())))
    final=_safe_packet(final,args,role);store.write(role+'-observed.json',{'actual':actual,'packet_pin':pin(canonical(final))})
    return final,actual


def _safe_packet(value,args,role):
    try:_packet(value,args,role);return value
    except BaseException:return {'capture_failure':'worker_packet'}


def _packet(value,args,role):
    require(type(value) is dict,'worker_packet')
    if set(value)=={'capture_failure'}:require(value['capture_failure'] in FINITE,'worker_packet');return
    require(value.get('binding')==binding(args),'worker_packet')
    if set(value)=={'binding','outside_failure'}:require(value['outside_failure'] in FINITE,'worker_packet');return
    require(set(value)=={'binding','role','result','failure_code'} and value['role']==role
        and (value['failure_code'] is None or value['failure_code'] in FINITE),'worker_packet')
    if role=='provider':validate_provider(value['result'],success=value['failure_code'] is None)
    else:
        if value['result'] is not None:validate_authentication(value['result'])
        if value['failure_code'] is None:require(value['result'] is not None
            and value['result']['identity_matched'] is True and value['result']['expected_date_coverage'] is True,'worker_packet')


def _packet_join(packet,actual,args,role):
    ap._actual(actual);_packet(packet,args,role)
    if set(packet)=={'capture_failure'}:return
    require(actual['stdout_bytes']==len(canonical(packet))+1 and actual['stdout_sha256']==sha(canonical(packet)+b'\n'),'output')
    require(actual['spawn_observed'] is True and actual['bound'] is None and actual['stderr_bytes']==0
        and actual['stderr_sha256']==sha(b''),'output')
    if 'outside_failure' in packet:require(actual['actual_exit']==2,'output')
    else:require(actual['actual_exit']==(0 if packet['failure_code'] is None else 2),'output')


def run(args,deadline):
    state={'stage':'claim','credential_handoff_complete':False,'provider':None,'provider_actual':None,
        'authentication':None,'authentication_actual':None,'child_packets':{}};key=None
    with Store() as store:
        store.write('claim.json',binding(args))
        for name in DATA_FILES:store.create(name)
        try:
            state['stage']='source_proof';source_context();preflight(args,deadline)
            state['stage']='credential_handoff';key=keychain.load_key('eodhd',timeout_seconds=min(20,remaining(deadline)))
            state['credential_handoff_complete']=True
            runtime=Path(tempfile.mkdtemp(prefix='r326-au-runtime-',dir=ROOT/'.pytest_cache'))
            state['stage']='provider';packet,actual=_child(args,store,'provider',{},runtime,deadline,key=key);key=None
            state['child_packets']['provider']=packet;state['provider_actual']=actual;_packet_join(packet,actual,args,'provider')
            require(set(packet)=={'binding','role','result','failure_code'},'worker_failed')
            state['provider']=packet['result'];require(packet['failure_code'] is None,'worker_failed');ap._actual(actual,zero=True)
            state['stage']='authenticate';packet,actual=_child(args,store,'authenticate',{'provider':state['provider']},runtime,deadline)
            state['child_packets']['authenticate']=packet;state['authentication_actual']=actual;_packet_join(packet,actual,args,'authenticate')
            require(set(packet)=={'binding','role','result','failure_code'},'worker_failed');state['authentication']=packet['result']
            require(packet['failure_code'] is None,'diagnostic_incomplete');ap._actual(actual,zero=True)
            state['stage']='postflight';preflight(args,deadline);store.verify();environment.require_safe_environment()
            result={'schema':SCHEMA,**state,'source_context':source_context(),'provider_request_count':None,
                'post_checks_complete':True,**FALSE_FLAGS};validate_result(result,args)
            report=store.write('report.json',{**binding(args),'result':result});store.verify();return {'result':result,'report':report}
        except BaseException as error:
            failed={'failure_code':finite(error),'state':state,'claim_consumed':True,'provider_request_count':None,**FALSE_FLAGS}
            try:store.write('failure.json',{**binding(args),**failed})
            except BaseException:pass
            return {'failure':failed}
        finally:key=None


def _state(value,args):
    require(type(value) is dict and set(value)=={'stage','credential_handoff_complete','provider','provider_actual',
        'authentication','authentication_actual','child_packets'} and value['stage'] in ('claim','source_proof',
        'credential_handoff','provider','authenticate','postflight') and type(value['credential_handoff_complete']) is bool
        and type(value['child_packets']) is dict and set(value['child_packets']) in (set(),{'provider'},{'provider','authenticate'}),'output')
    for role in ROLES:
        actual_name='authentication_actual' if role=='authenticate' else 'provider_actual'
        result_name='authentication' if role=='authenticate' else 'provider'
        if role in value['child_packets']:
            packet=value['child_packets'][role];_packet_join(packet,value[actual_name],args,role)
            require(packet.get('result')==value[result_name],'output')
        else:require(value[actual_name] is value[result_name] is None,'output')
    if value['provider'] is not None:require(value['credential_handoff_complete'],'output');validate_provider(value['provider'])
    if value['authentication'] is not None:validate_provider(value['provider'],success=True);validate_authentication(value['authentication'],value['provider'])


def validate_result(value,args):
    state_keys={'stage','credential_handoff_complete','provider','provider_actual','authentication','authentication_actual','child_packets'}
    require(type(value) is dict and set(value)=={'schema',*state_keys,'source_context','provider_request_count',
        'post_checks_complete',*FALSE_FLAGS} and value['schema']==SCHEMA and value['source_context']==source_context()
        and value['provider_request_count'] is None and value['post_checks_complete'] is True
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    _state({key:value[key] for key in state_keys},args)
    require(value['stage']=='postflight' and value['credential_handoff_complete'] is True
        and value['authentication'] is not None and value['authentication']['identity_matched'] is True
        and value['authentication']['expected_date_coverage'] is True,'output')
    for key in ('provider_actual','authentication_actual'):ap._actual(value[key],zero=True)


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_FRAME and raw.endswith(b'\n') and raw.count(b'\n')==1
        and type(actual_exit) is int and actual_exit in (0,2),'output');value=parse(raw[:-1])
    require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','outside_failure'}:require(actual_exit==2 and value['outside_failure'] in FINITE,'output');return value
    require(set(value)=={'binding','outcome'} and type(value['outcome']) is dict,'output');outcome=value['outcome']
    if set(outcome)=={'failure'}:
        failed=outcome['failure'];require(actual_exit==2 and type(failed) is dict
            and set(failed)=={'failure_code','state','claim_consumed','provider_request_count',*FALSE_FLAGS}
            and failed['failure_code'] in FINITE and failed['claim_consumed'] is True
            and failed['provider_request_count'] is None and all(failed[key] is False for key in FALSE_FLAGS),'output');_state(failed['state'],args)
    else:
        require(actual_exit==0 and set(outcome)=={'result','report'},'output');validate_result(outcome['result'],args)
        require(outcome['report']==pin(canonical({**binding(args),'result':outcome['result']})),'output')
    return value


def emit(value):
    raw=canonical(value);require(len(raw)<MAX_FRAME,'output');sys.stdout.buffer.write(raw+b'\n');sys.stdout.buffer.flush()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('run',*ROLES,'validate'))
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    for name in ('control-fd','claim-fd','intent-fd','started-fd','credential-fd','actual-exit'):parser.add_argument('--'+name,type=int)
    parser.add_argument('--data-fds');args=parser.parse_args(argv)
    deadline=time.monotonic()+{'run':PARENT_SECONDS,'provider':PROVIDER_SECONDS,'authenticate':AUTH_SECONDS,'validate':VALIDATOR_SECONDS}[args.operation]
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline)
            if args.operation=='run':
                ap.previous._bootstrap_broker_logging();outcome=run(args,deadline);emit({'binding':binding(args),'outcome':outcome})
                return 2 if 'failure' in outcome else 0
            environment._bootstrap_cli_logging()
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_FRAME+1);validate_output(raw,args.actual_exit,args);sys.stdout.buffer.write(raw);return 0
            ar._credential_free();raw=sys.stdin.buffer.read(MAX_FRAME+1)
            require(len(raw)<=MAX_FRAME and type(args.data_fds) is str,'arguments');args.data_fds=tuple(int(value) for value in args.data_fds.split(','))
            _inherited(args,args.operation,raw,deadline);packet=parse(raw);state=_provider_state();result=None
            try:
                if args.operation=='provider':
                    require(packet=={} and type(args.credential_fd) is int and args.credential_fd>2
                        and args.credential_fd not in (args.control_fd,args.claim_fd,args.intent_fd,args.started_fd,*args.data_fds)
                        and stat.S_ISFIFO(os.fstat(args.credential_fd).st_mode) and os.fstat(args.credential_fd).st_uid==os.getuid(),'worker_scope')
                    secret=os.read(args.credential_fd,keychain.MAX_KEY_BYTES+1);os.close(args.credential_fd)
                    key=secret.decode('ascii');ap._secret_encodings(key)
                    result=provider_observation(args.data_fds,key,state,deadline);key=secret=None
                else:
                    require(type(packet) is dict and set(packet)=={'provider'},'worker_scope')
                    result=authenticate_observation(args.data_fds,packet['provider'],deadline)
                    require(result['identity_matched'] is True and result['expected_date_coverage'] is True,'diagnostic_incomplete')
                preflight(args,deadline);environment.require_safe_environment()
                emit({'binding':binding(args),'role':args.operation,'result':result,'failure_code':None});return 0
            except BaseException as error:
                emit({'binding':binding(args),'role':args.operation,'result':state if args.operation=='provider' else result,
                    'failure_code':finite(error)});return 2
    except BaseException as error:
        emit({'binding':binding(args),'outside_failure':finite(error)});return 2


if __name__=='__main__':raise SystemExit(main())
