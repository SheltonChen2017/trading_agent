"""One prospective anonymous current-FIGI hierarchy diagnostic.

This separately frozen protocol authenticates only retained failed-AD source
selection DATA. It observes the exact nine public identifiers, then at most
nine new composite identifiers derived deterministically from unambiguous
first-phase results. Failure, ambiguity and all vendor blockers remain.
"""
from __future__ import annotations

import argparse
from collections import Counter
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

import requests

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import read_arv2_r298_eodhd_crosswalk_gaps as previous
from scripts import prepare_arv2_r298_native_price_specification as selection_proof
from scripts import arv2_r298_ad_source_binding as ad_anchor
from scripts import arv2_r298_ao_source_binding as ao_anchor
from scripts import arv2_r298_fixed_data_guard as guard_module
from scripts import arv2_r327_public_figi_hierarchy as hierarchy

ba,ap,ar=previous.ba,previous.ba.ap,previous.ba.ar
admitted,environment,PYTHON=ba.admitted,ba.environment,ba.PYTHON
canonical,sha,pin,parse,metadata=ba.canonical,ba.sha,ba.pin,ba.parse,ba.metadata
SOURCE=ROOT/'scripts/run_arv2_r327_public_figi_hierarchy.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_public_figi_diagnostic/R327-20261027-H'
SCHEMA='arv2-r327-anonymous-public-FIGI-hierarchy-h-v1'
PARENT_SECONDS,SOURCE_SECONDS,PROVIDER_SECONDS,AUTH_SECONDS,VALIDATOR_SECONDS=240,60,120,60,20
OUTER_SECONDS=270
MAX_FRAME,MAX_STDERR,MAX_BODY,MAX_JOURNAL,MAX_PRIVATE=131072,8192,2*1024*1024,8192,8*1024*1024
MAX_AGGREGATE,MAX_FIGIS,MAX_PHASES=4*1024*1024,9,2
ROLES=('source','provider','authenticate')
DATA_FILES=('selection-private.json','response-phase1.json','response-phase2.json','requests.jsonl',
    'provider-index.json','source-metadata.json','hierarchy-private.json')
ENDPOINT='https://api.openfigi.com/v3/mapping'
SOURCE_PLAN={'ad_selection':{'relative_path':'artifacts/analyst_revisions_v2/newrule_public_figi_lineage/R326-20261027-AD/public-figi-private.json',
    'byte_count':26503,'sha256':'babb09c92ccf109bede02e0e9d125dc650ad3d64fee99b64b08770f19a62961c'}}
SELECTION_PIN={'byte_count':24516,'sha256':'0776dc737e2b35f481b2f732d8bb17f5e2bf32e8faa3478e2897f64488740e7a'}
AD_FACT_SHA256='9283ca349c8ee2ca06392b8c977155acf733de0d342a286590362da648e40464'
AD_FAILURE_SHA256='dfa82225a1d2502a1e0bd2645f79f951c20a7a53a269e06b9f1c901cb25b3fb4'
AO_FACT_SHA256='f0c5db3f65451a93a82384b16603fb8f349980433566146af1b338d7b533dca8'
NEW_PINS={'scripts/read_arv2_r298_eodhd_crosswalk_gaps.py':'a80a0d784cee31cf1778f135f411e5e859f44f36fd1d26dba7f3b6b2e8c753b8',
    'scripts/arv2_r327_public_figi_hierarchy.py':'568a82d3cde4834394cb06f614ab48ba4c63e2586ab231ae2b1ffc23677733d6'}
FALSE_FLAGS={'credential_access':False,'QC_contact':False,'new_paid_rights':False,'old_operation_invoked':False,
    'old_control_read':False,'original_AD_success_accepted':False,'historical_AD_failure_cause_proven':False,
    'vendor_global_collision_cleared':False,'original_FIGI_replaced':False,'permanent_identity_proven':False,
    'source_or_price_admission_granted':False,'complete_strategy_price_coverage_proven':False,
    'strategy_result_accepted':False,'physical_request_count_measured':False,
    'point_in_time_proven':False,'formal_forward_ready':False,'paper_or_live_ready':False,
    'licensed_rows_disclosed':False,'continuous_integrity_proven':False}
FINITE=frozenset(('host','arguments','environment','source_pin','source_binding','git_state','deadline','public_CA',
    'claim_spent','control_changed','control_security','control_bound','control_write','inherited','worker_scope',
    'worker_packet','worker_failed','request','response','http_status','http_refused','body_bound','journal',
    'source_shape','source_metadata','selection','hierarchy','index','private','output','spawn_refused','os_error','unknown')) \
    |frozenset(code for code in ap.FINITE if code.startswith('transport_')) \
    |frozenset('guard_'+code for code in guard_module.FINITE)


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args=BaseException.args.__get__(error)
        return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is admitted.helpers.Deadline:return 'deadline'
    if type(error) is guard_module.Refused:return 'guard_'+guard_module.finite(error)
    if type(error) is environment.EnvironmentRefused:return 'environment'
    if type(error) is hierarchy.Refused:return 'deadline' if hierarchy.finite(error)=='deadline' else 'hierarchy'
    if type(error) is selection_proof.Refused:return 'source_shape'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=PARENT_SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def source_context():
    fact,failure=ad_anchor.observed_fact(),ad_anchor.expected_failure()
    require(sha(canonical(fact))==AD_FACT_SHA256 and sha(canonical(failure))==AD_FAILURE_SHA256
        and fact['producer']['actual_exit']==2 and type(fact['producer']['actual_exit']) is int
        and fact['validator']['actual_exit']==0 and type(fact['validator']['actual_exit']) is int
        and fact['source_guard_returned'] is True and fact['failure_code']=='transport_unknown'
        and fact['private_file']==SOURCE_PLAN['ad_selection'],'source_binding')
    selection=selection_proof.source_binding()
    require({'byte_count':selection['private_case_byte_count'],'sha256':selection['private_case_sha256']}==SELECTION_PIN
        and selection['case_count']==5 and selection['planned_job_count']==9,'source_binding')
    ao=ao_anchor.observed_fact()
    require(sha(canonical(ao))==AO_FACT_SHA256
        and all(type(ao[key]['actual_exit']) is int and ao[key]['actual_exit']==0 for key in ('producer','validator','child'))
        and ao['only_policy_exception']=='/private/var/run/mDNSResponder'
        and ao['historical_failure_cause_proven'] is False,'source_binding')
    return {'AD_fact_sha256':AD_FACT_SHA256,'AD_failed_output_sha256':AD_FAILURE_SHA256,
        'AD_actual_producer_exit':2,'AD_actual_validator_exit':0,'AD_source_selection_pin':dict(SELECTION_PIN),
        'AD_mapping_accepted':False,'AO_fact_sha256':AO_FACT_SHA256,
        'AO_only_proved_local_resolver_policy_not_AD_cause':True}


def pins():
    values=previous.pins();require(len(values)==215,'source_pin')
    for name,value in NEW_PINS.items():
        require(_hash(value) and value!='0'*64 and (name not in values or values[name]==value),'source_pin')
        values[name]=value
    return values


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),'prior_context':source_context(),
        'data_plan':SOURCE_PLAN,'guard_profile':guard_module.profile_record(SOURCE_PLAN),
        'seconds':{'parent':PARENT_SECONDS,'source':SOURCE_SECONDS,'provider':PROVIDER_SECONDS,
            'authenticate':AUTH_SECONDS,'validator':VALIDATOR_SECONDS,'outer':OUTER_SECONDS},
        'maximum_public_frame_bytes':MAX_FRAME,'maximum_stderr_bytes':MAX_STDERR,
        'maximum_body_bytes':MAX_BODY,'maximum_completed_body_bytes':MAX_AGGREGATE,
        'maximum_private_package_bytes':MAX_PRIVATE,'maximum_dispatches':2,
        'phase1_exact_public_identifier_count':9,'phase2_maximum_new_composite_count':9,
        'helper_profile_sha256':sha(canonical(hierarchy.profile_record())),
        'fixed_endpoint':ENDPOINT,'request_protocol':'anonymous_POST_ID_BB_GLOBAL_no_filters_no_alternate_idType',
        'no_retries_redirects_proxies_cookies_or_default_environment_trust':True,
        'owned_resolve_redirects_empty_iterator_prevents_failed_body_consumption':True,
        'pinned_CA_bytes':ap.public_transport.CA_BYTES,'pinned_CA_sha256':ap.public_transport.CA_SHA256,
        'provider_native_egress':'HTTPS443_DNS53_local_mDNSResolver_not_OS_domain_fence',
        'ordinary_credential_free_parent_launches_separate_native_role_children':True,
        'native_source_auth_validator_deny_all_network':True,
        'all_native_roles_deny_Keychains_and_security_CLI':True,
        'claim_and_persistent_role_intents_before_each_one_dispatch':True,
        'inherited_FDs_prevent_bare_worker_not_arbitrary_same_user_attack':True,
        'source_normal_return_and_owned_seed_rehash_before_provider':True,
        'body_pin_persisted_before_semantic_parse':True,'phase2_empty_means_no_second_request':True,
        'only_public_FIGIs_exported_no_private_rows_or_other_identifiers':True,
        'all_retained_AA_candidates_not_global_collision_counterparty_census':True,
        'all_completed_body_bytes_not_partial_or_physical_wire_bytes':True,
        'unknown_nonzero_or_ambiguous_is_terminal_spent':True,
        'actual_parent_zero_and_separate_native_validator_zero_required':True,
        'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


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
        self.verify();require(name not in self.held and len(self.held)<24
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
    require(role in ('parent',*ROLES,'validate'),'arguments')
    # The ordinary parent is not run under this fence: inherited deny-network
    # would also deny its provider child. Role workers are separate OS fences.
    value='(version 1)(allow default)'+(ap.public_transport.EGRESS if role=='provider' else '(deny network*)')
    value+=''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))'
    allowed=f'(require-not (subpath "{ROOT/".pytest_cache"}"))(require-not (literal "/dev/null"))'
    if role!='validate':allowed+=f'(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))'
    value+='(deny file-write* (require-all '+allowed+'))'
    if role=='validate':return value+f'(deny file-read* (subpath "{ROOT/"artifacts"}"))'
    scopes=[CONTROL]
    if role=='source':scopes.append(ROOT/SOURCE_PLAN['ad_selection']['relative_path'])
    return value+ap.previous._artifact_policy(scopes)+f'(allow file-read* file-write* (subpath "{CONTROL}"))'


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
        require(url==ENDPOINT and verify is True and cert is None,'request')
        conn.cert_reqs,conn.ca_certs,conn.ca_cert_dir,conn.ca_cert_data='CERT_REQUIRED',None,None,self.ca_ascii
    def build_connection_pool_key_attributes(self,request,verify,cert=None):
        require(verify is True and cert is None and request.url==ENDPOINT,'request')
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



def _selection(raw,deadline):
    require(type(raw) is bytes and pin(raw)==SELECTION_PIN,'selection')
    value=selection_proof.previous._decode_private(raw)
    evidence=selection_proof._selection_hashes(value,deadline)
    require(type(value['figis']) is list and len(value['figis'])==9
        and value['figis']==sorted(set(value['figis'])),'selection')
    selection_proof._evidence(evidence)
    return value,evidence


def source_observation(fds,deadline):
    environment.require_safe_environment()
    with guard_module.FixedDataGuard(SOURCE_PLAN,deadline=deadline) as guarded:
        buffers=guarded.read_all_once()
        raw=buffers['ad_selection']
        # Pure old package checks are reused; no old operational function runs.
        evidence,_=selection_proof.prepare(raw,deadline)
        selection=selection_proof.previous._decode_private(raw)['selection']
        selected_raw=canonical(selection)
        require(pin(selected_raw)==SELECTION_PIN,'selection')
        _selection(selected_raw,deadline)
        receipt=guarded.receipt()
        environment.require_safe_environment()
    # The original DATA guard has returned normally before seed publication.
    _write(fds[0],selected_raw)
    require(pin(_read(fds[0],SELECTION_PIN['byte_count'],deadline))==SELECTION_PIN,'source_metadata')
    observation={'schema':SCHEMA+'-source','source_guard_receipt':receipt,'source_guard_normal_return':True,
        'selection_pin':dict(SELECTION_PIN),'original_case_count':5,'original_public_identifier_count':9,
        'selected_candidate_pair_count':sum(len(case['candidate_figis']) for case in selection['cases']),
        'original_binding_evidence':evidence,'prior_context':source_context(),**FALSE_FLAGS}
    validate_source({'observation':observation,'source_metadata_pin':pin(canonical(observation))})
    _write(fds[5],canonical(observation))
    require(_read(fds[5],MAX_FRAME,deadline)==canonical(observation),'source_metadata')
    return {'observation':observation,'source_metadata_pin':pin(canonical(observation))}


def validate_source(value):
    require(type(value) is dict and set(value)=={'observation','source_metadata_pin'},'source_metadata')
    row=value['observation']
    require(type(row) is dict and set(row)=={'schema','source_guard_receipt','source_guard_normal_return',
        'selection_pin','original_case_count','original_public_identifier_count','selected_candidate_pair_count',
        'original_binding_evidence','prior_context',*FALSE_FLAGS}
        and row['schema']==SCHEMA+'-source' and row['source_guard_normal_return'] is True
        and row['selection_pin']==SELECTION_PIN and type(row['original_case_count']) is int and row['original_case_count']==5
        and type(row['original_public_identifier_count']) is int and row['original_public_identifier_count']==9
        and type(row['selected_candidate_pair_count']) is int and 5<=row['selected_candidate_pair_count']<=6
        and row['prior_context']==source_context() and all(row[key] is False for key in FALSE_FLAGS)
        and value['source_metadata_pin']==pin(canonical(row)),'source_metadata')
    guard_module.validate_receipt(row['source_guard_receipt'],SOURCE_PLAN)
    selection_proof._evidence(row['original_binding_evidence'])


def _request_bytes(jobs):
    require(type(jobs) is list and 0<len(jobs)<=MAX_FIGIS
        and all(type(job) is dict and set(job)=={'idType','idValue','includeUnlistedEquities'}
            and job['idType']=='ID_BB_GLOBAL' and type(job['idValue']) is str
            and selection_proof.previous._valid_figi(job['idValue']) and job['includeUnlistedEquities'] is True for job in jobs)
        and [row['idValue'] for row in jobs]==sorted(set(row['idValue'] for row in jobs)),'request')
    raw=canonical(jobs);require(0<len(raw)<=4096,'request');return raw


def _provider_state():
    return {'source_observation_sha256':None,'dispatch_intents':[],'HTTP_statuses':[],
        'response_pins':{},'request_pins':{},'completed_body_bytes':0,
        'phase_summaries':[],'phase2_job_count':None,'transport_failure':None,'OS_errno':None,
        'journal_pin':None,'index_pin':None,'hierarchy_protocol_complete':False}


def _intent(fd,phase,jobs,state,deadline):
    raw=_request_bytes(jobs)
    row={'phase':phase,'dispatch_intent_count':phase,'job_count':len(jobs),'request_pin':pin(raw)}
    require(phase==len(state['dispatch_intents'])+1 and phase in (1,2),'journal')
    remaining(deadline);_write(fd,canonical(row)+b'\n')
    state['dispatch_intents'].append(row);state['request_pins'][str(phase)]=pin(raw)
    return raw


def _fetch(request_raw,phase,state,ca_raw,deadline):
    environment.require_safe_environment()
    with _session(ca_raw) as session:
        _session_check(session,ENDPOINT)
        prepared=session.prepare_request(requests.Request('POST',ENDPOINT,data=request_raw,
            headers={'Accept':'application/json','Content-Type':'application/json','Accept-Encoding':'identity'}))
        require(prepared.method=='POST' and prepared.url==ENDPOINT and prepared.body==request_raw
            and dict(prepared.headers)=={'Accept':'application/json','Content-Type':'application/json',
                'Accept-Encoding':'identity','Content-Length':str(len(request_raw))}
            and prepared.hooks=={'response':[]},'request')
        try:
            with session.send(prepared,timeout=min(30,remaining(deadline)),allow_redirects=False,
                    stream=True,verify=True,proxies={}) as response:
                status=response.status_code
                require(type(status) is int and 100<=status<=599,'http_status')
                # Retain known status BEFORE any cookie/session checks.
                state['HTTP_statuses'].append({'phase':phase,'status':status})
                require(response.url==ENDPOINT and response.request is prepared and not response.history,'response')
                require(status==200,'http_refused')
                _session_check(session,ENDPOINT);environment.require_safe_environment()
                headers=response.headers
                require(len(headers)<=64 and not headers.get('Set-Cookie')
                    and headers.get('Content-Encoding','identity').casefold()=='identity','response')
                for name,value in headers.items():
                    require(type(name) is str and type(value) is str and len(name)+len(value)<=8192,'response')
                length=headers.get('Content-Length')
                require(length is None or type(length) is str and re.fullmatch('[0-9]{1,8}',length)
                    and 0<int(length)<=MAX_BODY,'body_bound')
                body=bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    remaining(deadline)
                    require(type(chunk) is bytes and len(body)+len(chunk)<=MAX_BODY
                        and state['completed_body_bytes']+len(body)+len(chunk)<=MAX_AGGREGATE,'body_bound')
                    body.extend(chunk)
                require(0<len(body)<=MAX_BODY and (length is None or len(body)==int(length)),'body_bound')
                return bytes(body)
        except requests.exceptions.RequestException as error:
            state['transport_failure']=ap.previous.transport_failure(error);state['OS_errno']=ap._errno(error)
            raise Refused(state['transport_failure']) from None


def _phase1(selection,response,deadline):
    jobs=hierarchy.mapping_jobs(selection['figis']);request=_request_bytes(jobs)
    summary,private=hierarchy.analyze_phase1(selection['figis'],request_raw=request,
        response_raw=response,http_status=200,deadline=deadline)
    record=private.private_record()
    hierarchy.validate_summary(summary);hierarchy.validate_private_record(record,expected_summary=summary,deadline=deadline)
    return summary,record


def _phase2(first,response,deadline):
    jobs=hierarchy.phase2_jobs(first,deadline=deadline);request=_request_bytes(jobs)
    summary,private=hierarchy.analyze_phase2(first,request_raw=request,response_raw=response,
        http_status=200,deadline=deadline)
    record=private.private_record()
    hierarchy.validate_summary(summary);hierarchy.validate_private_record(record,expected_summary=summary,deadline=deadline)
    return summary,record


def provider_observation(fds,state,source,deadline):
    validate_source(source);environment.require_safe_environment()
    seed=_read(fds[0],SELECTION_PIN['byte_count'],deadline)
    selection,_=_selection(seed,deadline)
    require(_read(fds[5],MAX_FRAME,deadline)==canonical(source['observation']),'source_metadata')
    state['source_observation_sha256']=sha(canonical(source['observation']))
    ca=_ca_bytes()
    jobs=hierarchy.mapping_jobs(selection['figis'])
    require(len(jobs)==9,'request')
    request=_intent(fds[3],1,jobs,state,deadline)
    body=_fetch(request,1,state,ca,deadline)
    _write(fds[1],body)
    require(_read(fds[1],MAX_BODY,deadline)==body,'control_changed')
    state['response_pins']['1']=pin(body);state['completed_body_bytes']+=len(body)
    first=_phase1(selection,body,deadline);state['phase_summaries'].append(first[0])
    second_jobs=hierarchy.phase2_jobs(first,deadline=deadline)
    require(type(second_jobs) is list and len(second_jobs)<=9,'hierarchy')
    state['phase2_job_count']=len(second_jobs)
    if second_jobs:
        request=_intent(fds[3],2,second_jobs,state,deadline)
        body=_fetch(request,2,state,ca,deadline)
        _write(fds[2],body)
        require(_read(fds[2],MAX_BODY,deadline)==body,'control_changed')
        state['response_pins']['2']=pin(body);state['completed_body_bytes']+=len(body)
        second=_phase2(first,body,deadline);state['phase_summaries'].append(second[0])
    state['journal_pin']=pin(_read(fds[3],MAX_JOURNAL,deadline))
    index={'schema':SCHEMA+'-provider-index','source_observation_sha256':state['source_observation_sha256'],
        'dispatch_intents':state['dispatch_intents'],'HTTP_statuses':state['HTTP_statuses'],
        'request_pins':state['request_pins'],'response_pins':state['response_pins'],
        'completed_body_bytes':state['completed_body_bytes'],'phase_summaries':state['phase_summaries'],
        'phase2_job_count':state['phase2_job_count'],'journal_pin':state['journal_pin']}
    _write(fds[4],canonical(index));state['index_pin']=pin(canonical(index))
    require(_read(fds[4],MAX_FRAME,deadline)==canonical(index),'index')
    state['hierarchy_protocol_complete']=True
    validate_provider(state,success=True);return state


def _public_pin(value,maximum):
    require(type(value) is dict and set(value)=={'byte_count','sha256'}
        and type(value['byte_count']) is int and 0<value['byte_count']<=maximum and _hash(value['sha256']),'output')


def validate_provider(value,*,success=False):
    require(type(value) is dict and set(value)==set(_provider_state())
        and (value['source_observation_sha256'] is None or _hash(value['source_observation_sha256']))
        and type(value['dispatch_intents']) is list and len(value['dispatch_intents'])<=2
        and type(value['HTTP_statuses']) is list and len(value['HTTP_statuses'])<=len(value['dispatch_intents'])
        and type(value['response_pins']) is dict and set(value['response_pins']) in (set(),{'1'},{'1','2'})
        and type(value['request_pins']) is dict
        and set(value['request_pins'])=={str(i+1) for i in range(len(value['dispatch_intents']))}
        and type(value['completed_body_bytes']) is int and 0<=value['completed_body_bytes']<=MAX_AGGREGATE
        and type(value['phase_summaries']) is list and len(value['phase_summaries'])<=len(value['response_pins'])
        and (value['phase2_job_count'] is None or type(value['phase2_job_count']) is int and 0<=value['phase2_job_count']<=9)
        and (value['transport_failure'] is None or value['transport_failure'] in FINITE and value['transport_failure'].startswith('transport_'))
        and (value['OS_errno'] is None or type(value['OS_errno']) is int)
        and type(value['hierarchy_protocol_complete']) is bool,'output')
    for index,row in enumerate(value['dispatch_intents'],1):
        require(type(row) is dict and set(row)=={'phase','dispatch_intent_count','job_count','request_pin'}
            and type(row['phase']) is type(row['dispatch_intent_count']) is type(row['job_count']) is int
            and row['phase']==row['dispatch_intent_count']==index and 0<row['job_count']<=9
            and (index!=1 or row['job_count']==9)
            and row['request_pin']==value['request_pins'][str(index)],'output')
        _public_pin(row['request_pin'],4096)
    for index,row in enumerate(value['HTTP_statuses'],1):
        require(type(row) is dict and set(row)=={'phase','status'} and type(row['phase']) is int
            and row['phase']==index and type(row['status']) is int and 100<=row['status']<=599,'output')
    for key,item in value['response_pins'].items():
        _public_pin(item,MAX_BODY);require(int(key)<=len(value['HTTP_statuses'])
            and value['HTTP_statuses'][int(key)-1]['status']==200,'output')
    require(sum(row['byte_count'] for row in value['response_pins'].values())==value['completed_body_bytes'],'output')
    for summary in value['phase_summaries']:hierarchy.validate_summary(summary)
    for key,maximum in (('journal_pin',MAX_JOURNAL),('index_pin',MAX_FRAME)):
        if value[key] is not None:_public_pin(value[key],maximum)
    if success:
        count=2 if value['phase2_job_count'] else 1
        require(value['hierarchy_protocol_complete'] is True and value['source_observation_sha256'] is not None
            and value['phase2_job_count'] is not None and len(value['dispatch_intents'])==count
            and len(value['response_pins'])==len(value['phase_summaries'])==len(value['HTTP_statuses'])==count
            and all(row['status']==200 for row in value['HTTP_statuses'])
            and value['journal_pin'] is not None and value['index_pin'] is not None
            and value['transport_failure'] is None and value['OS_errno'] is None,'output')


def analyse(seed,response1,response2,journal,index_raw,source,provider,deadline):
    validate_source(source);validate_provider(provider,success=True)
    require(pin(seed)==SELECTION_PIN and pin(response1)==provider['response_pins']['1']
        and (pin(response2)==provider['response_pins']['2'] if '2' in provider['response_pins'] else response2==b'')
        and pin(journal)==provider['journal_pin'] and pin(index_raw)==provider['index_pin'],'index')
    selection,_=_selection(seed,deadline)
    first=_phase1(selection,response1,deadline)
    jobs2=hierarchy.phase2_jobs(first,deadline=deadline)
    second=_phase2(first,response2,deadline) if jobs2 else None
    summaries=[first[0]]+([second[0]] if second else [])
    require(summaries==provider['phase_summaries'] and len(jobs2)==provider['phase2_job_count'],'index')
    intents=[]
    for phase,jobs in ((1,hierarchy.mapping_jobs(selection['figis'])),(2,jobs2)):
        if not jobs:continue
        intents.append({'phase':phase,'dispatch_intent_count':phase,'job_count':len(jobs),'request_pin':pin(_request_bytes(jobs))})
    require(intents==provider['dispatch_intents'] and journal==b''.join(canonical(row)+b'\n' for row in intents),'journal')
    index={'schema':SCHEMA+'-provider-index','source_observation_sha256':provider['source_observation_sha256'],
        **{key:provider[key] for key in ('dispatch_intents','HTTP_statuses','request_pins','response_pins',
            'completed_body_bytes','phase_summaries','phase2_job_count','journal_pin')}}
    require(index_raw==canonical(index),'index')
    observations=[];counts=Counter()
    for case in selection['cases']:
        for candidate in case['candidate_figis']:
            remaining(deadline)
            observed=hierarchy.corroborate(case['original_figi'],candidate,phase1=first,phase2=second,deadline=deadline)
            hierarchy.validate_observation(observed)
            observations.append({'case_ordinal':case['case_ordinal'],'original_figi':case['original_figi'],
                'candidate_figi':candidate,'observation':observed})
            counts[observed['observation']]+=1
    private={'schema':SCHEMA+'-private','selection_pin':dict(SELECTION_PIN),'selection':selection,
        'phases':[{'summary':summary,'private_mapping':record} for summary,record in (first,*((second,) if second else ()))],
        'observations':observations,'prior_context':source_context(),'vendor_source_blockers_remaining':5,
        'no_original_identifier_or_collision_clearance':True}
    raw=canonical(private);require(0<len(raw)<=MAX_PRIVATE,'private')
    summary={'schema':SCHEMA+'-authentication','source_observation_sha256':sha(canonical(source['observation'])),
        'selection_pin':dict(SELECTION_PIN),'original_case_count':5,'initial_public_identifier_count':9,
        'phase2_job_count':len(jobs2),'phase_count':len(summaries),'phase_summaries':summaries,
        'corroboration_counts':dict(sorted(counts.items())),'corroboration_pair_count':len(observations),
        'response_pins':provider['response_pins'],'journal_pin':provider['journal_pin'],'index_pin':provider['index_pin'],
        'private_pin':pin(raw),'vendor_source_blockers_remaining':5,'hierarchy_protocol_complete':True,**FALSE_FLAGS}
    validate_authentication(summary,source,provider);return summary,raw


def validate_authentication(value,source=None,provider=None):
    require(type(value) is dict and set(value)=={'schema','source_observation_sha256','selection_pin','original_case_count',
        'initial_public_identifier_count','phase2_job_count','phase_count','phase_summaries','corroboration_counts',
        'corroboration_pair_count','response_pins','journal_pin','index_pin','private_pin','vendor_source_blockers_remaining',
        'hierarchy_protocol_complete',*FALSE_FLAGS} and value['schema']==SCHEMA+'-authentication'
        and _hash(value['source_observation_sha256']) and value['selection_pin']==SELECTION_PIN
        and type(value['original_case_count']) is int and value['original_case_count']==5
        and type(value['initial_public_identifier_count']) is int and value['initial_public_identifier_count']==9
        and type(value['phase2_job_count']) is int and 0<=value['phase2_job_count']<=9
        and type(value['phase_count']) is int and value['phase_count']==(2 if value['phase2_job_count'] else 1)
        and type(value['phase_summaries']) is list and len(value['phase_summaries'])==value['phase_count']
        and type(value['corroboration_counts']) is dict and len(value['corroboration_counts'])<=32
        and type(value['corroboration_pair_count']) is int and 5<=value['corroboration_pair_count']<=6
        and all(type(key) is str and key in hierarchy.OBSERVATIONS and type(count) is int and 0<count<=6
            for key,count in value['corroboration_counts'].items())
        and sum(value['corroboration_counts'].values())==value['corroboration_pair_count']
        and value['vendor_source_blockers_remaining']==5 and type(value['vendor_source_blockers_remaining']) is int
        and value['hierarchy_protocol_complete'] is True and all(value[key] is False for key in FALSE_FLAGS),'output')
    for summary in value['phase_summaries']:hierarchy.validate_summary(summary)
    _public_pin(value['private_pin'],MAX_PRIVATE);_public_pin(value['journal_pin'],MAX_JOURNAL);_public_pin(value['index_pin'],MAX_FRAME)
    require(type(value['response_pins']) is dict
        and set(value['response_pins'])==({'1','2'} if value['phase2_job_count'] else {'1'}),'output')
    for item in value['response_pins'].values():_public_pin(item,MAX_BODY)
    if source is not None:
        validate_source(source);require(value['source_observation_sha256']==sha(canonical(source['observation']))
            and value['corroboration_pair_count']==source['observation']['selected_candidate_pair_count'],'output')
    if provider is not None:
        validate_provider(provider,success=True)
        require(all(value[key]==provider[key] for key in ('source_observation_sha256','phase2_job_count','phase_summaries',
            'response_pins','journal_pin','index_pin')),'output')


def authenticate_observation(fds,source,provider,deadline):
    environment.require_safe_environment();validate_source(source);validate_provider(provider,success=True)
    before=[(metadata(os.fstat(fd)),_security(fd)) for fd in fds]
    raw=[_read(fd,limit,deadline) for fd,limit in zip(fds,(SELECTION_PIN['byte_count'],MAX_BODY,MAX_BODY,
        MAX_JOURNAL,MAX_FRAME,MAX_FRAME,MAX_PRIVATE),strict=True)]
    require(raw[5]==canonical(source['observation']) and raw[6]==b'','source_metadata')
    summary,private=analyse(raw[0],raw[1],raw[2],raw[3],raw[4],source,provider,deadline)
    environment.require_safe_environment()
    require([(metadata(os.fstat(fd)),_security(fd)) for fd in fds]==before,'control_changed')
    _write(fds[6],private);require(pin(_read(fds[6],MAX_PRIVATE,deadline))==summary['private_pin'],'private')
    return summary


def _inherited(args,role,packet,deadline):
    fds=(args.control_fd,args.claim_fd,args.intent_fd,args.started_fd,*args.data_fds)
    require(all(type(fd) is int and fd>2 for fd in fds) and len(set(fds))==len(fds)
        and len(args.data_fds)==len(DATA_FILES),'inherited')
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


def _actual(value,*,zero=False):
    require(type(value) is dict and set(value)=={'actual_exit','spawn_observed','bound','stdout_bytes',
        'stdout_sha256','stderr_bytes','stderr_sha256'}
        and (value['actual_exit'] is None or type(value['actual_exit']) is int)
        and type(value['spawn_observed']) is bool and value['bound'] in (None,'deadline','output_bound','stdin_closed','capture_io')
        and type(value['stdout_bytes']) is type(value['stderr_bytes']) is int
        and 0<=value['stdout_bytes']<=MAX_FRAME and 0<=value['stderr_bytes']<=MAX_STDERR
        and _hash(value['stdout_sha256']) and _hash(value['stderr_sha256']),'output')
    if zero:require(type(value['actual_exit']) is int and value['actual_exit']==0 and value['spawn_observed'] is True
        and value['bound'] is None and value['stderr_bytes']==0 and value['stderr_sha256']==sha(b''),'output')


def _capture_child(command,safe,packet,inherited,seconds):
    require(type(packet) is bytes and len(packet)<=MAX_FRAME and type(seconds) in (int,float)
        and math.isfinite(seconds) and 0<seconds<=PARENT_SECONDS,'arguments')
    deadline=time.monotonic()+seconds;output,errors=bytearray(),bytearray();final=None
    actual={'actual_exit':None,'spawn_observed':False,'bound':None,'stdout_bytes':0,'stdout_sha256':sha(b''),
        'stderr_bytes':0,'stderr_sha256':sha(b'')}
    process=None;selector=None;written=0
    try:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=dict(safe),pass_fds=tuple(inherited),close_fds=True,shell=False)
    except BaseException as error:
        if type(error) is admitted.helpers.Deadline:
            actual['bound']='deadline';return {'capture_failure':'deadline'},actual
        return {'capture_failure':'spawn_refused'},actual
    actual['spawn_observed']=True
    try:
        selector=selectors.DefaultSelector()
        for pipe in (process.stdin,process.stdout,process.stderr):os.set_blocking(pipe.fileno(),False)
        selector.register(process.stdout,selectors.EVENT_READ,'out');selector.register(process.stderr,selectors.EVENT_READ,'err')
        if packet:selector.register(process.stdin,selectors.EVENT_WRITE,'in')
        else:process.stdin.close()
        while selector.get_map():
            left=deadline-time.monotonic()
            if left<=0:actual['bound']='deadline';raise Refused('deadline')
            for event,_ in selector.select(min(1,left)):
                if event.data=='in':
                    try:count=os.write(event.fileobj.fileno(),packet[written:written+4096])
                    except BlockingIOError:continue
                    except BrokenPipeError:
                        actual['bound']='stdin_closed';raise Refused('worker_packet') from None
                    require(count>0,'worker_packet');written+=count
                    if written==len(packet):selector.unregister(event.fileobj);event.fileobj.close()
                    continue
                target,cap=(output,MAX_FRAME) if event.data=='out' else (errors,MAX_STDERR)
                try:chunk=os.read(event.fileobj.fileno(),min(65536,cap-len(target)+1))
                except BlockingIOError:continue
                if not chunk:selector.unregister(event.fileobj);continue
                available=cap-len(target);target.extend(chunk[:available])
                if len(chunk)>available:
                    actual['bound']='output_bound';raise Refused('worker_packet')
        try:process.wait(timeout=max(.001,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            actual['bound']='deadline';raise Refused('deadline') from None
        require(written==len(packet) and not errors and output.endswith(b'\n') and output.count(b'\n')==1,'worker_packet')
        final=parse(bytes(output[:-1]))
    except BaseException as error:
        if type(error) is admitted.helpers.Deadline:actual['bound']='deadline'
        elif actual['bound'] is None and not isinstance(error,Refused):actual['bound']='capture_io'
        final={'capture_failure':finite(error)}
    finally:
        if selector is not None:selector.close()
        if process.poll() is None:process.kill()
        process.wait()
        actual.update(actual_exit=process.returncode,stdout_bytes=len(output),stdout_sha256=sha(bytes(output)),
            stderr_bytes=len(errors),stderr_sha256=sha(bytes(errors)))
        for pipe in (process.stdin,process.stdout,process.stderr):pipe.close()
    _actual(actual)
    return final,actual


def _child(args,store,role,payload,runtime,deadline):
    packet=canonical(payload);store.write(role+'-intent.json',{**binding(args),'role':role,'input_pin':pin(packet)})
    started=store.create(role+'-started.json');fds=[store.held[name]['fd'] for name in DATA_FILES]
    inherited=[store.fd,store.held['claim.json']['fd'],store.held[role+'-intent.json']['fd'],started,*fds]
    command=['/usr/bin/sandbox-exec','-p',native_profile(role),str(PYTHON),'-B',str(SOURCE),role,
        '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
        '--control-fd',str(inherited[0]),'--claim-fd',str(inherited[1]),'--intent-fd',str(inherited[2]),
        '--started-fd',str(started),'--data-fds',','.join(map(str,fds))]
    try:
        final,actual=_capture_child(command,ap.capture_support._environment(runtime,None),packet,inherited,
            min({'source':SOURCE_SECONDS,'provider':PROVIDER_SECONDS,'authenticate':AUTH_SECONDS}[role],remaining(deadline)))
    finally:store.refresh((role+'-started.json',*DATA_FILES))
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
    elif role=='source':
        if value['result'] is not None:validate_source(value['result'])
        if value['failure_code'] is None:require(value['result'] is not None,'worker_packet')
    else:
        if value['result'] is not None:validate_authentication(value['result'])
        if value['failure_code'] is None:require(value['result'] is not None,'worker_packet')


def _packet_join(packet,actual,args,role):
    _actual(actual);_packet(packet,args,role)
    if set(packet)=={'capture_failure'}:return
    require(actual['stdout_bytes']==len(canonical(packet))+1 and actual['stdout_sha256']==sha(canonical(packet)+b'\n'),'output')
    require(actual['spawn_observed'] is True and actual['bound'] is None and actual['stderr_bytes']==0
        and actual['stderr_sha256']==sha(b''),'output')
    if 'outside_failure' in packet:require(type(actual['actual_exit']) is int and actual['actual_exit']==2,'output')
    else:require(type(actual['actual_exit']) is int and actual['actual_exit']==(0 if packet['failure_code'] is None else 2),'output')


def _check_source_files(store,source,deadline):
    validate_source(source);store.verify()
    require(_read(store.held[DATA_FILES[5]]['fd'],MAX_FRAME,deadline)==canonical(source['observation'])
        and pin(_read(store.held[DATA_FILES[0]]['fd'],SELECTION_PIN['byte_count'],deadline))==SELECTION_PIN,'source_metadata')
    store.verify()


def run(args,deadline):
    state={'stage':'claim','source':None,'source_actual':None,'provider':None,'provider_actual':None,
        'authentication':None,'authentication_actual':None,'child_packets':{}}
    with Store() as store:
        store.write('claim.json',binding(args))
        for name in DATA_FILES:store.create(name)
        try:
            preflight(args,deadline);ar._credential_free();environment.require_safe_environment()
            runtime=Path(tempfile.mkdtemp(prefix='r327-h-runtime-',dir=ROOT/'.pytest_cache'))
            state['stage']='source';packet,actual=_child(args,store,'source',{},runtime,deadline)
            state['child_packets']['source']=packet;state['source_actual']=actual;_packet_join(packet,actual,args,'source')
            require(set(packet)=={'binding','role','result','failure_code'},'worker_failed');state['source']=packet['result']
            require(packet['failure_code'] is None,'worker_failed');_actual(actual,zero=True)
            _check_source_files(store,state['source'],deadline);preflight(args,deadline)
            ar._credential_free();environment.require_safe_environment()
            state['stage']='provider';packet,actual=_child(args,store,'provider',{'source':state['source']},runtime,deadline)
            state['child_packets']['provider']=packet;state['provider_actual']=actual;_packet_join(packet,actual,args,'provider')
            require(set(packet)=={'binding','role','result','failure_code'},'worker_failed')
            state['provider']=packet['result'];require(packet['failure_code'] is None,'worker_failed');_actual(actual,zero=True)
            state['stage']='authenticate';packet,actual=_child(args,store,'authenticate',
                {'source':state['source'],'provider':state['provider']},runtime,deadline)
            state['child_packets']['authenticate']=packet;state['authentication_actual']=actual;_packet_join(packet,actual,args,'authenticate')
            require(set(packet)=={'binding','role','result','failure_code'},'worker_failed');state['authentication']=packet['result']
            require(packet['failure_code'] is None,'hierarchy');_actual(actual,zero=True)
            state['stage']='postflight';preflight(args,deadline);_check_source_files(store,state['source'],deadline)
            require(pin(_read(store.held[DATA_FILES[6]]['fd'],MAX_PRIVATE,deadline))==state['authentication']['private_pin'],'private')
            ar._credential_free();environment.require_safe_environment()
            result={'schema':SCHEMA,**state,'prior_context':source_context(),'provider_request_count':None,
                'post_checks_complete':True,**FALSE_FLAGS};validate_result(result,args)
            report=store.write('report.json',{**binding(args),'result':result});store.verify()
            return {'result':result,'report':report}
        except BaseException as error:
            failed={'failure_code':finite(error),'state':state,'claim_consumed':True,'provider_request_count':None,**FALSE_FLAGS}
            try:store.write('failure.json',{**binding(args),**failed})
            except BaseException:pass
            return {'failure':failed}


STATE_KEYS=frozenset(('stage','source','source_actual','provider','provider_actual','authentication',
    'authentication_actual','child_packets'))


def _state(value,args):
    require(type(value) is dict and set(value)==STATE_KEYS
        and value['stage'] in ('claim','source','provider','authenticate','postflight')
        and type(value['child_packets']) is dict
        and set(value['child_packets']) in (set(),{'source'},{'source','provider'},set(ROLES)),'output')
    for role,result_name in (('source','source'),('provider','provider'),('authenticate','authentication')):
        actual_name=result_name+'_actual'
        if role in value['child_packets']:
            packet=value['child_packets'][role];_packet_join(packet,value[actual_name],args,role)
            require(packet.get('result')==value[result_name],'output')
        else:require(value[actual_name] is value[result_name] is None,'output')
    if value['provider'] is not None:
        require(value['source'] is not None,'output');validate_source(value['source'])
        _actual(value['source_actual'],zero=True);validate_provider(value['provider'])
        require(value['provider']['source_observation_sha256']==sha(canonical(value['source']['observation'])),'output')
    if value['authentication'] is not None:
        validate_provider(value['provider'],success=True)
        _actual(value['provider_actual'],zero=True)
        validate_authentication(value['authentication'],value['source'],value['provider'])


def validate_result(value,args):
    require(type(value) is dict and set(value)=={'schema',*STATE_KEYS,'prior_context','provider_request_count',
        'post_checks_complete',*FALSE_FLAGS} and value['schema']==SCHEMA and value['prior_context']==source_context()
        and value['provider_request_count'] is None and value['post_checks_complete'] is True
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    _state({key:value[key] for key in STATE_KEYS},args)
    require(value['stage']=='postflight' and value['source'] is not None and value['provider'] is not None
        and value['authentication'] is not None,'output')
    for key in ('source_actual','provider_actual','authentication_actual'):_actual(value[key],zero=True)
    validate_provider(value['provider'],success=True)


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_FRAME and raw.endswith(b'\n') and raw.count(b'\n')==1
        and type(actual_exit) is int and actual_exit in (0,2),'output');value=parse(raw[:-1])
    require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','outside_failure'}:
        require(actual_exit==2 and value['outside_failure'] in FINITE,'output');return value
    require(set(value)=={'binding','outcome'} and type(value['outcome']) is dict,'output');outcome=value['outcome']
    if set(outcome)=={'failure'}:
        failed=outcome['failure'];require(actual_exit==2 and type(failed) is dict
            and set(failed)=={'failure_code','state','claim_consumed','provider_request_count',*FALSE_FLAGS}
            and failed['failure_code'] in FINITE and failed['claim_consumed'] is True
            and failed['provider_request_count'] is None and all(failed[key] is False for key in FALSE_FLAGS),'output')
        _state(failed['state'],args)
    else:
        require(actual_exit==0 and set(outcome)=={'result','report'},'output');validate_result(outcome['result'],args)
        require(outcome['report']==pin(canonical({**binding(args),'result':outcome['result']})),'output')
    return value


def emit(value):
    raw=canonical(value);require(len(raw)<MAX_FRAME,'output');sys.stdout.buffer.write(raw+b'\n');sys.stdout.buffer.flush()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('run',*ROLES,'validate'))
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    for name in ('control-fd','claim-fd','intent-fd','started-fd','actual-exit'):parser.add_argument('--'+name,type=int)
    parser.add_argument('--data-fds');args=parser.parse_args(argv)
    deadline=time.monotonic()+{'run':PARENT_SECONDS,'source':SOURCE_SECONDS,'provider':PROVIDER_SECONDS,
        'authenticate':AUTH_SECONDS,'validate':VALIDATOR_SECONDS}[args.operation]
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline)
            environment._bootstrap_cli_logging();ar._credential_free()
            if args.operation=='run':
                outcome=run(args,deadline);emit({'binding':binding(args),'outcome':outcome})
                return 2 if 'failure' in outcome else 0
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_FRAME+1);validate_output(raw,args.actual_exit,args);sys.stdout.buffer.write(raw);return 0
            raw=sys.stdin.buffer.read(MAX_FRAME+1)
            require(len(raw)<=MAX_FRAME and type(args.data_fds) is str,'arguments')
            args.data_fds=tuple(int(value) for value in args.data_fds.split(','))
            _inherited(args,args.operation,raw,deadline);packet=parse(raw);state=_provider_state();result=None
            try:
                if args.operation=='source':
                    require(packet=={},'worker_scope');result=source_observation(args.data_fds,deadline)
                elif args.operation=='provider':
                    require(type(packet) is dict and set(packet)=={'source'},'worker_scope');validate_source(packet['source'])
                    result=provider_observation(args.data_fds,state,packet['source'],deadline)
                else:
                    require(type(packet) is dict and set(packet)=={'source','provider'},'worker_scope')
                    result=authenticate_observation(args.data_fds,packet['source'],packet['provider'],deadline)
                preflight(args,deadline);ar._credential_free();environment.require_safe_environment()
                emit({'binding':binding(args),'role':args.operation,'result':result,'failure_code':None});return 0
            except BaseException as error:
                emit({'binding':binding(args),'role':args.operation,'result':state if args.operation=='provider' else result,
                    'failure_code':finite(error)});return 2
    except BaseException as error:
        emit({'binding':binding(args),'outside_failure':finite(error)});return 2


if __name__=='__main__':raise SystemExit(main())
