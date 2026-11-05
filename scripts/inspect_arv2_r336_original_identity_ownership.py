"""Exclusive one-shot offline original-catalog ownership diagnostic.

No provider, USB, QC or Safari access; no binding correction or price admission.
Only four exact retained DATA leaves are read after a new exclusive claim.
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
SOURCE=ROOT/'scripts/inspect_arv2_r336_original_identity_ownership.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/identity_recovery/R336-20261103-M'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r336-original-identity-ownership-observation-v1'
DATA_PLAN={'manifest': {'relative_path': 'artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z/manifest.json', 'byte_count': 5998, 'sha256': '94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b'}, 'marker': {'relative_path': 'artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z/manifest.sha256', 'byte_count': 65, 'sha256': '1f57ad2bcf9aaff1fe9c9fdcff5a281043ad348c3bb596ce778f02ec34e0626f'}, 'archive': {'relative_path': 'artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z/01-tickers-years-full.zip', 'byte_count': 4937076, 'sha256': 'a7b129f159631ee50f1eefd2be8d4215c1c7818880570c0ad0a79c76c25e51bf'}, 'identity': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_available_history_identity/R327-20261027-I/identity-demand-private.json', 'byte_count': 4984462, 'sha256': 'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'}}
SOURCE_PINS={'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30', 'scripts/arv2_r298_fixed_data_guard.py': '00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145', 'scripts/arv2_r336_original_ticker_security.py': 'd2ca80e67b51e79df443a5d6dee192ce15632ddbb64cfe4045d7219cc42de5c2', 'scripts/arv2_r336_original_identity_ownership.py': 'e0e829c662c5dbc7c1a1e95f720db0e87e0725f3f3d428b3b785d991b55bef5b', 'scripts/arv2_r327_i_source_binding.py': '44405001183804020d8b211d79846d8ea70019758059cc73878cca883bac6416'}
SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,131072,16*1024*1024
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE='preflight',None
STAGES=frozenset(('preflight','retained_DATA','original_catalog','ownership','output'))
GUARD_MODULE=PURE_MODULE=ORIGINAL_GUARD_MODULE=None
GUARD_CODES=frozenset(('byte_pin', 'close', 'deadline', 'metadata', 'named_changed', 'path_open', 'plan', 'read_spent', 'receipt', 'scope', 'security', 'security_changed', 'shape', 'state'))
PURE_CODES=frozenset(('archive_pin', 'binding', 'cases', 'catalog_bound', 'csv', 'deadline', 'demand', 'header', 'input', 'manifest', 'member', 'original_proof', 'output', 'period', 'row', 'row_stream', 'unknown'))
ORIGINAL_GUARD_CODES=frozenset(('byte_pin', 'close', 'deadline', 'directory_policy', 'file_policy', 'leaf', 'metadata', 'metadata_changed', 'named_changed', 'path_open', 'read', 'read_spent', 'scope', 'security_changed', 'security_observation', 'state', 'xattr_names', 'xattr_values'))
FALSE_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'original_identifiers_rewritten': False, 'alias_created': False, 'global_collision_cleared': False, 'original_wrong_instrument_proven': False, 'later_mapping_drift_proven': False, 'historical_identity_proven': False, 'point_in_time_proven': False, 'price_input_admitted': False, 'price_coverage_proven': False, 'source_assignment_changed': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'current_full_catalog_freshly_authenticated': False, 'historical_metadata_preservation_proven': False, 'licensed_rows_disclosed': False}
FINITE=frozenset(('arguments','bound','changed','child_failure','child_stderr','claim_spent','control','deadline','environment','git_state','host','input','output','path','scope','shape','source_changed','source_pin','unknown'))|frozenset('guard_'+v for v in GUARD_CODES)|frozenset('pure_'+v for v in PURE_CODES)|frozenset('original_guard_'+v for v in ORIGINAL_GUARD_CODES)


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
    for module,prefix,codes in ((GUARD_MODULE,'guard_',GUARD_CODES),(PURE_MODULE,'pure_',PURE_CODES),
          (ORIGINAL_GUARD_MODULE,'original_guard_',ORIGINAL_GUARD_CODES)):
        if module is not None and type(error) is module.Refused:
            value=module.finite(error);return prefix+value if value in codes else 'unknown'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    return 'deadline' if isinstance(error,TimeoutError) else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'stage': FAILURE_STAGE, 'case_ordinal': FAILURE_CASE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE, **FALSE_FLAGS}

def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'attempt_reusable', 'claim_state', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
        and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
        and value['stage'] in STAGES and (value['case_ordinal'] is None or
            type(value['case_ordinal']) is int and 0 <= value['case_ordinal'] < 5)
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
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
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'maximum_seconds':SECONDS,'maximum_output_bytes':MAX_OUTPUT,
        'maximum_private_bytes':MAX_PRIVATE,'purpose':'original_five_binding_cross_table_ownership_diagnosis',
        'all_four_DATA_bytes_authenticated_before_parse':True,'original_full_catalog_rows':74150,'original_full_fields':28,
        'original_security_policy':'current_held_named_all_metadata_native_ACL_and_exact_vintage_directory_xattrs_not_old_device_ctime_projection',
        'source_guard_normal_return_before_publication':True,'original_SF1_hash_reconstruction_required':True,
        'physical_rows_and_table_scopes_retained_separately':True,'matching':'exact_perma_FIGI_complete_CUSIPs_poison_refusal_only',
        'current_scope':'six_retained_candidates_not_fresh_full_current_catalog','no_best_name_or_ticker_alias_choice':True,
        'validator':'once_stdin_only_actual_exit_plus_host_clean_HEAD_source_profile_binding',
        'deadline_limitation':'parent_alarm_after_CLI_binding_through_preflight_bootstrap_dispatch_capture_and_publication_except_uninterruptible_IO_host_suspension_and_own_child_5second_reap',**FALSE_FLAGS}



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
    global GUARD_MODULE,PURE_MODULE,ORIGINAL_GUARD_MODULE
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
    chosen=['arv2_relocation_security','arv2_r336_original_identity_ownership']
    if role=='worker':chosen.extend(('arv2_r298_fixed_data_guard','arv2_r336_original_ticker_security','arv2_r327_i_source_binding'))
    modules={}
    for name in chosen:
        full='scripts.'+name;relative='scripts/'+name+'.py';path=ROOT/relative
        spec=PathFinder.find_spec(full,[str(ROOT/'scripts')])
        require(spec is not None and spec.origin==str(path) and full not in sys.modules,'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__='scripts'
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(package,name,module)
        exec(compile(raw_by_name[name],str(path),'exec'),module.__dict__);modules[name]=module
    PURE_MODULE=modules['arv2_r336_original_identity_ownership'];require(PURE_MODULE.FINITE==PURE_CODES,'source_pin')
    if role=='worker':
        GUARD_MODULE=modules['arv2_r298_fixed_data_guard'];ORIGINAL_GUARD_MODULE=modules['arv2_r336_original_ticker_security']
        require(GUARD_MODULE.FINITE==GUARD_CODES and ORIGINAL_GUARD_MODULE.FINITE==ORIGINAL_GUARD_CODES,'source_pin')
    require(not any(name=='AlgorithmImports' or name.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298'))
        for name in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'pure':PURE_MODULE,
        **({'guard':GUARD_MODULE,'original_guard':ORIGINAL_GUARD_MODULE,'anchor':modules['arv2_r327_i_source_binding']} if role=='worker' else {})}

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
        require(name in ('claim.json', 'private-diagnosis.json', 'report.json', 'failure.json')
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
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}));FAILURE_STAGE='retained_DATA'
            with modules['original_guard'].SourceGuard(deadline=deadline) as original_guard:
                original_raw=[original_guard.read(name,deadline) for name in modules['original_guard'].LEAVES]
                for role,raw in zip(('manifest','marker','archive'),original_raw,strict=True):
                    require(pin(raw)=={key:DATA_PLAN[role][key] for key in ('byte_count','sha256')},'input')
                with modules['guard'].FixedDataGuard({'identity':DATA_PLAN['identity']},deadline=deadline) as guarded:
                    raw=guarded.read_all_once();fact=modules['anchor'].observed_fact()
                    require(fact['private_data']==DATA_PLAN['identity'],'input')
                    identity=parse(raw['identity'],DATA_PLAN['identity']['byte_count'])
                    modules['pure'].demands(identity,fact['result']['identity_summary'])
                    FAILURE_STAGE='original_catalog';rows=modules['pure'].decode_catalog(*original_raw,deadline=deadline)
                    FAILURE_STAGE='ownership';inspection,private=modules['pure'].inspect(rows,identity,deadline=deadline)
                    require(inspection['original_catalog_row_count']==74150,'output')
                    original_guard.verify();guarded.verify();receipt=guarded.receipt();budget(deadline)
                original_guard.verify()
            sources.close();FAILURE_STAGE='output'
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'output')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'inspection':inspection,'private_pin':private_pin,
                'all_four_DATA_authenticated':True,'both_source_guards_normal_return':True,
                'source_receipt_sha256':sha(canonical(receipt)),**FALSE_FLAGS}
            validate_result(result);preflight(args,deadline)
            report={'binding':binding(args),'result':result};report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}



def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','complete','inspection','private_pin','all_four_DATA_authenticated',
        'both_source_guards_normal_return','source_receipt_sha256',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['complete'] is True
        and value['all_four_DATA_authenticated'] is value['both_source_guards_normal_return'] is True
        and type(value['source_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256'])
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    require(PURE_MODULE is not None,'source_pin');PURE_MODULE.validate_summary(value['inspection'])
    require(value['inspection']['original_catalog_row_count']==74150,'output')
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
    preflight(args, ENTRY_DEADLINE)
    reader, writer = os.pipe()
    try:
        raw = canonical(binding(args)); require(len(raw) < 4096 and os.write(writer, raw) == len(raw), 'bound')
    finally: os.close(writer)
    child, output, stderr_count = None, bytearray(), 0
    try:
        child = subprocess.Popen(['/usr/bin/sandbox-exec', '-p', native_profile(), PYTHON, '-I', '-B', str(SOURCE), 'worker',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
            '--profile-sha256', args.profile_sha256, '--intent-fd', str(reader), '--outer-deadline', repr(ENTRY_DEADLINE)],
            cwd=ROOT, env=safe_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, pass_fds=(reader,))
        with selectors.DefaultSelector() as selected:
            for stream, label in ((child.stdout, 'stdout'), (child.stderr, 'stderr')):
                os.set_blocking(stream.fileno(), False); selected.register(stream, selectors.EVENT_READ, label)
            while selected.get_map() or child.poll() is None:
                for key, _ in selected.select(min(.1, budget(ENTRY_DEADLINE))):
                    raw = os.read(key.fileobj.fileno(), 8192)
                    if not raw: selected.unregister(key.fileobj)
                    elif key.data == 'stderr': stderr_count += len(raw); raise Refused('child_stderr')
                    else:
                        require(len(output) + len(raw) <= MAX_OUTPUT, 'bound'); output.extend(raw)
        actual = child.wait(timeout=min(5, budget(ENTRY_DEADLINE)))
        require(type(actual) is int and actual in (0, 2) and bytes(output).endswith(b'\n')
            and bytes(output).count(b'\n') == 1, 'child_failure')
        if actual == 0:
            value = validate_envelope(bytes(output), actual, args); key = 'outcome'
        else:
            value = parse(bytes(output)[:-1], MAX_OUTPUT)
            require(canonical(value) + b'\n' == bytes(output), 'output')
            validate_failure(value, args); key = 'failure'
        return {'binding': binding(args), 'actual_child_exit': actual, 'output_authenticated': True,
            'child_stdout_pin': pin(bytes(output)), 'child_stderr_byte_count': stderr_count, key: value}
    finally:
        os.close(reader)
        if child is not None:
            if child.poll() is None: child.kill()
            child.wait(timeout=5)
            child.stdout.close(); child.stderr.close()

def validate_envelope(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit == 0 and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'child_failure')
    value = parse(raw[:-1], MAX_OUTPUT); require(canonical(value) + b'\n' == raw and type(value) is dict
        and set(value) == {'binding', 'result', 'report_pin'} and value['binding'] == binding(args), 'output')
    validate_result(value['result'])
    require(value['report_pin'] == pin(canonical({'binding': binding(args), 'result': value['result']})), 'output')
    return value

def validate_parent_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2), 'output')
    value = parse(raw, MAX_OUTPUT)
    require(canonical(value) + b'\n' == raw, 'output')
    key = 'outcome' if actual_exit == 0 else 'failure'
    require(type(value) is dict and set(value) == {'binding', 'actual_child_exit', 'output_authenticated',
        'child_stdout_pin', 'child_stderr_byte_count', key} and value['binding'] == binding(args)
        and value['actual_child_exit'] == actual_exit and type(value['actual_child_exit']) is int
        and value['output_authenticated'] is True and type(value['child_stderr_byte_count']) is int
        and value['child_stderr_byte_count'] == 0, 'output')
    child_raw = canonical(value[key]) + b'\n'
    require(pin(child_raw) == value['child_stdout_pin'], 'output')
    if key == 'failure':
        validate_failure(value[key], args)
        return {'binding': binding(args), 'output_authenticated': True, 'accepted': False,
            'actual_child_exit': value['actual_child_exit'], 'failure': value[key]}
    validate_envelope(child_raw, value['actual_child_exit'], args)
    return {'binding': binding(args), 'output_authenticated': True, 'result': value['outcome']['result']}

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
