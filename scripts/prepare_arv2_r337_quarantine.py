"""One fresh offline exact-five catalog and vendor-archive preparation.

The original five bindings become a fixed private denial catalog. All source
bytes remain unchanged; no price, resolved identity or launch is admitted.
"""
import argparse
import csv
from contextlib import ExitStack
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
import importlib
from importlib.machinery import PathFinder
import io
import json
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
SOURCE=ROOT/'scripts/prepare_arv2_r337_quarantine.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/quarantine/R337-20261103-A'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r337-offline-quarantine-materialization-v1'
DATA_PLAN={'semantics': {'relative_path': 'artifacts/analyst_revisions_v2/identity_recovery/R336-20261103-N/private-diagnosis.json', 'byte_count': 294888, 'sha256': 'fd52e0d4177bf5c6b74dd0f1b6e8616ca03a9c8fb60ae5d9c57f584f075de86e'}, 'archive': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_available_history_archive/R327-20261028-K/vendor-payload-private.bin', 'byte_count': 148543046, 'sha256': '2a2815b543c41728b441b0b300a9d269f282778ef1915923fd68f61993f9ca1f'}}
SOURCE_PINS={'research/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'research/analyst_revisions_v2_qc/__init__.py': 'ce8f07aeab0358f5eb3241190169d4f967a5423dc88719f0783a83d010d43dcc', 'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30', 'scripts/arv2_r337_quarantine_data_guard.py': 'b0c5b464c268cd1cec7c4f656afc779bf847c8bc2cba006f0c42464a76a10ac4', 'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_policy.py': '77280e4963c38e9197da81f3b02b920d91d5e727380b1323bfa9e54a715a8ac0', 'research/analyst_revisions_v2_qc/newrule_common_price_format.py': 'd254b3e3a6a52445e4422f03885ec58a3d2b30e8ce902cb80ed8f841c374f873', 'scripts/arv2_r337_quarantine_preparation.py': 'e41136a3927564f3b5691f7d2a9272b8bc71ff810c19582c8ecbe35074a5fd6e'}
SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,131072,2*1024*1024
WORKER_SECONDS=240
PURE_PROFILE_PIN={'byte_count': 2903, 'sha256': 'aa32502370e68fc33ac9ec14589bc401f8d9efa05f82a3c1126172ff15365d6b'}
CHILD_OBSERVATION=None
DEADLINE_FIRED=False
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE='preflight',None
STAGES=frozenset(('preflight','retained_DATA','preparation','output'))
GUARD_MODULE=PURE_MODULE=None
GUARD_CODES=frozenset(('byte_pin', 'close', 'deadline', 'metadata', 'named_changed', 'path_open', 'plan', 'read_spent', 'receipt', 'scope', 'security', 'security_changed', 'shape', 'state'))
PURE_CODES=frozenset(('input_pin','json','shape','case_binding','catalog','header','range','range_hash','vendor_format','assignment','period','quarantine','bound','output','deadline','unknown'))

FALSE_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'generic_prose_disclosed': False, 'instrument_rows_disclosed': False, 'security_identifiers_disclosed': False, 'aliases_admitted': False, 'identity_admitted': False, 'permanent_security_continuity_proven': False, 'terminal_payoff_applied': False, 'price_input_admitted': False, 'price_coverage_proven': False, 'original_source_catalog_rewritten': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'full_original_catalog_freshly_reauthenticated': False, 'full_current_catalog_freshly_authenticated': False, 'strategy_action_invoked': False}
FINITE=frozenset(('arguments','bound','changed','child_failure','child_stderr','claim_spent','control','deadline','environment','git_state','host','input','output','path','scope','shape','source_changed','source_pin','unknown'))|frozenset('guard_'+v for v in GUARD_CODES if v!='deadline')|frozenset('pure_'+v for v in PURE_CODES if v!='deadline')


class Refused(ValueError):
    """Closed local predicate; never retain private source text in errors."""

class RunDeadline(BaseException):
    """Timer control flow outside ordinary JSON, data and transport errors."""

def deadline_expired(*_):
    global DEADLINE_FIRED
    DEADLINE_FIRED=True
    raise RunDeadline()

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
    if DEADLINE_FIRED or isinstance(error,(RunDeadline,TimeoutError,subprocess.TimeoutExpired)):
        return 'deadline'
    for module,prefix,codes in ((GUARD_MODULE,'guard_',GUARD_CODES),(PURE_MODULE,'pure_',PURE_CODES)):
        if module is not None and type(error) is module.Refused:
            value=module.finite(error);return 'deadline' if value=='deadline' else prefix+value if value in codes else 'unknown'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    return 'deadline' if isinstance(error,TimeoutError) else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'stage': FAILURE_STAGE, 'case_ordinal': FAILURE_CASE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE,'child_observation':CHILD_OBSERVATION,
        'deadline_fired':DEADLINE_FIRED, **FALSE_FLAGS}

def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'attempt_reusable', 'claim_state','child_observation','deadline_fired', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
        and type(value['deadline_fired']) is bool and (not value['deadline_fired'] or value['failure_code']=='deadline')
        and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
        and value['stage'] in STAGES and (value['case_ordinal'] is None or
            type(value['case_ordinal']) is int and 0 <= value['case_ordinal'] < 5)
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    if value['child_observation'] is not None:validate_observation(value['child_observation'])
    return value


def validate_observation(value):
    require(type(value) is dict and set(value)=={'actual_child_exit','child_stdout_pin','child_stderr_byte_count','child_stderr_sha256','failure_code'}
        and (value['actual_child_exit'] is None or type(value['actual_child_exit']) is int)
        and type(value['child_stderr_byte_count']) is int and 0<=value['child_stderr_byte_count']<=16384
        and type(value['child_stderr_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['child_stderr_sha256'])
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE),'output')
    item=value['child_stdout_pin'];require(type(item) is dict and set(item)=={'byte_count','sha256'}
        and type(item['byte_count']) is int and 0<=item['byte_count']<=MAX_OUTPUT
        and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']),'output')
    return value

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

    USB ExFAT metadata is a separate readonly transport scope. It makes no
    native ACL/xattr or historical continuity claim about the external disk.
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
                and (before[6] > 0 or (before[6] == 0 and self.path == ROOT/'research/__init__.py'))
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
    return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'pure_profile_pin':PURE_PROFILE_PIN,
        'purpose':'new_exact_five_quarantine_catalog_and_retained_vendor_archive_preparation_not_price_admission',
        'maximum_seconds':SECONDS,'maximum_worker_seconds':WORKER_SECONDS,'validator_seconds':30,'own_reap_seconds':5,
        'deadline_taxonomy':'dedicated_BaseException_timer_builtin_and_git_timeouts_canonical_deadline_timer_fact_survives_cleanup_refusal',
        'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,
        'claim':'exclusive_claim_fsync_and_owned_marker_before_any_retained_DATA_read',
        'normal_return':'all_current_full_metadata_security_byte_and_named_source_checks_before_any_catalog_private_report_write',
        'native_worker_policy_sha256':sha(native_profile().encode('utf8')),
        'public':'finite_source_counts_and_hashes_no_security_IDs_or_licensed_rows',
        'read_scope':'exact_N_and_retained_AR73_archive_only_no_old_controls_or_producers',
        'consumer_identity':'fixed_original_denial_catalog_not_resolved_identities_or_original_strategy_gate_clearance',
        'QC_gate':'project_independent_preparation_no_project_source_rights_or_launch_freeze_created',
        'deadline_limitation':'startup_host_suspension_and_uninterruptible_IO_not_bounded',**FALSE_FLAGS}



def binding(args):
    require(all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', getattr(args, key))
        for key, length in (('expected_head', 40), ('caller_sha256', 64), ('profile_sha256', 64))), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}

def safe_env():
    support = ROOT / '.pytest_cache/r337-runtime'
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

def bootstrap(role,stack,deadline):
    """Compile exact held selected public bytes; source and pyc paths are fixed."""
    global GUARD_MODULE,PURE_MODULE
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    require(role in ('worker','validate'),'arguments');raw_by_path={}
    for relative,expected in SOURCE_PINS.items():
        require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected),'source_pin')
        held=stack.enter_context(HeldFile(ROOT/relative,maximum=131072,deadline=deadline))
        raw=held.read();require(sha(raw)==expected,'source_pin');raw_by_path[relative]=raw
    sys.path[:]=[str(ROOT),*(v for v in sys.path if v and Path(v).is_absolute() and Path(v)!=ROOT and ROOT not in Path(v).parents)]
    for name,path,init in (('scripts',ROOT/'scripts',None),('research',ROOT/'research','research/__init__.py'),
            ('research.analyst_revisions_v2_qc',ROOT/'research/analyst_revisions_v2_qc','research/analyst_revisions_v2_qc/__init__.py')):
        search=[str(path.parent)] if '.' not in name else [str(ROOT/'research')]
        spec=PathFinder.find_spec(name,search)
        require(spec is not None and tuple(spec.submodule_search_locations)==(str(path),)
            and (spec.origin is None if init is None else spec.origin==str(ROOT/init)),'source_pin')
        if name=='scripts' and name in sys.modules:
            package=sys.modules[name]
            require(getattr(package,'__file__',None) is None and tuple(package.__path__)==(str(path),),'source_pin')
            continue
        require(name not in sys.modules,'source_pin');package=ModuleType(name);package.__package__=name;package.__path__=[str(path)]
        package.__spec__=spec
        if init is not None:package.__file__=str(ROOT/init)
        sys.modules[name]=package
        if '.' in name:setattr(sys.modules[name.rsplit('.',1)[0]],name.rsplit('.',1)[1],package)
        if init is not None:exec(compile(raw_by_path[init],str(ROOT/init),'exec'),package.__dict__)
    modules={}
    for relative in ('scripts/arv2_relocation_security.py',
            'research/analyst_revisions_v2_qc/newrule_five_case_quarantine_policy.py',
            'research/analyst_revisions_v2_qc/newrule_common_price_format.py',
            'scripts/arv2_r337_quarantine_data_guard.py','scripts/arv2_r337_quarantine_preparation.py'):
        full=relative[:-3].replace('/','.');name=full.rsplit('.',1)[-1];parent=full.rsplit('.',1)[0];path=ROOT/relative
        spec=PathFinder.find_spec(full,sys.modules[parent].__path__)
        require(spec is not None and spec.origin==str(path) and full not in sys.modules,'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__=parent
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(sys.modules[parent],name,module)
        exec(compile(raw_by_path[relative],str(path),'exec'),module.__dict__);modules[name]=module
    PURE_MODULE=modules['arv2_r337_quarantine_preparation'];GUARD_MODULE=modules['arv2_r337_quarantine_data_guard']
    require(PURE_MODULE.FINITE==PURE_CODES and pin(canonical(PURE_MODULE.profile_record()))==PURE_PROFILE_PIN
        and GUARD_MODULE.FINITE==GUARD_CODES and GUARD_MODULE.DATA_PLAN==DATA_PLAN,'source_pin')
    require(not any(n=='AlgorithmImports' or n=='assistant.dispatch_fence' or n.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298')) for n in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'pure':PURE_MODULE,'guard':GUARD_MODULE}

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
        require(name in ('claim.json', 'worker-started.json', 'private-diagnosis.json', 'quarantine-catalog-private.json', 'report.json', 'failure.json')
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

def worker(args,deadline):
    global FAILURE_STAGE
    require(type(args.intent_fd) is int and args.intent_fd>=3,'arguments')
    try:intent=os.read(args.intent_fd,4097)
    finally:os.close(args.intent_fd)
    require(intent==canonical(binding(args)),'arguments');preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('worker',sources,deadline)
        with Store(modules['security']) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
            marker_pin=store.write('worker-started.json',canonical({'binding':binding(args),'phase':'quarantine_preparation'}))
            FAILURE_STAGE='retained_DATA'
            with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as data:
                raw=data.read_all_once();FAILURE_STAGE='preparation'
                summary,catalog,private=modules['pure'].prepare(raw['semantics'],raw['archive'],deadline=deadline)
                data.verify();receipt=data.receipt();budget(deadline)
            sources.close();FAILURE_STAGE='output'
            catalog_pin=store.write('quarantine-catalog-private.json',canonical(catalog))
            require(catalog_pin==summary['quarantine_catalog_pin'],'output')
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'output')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'summary':summary,'private_pin':private_pin,
                'catalog_pin':catalog_pin,'both_DATA_authenticated':True,'source_guard_normal_return':True,
                'worker_marker_pin':marker_pin,'source_receipt_sha256':sha(canonical(receipt)),**FALSE_FLAGS}
            validate_result(result,args);preflight(args,deadline)
            report={'binding':binding(args),'result':result};report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}



def validate_result(value,args):
    require(type(value) is dict and set(value)=={'schema','complete','summary','private_pin','catalog_pin','both_DATA_authenticated',
        'source_guard_normal_return','worker_marker_pin','source_receipt_sha256',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['complete'] is True
        and value['both_DATA_authenticated'] is value['source_guard_normal_return'] is True
        and value['worker_marker_pin']==pin(canonical({'binding':binding(args),'phase':'quarantine_preparation'}))
        and type(value['source_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256'])
        and all(value[k] is False for k in FALSE_FLAGS),'output')
    require(PURE_MODULE is not None,'source_pin');PURE_MODULE.validate_summary(value['summary'])
    for key in ('private_pin','catalog_pin'):
        row=value[key];require(type(row) is dict and set(row)=={'byte_count','sha256'} and type(row['byte_count']) is int
            and 0<row['byte_count']<=MAX_PRIVATE and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),'output')
    require(value['catalog_pin']==value['summary']['quarantine_catalog_pin'],'output');return value



def native_profile():
    value='(version 1)(allow default)(deny network*)(deny file-read* file-write* (subpath "/Volumes"))'
    value+=''.join('(deny file-read* file-write* (subpath "'+path+'"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (subpath "'+str(CONTROL)+'"))'
    value+='(require-not (literal "'+str(CONTROL.parent)+'"))(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
    paths=[*(ROOT/item['relative_path'] for item in DATA_PLAN.values()),CONTROL]
    allowed={path for leaf in paths for path in (*leaf.parents,leaf) if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
    value+='(require-not (subpath "'+str(CONTROL)+'"))'
    value+=''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed))+'))'
    return value

def parent(args):
    preflight(args, ENTRY_DEADLINE)
    with ExitStack() as sources:
        bootstrap('validate',sources,ENTRY_DEADLINE)
        return _parent_bound(args)

def _parent_bound(args):
    global CHILD_OBSERVATION,CLAIM_STATE
    CHILD_OBSERVATION=None;preflight(args,ENTRY_DEADLINE)
    reader,writer=os.pipe()
    try:
        intent=canonical(binding(args));require(len(intent)<4096 and os.write(writer,intent)==len(intent),'bound')
    finally:os.close(writer)
    stop=min(ENTRY_DEADLINE,time.monotonic()+WORKER_SECONDS)
    command=['/usr/bin/sandbox-exec','-p',native_profile(),PYTHON,'-I','-B',str(SOURCE),'worker',
        '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
        '--intent-fd',str(reader),'--outer-deadline',repr(stop)]
    CLAIM_STATE='consumed_or_unknown'
    try:actual,raw,stderr_count,stderr_sha,problem=run_child(command,(reader,),stop)
    finally:os.close(reader)
    observed={'actual_child_exit':actual,'child_stdout_pin':pin(raw),'child_stderr_byte_count':stderr_count,
        'child_stderr_sha256':stderr_sha,'failure_code':problem}
    CHILD_OBSERVATION=observed
    require(problem is None,problem if problem in FINITE else 'child_failure')
    require(type(actual) is int and actual in (0,2) and stderr_count==0 and stderr_sha==sha(b'')
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'child_failure')
    value=parse(raw[:-1],MAX_OUTPUT);require(canonical(value)+b'\n'==raw,'output')
    if actual==0:validate_envelope(raw,actual,args);key='outcome'
    else:validate_failure(value,args);key='failure'
    return {'binding':binding(args),'observation':observed,'output_authenticated':True,key:value}

def validate_envelope(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit == 0 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'child_failure')
    value = parse(raw[:-1], MAX_OUTPUT); require(canonical(value) + b'\n' == raw and type(value) is dict
        and set(value) == {'binding', 'result', 'report_pin'} and value['binding'] == binding(args), 'output')
    validate_result(value['result'],args)
    require(value['report_pin'] == pin(canonical({'binding': binding(args), 'result': value['result']})), 'output')
    return value

def validate_parent_output(raw,actual_exit,args):
    require(type(actual_exit) is int and actual_exit in (0,2) and type(raw) is bytes
        and raw.endswith(b'\n') and raw.count(b'\n')==1,'output')
    value=parse(raw[:-1],MAX_OUTPUT);require(canonical(value)+b'\n'==raw and type(value) is dict,'output')
    if value.get('schema')==SCHEMA:
        require(actual_exit==2,'output');validate_failure(value,args)
        return {'binding':binding(args),'output_authenticated':True,'accepted':False,'failure':value}
    key='outcome' if actual_exit==0 else 'failure'
    require(set(value)=={'binding','observation','output_authenticated',key} and value['binding']==binding(args)
        and value['output_authenticated'] is True,'output')
    observed=validate_observation(value['observation'])
    require(type(observed['actual_child_exit']) is int and observed['actual_child_exit']==actual_exit
        and observed['child_stderr_byte_count']==0 and observed['child_stderr_sha256']==sha(b'')
        and observed['failure_code'] is None and observed['child_stdout_pin']==pin(canonical(value[key])+b'\n'),'output')
    if key=='failure':validate_failure(value[key],args)
    else:validate_envelope(canonical(value[key])+b'\n',actual_exit,args)
    return {'binding':binding(args),'output_authenticated':True,'accepted':actual_exit==0,
        **({'result':value[key]['result']} if actual_exit==0 else {'failure':value[key]})}

def run_child(command,descriptors,deadline):
    output=bytearray();stderr=hashlib.sha256();count=0;child=None;problem=None
    try:
        child=subprocess.Popen(command,cwd=ROOT,env=safe_env(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,close_fds=True,pass_fds=descriptors)
        with selectors.DefaultSelector() as selector:
            for stream,label in ((child.stdout,'out'),(child.stderr,'err')):
                os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,label)
            while selector.get_map() or child.poll() is None:
                for key,_ in selector.select(min(.1,budget(deadline))):
                    chunk=os.read(key.fileobj.fileno(),8192)
                    if not chunk:selector.unregister(key.fileobj)
                    elif key.data=='out':require(len(output)+len(chunk)<=MAX_OUTPUT,'bound');output.extend(chunk)
                    else:count+=len(chunk);stderr.update(chunk);require(count<=8192,'child_stderr')
        child.wait(timeout=min(5,budget(deadline)))
    except BaseException as error:problem=finite(error)
    finally:
        if child is not None:
            if child.poll() is None:child.kill()
            child.wait(timeout=5);child.stdout.close();child.stderr.close()
    return (None if child is None else child.returncode),bytes(output),count,stderr.hexdigest(),problem

class Parser(argparse.ArgumentParser):
    def error(self, message): raise Refused('arguments')

def main():
    global ACTIVE_BINDING
    parser = Parser(add_help=False)
    parser.add_argument('mode', choices=('launch', 'worker', 'validate', 'profile'))
    for name in ('expected-head', 'caller-sha256', 'profile-sha256'): parser.add_argument('--' + name)
    parser.add_argument('--intent-fd', type=int); parser.add_argument('--outer-deadline', type=float)
    parser.add_argument('--actual-parent-exit', type=int)
    args = parser.parse_args()
    if args.mode == 'profile':
        require(all(getattr(args, key) is None for key in ('expected_head', 'caller_sha256', 'profile_sha256',
            'intent_fd', 'outer_deadline', 'actual_parent_exit')), 'arguments')
        return profile_record()
    ACTIVE_BINDING = binding(args)
    if args.mode == 'launch':
        require(args.intent_fd is args.outer_deadline is args.actual_parent_exit is None, 'arguments')
        signal.signal(signal.SIGALRM,deadline_expired);signal.setitimer(signal.ITIMER_REAL,budget(ENTRY_DEADLINE))
        return parent(args)
    if args.mode == 'validate':
        require(args.intent_fd is args.outer_deadline is None and type(args.actual_parent_exit) is int
            and args.actual_parent_exit in (0, 2), 'arguments')
        signal.signal(signal.SIGALRM, deadline_expired); signal.setitimer(signal.ITIMER_REAL, 30)
        preflight(args, ENTRY_DEADLINE)
        with ExitStack() as sources:
            bootstrap('validate',sources,ENTRY_DEADLINE)
            return validate_parent_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_parent_exit, args)
    require(args.outer_deadline is not None and args.actual_parent_exit is None, 'arguments')
    deadline = min(ENTRY_DEADLINE, args.outer_deadline); budget(deadline)
    signal.signal(signal.SIGALRM, deadline_expired); signal.setitimer(signal.ITIMER_REAL, budget(deadline))
    return worker(args, deadline)

if __name__ == '__main__':
    try:
        value = main(); raw = canonical(value) + b'\n'; require(len(raw) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(raw); raise SystemExit(2 if type(value) is dict and 'failure' in value else 0)
    except SystemExit: raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure_packet(finite(error))) + b'\n')
        raise SystemExit(2)
