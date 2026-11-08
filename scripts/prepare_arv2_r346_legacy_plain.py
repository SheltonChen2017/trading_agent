"""Once-only OFFLINE plain DATA and old-six source proposal; never a launch.

The committed caller/plan/clean HEAD and external native denial precede use.
Only exact R343-B DATA is read after an exclusive claim. Two complete proposals
must agree inside the original DATA/source guards, and both guards must return
normally before publication. AR100 remains exhausted at three attempts.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import spec_from_loader
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import time
from types import ModuleType

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
SOURCE = ROOT / 'scripts/prepare_arv2_r346_legacy_plain.py'
PLAN = ROOT / 'scripts/arv2_r346_legacy_plain_plan.json'
PARENT_PLAN = ROOT / 'scripts/arv2_r345_legacy_six_plan_v3.json'
PARENT_PLAN_PIN = {'byte_count': 49439, 'sha256': '9cdf7743561da0e9ec4554b3a03d687a5b0f0c4ed9e349b3199429f1381073b4'}
DATA = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_extension/R343-20261105-B/submission-private.json'
DATA_PIN = {'byte_count': 6814004, 'sha256': 'bdb70766a8bfa54a183c5c0e261ee7e01c7036071f43bd703b7fa4eb24a61413'}
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_plain/R346-20261107-A'
SUPPORT = ROOT / '.pytest_cache/r346-preparation'
SCHEMA = 'arv2-r346-offline-legacy-plain-preparation-v1'
PLAN_SCHEMA = 'arv2-r346-legacy-plain-plan-v1'
SECONDS = 180
MAX_PUBLIC, MAX_PLAN, MAX_PRIVATE, MAX_PROPOSAL, MAX_OUTPUT = 2*1024*1024, 256*1024, 44*1024*1024, 8*1024*1024, 64*1024
FIELDS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
BRIDGE_PATH = 'scripts/arv2_r345_legacy_plain_bridge.py'
LOADER_PATH = 'research/analyst_revisions_v2_qc/newrule_plain_input_runtime.py'
TRANSPORT_PATH = 'research/analyst_revisions_v2_qc/newrule_plain_transport.py'
A3_PATH = 'scripts/arv2_r345_ar100_a3_failure_fact.json'
ADDITIONAL_PINS = {
    BRIDGE_PATH: {'byte_count':21563,'sha256':'622cf12adeea050070cf3c4720184279f1ccb6c0789a92a5c8c10afb68996491'},
    LOADER_PATH: {'byte_count':16429,'sha256':'bc07c0bebc141ecad38c774a52ea3bddaad4664a7dd85ccf47581572ef9beb8f'},
    TRANSPORT_PATH: {'byte_count':15710,'sha256':'4cf351095015fddb7a463692f6d789917d229966772e04a60de0c804ed965f5a'},
    A3_PATH: {'byte_count':6261,'sha256':'f2378ad12bde90eefb17d12210d5e10f358cd52993fbecb02e41d996e33643de'},
}
OBJECT_NAMES = ('evaluator-manifest.json','session_axis-0000.jsonl','memberships-0000.jsonl',
    'contributions-0000.jsonl','runtime_symbol_bindings-0000.jsonl','transport-manifest.json')
NORMAL_FILES = frozenset(('claim.json',*OBJECT_NAMES,'source-proposal.json','report.json'))
FLAGS = {key:False for key in ('QC_contact','Safari_access','provider_contact','credential_access','USB_access',
    'operational_authority','new_storage_admitted','qc_source_policy_acceptance_proven','attempt_budget_reset',
    'source_admission_granted','backtest_completed','point_in_time_proven','formal_identity_admitted',
    'formal_forward_ready','paper_or_live_ready')}
BRIDGE_CODES = frozenset(('json','bytes','hash','pin','inventory','parent','transport','plain','cells','sources',
    'source_ast','loader_surface','plain_loader','validity_guard','main','economic_ast','collection_semantics',
    'parent_profile','source_bound','unchanged'))
FINITE = frozenset(('arguments','environment','git','plan','source_pin','source_changed','inventory','claim_spent',
    'control','deadline','data','conversion','proposal','agreement','output','close','unknown'))
STAGE, CLAIM_STATE, DEPENDENCY_FAILURE = 'preflight','unallocated',None


class Refused(ValueError):
    pass


class Deadline(BaseException):
    pass


def require(value, code):
    if not value: raise Refused(code)


def canonical(value):
    try: return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (ValueError,TypeError,UnicodeError,RecursionError): raise Refused('output') from None


def pin(raw):
    return {'byte_count':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def valid_pin(value, maximum):
    return type(value) is dict and set(value)=={'byte_count','sha256'} and type(value['byte_count']) is int \
        and 0<=value['byte_count']<=maximum and type(value['sha256']) is str \
        and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None


def loads(raw, maximum, *, lf=False):
    require(type(raw) is bytes and 0<len(raw)<=maximum,'plan')
    def pairs(items):
        value={}
        for key,item in items:
            require(key not in value,'plan');value[key]=item
        return value
    try:
        value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('plan')))
        require(canonical(value)+(b'\n' if lf else b'')==raw,'plan');return value
    except Refused: raise
    except (ValueError,UnicodeError,RecursionError): raise Refused('plan') from None


def budget(deadline):
    left=deadline-time.monotonic()
    require(type(deadline) in (int,float) and math.isfinite(left) and 0<left<=SECONDS,'deadline')
    return left


def metadata(info):
    values=tuple(getattr(info,key,None) for key in FIELDS)
    require(all(type(value) is int and value>=0 for value in values),'source_changed');return values


meta=metadata


def safe_env():
    return {'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C',
        'TMPDIR':str(SUPPORT),'SQLITE_TMPDIR':str(SUPPORT),'XDG_CACHE_HOME':str(SUPPORT/'cache'),
        'PYTHONPYCACHEPREFIX':str(SUPPORT/'pycache'),'PYTHONDONTWRITEBYTECODE':'1',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','GIT_OPTIONAL_LOCKS':'0'}


def native_profile():
    value='(version 1)(allow default)(deny network*)'
    for path in ('/Volumes','/Users/sheltonchen/Library/Keychains','/Library/Keychains'):
        value+='(deny file-read* file-write* (subpath '+json.dumps(path)+'))'
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (subpath '+json.dumps(str(CONTROL))+'))'
    value+='(require-not (literal '+json.dumps(str(CONTROL.parent))+'))'
    value+='(require-not (subpath '+json.dumps(str(SUPPORT))+'))(require-not (literal "/dev/null"))))'
    ancestors={path for leaf in (DATA,CONTROL) for path in leaf.parents
        if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath '+json.dumps(str(ROOT/'artifacts'))+')'
    value+='(require-not (literal '+json.dumps(str(DATA))+'))(require-not (subpath '+json.dumps(str(CONTROL))+'))'
    value+=''.join('(require-not (literal '+json.dumps(str(path))+'))' for path in sorted(ancestors))+'))'
    return value


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'plan':str(PLAN),
        'parent_plan_pin':dict(PARENT_PLAN_PIN),'data':str(DATA),'data_pin':dict(DATA_PIN),'control':str(CONTROL),
        'seconds':SECONDS,'normal_files':sorted(NORMAL_FILES),'max_proposal_bytes':MAX_PROPOSAL,
        'max_output_bytes':MAX_OUTPUT,'native_policy_sha256':pin(native_profile().encode())['sha256'],
        'source_guard_and_B_guard_normal_return_before_publication':True,'complete_computations':2,
        'failure_policy':'actual_nonzero_or_unknown_exit_inadmissible_even_if_complete_files_exist_no_retry_cleanup_or_reader',
        'purpose':'offline_uncompressed_identity_DATA_and_transport_only_source_proposal_not_a_new_candidate',
        'deadline_qualification':'cannot_bound_uninterruptible_IO_or_host_suspension',**FLAGS}


def binding(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and all(type(getattr(args,key)) is str and re.fullmatch('[0-9a-f]{64}',getattr(args,key))
            for key in ('caller_sha256','plan_sha256')),'arguments')
    return {'schema':SCHEMA,'expected_head':args.expected_head,'caller_sha256':args.caller_sha256,
        'plan_sha256':args.plan_sha256,'profile_sha256':pin(canonical(profile_record()))['sha256']}


def preflight(args, deadline):
    bound=binding(args)
    require(Path.cwd()==ROOT and ROOT.resolve()==ROOT and sys.platform=='darwin' and os.name=='posix'
        and sys.version_info[:2]==(3,13) and sys.executable==PYTHON and sys.flags.isolated==1
        and sys.dont_write_bytecode and Path(__file__).absolute()==SOURCE,'environment')
    safe=safe_env()
    require(set(os.environ)<=set(safe)|{'__CF_USER_TEXT_ENCODING'}
        and all(os.environ.get(key)==value for key,value in safe.items())
        and ('__CF_USER_TEXT_ENCODING' not in os.environ
            or os.environ['__CF_USER_TEXT_ENCODING']==f'0x{os.getuid():X}:0x0:0x0'),'environment')
    for key in ('TMPDIR','SQLITE_TMPDIR','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX'):
        path=Path(safe[key]);require(path.is_dir() and path.resolve()==path,'environment')
    for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],BRANCH),
            (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
        result=subprocess.run(['/usr/bin/git',*command],cwd=ROOT,env=safe,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=min(10,budget(deadline)),check=False)
        require(result.returncode==0 and not result.stderr and len(result.stdout)<=262144
            and result.stdout.decode('ascii').strip()==expected,'git')
    return bound


def validate_a3_fact(value):
    require(type(value) is dict and set(value)=={'schema','binding','failure','observation'}
        and value['schema']=='arv2-r345-ar100-a3-failure-fact-v1'
        and type(value['binding']) is dict
        and type(value['observation']) is dict and type(value['observation'].get('actual_exit')) is int
        and value['observation']['actual_exit']==2 and value['observation'].get('stderr_bytes')==0
        and value['binding'].get('caller_sha256')=='adf9b60673f802f8c73a1767988748c3127f9986a49b9fb1e3929e323345f263'
        and value['binding'].get('plan_sha256')==PARENT_PLAN_PIN['sha256'],'plan')
    failure=value['failure'];require(type(failure) is dict and failure.get('claim_state')=='consumed'
        and failure.get('stage')=='source_compile' and failure.get('result_read') is False,'plan')
    require(type(failure.get('evidence')) is dict,'plan')
    allocated=failure['evidence'].get('allocated_identities')
    require(type(allocated) is dict and type(allocated.get('project_id')) is int
        and allocated['project_id']==39054561 and allocated.get('compile_id') is None
        and allocated.get('backtest_id') is None,'plan')
    return {'candidate_id':'R343-AR100','attempts_consumed':3,'maximum_attempts':3,
        'status':'exhausted_requires_Mia_checkpoint_and_separate_continuation','project_id':39054561,
        'compile_id':None,'backtest_id':None,'attempt_reset':False,'A4_permitted':False}


class Sources:
    """Selected code/JSON held through the operation and executed from buffers."""
    def __init__(self, args, deadline):
        self.args, self.deadline, self.rows, self.cache, self.raws = args, deadline, [], {}, {}
        self.finder = self.security = self.public_security = None

    def hold(self, path, expected):
        require(valid_pin(expected, MAX_PUBLIC), 'source_pin')
        if not self.cache:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.cache[Path('/')] = (fd, fd, '.', metadata(os.fstat(fd)))
        row = self.cache[Path('/')]
        current = Path('/')
        for part in path.parts[1:-1]:
            budget(self.deadline); current /= part
            if current not in self.cache:
                before = metadata(os.stat(part, dir_fd=row[0], follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=row[0])
                self.cache[current] = (fd, row[0], part, before)
                require(stat.S_ISDIR(before[2]) and metadata(os.fstat(fd)) == before, 'source_changed')
            row = self.cache[current]
        before = metadata(os.stat(path.name, dir_fd=row[0], follow_symlinks=False))
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=row[0])
        item = [fd, row[0], path.name, before, expected, None]
        self.rows.append(item)
        require(stat.S_ISREG(before[2]) and before[3] == os.getuid() and before[5] == 1
            and stat.S_IMODE(before[2]) in (0o600, 0o644) and metadata(os.fstat(fd)) == before, 'source_pin')
        raw = os.pread(fd, MAX_PUBLIC + 1, 0)
        require(pin(raw) == expected and before[6] == len(raw), 'source_pin')
        return raw

    def __enter__(self):
        try:
            self.hold(SOURCE, {'byte_count': SOURCE.stat().st_size, 'sha256': self.args.caller_sha256})
            raw = self.hold(PLAN, {'byte_count': PLAN.stat().st_size, 'sha256': self.args.plan_sha256})
            require(len(raw) <= MAX_PLAN, 'plan')
            self.plan = loads(raw, MAX_PLAN)
            require(type(self.plan) is dict and set(self.plan) == {'schema', 'preparation_binding', 'private_pin',
                'source_summary', 'source_pins', 'parent_plan_pin'} and self.plan['schema'] == PLAN_SCHEMA
                and self.plan['private_pin'] == DATA_PIN and self.plan['parent_plan_pin'] == PARENT_PLAN_PIN
                and type(self.plan['source_pins']) is dict and len(self.plan['source_pins']) == 170, 'plan')
            parent_raw = self.hold(PARENT_PLAN, PARENT_PLAN_PIN)
            parent = loads(parent_raw, MAX_PLAN)
            require(type(parent) is dict and type(parent.get('source_pins')) is dict
                and len(parent['source_pins']) == 168
                and canonical(self.plan['source_pins']) == canonical({**parent['source_pins'], **ADDITIONAL_PINS})
                and canonical(self.plan['preparation_binding']) == canonical(parent['preparation_binding'])
                and canonical(self.plan['source_summary']) == canonical(parent['source_summary']), 'plan')
            soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            require(soft == resource.RLIM_INFINITY or soft >= len(self.plan['source_pins']) + 180, 'environment')
            for relative, expected in sorted(self.plan['source_pins'].items()):
                require(type(relative) is str and not relative.startswith('/') and '..' not in Path(relative).parts
                    and relative.endswith(('.py', '.json')) and 'artifacts' not in Path(relative).parts
                    and relative != PLAN.relative_to(ROOT).as_posix(), 'plan')
                self.raws[relative] = self.hold(ROOT / relative, expected)
            for required in ('scripts/arv2_relocation_security.py', 'scripts/prepare_arv2_r343_legacy_six.py',
                    'scripts/arv2_r343_legacy_six_source_pins.json', 'scripts/arv2_r345_legacy_six_submission_data.py',
                    BRIDGE_PATH, LOADER_PATH, TRANSPORT_PATH, A3_PATH):
                require(required in self.raws, 'inventory')
            original = loads(self.raws['scripts/arv2_r343_legacy_six_source_pins.json'], MAX_PUBLIC)
            require(type(original) is dict and type(original.get('files')) is dict
                and all(self.plan['source_pins'].get(key) == expected for key, expected in original['files'].items()), 'inventory')
            helper = ModuleType('_r345_public_source_helpers')
            exec(compile(self.raws['scripts/prepare_arv2_r343_legacy_six.py'],
                str(ROOT / 'scripts/prepare_arv2_r343_legacy_six.py'), 'exec'), helper.__dict__)
            security_module = ModuleType('_r345_exact_security')
            exec(compile(self.raws['scripts/arv2_relocation_security.py'],
                str(ROOT / 'scripts/arv2_relocation_security.py'), 'exec'), security_module.__dict__)
            self.security, self.public_security = security_module, helper.public_source_security
            for item in self.rows:
                item[5] = self.public_security(item[0], self.security)
            names = {key[:-3].replace('/', '.').removesuffix('.__init__'): key
                for key in self.raws if key.endswith('.py')}
            require('scripts' not in sys.modules and not any(name in sys.modules for name in names), 'environment')
            raws = self.raws
            class ExactLoader(Loader):
                def __init__(self, relative): self.relative = relative
                def create_module(self, spec): return None
                def exec_module(self, module):
                    module.__file__ = str(ROOT / self.relative)
                    if self.relative.endswith('/__init__.py'):
                        module.__path__ = [str((ROOT / self.relative).parent)]
                    exec(compile(raws[self.relative], module.__file__, 'exec'), module.__dict__)
            class ExactFinder(MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == 'scripts':
                        result = ModuleSpec(fullname, loader=None, is_package=True)
                        result.submodule_search_locations = [str(ROOT / 'scripts')]
                        return result
                    if fullname in names:
                        relative = names[fullname]
                        return spec_from_loader(fullname, ExactLoader(relative), origin=str(ROOT / relative),
                            is_package=relative.endswith('/__init__.py'))
                    found = PathFinder.find_spec(fullname, path)
                    origin = None if found is None else found.origin
                    require(not (type(origin) is str and Path(origin).is_absolute()
                        and Path(origin).is_relative_to(ROOT)), 'source_pin')
                    return None
            self.finder = ExactFinder(); sys.meta_path.insert(0, self.finder)
            self.consumer = importlib.import_module('scripts.arv2_r345_legacy_six_submission_data')
            self.bridge = importlib.import_module('scripts.arv2_r345_legacy_plain_bridge')
            self.a3_state = validate_a3_fact(loads(self.raws[A3_PATH], MAX_OUTPUT, lf=True))
            self.verify()
            return self
        except BaseException:
            self.close(); raise

    def verify(self):
        for fd, parent, name, before in self.cache.values():
            budget(self.deadline)
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'source_changed')
        for fd, parent, name, before, expected, native in self.rows:
            budget(self.deadline)
            require(metadata(os.fstat(fd)) == before == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and pin(os.pread(fd, MAX_PUBLIC + 1, 0)) == expected, 'source_changed')
            if native is not None:
                require(self.public_security(fd, self.security) == native, 'source_changed')

    def close(self):
        if self.finder in sys.meta_path:
            sys.meta_path.remove(self.finder)
        failed = False
        for fd in [item[0] for item in reversed(self.rows)] + [row[0] for row in reversed(tuple(self.cache.values()))]:
            try: os.close(fd)
            except OSError: failed = True
        self.rows.clear(); self.cache.clear()
        require(not failed, 'close')

    def __exit__(self, *_):
        try: self.verify()
        finally: self.close()


class Store:
    """Exclusively allocated own control; no cleanup, overwrites or retries."""
    NAMES = NORMAL_FILES
    def __init__(self, security):
        self.security, self.chain, self.leaves = security, [], []
        self.fd = None

    def __enter__(self):
        global CLAIM_STATE
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.chain.append((parent, parent, '.', meta(os.fstat(parent)), None))
            current = Path('/')
            for part in CONTROL.parts[1:]:
                current /= part
                if current in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                        if current == CONTROL:
                            CLAIM_STATE = 'allocated_unknown'
                        os.fsync(parent)
                        old = self.chain[-1]
                        after = meta(os.fstat(parent))
                        require(all(after[index] == old[3][index] for index in (0, 1, 2, 3, 4, 9))
                            and (old[4] is None or self.security.snapshot(parent) == old[4]), 'control')
                        self.chain[-1] = (old[0], old[1], old[2], after, old[4])
                    except FileExistsError:
                        if current == CONTROL:
                            CLAIM_STATE = 'consumed_or_unknown'
                            raise Refused('claim_spent') from None
                before = meta(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.chain.append((fd, parent, part, before, None))
                checked = current == ROOT or ROOT in current.parents
                require(meta(os.fstat(fd)) == before and stat.S_ISDIR(before[2])
                    and (not checked or (before[3] == os.getuid()
                    and stat.S_IMODE(before[2]) == (0o755 if current == ROOT else 0o700))), 'control')
                self.chain[-1] = (fd, parent, part, before,
                    self.security.snapshot(fd) if checked else None)
                parent = fd
            self.fd = parent
            self.refresh()
            self.verify()
            return self
        except BaseException:
            self.close()
            raise

    def refresh(self):
        fd, parent, name, _, security = self.chain[-1]
        self.chain[-1] = (fd, parent, name, meta(os.fstat(fd)), security)

    def verify(self):
        require(self.fd is not None and set(os.listdir(self.fd)) == {row[0] for row in self.leaves}, 'control')
        for fd, parent, name, observed, security in self.chain:
            require(meta(os.fstat(fd)) == observed == meta(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'control')
            if security is not None:
                require(self.security.snapshot(fd) == security, 'control')
        for name, fd, observed, security, expected in self.leaves:
            require(meta(os.fstat(fd)) == observed == meta(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and stat.S_ISREG(observed[2]) and stat.S_IMODE(observed[2]) == 0o600
                and observed[3] == os.getuid() and observed[5] == 1
                and self.security.snapshot(fd) == security
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'control')

    def write(self, name, raw):
        global CLAIM_STATE
        require(name in self.NAMES and type(raw) is bytes and 0 < len(raw) <=
            (MAX_PROPOSAL if name == 'source-proposal.json' else MAX_OUTPUT if name in ('claim.json','report.json') else 32*1024*1024), 'output')
        self.verify()
        before = self.chain[-1][3]
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:])
                require(count > 0, 'output')
                offset += count
            os.fsync(fd)
            observed = meta(os.fstat(fd))
            require(os.pread(fd, len(raw) + 1, 0) == raw, 'output')
            after = meta(os.fstat(self.fd))
            require(all(after[index] == before[index] for index in (0, 1, 2, 3, 4, 9))
                and self.security.snapshot(self.fd) == self.chain[-1][4], 'control')
            self.leaves.append((name, fd, observed, self.security.snapshot(fd), pin(raw)))
            fd = None
            self.refresh()
            os.fsync(self.fd)
            self.verify()
            if name == 'claim.json':
                CLAIM_STATE = 'consumed'
            return pin(raw)
        finally:
            if fd is not None:
                os.close(fd)

    def close(self):
        failed = False
        for _, fd, _, _, _ in self.leaves:
            try:
                os.close(fd)
            except OSError:
                failed = True
        self.leaves.clear()
        for fd, _, _, _, _ in reversed(self.chain):
            try:
                os.close(fd)
            except OSError:
                failed = True
        self.chain.clear()
        self.fd = None
        require(not failed, 'close')

    def __exit__(self, *_):
        try:
            self.verify()
        finally:
            self.close()



def attempt_state(a3):
    return {'R343-AR100':dict(a3),'other_candidates':[
        {'candidate_id':f'R343-AR{value:03d}','attempts_consumed':0,'status':'uninvoked_no_submission_authority'}
        for value in (80,120,140,160,180,200)],'new_candidate_created':False,'attempt_budget_reset':False}


def compute(submission, sources, bound, deadline):
    budget(deadline);bridge=sources.bridge
    pairs=tuple((loads(item.descriptor_json,MAX_OUTPUT),item.payload) for item in submission.uploads)
    # The complete enclosing B DATA pin has already authenticated every supplied
    # descriptor and payload. This derived inventory is NOT a refreshed source
    # pin or a replacement for that prior external byte binding.
    inventory_pin=pin(canonical([row for row,_ in pairs]))
    plain=bridge.convert_supplied_inputs(pairs,
        expected_package_sha256='411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad',
        expected_lineage_sha256='e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9',
        expected_inventory_pin=inventory_pin)
    record,_,activation=bridge.validate_plain_data(plain)
    require(record['package_sha256']=='1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
        and record['parent_proof_sha256']=='95405d1b569d4bfeeb6c6d87fdb430f2fd27b8b7a31d6dcde7f82276d9903cd1'
        and {key:activation[key] for key in ('byte_count','content_sha256')}
            =={'byte_count':5901,'content_sha256':'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b'},'conversion')
    parents=tuple(bridge.ParentCell(row.candidate_id,row.ar_percent,row.profile_json,row.sources)
        for row in submission.candidates)
    # This vector is externally pinned through the original validated B public
    # summary in the committed plan, rather than adopted from current code.
    vector=canonical([{key:row[key] for key in ('candidate_id','ar_percent','profile_pin','sources')}
        for row in sources.plan['source_summary']['cells']])
    require(bridge.parent_vector(parents)==vector,'proposal')
    cells=bridge.build_source_bridge(parents,plain,expected_parent_vector_pin=pin(vector),
        plain_loader_source=sources.raws[LOADER_PATH],expected_plain_loader_pin=ADDITIONAL_PINS[LOADER_PATH])
    objects=[]
    for descriptor_raw,payload in plain.uploads:
        budget(deadline);descriptor=loads(descriptor_raw,MAX_OUTPUT)
        objects.append((descriptor['relative_path'],payload,descriptor_raw))
    require(tuple(row[0] for row in objects)==OBJECT_NAMES and len(objects)==6
        and all(type(raw) is bytes and 0<len(raw)<=32*1024*1024 for _,raw,_ in objects)
        and sum(len(raw) for _,raw,_ in objects)<=MAX_PRIVATE,'conversion')
    rows=[{'candidate_id':cell.candidate_id,'ar_percent':cell.ar_percent,
        'profile':loads(cell.profile_bytes,MAX_OUTPUT),'source_pairs':[[name,raw.decode('ascii')] for name,raw in cell.sources],
        'bridge_record':loads(cell.record_bytes,MAX_OUTPUT)} for cell in cells]
    proposal={'schema':SCHEMA+'-source-proposal','binding':bound,'parent_B_data_pin':dict(DATA_PIN),
        'source_inventory_pin':inventory_pin,'parent_source_vector_pin':pin(vector),
        'parent_proof':record['parent_proof'],'actual_plain_package_sha256':record['package_sha256'],
        'actual_plain_activation':activation,'objects':[loads(raw,MAX_OUTPUT) for _,_,raw in objects],
        'cells':rows,'current_attempt_state':attempt_state(sources.a3_state),**FLAGS}
    proposal_raw=canonical(proposal);require(len(proposal_raw)<=MAX_PROPOSAL,'proposal')
    summary={'actual_plain_package_sha256':record['package_sha256'],
        'parent_proof_sha256':record['parent_proof_sha256'],'source_inventory_pin':inventory_pin,
        'parent_source_vector_pin':pin(vector),'actual_activation':activation,
        'object_files':[{'relative_path':name,**pin(raw)} for name,raw,_ in objects],
        'cells':[loads(cell.record_bytes,MAX_OUTPUT) for cell in cells],
        'current_attempt_state':attempt_state(sources.a3_state),**FLAGS}
    budget(deadline)
    return tuple((name,raw) for name,raw,_ in objects),proposal_raw,canonical(summary)


def run(args):
    global STAGE,DEPENDENCY_FAILURE
    deadline=time.monotonic()+SECONDS;bound=preflight(args,deadline)
    with ExitStack() as controls:
        with Sources(args,deadline) as sources:
            store=controls.enter_context(Store(sources.security))
            store.write('claim.json',canonical({'schema':SCHEMA+'-claim','binding':bound,
                'profile':profile_record(),'claimed_utc':datetime.now(timezone.utc).isoformat()}))
            STAGE='B_DATA'
            try:
                with sources.consumer.FreshSubmission(expected_pin=DATA_PIN,
                        expected_summary=canonical(sources.plan['source_summary']),
                        expected_binding=canonical(sources.plan['preparation_binding']),deadline=deadline) as held:
                    STAGE='compute_first';first=compute(held.value,sources,bound,deadline)
                    STAGE='compute_second';second=compute(held.value,sources,bound,deadline)
                    require(first==second,'agreement')
                STAGE='source_guard_return';sources.verify()
            except BaseException as error:
                DEPENDENCY_FAILURE=dependency(error,sources)
                raise
        # BOTH original guards have returned normally. Only detached immutable
        # buffers remain, and the original Store descriptors are still held.
        STAGE='publication';objects,proposal_raw,summary_raw=first
        for name,raw in objects:
            budget(deadline);store.write(name,raw)
        proposal_pin=store.write('source-proposal.json',proposal_raw)
        report={'schema':SCHEMA+'-result','binding':bound,'source_guard_returned':True,
            'B_DATA_guard_returned':True,'two_complete_buffers_equal':True,
            'qualification':'fresh_endpoint_buffers_only_not_formal_source_or_continuous_integrity_or_QC_acceptance',
            'source_proposal_pin':proposal_pin,'summary':loads(summary_raw,MAX_OUTPUT),**FLAGS}
        report_raw=canonical(report);require(len(report_raw)<=MAX_OUTPUT-1024,'output')
        report_pin=store.write('report.json',report_raw);store.verify();budget(deadline)
    STAGE='complete'
    return {'report':report,'report_pin':report_pin}


def dependency(error,sources):
    if type(error) is sources.consumer.Refused:
        args=BaseException.args.__get__(error)
        return {'module':'B_consumer','code':args[0] if len(args)==1 and args[0] in sources.consumer.FINITE else 'unknown'}
    if type(error) is sources.bridge.Refused:
        args=BaseException.args.__get__(error)
        return {'module':'bridge','code':args[0] if len(args)==1 and args[0] in BRIDGE_CODES else 'unknown'}
    return None


def finite(error):
    if isinstance(error,(Deadline,TimeoutError,subprocess.TimeoutExpired)):return 'deadline'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def validate_original_stdout(raw, *, actual_exit, expected_binding):
    """Pure ORIGINAL-output/observed-exit check, never an on-disk reader.

    This is not independent process attestation. Future use must freshly
    authenticate all nine retained files against the externally observed pins.
    """
    require(type(actual_exit) is int and actual_exit==0 and type(raw) is bytes
        and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n') and raw.count(b'\n')==1,'output')
    expected_keys={'schema','expected_head','caller_sha256','plan_sha256','profile_sha256'}
    require(type(expected_binding) is dict and set(expected_binding)==expected_keys
        and expected_binding['schema']==SCHEMA
        and all(type(expected_binding[key]) is str
            and re.fullmatch('[0-9a-f]{40}' if key=='expected_head' else '[0-9a-f]{64}',expected_binding[key])
            for key in expected_keys-{'schema'}),'output')
    try:value=loads(raw[:-1],MAX_OUTPUT)
    except Refused:raise Refused('output') from None
    require(type(value) is dict and set(value)=={'report','report_pin'},'output')
    report=value['report'];guard_fields=('source_guard_returned','B_DATA_guard_returned','two_complete_buffers_equal')
    require(type(report) is dict and set(report)=={'schema','binding',*guard_fields,'qualification',
        'source_proposal_pin','summary',*FLAGS} and report['schema']==SCHEMA+'-result'
        and canonical(report['binding'])==canonical(expected_binding)
        and all(report[key] is True for key in guard_fields) and all(report[key] is False for key in FLAGS)
        and report['qualification']=='fresh_endpoint_buffers_only_not_formal_source_or_continuous_integrity_or_QC_acceptance'
        and valid_pin(report['source_proposal_pin'],MAX_PROPOSAL) and report['source_proposal_pin']['byte_count']>0
        and valid_pin(value['report_pin'],MAX_OUTPUT) and value['report_pin']==pin(canonical(report)),'output')
    summary=report['summary']
    require(type(summary) is dict and set(summary)=={'actual_plain_package_sha256','parent_proof_sha256',
        'source_inventory_pin','parent_source_vector_pin','actual_activation','object_files','cells','current_attempt_state',*FLAGS}
        and all(summary[key] is False for key in FLAGS)
        and summary['actual_plain_package_sha256']=='1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
        and summary['parent_proof_sha256']=='95405d1b569d4bfeeb6c6d87fdb430f2fd27b8b7a31d6dcde7f82276d9903cd1'
        and all(valid_pin(summary[key],MAX_OUTPUT) and summary[key]['byte_count']>0
            for key in ('source_inventory_pin','parent_source_vector_pin')),'output')
    current=summary['current_attempt_state']
    require(type(current) is dict and set(current)=={'R343-AR100','other_candidates','new_candidate_created','attempt_budget_reset'}
        and current['new_candidate_created'] is current['attempt_budget_reset'] is False
        and canonical(current['R343-AR100'])==canonical({'candidate_id':'R343-AR100','attempts_consumed':3,
            'maximum_attempts':3,'status':'exhausted_requires_Mia_checkpoint_and_separate_continuation',
            'project_id':39054561,'compile_id':None,'backtest_id':None,'attempt_reset':False,'A4_permitted':False})
        and canonical(current['other_candidates'])==canonical([
            {'candidate_id':f'R343-AR{percent:03d}','attempts_consumed':0,'status':'uninvoked_no_submission_authority'}
            for percent in (80,120,140,160,180,200)]),'output')
    objects=summary['object_files']
    require(type(objects) is list and len(objects)==6,'output')
    for name,row in zip(OBJECT_NAMES,objects,strict=True):
        require(type(row) is dict and set(row)=={'relative_path','byte_count','sha256'} and row['relative_path']==name
            and valid_pin({key:row[key] for key in ('byte_count','sha256')},32*1024*1024) and row['byte_count']>0,'output')
    require(sum(row['byte_count'] for row in objects)<=MAX_PRIVATE
        and objects[-1]['byte_count']==5901
        and objects[-1]['sha256']=='ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b','output')
    activation={'schema':'arv2-newrule-plain-upload-object-v1','role':'activation_manifest','ordinal':0,
        'object_store_key':'arv2/newrule-plain-v1/'+summary['parent_proof_sha256'][:24]+'/transport-manifest.json',
        'relative_path':'transport-manifest.json','byte_count':5901,
        'content_sha256':'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b',
        'record_count':1,'compression':'identity','activation_manifest':True}
    require(canonical(summary['actual_activation'])==canonical(activation),'output')
    cells=summary['cells'];bridge_flags={'operational_authority','fresh_private_input_authenticated','new_storage_admitted',
        'qc_source_policy_acceptance_proven','attempt_budget_reset','backtest_completed','point_in_time_proven',
        'formal_identity_admitted','formal_forward_ready','paper_or_live_ready'}
    cell_keys={'schema','candidate_id','ar_percent','prepared_only','parent_vector_pin','unchanged_profile_pin',
        'ancestral_source_package_sha256','source_lineage_sha256','actual_plain_package_sha256','actual_activation',
        'parent_proof_sha256','changed_files','unchanged_files','input_exports_used','source_mapping','actual_loader_source_pin',
        'selected_loader_source_pin','source_files','result_contract',*bridge_flags}
    require(type(cells) is list and len(cells)==7,'output')
    for percent,cell in zip((80,100,120,140,160,180,200),cells,strict=True):
        require(type(cell) is dict and set(cell)==cell_keys and cell['schema']=='arv2-r345-legacy-six-plain-buffer-bridge-v1'
            and cell['candidate_id']==f'R343-AR{percent:03d}' and type(cell['ar_percent']) is int and cell['ar_percent']==percent
            and cell['prepared_only'] is True and all(cell[key] is False for key in bridge_flags)
            and cell['parent_vector_pin']==summary['parent_source_vector_pin']
            and cell['actual_plain_package_sha256']==summary['actual_plain_package_sha256']
            and cell['parent_proof_sha256']==summary['parent_proof_sha256']
            and canonical(cell['actual_activation'])==canonical({key:activation[key] for key in ('object_store_key','content_sha256','byte_count')})
            and valid_pin(cell['unchanged_profile_pin'],MAX_OUTPUT)
            and type(cell['source_files']) is list and len(cell['source_files'])==18,'output')
        names=[]
        for row in cell['source_files']:
            require(type(row) is dict and set(row)=={'project_path','byte_count','sha256'}
                and type(row['project_path']) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_]*[.]py',row['project_path'])
                and valid_pin({key:row[key] for key in ('byte_count','sha256')},64000) and row['byte_count']>0,'output')
            names.append(row['project_path'])
        require(names==sorted(set(names)) and {'main.py','accepted_risk_order_level_input_runtime.py','legacy_six_october_reporting.py'}<=set(names)
            and sum(row['byte_count'] for row in cell['source_files'])+32768<=448*1024,'output')
        emitted=next(row for row in cell['source_files'] if row['project_path']=='accepted_risk_order_level_input_runtime.py')
        require(cell['ancestral_source_package_sha256']=='411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
            and cell['source_lineage_sha256']=='e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
            and cell['changed_files']==['accepted_risk_order_level_input_runtime.py','main.py']
            and cell['unchanged_files']==[name for name in names if name not in cell['changed_files']]
            and cell['input_exports_used']==['collection_rows','load_accepted_risk_preliminary_package']
            and cell['source_mapping']=={'accepted_risk_order_level_input_runtime.py':'newrule_plain_input_runtime.py'}
            and cell['result_contract']=='new_actual_plain_transport_META_plus_unchanged_ancestral_profile'
            and canonical(cell['selected_loader_source_pin'])==canonical(ADDITIONAL_PINS[LOADER_PATH])
            and canonical(cell['actual_loader_source_pin'])==canonical({key:emitted[key] for key in ('byte_count','sha256')}),'output')
    return {'original_stdout_validated':True,'report':report,'report_pin':value['report_pin'],
        'qualification':'original_output_and_observed_exit_only_not_independent_private_file_authentication'}


class Parser(argparse.ArgumentParser):
    def error(self,message):raise Refused('arguments')


def main():
    parser=Parser(add_help=False);parser.add_argument('mode',choices=('profile','prepare'))
    for name in ('expected-head','caller-sha256','plan-sha256'):parser.add_argument('--'+name)
    args=parser.parse_args()
    if args.mode=='profile':
        require(all(getattr(args,key) is None for key in ('expected_head','caller_sha256','plan_sha256')),'arguments')
        return profile_record()
    def expired(*_):raise Deadline()
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,SECONDS)
    return run(args)


if __name__=='__main__':
    try:
        raw=canonical(main())+b'\n';require(len(raw)<=MAX_OUTPUT,'output');sys.stdout.buffer.write(raw)
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'schema':SCHEMA+'-failure','stage':STAGE,'claim_state':CLAIM_STATE,
            'failure_code':finite(error),'dependency_failure':DEPENDENCY_FAILURE,**FLAGS})+b'\n')
        raise SystemExit(2)
