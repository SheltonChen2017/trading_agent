"""One-shot existing-rights historical ETF source capability observation.

No QC/Safari/provider fallback, paid upgrade, acquisition, selector, backtest,
or old operation is invoked. Raw 200 bodies exist only in bounded memory;
non-200 bodies are not explicitly accessed. Socket buffering is not zero-read
proof. A separate committed exact run freeze precedes any credential/contact.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import sys
import time
from types import ModuleType
from urllib.parse import urlencode

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH='codex/strategy-analyst-revisions-v2'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE=ROOT/'scripts/probe_arv2_r339_holdings_access.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/holdings_discovery/R339-20261104-A'
SCHEMA='arv2-r339-historical-holdings-access-observation-v1'
SOURCE_PINS={
 'scripts/arv2_keychain_connections.py':'bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227',
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_r339_holdings_discovery.py':'ac23cea52e749d1400cf2d52654b8f593a81dd6b0add42d006284d7360057600'}
CORE_PROFILE_PIN={'byte_count':7804,'sha256':'5bdf06835bafac283ffbcb707c99fac4863de851144b34eab1723c55ae4dd2b3'}
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
SECONDS,READER_SECONDS,REQUEST_SECONDS,MAX_BODY=360,30,10,1024*1024
MAX_OUTPUT=MAX_PRIVATE=131072
ORIGINS={'massive':'api.massive.com','fmp':'financialmodelingprep.com'}
CLAIM_STATE='unallocated'
DEADLINE_FIRED=False
MODULES={}
PROGRESS=None
FLAGS={name:False for name in ('QC_contact','Safari_access','USB_read','licensed_rows_disclosed',
 'capture_accepted','historical_holdings_complete','exact_callback_history_proven',
 'actual_strategy_holdings_proven','stock_price_gaps_resolved','source_admission_granted',
 'point_in_time_proven','formal_identity_admitted','formal_forward_ready','backtest_ready',
 'paper_or_live_ready','new_paid_rights','old_control_read','old_operation_replayed')}
FINITE=frozenset(('arguments','host','environment','source_pin','git_state','deadline','metadata',
 'path','shape','changed','control','claim_spent','output','schema','unknown'))
ROW_TERMINALS=frozenset(('valid_sample','valid_empty','http_status','credentials_unavailable',
 'transport_refused','response_refused','schema_refused','skipped_after_provider_stop'))
ENTRY_DEADLINE=time.monotonic()+SECONDS

class Refused(ValueError):pass
class RunDeadline(BaseException):pass

def require(value,code):
 if not value:raise Refused(code)

def expired(*_):
 global DEADLINE_FIRED
 DEADLINE_FIRED=True
 raise RunDeadline()

def finite(error):
 if DEADLINE_FIRED or isinstance(error,(RunDeadline,TimeoutError,subprocess.TimeoutExpired)):
  return 'deadline'
 args=BaseException.args.__get__(error) if type(error) is Refused else ()
 return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'

def canonical(value):
 return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def utc():return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def budget(deadline):
 global DEADLINE_FIRED
 if type(deadline) in (int,float) and math.isfinite(deadline) and deadline<=time.monotonic():
  DEADLINE_FIRED=True;raise RunDeadline()
 require(type(deadline) in (int,float) and math.isfinite(deadline)
  and 0<deadline-time.monotonic()<=SECONDS,'deadline')
 return deadline-time.monotonic()

def meta(info):
 values=tuple(getattr(info,key,None) for key in FIELDS)
 require(all(type(v) is int and v>=0 for v in values),'metadata')
 return values

class HeldFile:
    """Original nofollow leaf/ancestor descriptors; current equality only.

    This code-only held-source guard makes endpoint equality checks; native
    security for private package/DATA is enforced by separate concrete guards.
    """
    def __init__(self, path, *, maximum, expected=None, deadline):
        self.path, self.maximum, self.expected, self.deadline = Path(path), maximum, expected, deadline
        self.directories, self.fd, self.info = [], None, None

    def __enter__(self):
        require(self.path.is_absolute() and '..' not in self.path.parts, 'path')
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.directories.append((parent, parent, '.', meta(os.fstat(parent))))
            for part in self.path.parts[1:-1]:
                budget(self.deadline)
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.directories.append((fd, parent, part, before))
                require(stat.S_ISDIR(before[2]) and meta(os.fstat(fd)) == before, 'changed'); parent = fd
            before = meta(os.stat(self.path.name, dir_fd=parent, follow_symlinks=False))
            self.fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            require(stat.S_ISREG(before[2]) and before[5] == 1 and before[6] <= self.maximum
                and (before[6] > 0 or (before[6] == 0 and self.path.is_relative_to(ROOT) and self.path.name == '__init__.py'
                    and SOURCE_PINS.get(self.path.relative_to(ROOT).as_posix()) == sha(b'')))
                and meta(os.fstat(self.fd)) == before, 'shape')
            self.info = before; self.verify(); return self
        except BaseException:
            self.close(); raise

    def verify(self):
        budget(self.deadline)
        for fd, parent, name, before in self.directories:
            require(meta(os.fstat(fd)) == before == meta(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'changed')
        require(self.fd is not None and meta(os.fstat(self.fd)) == self.info
            == meta(os.stat(self.path.name, dir_fd=self.directories[-1][0], follow_symlinks=False)), 'changed')

    def read(self):
        self.verify(); chunks, count = [], 0
        while count <= self.info[6]:
            budget(self.deadline)
            raw = os.pread(self.fd, min(65536, self.info[6] + 1 - count), count)
            if not raw: break
            chunks.append(raw); count += len(raw)
        raw = b''.join(chunks)
        require(len(raw) == self.info[6] and (self.expected is None or pin(raw) == self.expected), 'source_pin')
        self.verify(); return raw

    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd = None
        for fd, _, _, _ in reversed(self.directories): os.close(fd)
        self.directories.clear()

    def __exit__(self, kind, *_):
        try:
            if kind is None: self.verify()
        finally: self.close()

class Store:
    def __init__(self, security):
        self.fd, self.held, self.security = None, [], security
        self.directory_info, self.directory_security = None, None
        self.chain, self.pending = [], []

    def verify(self):
        require(self.fd is not None and meta(os.fstat(self.fd)) == self.directory_info
            == meta(os.stat(CONTROL, follow_symlinks=False))
            and self.directory_info[3] == os.getuid() and stat.S_IMODE(self.directory_info[2]) == 0o700
            and self.security.snapshot(self.fd) == self.directory_security
            and set(os.listdir(self.fd)) == {item[0] for item in self.held}, 'control')
        for parent, name, fd, expected, observed_security in self.chain:
            require(meta(os.fstat(fd)) == expected == meta(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and (observed_security is None or self.security.snapshot(fd) == observed_security), 'control')
        for name, fd, original, expected, observed_security in self.held:
            require(meta(os.fstat(fd)) == original == meta(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and original[3] == os.getuid() and stat.S_IMODE(original[2]) == 0o600 and original[5] == 1
                and not original[9] & ~(stat.UF_TRACKED | stat.UF_HIDDEN)
                and self.security.snapshot(fd) == observed_security
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'output')

    def __enter__(self):
        global CLAIM_STATE
        opened = []; path = Path('/')
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened.append((parent, '.', parent, None))
            for part in CONTROL.parts[1:]:
                path /= part
                if path in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                        if path == CONTROL: CLAIM_STATE = 'allocated_unknown'
                        os.fsync(parent)
                    except FileExistsError:
                        if path == CONTROL: CLAIM_STATE = 'consumed_or_unknown'
                        require(path != CONTROL, 'claim_spent')
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                opened.append((parent, part, fd, None))
                require(meta(os.fstat(fd)) == before and stat.S_ISDIR(before[2]), 'control')
                if path == ROOT or ROOT in path.parents:
                    require(before[3] == os.getuid() and stat.S_IMODE(before[2]) == (0o755 if path == ROOT else 0o700), 'control')
                parent = fd
            self.fd = parent; CLAIM_STATE = 'allocated_unknown'
            self.chain = [(parent, name, fd, meta(os.fstat(fd)),
                self.security.snapshot(fd) if index >= len(ROOT.parts) - 1 else None)
                for index, (parent, name, fd, _) in enumerate(opened[:-1])]
            self.directory_info = meta(os.fstat(self.fd)); self.directory_security = self.security.snapshot(self.fd)
            os.fsync(self.fd); self.verify(); return self
        except BaseException:
            for _, _, fd, _ in reversed(opened): os.close(fd)
            self.fd = None; raise

    def write(self, name, raw):
        global CLAIM_STATE
        require((name in ('claim.json','observation-started.json','report.json') or re.fullmatch(r'credential-(massive|fmp)-started[.]json|send-(?:[0-9]|1[0-9]|2[0-3])-started[.]json',name) is not None)
            and type(raw) is bytes and 0 < len(raw) <= MAX_PRIVATE, 'output')
        self.verify(); before = self.directory_info
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.pending.append(fd)
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); require(count > 0, 'output'); offset += count
        os.fsync(fd); require(os.pread(fd, len(raw) + 1, 0) == raw, 'output')
        require(os.stat(name, dir_fd=self.fd, follow_symlinks=False) == os.fstat(fd), 'output')
        after = meta(os.fstat(self.fd))
        require(all(after[index] == before[index] for index in (0, 1, 2, 3, 4, 9))
            and after[5] in (before[5], before[5] + 1) and after[6] >= before[6]
            and self.security.snapshot(self.fd) == self.directory_security, 'control')
        self.directory_info = after
        self.held.append((name, fd, meta(os.fstat(fd)), pin(raw), self.security.snapshot(fd)))
        self.pending.remove(fd)
        os.fsync(self.fd); self.verify()
        if name == 'claim.json': CLAIM_STATE = 'consumed'
        return pin(raw)

    def __exit__(self, *_):
        try: self.verify()
        finally:
            for _, fd, _, _, _ in self.held: os.close(fd)
            for fd in self.pending: os.close(fd)
            if self.fd is not None: os.close(self.fd)
            for _, _, fd, _, _ in reversed(self.chain): os.close(fd)

def binding(args):
 require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
  and all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in
   (args.caller_sha256,args.profile_sha256)),'arguments')
 return {'schema':SCHEMA,'expected_head':args.expected_head,
  'caller_sha256':args.caller_sha256,'profile_sha256':args.profile_sha256}

def profile_record():
 return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),
  'source_pins':SOURCE_PINS,'core_profile_pin':CORE_PROFILE_PIN,
  'purpose':'fixed_historical_source_capability_samples_not_replacement_acquisition_or_strategy',
  'source_guard':'original_nofollow_public_FDs_full10metadata_and_exact_byte_pins_not_native_public_ACL_or_whole_interpreter_integrity',
  'claim_before_credentials_or_contact':True,'maximum_application_send_intents':24,
  'credential_lookups':{'massive':1,'fmp':1},'provider_failure_skips_remaining_same_provider':True,
  'independent_other_provider_may_proceed':True,'parent_seconds':SECONDS,'reader_seconds':READER_SECONDS,
  'request_seconds':REQUEST_SECONDS,'keychain_seconds':20,'maximum_body_bytes':MAX_BODY,
  'transport':'fresh_stdlib_HTTPSConnection_per_query_exact_two_origins_no_session_retry_redirect_proxy_cookie_logic',
  'TLS_verify_and_hostname_required':True,'non200_body_explicitly_unread':True,
  'socket_buffering_not_no_prior_byte_read_proof':True,
  '200_bodies_memory_only_no_body_or_row_hash_retained':True,
  'no_pagination_or_capture':True,'provider_request_count':None,
  'failure_evidence':'finite_original_causes_and_already_measured_partial_statuses_retained_not_success_or_capture',
  'acceptance':'actual_exit0_and_strict_original_stdout_authentication_means_observation_only_even_HTTP_refused',
  'deadline_qualification':'cannot_bound_host_suspension_or_uninterruptible_IO',
  'native_parent_policy_sha256':sha(native_profile().encode()),**FLAGS}

def safe_env():
 support=ROOT/'.pytest_cache/r339-runtime'
 support.mkdir(mode=0o700,parents=True,exist_ok=True)
 require(support.resolve()==support,'environment')
 return {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C',
  'TMPDIR':str(support),'PYTHONPYCACHEPREFIX':str(support/'pycache'),
  'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','GIT_OPTIONAL_LOCKS':'0'}

def preflight(args,deadline):
 binding(args);budget(deadline)
 require(Path.cwd()==ROOT and ROOT.resolve()==ROOT and sys.platform=='darwin' and os.name=='posix'
  and sys.version_info[:2]==(3,13) and sys.executable==PYTHON and sys.flags.isolated==1
  and sys.dont_write_bytecode and Path(__file__).absolute()==SOURCE,'host')
 require(not any(k in os.environ for k in ('SSLKEYLOGFILE','SSL_CERT_FILE','SSL_CERT_DIR','PYTHONPATH'))
  and http.client.HTTPConnection.debuglevel==http.client.HTTPSConnection.debuglevel==0,'environment')
 require(pin(canonical(profile_record()))['sha256']==args.profile_sha256,'source_pin')
 for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],BRANCH),
   (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
  row=subprocess.run(['/usr/bin/git',*command],cwd=ROOT,env=safe_env(),stdin=subprocess.DEVNULL,
   stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=min(10,budget(deadline)))
  require(row.returncode==0 and not row.stderr and len(row.stdout)<=131072
   and row.stdout.decode('ascii').strip()==expected,'git_state')
 with HeldFile(SOURCE,maximum=131072,expected=None,deadline=deadline) as held:raw=held.read()
 require(sha(raw)==args.caller_sha256,'source_pin')
 row=subprocess.run(['/usr/bin/git','cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],
  cwd=ROOT,env=safe_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
  timeout=min(10,budget(deadline)))
 require(row.returncode==0 and not row.stderr and row.stdout==raw,'source_pin')

def bootstrap(stack,deadline):
 global MODULES
 roles={}
 for role,relative in (('security','scripts/arv2_relocation_security.py'),
  ('credentials','scripts/arv2_keychain_connections.py'),('core','scripts/arv2_r339_holdings_discovery.py')):
  raw=stack.enter_context(HeldFile(ROOT/relative,maximum=131072,
   expected=None,deadline=deadline)).read()
  require(sha(raw)==SOURCE_PINS[relative],'source_pin')
  name='r339_frozen_'+role
  require(name not in sys.modules,'environment')
  module=ModuleType(name);module.__file__=str(ROOT/relative)
  sys.modules[name]=module
  stack.callback(lambda n=name:sys.modules.pop(n,None))
  exec(compile(raw,str(ROOT/relative),'exec'),module.__dict__)
  roles[role]=module
 require(pin(canonical(roles['core'].profile_record()))==CORE_PROFILE_PIN,'source_pin')
 require(not any(n=='AlgorithmImports' or n=='assistant.dispatch_fence'
  or n.startswith(('QuantConnect','quantconnect','qc.client')) for n in sys.modules),'environment')
 MODULES=roles
 return roles

def native_profile():
 value='(version 1)(allow default)(deny network-inbound)'
 value+='(deny file-read* file-write* (subpath "/Volumes"))'
 value+='(deny file-write* (subpath "/Users/sheltonchen/Library/Keychains"))'
 value+='(deny file-read* file-write* (subpath "/Library/Keychains"))'
 value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
 value+='(require-not (subpath "'+str(CONTROL)+'"))'
 value+=''.join('(require-not (literal "'+str(p)+'"))' for p in CONTROL.parents
  if p==ROOT/'artifacts' or ROOT/'artifacts' in p.parents)+'))'
 value+='(deny file-write* (require-all (require-not (subpath "'+str(CONTROL)+'"))'
 value+='(require-not (literal "'+str(CONTROL.parent)+'"))'
 value+='(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
 return value

def request_once(request,key,deadline,row):
 require(request in MODULES['core'].request_plan(),'schema')
 provider=request['provider'];host=ORIGINS[provider]
 query=dict(request['query'])
 if provider=='fmp':query['apikey']=key
 target=request['path']+'?'+urlencode(query)
 headers={'Accept':'application/json','Accept-Encoding':'identity'}
 if provider=='massive':headers['Authorization']='Bearer '+key
 context=ssl.create_default_context()
 require(context.check_hostname is True and context.verify_mode==ssl.CERT_REQUIRED
  and context.keylog_filename is None,'environment')
 connection=http.client.HTTPSConnection(host,443,timeout=min(REQUEST_SECONDS,budget(deadline)),context=context)
 response=None
 try:
  require(connection.host==host and connection.port==443 and connection._tunnel_host is None
   and connection.debuglevel==0,'environment')
  connection.request('GET',target,headers=headers)
  response=connection.getresponse();budget(deadline)
  status=response.status
  require(type(status) is int and 100<=status<=599,'output')
  row['status_code']=status
  if status!=200:return status,None
  encoding=response.getheader('Content-Encoding','')
  media=response.getheader('Content-Type','').split(';',1)[0].strip().lower()
  require(type(encoding) is str and encoding.strip().lower() in ('','identity')
   and media in ('application/json','text/json'),'output')
  length=response.getheader('Content-Length')
  require(length is None or type(length) is str and re.fullmatch('[0-9]{1,8}',length)
   and 0<int(length)<=MAX_BODY,'output')
  chunks=[];count=0
  while True:
   budget(deadline);chunk=response.read1(min(16384,MAX_BODY+1-count))
   require(type(chunk) is bytes,'output')
   if not chunk:break
   count+=len(chunk);require(count<=MAX_BODY,'output');chunks.append(chunk)
  require(count>0 and (length is None or count==int(length)),'output')
  return status,b''.join(chunks)
 finally:
  try:
   if response is not None:response.close()
  finally:connection.close()

def observe(roles,store,args,deadline):
 global PROGRESS
 plan=roles['core'].request_plan()
 rows=[{'ordinal':q['ordinal'],'provider':q['provider'],'fund':q['fund'],
  'effective_date':q['effective_date'],'status_code':None,'send_intent_recorded':False,
  'terminal':'not_attempted','failure_code':None,'summary':None} for q in plan]
 counts={'massive':0,'fmp':0};stops=set();keys={}
 PROGRESS={'schema':SCHEMA,'binding':binding(args),'protocol_complete':False,
  'terminal':'incomplete_observation','observations':rows,'application_send_intents':0,
  'credential_lookup_attempts':counts,'provider_request_count':None,**FLAGS}
 try:
  for request,row in zip(plan,rows,strict=True):
   budget(deadline);provider=request['provider']
   if provider in stops:
    row.update(terminal='skipped_after_provider_stop',failure_code='previous_provider_stop');continue
   if provider not in keys:
    row['terminal']='credentials_pending'
    store.write('credential-'+provider+'-started.json',canonical({'binding':binding(args),'provider':provider}))
    counts[provider]+=1
    try:keys[provider]=roles['credentials'].load_key(provider,timeout_seconds=min(20,budget(deadline)))
    except roles['credentials'].KeychainUnavailable:
     row.update(terminal='credentials_unavailable',failure_code='credentials_unavailable');stops.add(provider);continue
   key=keys[provider]
   if type(key) is not str or not 8<=len(key)<=roles['core'].MAX_CREDENTIAL:
    row.update(terminal='credentials_unavailable',failure_code='credentials_unavailable');stops.add(provider);continue
   store.verify();row['terminal']='dispatch_pending'
   store.write('send-'+str(request['ordinal'])+'-started.json',
    canonical({'binding':binding(args),'ordinal':request['ordinal']}))
   row['send_intent_recorded']=True;PROGRESS['application_send_intents']+=1
   try:
    status,raw=request_once(request,key,deadline,row)
   except RunDeadline:raise
   except Exception as error:
    row.update(terminal='response_refused' if row['status_code'] is not None else 'transport_refused',
     failure_code=finite(error))
    stops.add(provider);continue
   if status!=200:
    row.update(terminal='http_status',failure_code='http_status');stops.add(provider);continue
   row['terminal']='parse_pending'
   try:
    summary=roles['core'].parse_response(request,raw,credential=key)
    roles['core'].validate_summary(request,summary)
   except RunDeadline:raise
   except Exception as error:
    row.update(terminal='schema_refused',failure_code=roles['core'].finite(error))
    stops.add(provider);continue
   finally:raw=None
   row.update(summary=summary,terminal='valid_sample' if summary['result_count'] else 'valid_empty')
  PROGRESS.update(protocol_complete=True,terminal='capability_observation_complete')
  return PROGRESS
 finally:
  keys.clear()

def validate_result(value,args,core,*,complete=True):
 require(type(complete) is bool,'output')
 require(type(value) is dict and set(value)=={'schema','binding','protocol_complete','terminal',
  'observations','application_send_intents','credential_lookup_attempts','provider_request_count',*FLAGS},'output')
 require(value['schema']==SCHEMA and value['binding']==binding(args) and value['protocol_complete'] is complete
  and value['terminal']==('capability_observation_complete' if complete else 'incomplete_observation')
  and value['provider_request_count'] is None and all(value[name] is False for name in FLAGS),'output')
 plan=core.request_plan();rows=value['observations']
 require(type(rows) is list and len(rows)==len(plan)==24,'output')
 counts=value['credential_lookup_attempts']
 require(type(counts) is dict and set(counts)==set(ORIGINS)
  and all(type(v) is int and v in ((1,) if complete else (0,1)) for v in counts.values()),'output')
 stopped=set();sends=0;unfinished=False
 pending={'not_attempted','credentials_pending','dispatch_pending','parse_pending'}
 causes=set(core.FINITE)|set(FINITE)|{'http_status','previous_provider_stop','credentials_unavailable'}
 for request,row in zip(plan,rows,strict=True):
  provider=request['provider']
  require(type(row) is dict and type(row.get('ordinal')) is int and set(row)=={'ordinal','provider','fund',
   'effective_date','status_code','send_intent_recorded','terminal','failure_code','summary'}
   and all(row[k]==request[k] for k in ('ordinal','provider','fund','effective_date')),'output')
  terminal=row['terminal'];status=row['status_code'];cause=row['failure_code']
  require(type(row['send_intent_recorded']) is bool and type(terminal) is str
   and terminal in ROW_TERMINALS|pending and (status is None or type(status) is int and 100<=status<=599)
   and (cause is None or type(cause) is str and cause in causes),'output')
  if unfinished:require(terminal=='not_attempted','output')
  if terminal in pending:
   require(not complete and cause is None and row['summary'] is None,'output')
   if terminal=='not_attempted':
    require(status is None and not row['send_intent_recorded'],'output')
   elif terminal=='credentials_pending':
    require(status is None and not row['send_intent_recorded'],'output')
   elif terminal=='parse_pending':require(status==200 and row['send_intent_recorded'],'output')
   else:require(status is None or row['send_intent_recorded'] is True,'output')
   unfinished=True
  else:
   require((provider in stopped)==(terminal=='skipped_after_provider_stop'),'output')
   if terminal.startswith('valid_'):
    require(status==200 and row['send_intent_recorded'] and cause is None,'output')
    core.validate_summary(request,row['summary'])
    require(bool(row['summary']['result_count'])==(terminal=='valid_sample'),'output')
   else:
    require(row['summary'] is None and cause is not None,'output')
    if terminal=='credentials_unavailable':
     require(status is None and not row['send_intent_recorded'] and cause=='credentials_unavailable','output')
    elif terminal=='skipped_after_provider_stop':
     require(status is None and not row['send_intent_recorded'] and cause=='previous_provider_stop','output')
    else:
     require(row['send_intent_recorded'],'output')
     if terminal=='http_status':require(status is not None and status!=200 and cause=='http_status','output')
     elif terminal=='schema_refused':require(status==200 and cause in core.FINITE,'output')
     elif terminal=='response_refused':require(status is not None,'output')
     else:require(status is None,'output')
    stopped.add(provider)
  if row['send_intent_recorded']:require(counts[provider]==1,'output')
  sends+=int(row['send_intent_recorded'])
 require(type(value['application_send_intents']) is int and sends==value['application_send_intents']
  and 0<=sends<=24,'output')
 return value

def launch(args,deadline):
 preflight(args,deadline)
 with ExitStack() as sources:
  sources.enter_context(HeldFile(SOURCE,maximum=131072,
   expected={'byte_count':SOURCE.stat().st_size,'sha256':args.caller_sha256},deadline=deadline)).read()
  roles=bootstrap(sources,deadline)
  with Store(roles['security']) as store:
   store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
   store.write('observation-started.json',canonical({'binding':binding(args)}))
   result=observe(roles,store,args,deadline)
   validate_result(result,args,roles['core'])
   sources.close()
   report=store.write('report.json',canonical(result))
   store.verify();preflight(args,deadline)
  return {'binding':binding(args),'report_pin':report,'result':result}

def validate_output(args,raw):
 preflight(args,min(ENTRY_DEADLINE,time.monotonic()+READER_SECONDS))
 require(args.actual_parent_exit in (0,2) and type(args.actual_parent_exit) is int
  and type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT,'output')
 def pairs(items):
  result={}
  for k,v in items:
   require(k not in result,'output');result[k]=v
  return result
 value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
  parse_constant=lambda _:(_ for _ in ()).throw(Refused('output')))
 require(canonical(value)+b'\n'==raw,'output')
 with ExitStack() as sources:
  core=bootstrap(sources,min(ENTRY_DEADLINE,time.monotonic()+READER_SECONDS))['core']
  if 'failure_code' in value:
   require(args.actual_parent_exit==2 and set(value)=={'binding','failure_code','claim_state','progress',*FLAGS}
    and value['binding']==binding(args) and value['failure_code'] in FINITE
    and value['claim_state'] in ('unallocated','allocated_unknown','consumed_or_unknown','consumed')
    and all(value[k] is False for k in FLAGS),'output')
   if value['progress'] is not None:
    validate_result(value['progress'],args,core,complete=value['progress']['protocol_complete'])
   return {'accepted':False,'output_authenticated':True,'failure':value}
  require(args.actual_parent_exit==0 and set(value)=={'binding','report_pin','result'}
   and value['binding']==binding(args),'output')
  validate_result(value['result'],args,core)
  require(value['report_pin']==pin(canonical(value['result'])),'output')
 return {'accepted':True,'output_authenticated':True,'result':value['result'],'report_pin':value['report_pin']}

def main():
 parser=argparse.ArgumentParser(add_help=False)
 parser.add_argument('mode',choices=('launch','validate','profile'))
 for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name)
 parser.add_argument('--actual-parent-exit',type=int)
 args=parser.parse_args()
 if args.mode=='profile':return profile_record()
 global ACTIVE_BINDING
 ACTIVE_BINDING=binding(args)
 signal.signal(signal.SIGALRM,expired)
 signal.setitimer(signal.ITIMER_REAL,READER_SECONDS if args.mode=='validate' else budget(ENTRY_DEADLINE))
 if args.mode=='validate':return validate_output(args,sys.stdin.buffer.read(MAX_OUTPUT+1))
 require(args.actual_parent_exit is None,'arguments')
 return launch(args,ENTRY_DEADLINE)

if __name__=='__main__':
 try:
  value=main()
  raw=canonical(value)+b'\n';require(len(raw)<=MAX_OUTPUT,'output')
  sys.stdout.buffer.write(raw)
  raise SystemExit(2 if value.get('accepted') is False else 0)
 except SystemExit:raise
 except BaseException as error:
  # The binding is set before any scoped operation; no raw exception text.
  progress=None if PROGRESS is None else json.loads(canonical(PROGRESS))
  if progress is not None:
   progress['application_send_intents']=sum(int(row['send_intent_recorded']) for row in progress['observations'])
  value={'binding':globals().get('ACTIVE_BINDING'), 'failure_code':finite(error),
   'claim_state':CLAIM_STATE,'progress':progress,**FLAGS}
  sys.stdout.buffer.write(canonical(value)+b'\n')
  raise SystemExit(2)
