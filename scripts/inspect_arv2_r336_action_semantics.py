"""One fresh offline semantics enrichment of exact retained events/ownership/dictionary DATA.

Explicit evidence-bound normative rules classify discovery roles; every market
row stays private and no alias, price, cash payoff or source choice is admitted.
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
SOURCE=ROOT/'scripts/inspect_arv2_r336_action_semantics.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/identity_recovery/R336-20261103-N'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r336-offline-action-semantics-observation-v1'
DATA_PLAN={'events': {'relative_path': 'artifacts/analyst_revisions_v2/firstrate/R335-20261103-I/private-diagnosis.json', 'byte_count': 126797, 'sha256': 'abf7c0b602757a6c915e1d7d452ad5ff88901f7c619b33aaee638ead6c7bbb7d'}, 'ownership': {'relative_path': 'artifacts/analyst_revisions_v2/identity_recovery/R336-20261103-M/private-diagnosis.json', 'byte_count': 71708, 'sha256': 'ed177bf0b7b8ec5683d3bda27ef69c82b72ef97b57efa8e3db5605effde4044a'}, 'dictionary': {'relative_path': 'artifacts/analyst_revisions_v2/firstrate/R335-20261103-J/response-00.csv', 'byte_count': 50967, 'sha256': 'ad3acf93fedbdf7f4bd3af47ca7347beca615358a1736382360ba048ebfb415f'}}
SOURCE_PINS={'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30', 'scripts/arv2_r298_fixed_data_guard.py': '00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145', 'scripts/arv2_r336_original_identity_ownership.py': 'e0e829c662c5dbc7c1a1e95f720db0e87e0725f3f3d428b3b785d991b55bef5b', 'scripts/arv2_r336_action_semantics.py': 'd95bfb69b9383306bbee8c83ac34d8c22fb8e9ed9cd33500c886742b8c652bbe'}
SECONDS,MAX_OUTPUT,MAX_PRIVATE=150,131072,2*1024*1024
WORKER_SECONDS=90
PURE_PROFILE_PIN={'byte_count':5562,'sha256':'752b75a4f750c2c1c85c437c22bb22061735a65d77b2f53cce2de162f9bdf7cd'}
CHILD_OBSERVATION=None
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE='preflight',None
STAGES=frozenset(('preflight','retained_DATA','semantics','output'))
GUARD_MODULE=PURE_MODULE=None
GUARD_CODES=frozenset(('byte_pin', 'close', 'deadline', 'metadata', 'named_changed', 'path_open', 'plan', 'read_spent', 'receipt', 'scope', 'security', 'security_changed', 'shape', 'state'))
PURE_CODES=frozenset(('input_pin','input','dictionary','case_binding','original_proof','demand','events','links','rule','pairs','output','deadline','unknown'))

FALSE_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'generic_prose_disclosed': False, 'instrument_rows_disclosed': False, 'security_identifiers_disclosed': False, 'aliases_admitted': False, 'identity_admitted': False, 'permanent_security_continuity_proven': False, 'terminal_payoff_applied': False, 'price_input_admitted': False, 'price_coverage_proven': False, 'source_assignment_changed': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'full_original_catalog_freshly_reauthenticated': False, 'full_current_catalog_freshly_authenticated': False, 'strategy_action_invoked': False}
FINITE=frozenset(('arguments','bound','changed','child_failure','child_stderr','claim_spent','control','deadline','environment','git_state','host','input','output','path','scope','shape','source_changed','source_pin','unknown'))|frozenset('guard_'+v for v in GUARD_CODES)|frozenset('pure_'+v for v in PURE_CODES)


class Refused(ValueError):
    """Closed local predicate; never retain private source text in errors."""

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
    for module,prefix,codes in ((GUARD_MODULE,'guard_',GUARD_CODES),(PURE_MODULE,'pure_',PURE_CODES)):
        if module is not None and type(error) is module.Refused:
            value=module.finite(error);return prefix+value if value in codes else 'unknown'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    return 'deadline' if isinstance(error,TimeoutError) else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'stage': FAILURE_STAGE, 'case_ordinal': FAILURE_CASE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE,'child_observation':CHILD_OBSERVATION, **FALSE_FLAGS}

def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'attempt_reusable', 'claim_state','child_observation', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
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
    return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'pure_profile_pin':PURE_PROFILE_PIN,
        'purpose':'apply_manually_reviewed_evidence_bound_generic_code_rules_to_all_33_retained_events_and_original_ownership',
        'public':'five_case_count_class_and_predicate_matrices_only_no_instrument_or_generic_prose',
        'private':'retain_all_original_events_ownership_links_and_rule_row_pins_no_alias_or_price_admission',
        'maximum_seconds':SECONDS,'maximum_worker_seconds':WORKER_SECONDS,'validator_seconds':30,'own_reap_seconds':5,
        'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,
        'claim':'native_worker_exclusive_claim_fsync_and_owned_worker_marker_before_any_DATA_read',
        'authentication':'exact_three_retained_DATA_current_held_named_metadata_security_and_bytes_guard_normal_return_before_publication',
        'source_execution':'compile_exact_held_selected_repo_source_no_repo_pyc_not_whole_interpreter_integrity',
        'native_worker_policy_sha256':sha(native_profile().encode('utf8')),
        'prior_results':'I_J_and_M_passed_once_retained_DATA_consumption_only_no_used_producer_reader_or_control_replay',
        'validator':'once_stdin_only_actual_parent_exit_and_child_stdout_pin_plus_exact_host_clean_HEAD_caller_profile',
        'deadline_limitation':'uninterruptible_IO_host_suspension_startup_and_own5s_reap_qualification',**FALSE_FLAGS}



def binding(args):
    require(all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', getattr(args, key))
        for key, length in (('expected_head', 40), ('caller_sha256', 64), ('profile_sha256', 64))), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}

def safe_env():
    support = ROOT / '.pytest_cache/r336-runtime'
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
    """Compile exact held selected source bytes; never execute repo pyc caches."""
    global GUARD_MODULE,PURE_MODULE
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    require(role in ('worker','validate'),'arguments')
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
    chosen=['arv2_relocation_security','arv2_r336_original_identity_ownership','arv2_r336_action_semantics']
    if role=='worker':chosen.append('arv2_r298_fixed_data_guard')
    modules={}
    for name in chosen:
        full='scripts.'+name;relative='scripts/'+name+'.py';path=ROOT/relative
        spec=PathFinder.find_spec(full,[str(ROOT/'scripts')])
        require(spec is not None and spec.origin==str(path) and full not in sys.modules,'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__='scripts'
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(package,name,module)
        exec(compile(raw_by_name[name],str(path),'exec'),module.__dict__);modules[name]=module
    PURE_MODULE=modules['arv2_r336_action_semantics'];require(PURE_MODULE.FINITE==PURE_CODES and pin(canonical(PURE_MODULE.profile_record()))==PURE_PROFILE_PIN,'source_pin')
    if role=='worker':
        GUARD_MODULE=modules['arv2_r298_fixed_data_guard'];require(GUARD_MODULE.FINITE==GUARD_CODES,'source_pin')
    require(not any(name=='AlgorithmImports' or name.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298'))
        for name in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'pure':PURE_MODULE,
        **({'guard':GUARD_MODULE} if role=='worker' else {})}

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
        require(name in ('claim.json', 'worker-started.json', 'private-diagnosis.json', 'report.json', 'failure.json')
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
            marker={'binding':binding(args),'phase':'semantics'}
            marker_pin=store.write('worker-started.json',canonical(marker));FAILURE_STAGE='retained_DATA'
            with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as data:
                raw=data.read_all_once()
                i_value=parse(raw['events'],DATA_PLAN['events']['byte_count'])
                m_value=parse(raw['ownership'],DATA_PLAN['ownership']['byte_count'])
                require(canonical(i_value)==raw['events'] and canonical(m_value)==raw['ownership'],'input')
                FAILURE_STAGE='semantics'
                summary,private=modules['pure'].analyze(i_value,m_value,raw['dictionary'],deadline=deadline)
                data.verify();receipt=data.receipt();budget(deadline)
            sources.close();FAILURE_STAGE='output'
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'output')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'summary':summary,'private_pin':private_pin,
                'all_three_DATA_authenticated':True,'source_guard_normal_return':True,'worker_marker_pin':marker_pin,
                'source_receipt_sha256':sha(canonical(receipt)),**FALSE_FLAGS}
            validate_result(result,args);preflight(args,deadline)
            report={'binding':binding(args),'result':result};report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}



def validate_result(value,args):
    require(type(value) is dict and set(value)=={'schema','complete','summary','private_pin','all_three_DATA_authenticated',
        'source_guard_normal_return','worker_marker_pin','source_receipt_sha256',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['complete'] is True
        and value['all_three_DATA_authenticated'] is value['source_guard_normal_return'] is True
        and value['worker_marker_pin']==pin(canonical({'binding':binding(args),'phase':'semantics'}))
        and type(value['source_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256'])
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    require(PURE_MODULE is not None,'source_pin');PURE_MODULE.validate_summary(value['summary'])
    item=value['private_pin'];require(type(item) is dict and set(item)=={'byte_count','sha256'} and type(item['byte_count']) is int
        and 0<item['byte_count']<=MAX_PRIVATE and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']),'output')
    return value



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
        def parent_expired(*_): raise Refused('deadline')
        signal.signal(signal.SIGALRM,parent_expired);signal.setitimer(signal.ITIMER_REAL,budget(ENTRY_DEADLINE))
        return parent(args)
    if args.mode == 'validate':
        require(args.intent_fd is args.outer_deadline is None and type(args.actual_parent_exit) is int
            and args.actual_parent_exit in (0, 2), 'arguments')
        def validation_expired(*_): raise Refused('deadline')
        signal.signal(signal.SIGALRM, validation_expired); signal.setitimer(signal.ITIMER_REAL, 30)
        preflight(args, ENTRY_DEADLINE)
        with ExitStack() as sources:
            bootstrap('validate',sources,ENTRY_DEADLINE)
            return validate_parent_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_parent_exit, args)
    require(args.outer_deadline is not None and args.actual_parent_exit is None, 'arguments')
    deadline = min(ENTRY_DEADLINE, args.outer_deadline); budget(deadline)
    def expired(*_): raise Refused('deadline')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, budget(deadline))
    return worker(args, deadline)

if __name__ == '__main__':
    try:
        value = main(); raw = canonical(value) + b'\n'; require(len(raw) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(raw); raise SystemExit(2 if type(value) is dict and 'failure' in value else 0)
    except SystemExit: raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure_packet(finite(error))) + b'\n')
        raise SystemExit(2)
