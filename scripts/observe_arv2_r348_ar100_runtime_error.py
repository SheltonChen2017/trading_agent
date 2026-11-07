"""One bounded read-only inspection of the known A4 Runtime Error.

Raw error/traceback exists only in the bounded response buffer. Outputs retain
public literal matches, closed structural classes and known-source frame pins.
No private DATA, old control, mutation, new attempt, logs or orders are accessed.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib,json,math,os,re,signal,stat,subprocess,sys,time
from pathlib import Path
from types import ModuleType

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH='codex/strategy-analyst-revisions-v2'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE=ROOT/'scripts/observe_arv2_r348_ar100_runtime_error.py'
PLAN=ROOT/'scripts/arv2_r348_ar100_runtime_error_plan.json'
PARENT_PLAN=ROOT/'scripts/arv2_r348_ar100_result_plan.json'
PARENT_PIN={'byte_count':39811,'sha256':'165de7a174f3c4b0cf873a2aae0e434bcbee0a92f9e0c8a533526c006b8e6a9c'}
CONTROL=ROOT/'artifacts/analyst_revisions_v2/legacy_six_results/R348-20261107-AR100-ERROR-A'
SUPPORT=ROOT/'.pytest_cache/r348-runtime-error'
CUSTODY='scripts/read_arv2_r348_ar100_result.py'
CUSTODY_PIN={'byte_count':59358,'sha256':'d358ba396714685a6547bcb4c2108dc78b36398c0b7f8521c2440fc112c0d5dc'}
TLS='scripts/observe_arv2_r345_qc_availability.py'
SECURITY='scripts/arv2_relocation_security.py'
HELPER='scripts/prepare_arv2_r343_legacy_six.py'
FACT='scripts/arv2_r348_ar100_failure_fact.json'
FACT_PIN={'byte_count':3820,'sha256':'9666a1e0adc92599cc49586a714dba4b5eea79a7cb347c3c16fe5d6be54085ac'}
INVENTORY='scripts/arv2_r348_runtime_error_inventory.json'
INVENTORY_PIN={'byte_count':76451,'sha256':'9b46b2566a5f351044a47dd25ff0441d96f7fd205bfa1649b865896fa351df52'}
PROJECT=39054561
BACKTEST='007d4ab27c26d337ae53acb492a83410'
COMPILE='251b7dbcc94a6db5740a3b83a83ec133-232313c1c0b6b9f62aae03cca921fd2f'
BACKTEST_NAME='ARV2 LEGACY SIX R343-AR100 OCT2026 A4'
SCHEMA='arv2-r348-ar100-runtime-error-observation-v1'
SECONDS,MAX_OUTPUT,MAX_TEXT=180,32768,65536
CREDENTIALS=('QC_USER_ID','QC_API_TOKEN')
ENDPOINTS={'authenticate':set(),'backtests/read':{'projectId','backtestId'}}
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
FLAGS={'source_uploaded':False,'new_launch_performed':False,'attempt_budget_reset':False,
 'point_in_time_proven':False,'formal_identity_admitted':False,'formal_forward_ready':False,'paper_or_live_ready':False}
FINITE=frozenset(('arguments','host','environment','git','source','source_changed','plan','fact','inventory','claim_spent',
 'control','security','deadline','credentials','transport','response','identity','error_shape','output','close','bound','unknown'))
SAFE=None
class Refused(ValueError):pass
class Deadline(BaseException):pass
def require(value,code):
 if not value:raise Refused(code)
def canonical(value):
 try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
 except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('output') from None
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def utc():return datetime.now(timezone.utc).isoformat()
def metadata(info):
 result=tuple(getattr(info,key,None) for key in FIELDS)
 require(all(type(v) is int and v>=0 for v in result),'source_changed');return result
def budget(deadline):
 left=deadline-time.monotonic();require(math.isfinite(left) and 0<left<=SECONDS,'deadline');return left
def loads(raw,lf=False):
 require(type(raw) is bytes and 0<len(raw)<=2*1024*1024,'plan')
 def pairs(items):
  result={}
  for key,value in items:require(key not in result,'plan');result[key]=value
  return result
 try:value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Refused('plan')))
 except (ValueError,UnicodeError,RecursionError):raise Refused('plan') from None
 require(canonical(value)+(b'\n' if lf else b'')==raw,'plan');return value
def security_snapshot(security,fd):
 try:return security.snapshot(fd)
 except security.Refusal:raise Refused('security') from None
def safe_env():
 return {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C','TMPDIR':str(SUPPORT),
  'XDG_CACHE_HOME':str(SUPPORT/'cache'),'SQLITE_TMPDIR':str(SUPPORT),'PYTHONPYCACHEPREFIX':str(SUPPORT/'pycache'),
  'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','GIT_OPTIONAL_LOCKS':'0'}
def native_profile():
 own=str(CONTROL);value='(version 1)(allow default)(deny network-bind)(deny network-inbound)'
 value+='(deny network-outbound (require-all (require-not (remote tcp "*:443"))(require-not (remote tcp "*:53"))(require-not (remote udp "*:53"))(require-not (literal "/private/var/run/mDNSResponder"))))'
 for path in ('/Volumes','/Users/sheltonchen/Library/Keychains','/Library/Keychains'):
  value+='(deny file-read* file-write* (subpath '+json.dumps(path)+'))'
 value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
 value+='(deny file-write* (require-all (require-not (subpath '+json.dumps(own)+'))(require-not (literal '+json.dumps(str(CONTROL.parent))+'))(require-not (subpath '+json.dumps(str(SUPPORT))+'))(require-not (literal "/dev/null"))))'
 ancestors=[p for p in CONTROL.parents if p==ROOT/'artifacts' or ROOT/'artifacts' in p.parents]
 value+='(deny file-read* (require-all (subpath '+json.dumps(str(ROOT/'artifacts'))+')(require-not (subpath '+json.dumps(own)+'))'+''.join('(require-not (literal '+json.dumps(str(p))+'))' for p in ancestors)+'))'
 return value
def profile_record():
 return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),
  'project_id':PROJECT,'backtest_id':BACKTEST,'compile_id':COMPILE,'fact_pin':FACT_PIN,'inventory_pin':INVENTORY_PIN,
  'seconds':SECONDS,'max_requests':2,'max_error_and_stacktrace_each':MAX_TEXT,'max_output':MAX_OUTPUT,
  'native_policy_sha256':sha(native_profile().encode()),'private_DATA_or_old_controls_read':False,
  'raw_error_or_traceback_retained':False,'cause_authenticated':False,
  'response_qualification':'bounded_full_backtests_read_JSON_ephemerally_parsed_no_other_fields_retained',
  'source_reuse':'frozen_custody_methods_only_and_TLS_primitive_no_old_operator_entry_or_global_mutation',**FLAGS}
def binding(args):
 require(all(type(getattr(args,key,None)) is str and re.fullmatch(pattern,getattr(args,key)) for key,pattern in
  (('expected_head','[0-9a-f]{40}'),('caller_sha256','[0-9a-f]{64}'),('plan_sha256','[0-9a-f]{64}'))),'arguments')
 return {'schema':SCHEMA,'expected_head':args.expected_head,'caller_sha256':args.caller_sha256,
  'plan_sha256':args.plan_sha256,'profile_sha256':sha(canonical(profile_record()))}
def preflight(args,deadline):
 bound=binding(args);safe=safe_env()
 require(Path.cwd()==ROOT and ROOT.resolve()==ROOT and sys.platform=='darwin' and os.name=='posix'
  and sys.version_info[:2]==(3,13) and sys.executable==PYTHON and sys.flags.isolated==1
  and sys.dont_write_bytecode and Path(__file__).absolute()==SOURCE,'host')
 require(set(os.environ)<=set(safe)|set(CREDENTIALS)|{'__CF_USER_TEXT_ENCODING'}
  and all(os.environ.get(k)==v for k,v in safe.items())
  and ('__CF_USER_TEXT_ENCODING' not in os.environ or os.environ['__CF_USER_TEXT_ENCODING']==f'0x{os.getuid():X}:0x0:0x0'),'environment')
 for key in ('TMPDIR','XDG_CACHE_HOME','SQLITE_TMPDIR','PYTHONPYCACHEPREFIX'):
  p=Path(safe[key]);require(p.is_dir() and p.resolve()==p,'environment')
 for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],BRANCH),(['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
  r=subprocess.run(['/usr/bin/git',*command],cwd=ROOT,env=safe,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=min(15,budget(deadline)),check=False)
  require(r.returncode==0 and not r.stderr and len(r.stdout)<=262144 and r.stdout.decode('ascii').strip()==expected,'git')
 return bound

class Held:
 def __init__(self,path,expected):self.path,self.expected,self.fd=path,expected,None
 def __enter__(self):
  try:
   self.fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK);self.info=metadata(os.fstat(self.fd))
   require(stat.S_ISREG(self.info[2]) and self.info[3]==os.getuid() and self.info[5]==1,'source')
   self.raw=os.pread(self.fd,2*1024*1024+1,0);self.verify();return self
  except BaseException:
   if self.fd is not None:os.close(self.fd);self.fd=None
   raise
 def verify(self):
  require(metadata(os.fstat(self.fd))==self.info==metadata(self.path.stat(follow_symlinks=False))
   and self.info[6]==len(self.raw) and pin(self.raw)==self.expected
   and os.pread(self.fd,len(self.raw)+1,0)==self.raw,'source_changed')
 def __exit__(self,*_):
  try:self.verify()
  finally:os.close(self.fd);self.fd=None

def module(raw,name,path):
 value=ModuleType(name);value.__file__=str(ROOT/path);exec(compile(raw,value.__file__,'exec'),value.__dict__);return value

class Sources:
 def __init__(self,args,deadline):self.args,self.deadline,self.stack=args,deadline,ExitStack()
 def __enter__(self):
  try:
   bootstrap=self.stack.enter_context(Held(ROOT/CUSTODY,CUSTODY_PIN))
   custody=module(bootstrap.raw,'_r348_error_custody',CUSTODY)
   self.held=custody.Sources(self.args,self.deadline)
   self.stack.callback(self.held.close)
   self.held.hold(SOURCE,{'byte_count':SOURCE.stat().st_size,'sha256':self.args.caller_sha256})
   plan=loads(self.held.hold(PLAN,{'byte_count':PLAN.stat().st_size,'sha256':self.args.plan_sha256}))
   parent=loads(self.held.hold(PARENT_PLAN,PARENT_PIN))
   require(set(plan)=={'schema','parent_plan_pin','fact_pin','inventory_pin','source_pins'} and plan['schema']==SCHEMA+'-plan'
    and plan['parent_plan_pin']==PARENT_PIN and plan['fact_pin']==FACT_PIN and plan['inventory_pin']==INVENTORY_PIN
    and type(plan['source_pins']) is dict and len(parent['source_pins'])==210
    and set(plan['source_pins'])==set(parent['source_pins'])|{CUSTODY,FACT,INVENTORY}
    and all(plan['source_pins'].get(k)==v for k,v in parent['source_pins'].items())
    and plan['source_pins'][CUSTODY]==CUSTODY_PIN and plan['source_pins'][FACT]==FACT_PIN
    and plan['source_pins'][INVENTORY]==INVENTORY_PIN,'plan')
   raw={}
   for relative,expected in sorted(plan['source_pins'].items()):
    require(not Path(relative).is_absolute() and '..' not in Path(relative).parts and 'artifacts' not in Path(relative).parts and relative.endswith(('.py','.json')),'plan')
    raw[relative]=self.held.hold(ROOT/relative,expected)
   self.security=module(raw[SECURITY],'_r348_error_security',SECURITY)
   helper=module(raw[HELPER],'_r348_error_public_security',HELPER)
   self.held.security,self.held.public_security=self.security,helper.public_source_security
   for row in self.held.rows:row[5]=helper.public_source_security(row[0],self.security)
   fact=loads(raw[FACT],lf=True)
   require(fact.get('schema')=='arv2-r348-ar100-failure-fact-v1' and fact.get('observation',{}).get('actual_exit')==2
    and fact['observation'].get('original_stdout_validated') is True
    and fact.get('original_result',{}).get('evidence',{}).get('observed_status')=='Runtime Error','fact')
   self.inventory=loads(raw[INVENTORY]);validate_inventory(self.inventory)
   self.tls=module(raw[TLS],'_r348_error_TLS',TLS)
   self.verify();return self
  except BaseException:self.stack.close();raise
 def verify(self):self.held.verify()
 def __exit__(self,*_):
  try:self.verify()
  finally:self.stack.close()

class Store:
    """Original held descriptors, full metadata and native security until close."""
    def __init__(self, security):
        self.security, self.chain, self.leaves, self.fd = security, [], [], None
        self.intents = self.application_dispatch_count = 0
    def __enter__(self):
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.chain.append((parent, parent, '.', metadata(os.fstat(parent)), None))
            current = Path('/')
            for part in CONTROL.parts[1:]:
                current /= part
                if current in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                        os.fsync(parent)
                        old = self.chain[-1]; after = metadata(os.fstat(parent))
                        require(all(after[i] == old[3][i] for i in (0, 1, 2, 3, 4, 9))
                            and (old[4] is None or security_snapshot(self.security, parent) == old[4]), 'control')
                        self.chain[-1] = (*old[:3], after, old[4])
                    except FileExistsError:
                        require(current != CONTROL, 'claim_spent')
                before = metadata(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                checked = current == ROOT or ROOT in current.parents
                self.chain.append((fd, parent, part, before, None))
                require(metadata(os.fstat(fd)) == before and stat.S_ISDIR(before[2])
                    and (not checked or (before[3] == os.getuid()
                        and stat.S_IMODE(before[2]) == (0o755 if current == ROOT else 0o700))), 'control')
                self.chain[-1] = (fd, parent, part, before,
                    security_snapshot(self.security, fd) if checked else None)
                parent = fd
            self.fd = parent
            self.verify()
            return self
        except BaseException:
            self.close(); raise
    def verify(self):
        require(self.fd is not None and set(os.listdir(self.fd)) == {r[0] for r in self.leaves}, 'control')
        for fd, parent, name, info, secure in self.chain:
            require(metadata(os.fstat(fd)) == info == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and (secure is None or security_snapshot(self.security, fd) == secure), 'control')
        for name, fd, info, secure, expected in self.leaves:
            require(metadata(os.fstat(fd)) == info == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and stat.S_ISREG(info[2]) and stat.S_IMODE(info[2]) == 0o600
                and info[3] == os.getuid() and info[5] == 1
                and security_snapshot(self.security, fd) == secure
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'control')
    def write(self, name, value):
        require(name in ('claim.json', 'report.json', 'failure.json') or
            re.fullmatch('(intent|dispatch)-[0-1][.]json', name), 'output')
        raw = canonical(value)
        require(0 < len(raw) <= MAX_OUTPUT, 'bound')
        self.verify()
        before = self.chain[-1][3]
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:]); require(count > 0, 'output'); offset += count
            os.fsync(fd)
            info = metadata(os.fstat(fd)); secure = security_snapshot(self.security, fd)
            require(os.pread(fd, len(raw) + 1, 0) == raw, 'output')
            after = metadata(os.fstat(self.fd))
            require(all(after[i] == before[i] for i in (0, 1, 2, 3, 4, 9))
                and security_snapshot(self.security, self.fd) == self.chain[-1][4], 'control')
            self.leaves.append((name, fd, info, secure, pin(raw))); fd = None
            old = self.chain[-1]; self.chain[-1] = (*old[:3], after, old[4])
            os.fsync(self.fd); self.verify()
            return pin(raw)
        finally:
            if fd is not None: os.close(fd)
    def intent(self, endpoint, project_id):
        require(self.intents < 2, 'bound')
        self.write(f'intent-{self.intents}.json', {'endpoint': endpoint, 'project_id': project_id,
            'ordinal': self.intents, 'utc': utc()})
        self.intents += 1
    def attempt(self, endpoint, project_id):
        require(self.application_dispatch_count < self.intents, 'bound')
        self.write(f'dispatch-{self.application_dispatch_count}.json', {'endpoint': endpoint,
            'project_id': project_id, 'ordinal': self.application_dispatch_count, 'utc': utc()})
        self.application_dispatch_count += 1
    def close(self):
        failed = False
        for _, fd, _, _, _ in self.leaves:
            try: os.close(fd)
            except OSError: failed = True
        self.leaves.clear()
        for fd, _, _, _, _ in reversed(self.chain):
            try: os.close(fd)
            except OSError: failed = True
        self.chain.clear(); self.fd = None
        require(not failed, 'close')
    def __exit__(self, *_):
        try: self.verify()
        finally: self.close()

def validate_inventory(value):
 require(type(value) is dict and value.get('schema')=='arv2-r348-public-runtime-error-inventory-v1'
  and type(value.get('file_whitelist')) is list and len(value['file_whitelist'])==18
  and type(value.get('known_literals')) is dict and all(type(text) is str and text.isascii() and 0<len(text)<=1024 and sha(text.encode())==digest for digest,text in value['known_literals'].items())
  and all(type(value.get(k)) is list and len(value[k])<=1024 and all(type(v) is str and v.isidentifier() for v in value[k]) for k in ('attribute_whitelist','key_whitelist','exception_classes')),'inventory')

def project_text(text,inventory):
 if text is None:return {'present':False,'byte_count':0,'sha256':sha(b''),'known_public_literal':None,'finite_exception_class':None,'structured_error':None}
 require(type(text) is str,'error_shape');raw=text.encode('utf-8');require(len(raw)<=MAX_TEXT,'error_shape')
 literal=inventory['known_literals'].get(sha(raw));kind=None;structured=None
 classes=inventory['exception_classes']
 if literal is None:
  for cls in classes:
   for separator in (': ',' : '):
    prefix=cls+separator
    if text.startswith(prefix) and inventory['known_literals'].get(sha(text[len(prefix):].encode('utf-8')))==text[len(prefix):]:
     literal=text[len(prefix):];kind=cls
  match=re.fullmatch("(?:AttributeError: |AttributeError : )?'(str|dict|list|tuple|int|NoneType|bool|Decimal)' object has no attribute '([A-Za-z_][A-Za-z_0-9]{0,99})'",text)
  if match and match[2] in inventory['attribute_whitelist']:
   kind='AttributeError';structured={'kind':'AttributeError','object_type':match[1],'attribute':match[2]}
  match=re.fullmatch("(?:KeyError: |KeyError : )?'([A-Za-z_][A-Za-z_0-9]{0,99})'",text)
  if match and match[1] in inventory['key_whitelist']:
   kind='KeyError';structured={'kind':'KeyError','key':match[1]}
 if text in classes:kind=text
 return {'present':True,'byte_count':len(raw),'sha256':sha(raw),'known_public_literal':literal,
  'finite_exception_class':kind,'structured_error':structured}

def frames(text,inventory):
 if text is None:return []
 require(type(text) is str and len(text.encode('utf-8'))<=MAX_TEXT,'error_shape');result=[]
 patterns=(r'File [\"\'](?:[^\"\'\n]*/)?([A-Za-z_][A-Za-z_0-9]*[.]py)[\"\'], line ([0-9]{1,5})(?:, in ([A-Za-z_][A-Za-z_0-9]{0,127}))?',
  r'\bin ([A-Za-z_][A-Za-z_0-9]*[.]py):\s*line ([0-9]{1,5})')
 for pattern in patterns:
  for match in re.finditer(pattern,text):
   name,line=match[1],int(match[2]);function=match[3] if len(match.groups())>2 else None
   if name in inventory['file_whitelist'] and 1<=line<=20000:
    row={'file':name,'line':line,'function_sha256':None if function is None else sha(function.encode())}
    if row not in result:result.append(row)
 require(len(result)<=64,'error_shape');return result

def observe(api,inventory):
 global SAFE
 used=set()
 def request(endpoint,payload):
  require(endpoint in ENDPOINTS and endpoint not in used and type(payload) is dict and set(payload)==ENDPOINTS[endpoint]
   and (endpoint=='authenticate' or type(payload['projectId']) is int and payload['projectId']==PROJECT and payload['backtestId']==BACKTEST),'response')
  used.add(endpoint);api.deadline=min(api.parent_deadline,time.monotonic()+89);return api._exchange(endpoint,payload)
 request('authenticate',{})
 packet=request('backtests/read',{'projectId':PROJECT,'backtestId':BACKTEST});row=packet.get('backtest')
 require(type(row) is dict and type(row.get('projectId')) is int and row['projectId']==PROJECT
  and row.get('backtestId')==BACKTEST and row.get('name')==BACKTEST_NAME and row.get('status')=='Runtime Error'
  and ('compileId' not in row or row['compileId']==COMPILE),'identity')
 SAFE={'known_identities':{'project_id':PROJECT,'backtest_id':BACKTEST,'compile_id':COMPILE,'attempt':4},
  'observed_status':'Runtime Error','projection_complete':False,
  'http_statuses':api.statuses,'response_pins':api.responses,'raw_error_or_traceback_retained':False,**FLAGS}
 error,trace=row.get('error'),row.get('stacktrace')
 summary={'known_identities':{'project_id':PROJECT,'backtest_id':BACKTEST,'compile_id':COMPILE,'attempt':4},
  'observed_status':'Runtime Error','projection_complete':True,'error':project_text(error,inventory),'stacktrace':project_text(trace,inventory),
  'frames':frames(trace,inventory),'raw_error_or_traceback_retained':False,'cause_authenticated':False,
  'http_statuses':api.statuses,'response_pins':api.responses,
  'result_body_qualification':'bounded_full_response_ephemerally_parsed_only_safe_error_projection_retained',**FLAGS}
 SAFE=summary;return summary

def finite(error):
 if isinstance(error,(Deadline,TimeoutError,subprocess.TimeoutExpired)):return 'deadline'
 args=BaseException.args.__get__(error) if type(error) is Refused else ()
 return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'

def run(args):
 global SAFE
 SAFE=None;deadline=time.monotonic()+SECONDS;bound=preflight(args,deadline)
 with Sources(args,deadline) as sources:
  with Store(sources.security) as store:
   store.write('claim.json',{'binding':bound,'profile':profile_record(),'attempt_consumed':True,'utc':utc()})
   api=None
   try:
    secret=sources.tls.credentials({k:os.environ.get(k) for k in CREDENTIALS})
    api=sources.tls.API(secret,store,min(deadline,time.monotonic()+89));api.parent_deadline=deadline
    summary=observe(api,sources.inventory);api.close();api=None;sources.verify();budget(deadline)
    result={'schema':SCHEMA+'-result','binding':bound,'attempt_consumed':True,'complete':True,
     'summary':summary,'application_dispatch_count':store.application_dispatch_count,'request_intent_count':store.intents,
     'physical_request_count_measured':False,**FLAGS}
    report_pin=store.write('report.json',result);store.verify()
   finally:
    if api is not None:api.close()
 return {**result,'report_pin':report_pin}

def validate_original_stdout(raw,*,actual_exit,expected_binding,inventory):
 """Pure original-byte/actual-exit consistency, not process/disk attestation."""
 require(type(actual_exit) is int and actual_exit in (0,2),'output')
 require(type(expected_binding) is dict and set(expected_binding)=={'schema','expected_head','caller_sha256','plan_sha256','profile_sha256'}
  and expected_binding['schema']==SCHEMA and type(expected_binding['expected_head']) is str
  and re.fullmatch('[0-9a-f]{40}',expected_binding['expected_head'])
  and all(type(expected_binding[k]) is str and re.fullmatch('[0-9a-f]{64}',expected_binding[k]) for k in ('caller_sha256','plan_sha256','profile_sha256'))
  and expected_binding['profile_sha256']==sha(canonical(profile_record())),'output')
 require(pin(canonical(inventory))==INVENTORY_PIN,'inventory');validate_inventory(inventory)
 require(type(raw) is bytes and 1<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n'),'output')
 value=loads(raw,lf=True)
 if actual_exit==0:
  require(type(value) is dict and set(value)=={'schema','binding','attempt_consumed','complete','summary',
   'application_dispatch_count','request_intent_count','physical_request_count_measured','report_pin',*FLAGS}
   and value['schema']==SCHEMA+'-result' and value['binding']==expected_binding
   and value['attempt_consumed'] is value['complete'] is True
   and type(value['application_dispatch_count']) is int and value['application_dispatch_count']==2
   and type(value['request_intent_count']) is int and value['request_intent_count']==2
   and value['physical_request_count_measured'] is False and all(value[k] is False for k in FLAGS)
   and value['report_pin']==pin(canonical({k:v for k,v in value.items() if k!='report_pin'})),'output')
  summary=value['summary']
 else:
  require(type(value) is dict and set(value)=={'schema','failure_code','observation',*FLAGS}
   and value['schema']==SCHEMA+'-failure' and type(value['failure_code']) is str and value['failure_code'] in FINITE
   and all(value[k] is False for k in FLAGS),'output');summary=value['observation']
 if summary is not None:
  base={'known_identities','observed_status','projection_complete','http_statuses','response_pins','raw_error_or_traceback_retained',*FLAGS}
  require(type(summary) is dict and type(summary.get('projection_complete')) is bool
   and set(summary)==(base|{'error','stacktrace','frames','cause_authenticated','result_body_qualification'}
    if summary['projection_complete'] else base),'output')
  require(type(summary) is dict and summary.get('known_identities')=={'project_id':PROJECT,'backtest_id':BACKTEST,'compile_id':COMPILE,'attempt':4}
   and summary.get('observed_status')=='Runtime Error' and summary.get('raw_error_or_traceback_retained') is False
   and all(summary.get(k) is False for k in FLAGS),'output')
  require(type(summary['http_statuses']) is list and len(summary['http_statuses'])==2
   and type(summary['response_pins']) is list and len(summary['response_pins'])==2,'output')
  for endpoint,status,response in zip(ENDPOINTS,summary['http_statuses'],summary['response_pins'],strict=True):
   require(type(status) is dict and set(status)=={'endpoint','http_status'} and status['endpoint']==endpoint
    and type(status['http_status']) is int and status['http_status']==200
    and type(response) is dict and set(response)=={'endpoint','byte_count','sha256'} and response['endpoint']==endpoint
    and type(response['byte_count']) is int and 0<response['byte_count']<=1024*1024
    and type(response['sha256']) is str and re.fullmatch('[0-9a-f]{64}',response['sha256']),'output')
  if summary.get('projection_complete') is True:
   require(summary['cause_authenticated'] is False and summary['result_body_qualification']=='bounded_full_response_ephemerally_parsed_only_safe_error_projection_retained','output')
   for name in ('error','stacktrace'):
    item=summary[name]
    require(type(item) is dict and set(item)=={'present','byte_count','sha256','known_public_literal','finite_exception_class','structured_error'}
     and type(item['present']) is bool and type(item['byte_count']) is int and 0<=item['byte_count']<=MAX_TEXT
     and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256'])
     and (item['known_public_literal'] is None or item['known_public_literal'] in inventory['known_literals'].values())
     and (item['finite_exception_class'] is None or item['finite_exception_class'] in inventory['exception_classes']),'output')
    structured=item['structured_error']
    if structured is not None:
     require(type(structured) is dict and ((set(structured)=={'kind','object_type','attribute'}
      and structured['kind']=='AttributeError' and structured['object_type'] in ('str','dict','list','tuple','int','NoneType','bool','Decimal')
      and structured['attribute'] in inventory['attribute_whitelist']) or (set(structured)=={'kind','key'}
      and structured['kind']=='KeyError' and structured['key'] in inventory['key_whitelist'])),'output')
   require(type(summary.get('frames')) is list and len(summary['frames'])<=64,'output')
   for item in summary['frames']:
    require(type(item) is dict and set(item)=={'file','line','function_sha256'} and item['file'] in inventory['file_whitelist']
     and type(item['line']) is int and 1<=item['line']<=20000 and (item['function_sha256'] is None
     or type(item['function_sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['function_sha256'])),'output')
 require(actual_exit!=0 or summary is not None and summary.get('projection_complete') is True,'output')
 return {'schema':SCHEMA+'-original-output-validation','original_output_validated':True,'actual_exit':actual_exit,
  'diagnostic_complete':actual_exit==0,'original_stdout_pin':pin(raw),'original_envelope':loads(canonical(value)),
  'qualification':'supplied_original_bytes_and_observed_exit_not_independent_disk_process_or_authenticated_cause'}

class Parser(argparse.ArgumentParser):
 def error(self,message):raise Refused('arguments')
def main():
 p=Parser(add_help=False);p.add_argument('mode',choices=('profile','run'))
 for key in ('expected-head','caller-sha256','plan-sha256'):p.add_argument('--'+key)
 a=p.parse_args()
 if a.mode=='profile':
  require(all(getattr(a,k) is None for k in ('expected_head','caller_sha256','plan_sha256')),'arguments');return profile_record()
 def expired(*_):raise Deadline()
 signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,SECONDS);return run(a)
if __name__=='__main__':
 try:
  raw=canonical(main())+b'\n';require(len(raw)<=MAX_OUTPUT,'output');sys.stdout.buffer.write(raw)
 except BaseException as error:
  sys.stdout.buffer.write(canonical({'schema':SCHEMA+'-failure','failure_code':finite(error),'observation':SAFE,**FLAGS})+b'\n');raise SystemExit(2)
