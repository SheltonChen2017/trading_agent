"""One new public-plan actiontypes dictionary capture and native validation.

The parent exclusively claims before one Keychain lookup and one fixed GET.
A complete authenticated status200 body is retained before any CSV parse.
Only after session close and local key-reference clearing can a credential-
free native worker read inherited own response/claim/intent descriptors.
No old private DATA/control, source acquisition, QC or browser is accessed.
"""
import argparse
import fcntl
from contextlib import ExitStack
import hashlib
import http.client
import importlib
from importlib.machinery import PathFinder
import json
import logging
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE=ROOT/'scripts/run_arv2_r335_action_types.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R335-20261103-J'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r335-action-types-diagnostic-v1'
SOURCE_PINS={
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_keychain_connections.py':'bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227',
 'scripts/arv2_r335_action_types.py':'22c7d74679a44b33316a2b5facc1f678e73f131aaa443d6805ed1380885f9974',
}
SECONDS,WORKER_SECONDS,MAX_OUTPUT,MAX_PRIVATE=150,60,131072,512*1024
MAX_WORKER_OUTPUT,MAX_WORKER_STDERR=32768,8192
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
OBSERVER_MODULE=KEYCHAIN_MODULE=None
PROVIDER_CODES=frozenset(('plan','credential','session','deadline','journal','event','prepared_identity','request_failed',
 'http_status_unavailable','http_status','response_identity','response_headers','response_encoding','response_bound',
 'response_stream','response_close','credential_echo','retention','aggregate_bound','changed','csv','header','row_cap','row_scope','receipt','private','unknown'))
FINITE=frozenset(('arguments','host','environment','git_state','source_pin','source_changed','scope','deadline','bound','input','claim_spent',
 'control','path','shape','metadata','changed','worker_claim','worker_marker','worker_output','worker_failure','worker_stderr',
 'worker_deadline','credential','session','retention','output','unknown'))|frozenset('provider_'+code for code in PROVIDER_CODES)
FALSE_FLAGS={'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'old_control_read': False, 'old_operation_replayed': False, 'old_private_DATA_read': False, 'provider_request_count_measured': False, 'credential_persisted': False, 'licensed_rows_disclosed': False, 'definition_semantics_interpreted': False, 'new_aliases_generated': False, 'identity_admitted': False, 'terminal_payoff_proven': False, 'price_acquired': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'strategy_run_invoked': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'historical_or_continuous_integrity_proven': False}


class Refused(ValueError):
    pass

def require(value, code):
    if not value:
        raise Refused(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}

def finite(error):
    if OBSERVER_MODULE is not None and type(error) is OBSERVER_MODULE.Refused:
        code=OBSERVER_MODULE.finite(error)
        return 'provider_'+code if code in PROVIDER_CODES else 'unknown'
    if KEYCHAIN_MODULE is not None and type(error) is KEYCHAIN_MODULE.KeychainUnavailable:return 'credential'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    return 'deadline' if isinstance(error,TimeoutError) else 'unknown'


def parse(raw, bound):
    require(type(raw) is bytes and 0 < len(raw) <= bound, 'bound')
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'input'); result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('input')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('input') from None

def budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')
    return deadline - time.monotonic()

def meta(info):
    result = tuple(getattr(info, key, None) for key in FIELDS)
    require(all(type(value) is int and value >= 0 for value in result), 'metadata')
    return result

class HeldFile:
    """Original nofollow leaf/ancestor descriptors; current equality only.

    This J contract holds selected public repository source only. It makes
    no historical or continuous integrity claim and opens no USB input.
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
            require(stat.S_ISREG(before[2]) and before[5] == 1 and 0 < before[6] <= self.maximum
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

def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),'source_pins':SOURCE_PINS,
        'purpose':'one_current_vintage_public_plan_actiontypes_dictionary_not_old_G_retry_or_price_acquisition',
        'static_query':{'endpoint':'https://api.sharadar.com/v1.0/data/descriptions','tablename':'actiontypes','format':'csv',
            'limit':'1000','skip':'0','sort':'indicator.asc'},
        'forbidden_query_fields':['fields','from','to','years'],'maximum_seconds':SECONDS,'maximum_worker_seconds':WORKER_SECONDS,
        'keychain_seconds':20,'HTTP_seconds':30,'maximum_response_bytes':MAX_PRIVATE,'maximum_rows_strictly_less_than':1000,
        'maximum_worker_output_bytes':MAX_WORKER_OUTPUT,'maximum_output_bytes':MAX_OUTPUT,
        'credentials':'one_memory_only_existing_Sharadar_login_Keychain_read_no_env_or_file_fallback',
        'source_execution':'compile_exact_held_selected_repo_bytes_no_repo_pyc_not_whole_interpreter_integrity',
        'observer_profile_pin':{'byte_count':2106,'sha256':'bccbea3345167e255fba90f61ed015326e35001654eff3002aeb45639bc88983'},
        'worker_native_policy_sha256':sha(worker_native_profile().encode('utf8')),
        'retention':'numeric_status_before_failed_body_refusal_authenticated_complete_HTTP200_CSV_and_transport_before_close_or_parse',
        'body_validation':'one_credential_free_native_allnetwork_USB_Keychains_denied_worker_inherited_own_response_claim_intent_only',
        'reader':'exact_host_HEAD_source_profile_bootstrap_then_bounded_stdin_only_no_own_or_old_control_read',
        'acceptance':'actual_parent0_actual_worker0_finite_matching_capture_dictionary_receipts_and_pins_report_alone_never_sufficient',
        'no_private_input_plan':True,'retries':0,'pagination':False,'new_paid_rights':False,
        'deadline_limitation':'uninterruptible_IO_host_suspension_and_own5s_reap_qualification',**FALSE_FLAGS}


def binding(args):
    require(all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', getattr(args, key))
        for key, length in (('expected_head', 40), ('caller_sha256', 64), ('profile_sha256', 64))), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}

def safe_env():
    support = ROOT / '.pytest_cache/r335-runtime'
    support.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(support.resolve() == support, 'environment')
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'GIT_OPTIONAL_LOCKS': '0'}

def preflight(args, deadline):
    binding(args); budget(deadline)
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON and sys.flags.isolated == 1
        and Path(__file__).absolute() == SOURCE and sys.dont_write_bytecode, 'host')
    require(args.profile_sha256 == sha(canonical(profile_record())), 'source_pin')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(15, budget(deadline)))
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144
            and result.stdout.decode('ascii').strip() == expected, 'git_state')
    with HeldFile(SOURCE, maximum=131072, expected={'byte_count': SOURCE.stat().st_size,
            'sha256': args.caller_sha256}, deadline=deadline) as held:
        raw = held.read()
    result = subprocess.run(['/usr/bin/git', 'cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
        cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=min(15, budget(deadline)))
    require(result.returncode == 0 and not result.stderr and result.stdout == raw, 'source_pin')

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
        require(allowed_name(name)
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

def allowed_name(name):
    return type(name) is str and name in ('claim.json','request-00-intent.json','request-00-status.json','request-00-terminal.json',
        'response-00.csv','transport-00.json','dictionary-intent.json','dictionary-observed.json','report.json','failure.json')


def bootstrap(role,stack,deadline):
    """Compile exact held selected source bytes; never execute repo pyc caches."""
    global OBSERVER_MODULE,KEYCHAIN_MODULE
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    require(role in ('parent','dictionary','validate'),'arguments')
    raw_by_name={}
    for relative,expected in SOURCE_PINS.items():
        require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected),'source_pin')
        held=stack.enter_context(HeldFile(ROOT/relative,maximum=131072,deadline=deadline))
        raw=held.read();require(sha(raw)==expected,'source_pin');raw_by_name[Path(relative).stem]=raw
    sys.path[:]=[str(ROOT),*(value for value in sys.path if value and Path(value).is_absolute()
        and Path(value)!=ROOT and ROOT not in Path(value).parents)]
    package_spec=PathFinder.find_spec('scripts',sys.path)
    require(package_spec is not None and package_spec.origin is None
        and tuple(package_spec.submodule_search_locations)==(str(ROOT/'scripts'),),'source_pin')
    package=sys.modules.get('scripts')
    if package is None:
        package=ModuleType('scripts');package.__package__='scripts';package.__path__=[str(ROOT/'scripts')]
        package.__spec__=package_spec;sys.modules['scripts']=package
    require(getattr(package,'__file__',None) is None and tuple(package.__path__)==(str(ROOT/'scripts'),),'source_pin')
    chosen=['arv2_relocation_security']
    chosen.append('arv2_r335_action_types')
    if role=='parent':chosen.append('arv2_keychain_connections')
    modules={}
    for name in chosen:
        full='scripts.'+name;relative='scripts/'+name+'.py';path=ROOT/relative
        spec=PathFinder.find_spec(full,[str(ROOT/'scripts')])
        require(spec is not None and spec.origin==str(path) and full not in sys.modules,'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__='scripts'
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(package,name,module)
        exec(compile(raw_by_name[name],str(path),'exec'),module.__dict__)
        modules[name]=module
    OBSERVER_MODULE=modules['arv2_r335_action_types']
    require(OBSERVER_MODULE.FINITE==PROVIDER_CODES,'source_pin')
    if role=='parent':KEYCHAIN_MODULE=modules['arv2_keychain_connections']
    require(not any(name=='AlgorithmImports' or name.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298'))
        for name in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'observer':OBSERVER_MODULE,
        **({'keychain':KEYCHAIN_MODULE} if role=='parent' else {})}

def safe_runtime():
    allowed={'PATH','LANG','LC_ALL','TMPDIR','PYTHONPYCACHEPREFIX','PYTHONDONTWRITEBYTECODE',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD','GIT_OPTIONAL_LOCKS','__CF_USER_TEXT_ENCODING'}
    require(set(os.environ)<=allowed and sys.gettrace() is None and sys.getprofile() is None,'environment')
    require(http.client.HTTPConnection.debuglevel==0 and http.client.HTTPSConnection.debuglevel==0,'environment')
    root=logging.getLogger()
    require(not root.handlers and all(type(handler) is logging.NullHandler
        for name in ('requests','urllib3','http.client') for handler in logging.getLogger(name).handlers),'environment')

def checked_pin(value,maximum,*,empty=False):
    require(type(value) is dict and set(value)=={'byte_count','sha256'}
        and type(value['byte_count']) is int and (0 if empty else 1)<=value['byte_count']<=maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),'output')
    return value

def _held_fd(store,name):
    found=[entry[1] for entry in store.held if entry[0]==name]
    require(len(found)==1,'control');return found[0]

def _regular_fd(fd,name,directory,maximum,security):
    require(type(fd) is int and fd>=3,'worker_claim')
    before=meta(os.fstat(fd))
    require(before==meta(os.stat(name,dir_fd=directory,follow_symlinks=False)) and stat.S_ISREG(before[2])
        and before[3]==os.getuid() and before[5]==1 and stat.S_IMODE(before[2])==0o600
        and 0<before[6]<=maximum,'worker_claim')
    original_security=security.snapshot(fd);raw=os.pread(fd,before[6]+1,0)
    require(len(raw)==before[6] and meta(os.fstat(fd))==before
        ==meta(os.stat(name,dir_fd=directory,follow_symlinks=False)) and security.snapshot(fd)==original_security,'worker_claim')
    return raw

def adopt_marker(store,phase):
    require(phase=='dictionary','worker_marker');name=phase+'-started.json'
    names=set(os.listdir(store.fd));owned={item[0] for item in store.held}
    if name not in names:
        store.verify();return None
    require(names==owned|{name},'worker_marker')
    before=store.directory_info;after=meta(os.fstat(store.fd))
    require(all(after[index]==before[index] for index in (0,1,2,3,4,9))
        and after[5] in (before[5],before[5]+1) and after[6]>=before[6]
        and store.security.snapshot(store.fd)==store.directory_security,'worker_marker')
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=store.fd)
    store.pending.append(fd)
    info=meta(os.fstat(fd))
    require(info==meta(os.stat(name,dir_fd=store.fd,follow_symlinks=False)) and stat.S_ISREG(info[2])
        and info[3]==os.getuid() and info[5]==1 and stat.S_IMODE(info[2])==0o600 and 0<=info[6]<=8192,'worker_marker')
    raw=os.pread(fd,info[6]+1,0);require(len(raw)==info[6],'worker_marker')
    store.directory_info=after
    store.held.append((name,fd,info,pin(raw),store.security.snapshot(fd)));store.pending.remove(fd)
    store.verify();return raw

def dictionary_worker(args,deadline):
    require(type(args.control_fd) is int and args.control_fd>=3,'arguments');preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('dictionary',sources,deadline);security=modules['security'];observer=modules['observer']
        info=meta(os.fstat(args.control_fd))
        require(stat.S_ISDIR(info[2]) and stat.S_IMODE(info[2])==0o700 and info[3]==os.getuid()
            and info==meta(os.stat(CONTROL,follow_symlinks=False)),'worker_claim')
        claim=_regular_fd(args.claim_fd,'claim.json',args.control_fd,MAX_OUTPUT,security)
        require(claim==canonical({'binding':binding(args),'profile':profile_record()}),'worker_claim')
        intent_raw=_regular_fd(args.intent_fd,'dictionary-intent.json',args.control_fd,16384,security)
        intent=parse(intent_raw,16384)
        require(canonical(intent)==intent_raw and type(intent) is dict
            and set(intent)=={'binding','phase','claim_pin','plan','capture_receipt','response_pin'}
            and intent['binding']==binding(args) and intent['phase']=='dictionary' and intent['claim_pin']==pin(claim),'worker_claim')
        plan=observer.validate_plan(intent['plan']);receipt=observer.validate_capture_receipt(intent['capture_receipt'],plan)
        require(plan==observer.plan_record() and receipt['response_pin']==intent['response_pin']
            and fcntl.fcntl(args.response_fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY,'worker_claim')
        marker=canonical({'binding':binding(args),'phase':'dictionary','intent_pin':pin(intent_raw)})
        fd=os.open('dictionary-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=args.control_fd)
        try:require(os.write(fd,marker)==len(marker),'worker_marker');os.fsync(fd);os.fsync(args.control_fd)
        finally:os.close(fd)
        raw=_regular_fd(args.response_fd,'response-00.csv',args.control_fd,MAX_PRIVATE,security)
        require(pin(raw)==intent['response_pin'],'worker_output')
        validated=observer.validate_capture(plan,receipt,raw);budget(deadline)
        require(_regular_fd(args.claim_fd,'claim.json',args.control_fd,MAX_OUTPUT,security)==claim
            and _regular_fd(args.intent_fd,'dictionary-intent.json',args.control_fd,16384,security)==intent_raw
            and _regular_fd(args.response_fd,'response-00.csv',args.control_fd,MAX_PRIVATE,security)==raw,'changed')
        result={'dictionary_receipt':validated,'response_pin':pin(raw),'capture_receipt_sha256':sha(canonical(receipt)),
            'descriptor_validation_normal_return':True,'credential_access':False,'network_access':False,'old_control_access':False}
        sources.close()
        return {'schema':SCHEMA+'-worker','binding':binding(args),'result':result}


def worker_native_profile():
    value='(version 1)(allow default)(deny network*)(deny file-read* file-write* (subpath "/Volumes"))'
    value+=''.join('(deny file-read* file-write* (subpath "'+path+'"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (literal "'+str(CONTROL/'dictionary-started.json')+'"))'
    value+='(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
    leaves=[CONTROL/name for name in ('claim.json','response-00.csv','dictionary-intent.json','dictionary-started.json')]
    allowed={path for leaf in leaves for path in (*leaf.parents,leaf) if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
    value+=''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed))+'))'
    return value


def worker_failure(args,code):
    return {'schema':SCHEMA+'-worker','binding':ACTIVE_BINDING,'failure_code':code,'attempt_reusable':False}


def capture_worker(args,store,deadline,observer):
    store.verify();budget(deadline)
    claim=os.pread(_held_fd(store,'claim.json'),MAX_OUTPUT+1,0)
    intent={'binding':binding(args),'phase':'dictionary','claim_pin':pin(claim),'plan':observer.plan_record(),
        'capture_receipt':STATE['capture_receipt'],'response_pin':STATE['response_pin']}
    intent_raw=canonical(intent);store.write('dictionary-intent.json',intent_raw)
    response_fd=os.open('response-00.csv',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=store.fd)
    try:
        require(meta(os.fstat(response_fd))==meta(os.fstat(_held_fd(store,'response-00.csv'))),'changed')
        inherited=(store.fd,_held_fd(store,'claim.json'),response_fd,_held_fd(store,'dictionary-intent.json'))
        command=['/usr/bin/sandbox-exec','-p',worker_native_profile(),PYTHON,'-I','-B',str(SOURCE),'dictionary',
            '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
            '--control-fd',str(inherited[0]),'--claim-fd',str(inherited[1]),'--response-fd',str(inherited[2]),'--intent-fd',str(inherited[3]),
            '--outer-deadline',repr(min(deadline,time.monotonic()+WORKER_SECONDS))]
        observed={'spawn_observed':False,'actual_exit':None,'stdout_pin':pin(b''),'stderr_byte_count':0,'stderr_sha256':sha(b''),
            'marker_created':False,'marker_authenticated':False,'output_authenticated':False,'failure_code':None,
            'descriptor_validation_normal_return':False}
        require(STATE['worker_observation'] is None,'scope');STATE['worker_observation']=observed
        child=None;output=bytearray();errors=hashlib.sha256();stderr_count=0;problem=None
        stop=min(deadline,time.monotonic()+WORKER_SECONDS)
        try:
            child=subprocess.Popen(command,cwd=ROOT,env=safe_env(),stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,pass_fds=inherited)
            observed['spawn_observed']=True
            with selectors.DefaultSelector() as selected:
                for stream,label in ((child.stdout,'stdout'),(child.stderr,'stderr')):
                    os.set_blocking(stream.fileno(),False);selected.register(stream,selectors.EVENT_READ,label)
                while selected.get_map() or child.poll() is None:
                    for key,_ in selected.select(min(.1,budget(stop))):
                        raw=os.read(key.fileobj.fileno(),8192)
                        if not raw:selected.unregister(key.fileobj)
                        elif key.data=='stderr':
                            stderr_count+=len(raw);errors.update(raw);require(stderr_count<=MAX_WORKER_STDERR,'worker_stderr')
                        else:require(len(output)+len(raw)<=MAX_WORKER_OUTPUT,'bound');output.extend(raw)
            child.wait(timeout=min(5,budget(stop)))
        except BaseException as error:problem=finite(error)
        finally:
            if child is not None:
                if child.poll() is None:child.kill()
                child.wait(timeout=5);observed['actual_exit']=child.returncode;child.stdout.close();child.stderr.close()
            observed.update(stdout_pin=pin(bytes(output)),stderr_byte_count=stderr_count,stderr_sha256=errors.hexdigest())
    finally:os.close(response_fd)
    try:marker=adopt_marker(store,'dictionary')
    except BaseException as error:observed['failure_code']=finite(error);raise
    observed['marker_created']=marker is not None
    observed['marker_authenticated']=marker==canonical({'binding':binding(args),'phase':'dictionary','intent_pin':pin(intent_raw)})
    result=None
    if problem is None:
        try:
            require(stderr_count==0,'worker_stderr')
            require(type(observed['actual_exit']) is int and observed['actual_exit'] in (0,2)
                and bytes(output).endswith(b'\n') and bytes(output).count(b'\n')==1,'worker_output')
            packet=parse(bytes(output)[:-1],MAX_WORKER_OUTPUT)
            require(type(packet) is dict and canonical(packet)+b'\n'==bytes(output)
                and packet.get('schema')==SCHEMA+'-worker' and packet.get('binding')==binding(args),'worker_output')
            if observed['actual_exit']==2:
                require(set(packet)=={'schema','binding','failure_code','attempt_reusable'}
                    and type(packet['failure_code']) is str and packet['failure_code'] in FINITE and packet['attempt_reusable'] is False,'worker_output')
                observed['output_authenticated']=True;problem=packet['failure_code']
            else:
                require(set(packet)=={'schema','binding','result'} and observed['marker_authenticated'] is True,'worker_output')
                result=packet['result'];validate_worker_result(result,observer,STATE['capture_receipt'])
                observed.update(output_authenticated=True,descriptor_validation_normal_return=True)
        except BaseException as error:problem=finite(error);result=None
    observed['failure_code']=problem;store.write('dictionary-observed.json',canonical(observed))
    return result,observed


def new_state():
    return {'stage':'preflight','claim_state':'unallocated','complete':False,'accepted':False,'failure_code':None,
        'keychain_lookup_attempts':0,'keychain_lookup_completed':0,'http_events':[],'response_pin':None,'transport_pin':None,
        'capture_receipt':None,'dictionary_receipt':None,'worker_observation':None,
        'session_closed_before_worker':False,'key_local_reference_cleared_before_worker':False,
        'provider_request_count':None,**FALSE_FLAGS}


STATE=new_state()


def launch(args,deadline):
    global STATE
    STATE=new_state();preflight(args,deadline);safe_runtime()
    with ExitStack() as sources:
        modules=bootstrap('parent',sources,deadline);observer=modules['observer'];safe_runtime()
        with Store(modules['security']) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}));STATE['claim_state']=CLAIM_STATE
            key=None;session=None
            try:
                STATE['stage']='credential';STATE['keychain_lookup_attempts']+=1
                key=modules['keychain'].load_key('sharadar',timeout_seconds=min(20,budget(deadline)));STATE['keychain_lookup_completed']+=1
                budget(deadline);safe_runtime();STATE['stage']='capture';plan=observer.plan_record()
                session=observer.configure_owned_session(observer.requests.Session())
                def journal(marker,event):
                    budget(deadline);safe_runtime();row=observer.validate_event(event)
                    require(marker=='request-00-'+row['event'],'output')
                    events=observer.validate_events([*STATE['http_events'],row],plan)
                    store.write(marker+'.json',canonical(row));STATE['http_events']=events
                def retain_response(ordinal,raw,transport):
                    budget(deadline);safe_runtime()
                    require(type(ordinal) is int and ordinal==0 and STATE['response_pin'] is None
                        and type(raw) is bytes and 0<len(raw)<=MAX_PRIVATE,'retention')
                    expected=pin(raw)
                    require(type(transport) is dict and set(transport)=={'schema','plan_sha256','request_ordinal','role','http_status','body_pin','CSV_validation_complete'}
                        and transport['schema']==observer.SCHEMA+'-private-transport' and transport['plan_sha256']==sha(canonical(plan))
                        and type(transport['request_ordinal']) is int and transport['request_ordinal']==0 and transport['role']=='actiontypes'
                        and type(transport['http_status']) is int and transport['http_status']==200
                        and transport['body_pin']==expected and transport['CSV_validation_complete'] is False,'retention')
                    STATE['response_pin']=store.write('response-00.csv',raw)
                    STATE['transport_pin']=store.write('transport-00.json',canonical(transport))
                    return STATE['response_pin']
                receipt,opaque=observer.capture(plan,session=session,api_key=key,journal=journal,retain_response=retain_response,deadline=deadline)
                opaque=None
                observer.validate_capture_receipt(receipt,plan);observer.validate_events(STATE['http_events'],plan,receipt)
                STATE['capture_receipt']=receipt
                session.close();session=None;STATE['session_closed_before_worker']=True
                key=None;STATE['key_local_reference_cleared_before_worker']=True
                require(key is session is None,'credential');budget(deadline);STATE['stage']='dictionary'
                result,observed=capture_worker(args,store,deadline,observer)
                if STATE['worker_observation'] is None:STATE['worker_observation']=observed
                require(result is not None,observed['failure_code'] if observed['failure_code'] in FINITE else 'worker_failure')
                STATE['dictionary_receipt']=result['dictionary_receipt'];budget(deadline)
                STATE.update(complete=True,accepted=True,stage='complete')
            except BaseException as error:STATE['failure_code']=finite(error);STATE['complete']=STATE['accepted']=False
            finally:
                key=None
                if session is not None:
                    try:session.close()
                    except BaseException:
                        if STATE['failure_code'] is None:STATE['failure_code']='session'
                        STATE['complete']=STATE['accepted']=False
            STATE['claim_state']=CLAIM_STATE;validate_state(STATE,observer,binding(args))
            report={'binding':binding(args),'result':STATE};report_pin=store.write('report.json',canonical(report))
            return {**report,'report_pin':report_pin}


def validate_worker_result(value,observer,captured):
    require(type(value) is dict and set(value)=={'dictionary_receipt','response_pin','capture_receipt_sha256',
        'descriptor_validation_normal_return','credential_access','network_access','old_control_access'}
        and value['descriptor_validation_normal_return'] is True
        and all(value[name] is False for name in ('credential_access','network_access','old_control_access')),'output')
    receipt=observer.validate_capture_receipt(captured,observer.plan_record())
    observer.validate_dictionary_receipt(value['dictionary_receipt'],observer.plan_record(),receipt)
    checked_pin(value['response_pin'],MAX_PRIVATE)
    require(value['response_pin']==receipt['response_pin']
        and value['capture_receipt_sha256']==sha(canonical(receipt)),'output')
    return value


def validate_worker_observation(value):
    require(type(value) is dict and set(value)=={'spawn_observed','actual_exit','stdout_pin','stderr_byte_count','stderr_sha256',
        'marker_created','marker_authenticated','output_authenticated','failure_code','descriptor_validation_normal_return'}
        and all(type(value[name]) is bool for name in ('spawn_observed','marker_created','marker_authenticated',
            'output_authenticated','descriptor_validation_normal_return'))
        and (value['actual_exit'] is None or type(value['actual_exit']) is int)
        and type(value['stderr_byte_count']) is int and 0<=value['stderr_byte_count']<=MAX_WORKER_STDERR+8192
        and type(value['stderr_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['stderr_sha256'])
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE),'output')
    checked_pin(value['stdout_pin'],MAX_WORKER_OUTPUT,empty=True)
    require(not value['marker_authenticated'] or value['marker_created'],'output')
    if value['actual_exit'] is not None:require(value['spawn_observed'] is True,'output')
    if value['output_authenticated']:
        require(value['spawn_observed'] is True and type(value['actual_exit']) is int and value['actual_exit'] in (0,2)
            and value['stdout_pin']['byte_count']>0 and value['stderr_byte_count']==0 and value['stderr_sha256']==sha(b''),'output')
        if not value['descriptor_validation_normal_return']:
            require(value['actual_exit']==2 and value['failure_code'] is not None,'output')
    if value['descriptor_validation_normal_return']:
        require(value['spawn_observed'] is value['marker_created'] is value['marker_authenticated'] is value['output_authenticated'] is True
            and type(value['actual_exit']) is int and value['actual_exit']==0 and value['failure_code'] is None
            and value['stderr_byte_count']==0 and value['stderr_sha256']==sha(b'') and value['stdout_pin']['byte_count']>0,'output')
    return value


def validate_state(value,observer,run_binding):
    require(type(run_binding) is dict and set(run_binding)=={'schema','expected_head','caller_sha256','profile_sha256'}
        and run_binding['schema']==SCHEMA and all(type(run_binding[name]) is str and re.fullmatch('[0-9a-f]{'+str(size)+'}',run_binding[name])
            for name,size in (('expected_head',40),('caller_sha256',64),('profile_sha256',64))),'output')
    require(type(value) is dict and set(value)==set(new_state())
        and value['stage'] in ('preflight','credential','capture','dictionary','complete')
        and value['claim_state'] in ('unallocated','allocated_unknown','consumed','consumed_or_unknown')
        and type(value['complete']) is type(value['accepted']) is bool and value['complete'] is value['accepted']
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE)
        and type(value['keychain_lookup_attempts']) is type(value['keychain_lookup_completed']) is int
        and 0<=value['keychain_lookup_completed']<=value['keychain_lookup_attempts']<=1
        and type(value['http_events']) is list and len(value['http_events'])<=3
        and type(value['session_closed_before_worker']) is type(value['key_local_reference_cleared_before_worker']) is bool
        and value['provider_request_count'] is None and all(value[name] is False for name in FALSE_FLAGS),'output')
    plan=observer.plan_record();observer.validate_events(value['http_events'],plan)
    if value['keychain_lookup_attempts']:
        require(value['claim_state']=='consumed','output')
    if (value['http_events'] or any(value[name] is not None for name in
            ('response_pin','transport_pin','capture_receipt','dictionary_receipt','worker_observation'))):
        require(value['claim_state']=='consumed' and value['keychain_lookup_attempts']==value['keychain_lookup_completed']==1,'output')
    if value['response_pin'] is not None:
        checked_pin(value['response_pin'],MAX_PRIVATE)
        require(any(event['event']=='status' and type(event['http_status']) is int and event['http_status']==200
            for event in value['http_events']),'output')
    if value['transport_pin'] is not None:
        checked_pin(value['transport_pin'],8192);require(value['response_pin'] is not None,'output')
    for event in value['http_events']:
        if event['response_pin'] is not None:
            require(value['response_pin']==event['response_pin'],'output')
    captured=value['capture_receipt']
    if captured is not None:
        observer.validate_capture_receipt(captured,plan);observer.validate_events(value['http_events'],plan,captured)
        require(captured['response_pin']==value['response_pin'] and value['transport_pin'] is not None,'output')
    if value['worker_observation'] is not None:
        validate_worker_observation(value['worker_observation'])
        require(captured is not None and value['session_closed_before_worker'] is value['key_local_reference_cleared_before_worker'] is True,'output')
    if value['dictionary_receipt'] is not None:
        require(captured is not None and value['worker_observation'] is not None
            and value['worker_observation']['descriptor_validation_normal_return'] is True,'output')
        observer.validate_dictionary_receipt(value['dictionary_receipt'],plan,captured)
        reconstructed={'dictionary_receipt':value['dictionary_receipt'],'response_pin':value['response_pin'],
            'capture_receipt_sha256':sha(canonical(captured)),'descriptor_validation_normal_return':True,
            'credential_access':False,'network_access':False,'old_control_access':False}
        require(value['worker_observation']['stdout_pin']==pin(canonical({'schema':SCHEMA+'-worker',
            'binding':run_binding,'result':reconstructed})+b'\n'),'output')
    if value['accepted']:
        require(value['stage']=='complete' and value['claim_state']=='consumed' and value['failure_code'] is None
            and value['dictionary_receipt'] is not None and value['worker_observation'] is not None
            and value['worker_observation']['descriptor_validation_normal_return'] is True,'output')
    else:require(value['failure_code'] is not None,'output')
    return value


def failure_packet(code):
    return {'binding':ACTIVE_BINDING,'failure_code':code,'attempt_reusable':False,'state':STATE}


def validate_output(raw,actual_exit,args,observer):
    require(type(actual_exit) is int and actual_exit in (0,2) and type(raw) is bytes
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'output')
    packet=parse(raw[:-1],MAX_OUTPUT)
    require(type(packet) is dict and canonical(packet)+b'\n'==raw and packet.get('binding')==binding(args),'output')
    if set(packet)=={'binding','result','report_pin'}:
        validate_state(packet['result'],observer,binding(args))
        checked_pin(packet['report_pin'],MAX_OUTPUT)
        require(actual_exit==(0 if packet['result']['accepted'] else 2)
            and packet['report_pin']==pin(canonical({'binding':binding(args),'result':packet['result']})),'output')
        return {'binding':binding(args),'output_authenticated':True,'accepted':packet['result']['accepted'],
            'actual_parent_exit':actual_exit,'report_pin':packet['report_pin'],'result':packet['result']}
    require(actual_exit==2 and set(packet)=={'binding','failure_code','attempt_reusable','state'}
        and packet['attempt_reusable'] is False and type(packet['failure_code']) is str and packet['failure_code'] in FINITE,'output')
    validate_state(packet['state'],observer,binding(args));require(packet['state']['accepted'] is False,'output')
    return {'binding':binding(args),'output_authenticated':True,'accepted':False,'actual_parent_exit':actual_exit,
        'failure_code':packet['failure_code'],'report_pin':None,'result':packet['state']}


class Parser(argparse.ArgumentParser):
    def error(self,message):raise Refused('arguments')


def main():
    global ACTIVE_BINDING,ACTIVE_MODE
    parser=Parser(add_help=False)
    parser.add_argument('mode',choices=('launch','dictionary','validate','profile'))
    for key in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+key)
    for key in ('control-fd','claim-fd','response-fd','intent-fd','actual-parent-exit'):parser.add_argument('--'+key,type=int)
    parser.add_argument('--outer-deadline',type=float)
    args=parser.parse_args();ACTIVE_MODE=args.mode
    if args.mode=='profile':
        require(all(getattr(args,key) is None for key in ('expected_head','caller_sha256','profile_sha256',
            'control_fd','claim_fd','response_fd','intent_fd','actual_parent_exit','outer_deadline')),'arguments')
        return profile_record()
    ACTIVE_BINDING=binding(args);deadline=ENTRY_DEADLINE
    if args.mode=='dictionary':
        require(args.actual_parent_exit is None and type(args.outer_deadline) in (int,float)
            and math.isfinite(args.outer_deadline),'arguments')
        deadline=min(deadline,args.outer_deadline);budget(deadline)
    else:require(args.control_fd is args.claim_fd is args.response_fd is args.intent_fd is args.outer_deadline is None,'arguments')
    def expired(*args):raise Refused('deadline')
    signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,min(30,budget(deadline)) if args.mode=='validate' else budget(deadline))
    if args.mode=='launch':
        require(args.actual_parent_exit is None,'arguments');return launch(args,deadline)
    if args.mode=='validate':
        require(type(args.actual_parent_exit) is int and args.actual_parent_exit in (0,2),'arguments')
        preflight(args,deadline)
        with ExitStack() as sources:
            modules=bootstrap('validate',sources,deadline)
            return validate_output(sys.stdin.buffer.read(MAX_OUTPUT+1),args.actual_parent_exit,args,modules['observer'])
    try:return dictionary_worker(args,deadline)
    except BaseException as error:return worker_failure(args,finite(error))


ACTIVE_MODE=None
if __name__=='__main__':
    try:
        value=main();raw=canonical(value)+b'\n';require(len(raw)<=MAX_OUTPUT,'bound')
        sys.stdout.buffer.write(raw)
        if ACTIVE_MODE=='profile':code=0
        elif ACTIVE_MODE=='dictionary':code=0 if 'result' in value else 2
        elif ACTIVE_MODE=='validate':code=0 if value['accepted'] else 2
        else:code=0 if value['result']['accepted'] else 2
        raise SystemExit(code)
    except SystemExit:raise
    except BaseException as error:
        code=finite(error);STATE.update(complete=False,accepted=False,claim_state=CLAIM_STATE)
        if STATE['failure_code'] is None:STATE['failure_code']=code
        sys.stdout.buffer.write(canonical(failure_packet(code))+b'\n')
        raise SystemExit(2)
