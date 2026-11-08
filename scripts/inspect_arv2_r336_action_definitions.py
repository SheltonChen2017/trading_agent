"""One new offline generic documentation review packet from exact retained I/J DATA.

Outputs only actiontypes indicator/title/definition text and generic definition
provenance. Instrument rows, event frequencies/ordinals/case links and all
security identifiers remain private. No interpretation, aliases or admission.
"""
import argparse
from contextlib import ExitStack
import hashlib
from importlib.machinery import PathFinder,ModuleSpec
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
from types import ModuleType

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE=ROOT/'scripts/inspect_arv2_r336_action_definitions.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R336-20261103-K'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r336-offline-generic-action-definitions-v1'
SOURCE_PINS={
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_r298_fixed_data_guard.py':'00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145',
 'scripts/arv2_r335_action_types.py':'22c7d74679a44b33316a2b5facc1f678e73f131aaa443d6805ed1380885f9974',
}
DATA_PLAN={
 'events':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-I/private-diagnosis.json','byte_count':126797,
  'sha256':'abf7c0b602757a6c915e1d7d452ad5ff88901f7c619b33aaee638ead6c7bbb7d'},
 'dictionary':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-J/response-00.csv','byte_count':50967,
  'sha256':'ad3acf93fedbdf7f4bd3af47ca7347beca615358a1736382360ba048ebfb415f'},
 'transport':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-J/transport-00.json','byte_count':336,
  'sha256':'a2aa22f2b22275f4972594b4dc2661569df2786844bd298b47070278db9c4dc2'},
}
I_PROVENANCE={'clean_head':'108fce4e0cea38e45fb1587095be1ce6e699f148','caller_sha256':'49fcfc0ef268097e752786c188cd77cf2b8c44c833d53d2a055b8ad98c7b8968',
 'actual_parent_exit':0,'actual_child_exit':0,'actual_validator_exit':0,'row_count':33,'whole_original_identity_freshly_reauthenticated':False}
J_PROVENANCE={'clean_head':'26dfac6ec8948c8cf8dedfe1ebeca3687058159e','actual_parent_exit':0,'actual_child_exit':0,'actual_validator_exit':0,
 'dictionary_row_count':75,'capture_receipt_sha256':'592ba194651bf86e7e85aeffdc586edeba02c9f44521b38e6f5c382a5a819d45',
 'plan_sha256':'51ba55c0ec99b69bba99f099983684e7036ec413246f9f65f3f7835dbfce45b9'}
SECONDS,WORKER_SECONDS,MAX_OUTPUT,MAX_PRIVATE=150,90,131072,131072
MAX_PACKET,MAX_FIELD,MAX_WORKER_STDERR=65536,16384,8192
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
STAGE='preflight'
CHILD_OBSERVATION=None
GUARD=DICTIONARY=None
I_FALSE_FLAGS={'provider_contact': False, 'credential_access': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'old_control_read': False, 'old_operation_replayed': False, 'H_DATA_read': False, 'G_attempt_accepted': False, 'G_request_plan_completed': False, 'v2_producer_invoked': False, 'remaining_G_query_authority_granted': False, 'source_choice_changed': False, 'rows_dropped_or_normalized': False, 'new_aliases_generated': False, 'corporate_action_semantics_applied': False, 'identity_admitted': False, 'historical_ticker_continuity_proven': False, 'terminal_payoff_proven': False, 'synthetic_cash_created': False, 'price_acquired': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False, 'historical_or_continuous_integrity_proven': False, 'full_original_inventory_freshly_authenticated': False, 'price_coverage_proven': False, 'known_native_gap_resolved': False, 'actual_holdings_path_proven': False}
GUARD_CODES=frozenset(('scope','plan','deadline','state','shape','path_open','metadata','named_changed','security','security_changed','read_spent','byte_pin','close','receipt'))
DICTIONARY_CODES=frozenset(('plan','credential','session','deadline','journal','event','prepared_identity','request_failed','http_status_unavailable',
 'http_status','response_identity','response_headers','response_encoding','response_bound','response_stream','response_close','credential_echo',
 'retention','aggregate_bound','changed','csv','header','row_cap','row_scope','receipt','private','unknown'))
FALSE_FLAGS={name:False for name in ('provider_contact','credential_access','QC_contact','Safari_access','USB_read','old_control_read',
 'old_operation_replayed','instrument_rows_disclosed','instrument_associations_disclosed','event_frequencies_disclosed',
 'security_identifiers_disclosed','definitions_interpreted','aliases_generated','identity_admitted','terminal_payoff_proven',
 'price_input_admitted','source_assignment_changed','source_or_processing_rights_granted','point_in_time_proven',
 'formal_forward_ready','paper_or_live_ready','whole_original_identity_freshly_reauthenticated')}
FINITE=frozenset(('arguments','host','environment','git_state','source_pin','source_changed','scope','deadline','bound','input',
 'claim_spent','control','path','shape','metadata','changed','worker_claim','worker_marker','worker_output','worker_failure',
 'worker_stderr','output','events','transport','dictionary','definitions','unknown'))|frozenset('guard_'+x for x in GUARD_CODES)|frozenset('dictionary_'+x for x in DICTIONARY_CODES)

class Refused(ValueError):pass


def finite(error):
    if GUARD is not None and type(error) is GUARD.Refused:return 'guard_'+GUARD.finite(error)
    if DICTIONARY is not None and type(error) is DICTIONARY.Refused:return 'dictionary_'+DICTIONARY.finite(error)
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'deadline' if isinstance(error,TimeoutError) else 'unknown'

def require(value, code):
    if not value:
        raise Refused(code)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}

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
    require(phase=='review','worker_marker');name=phase+'-started.json'
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

def bootstrap(role,stack,deadline):
    """Compile exact held selected source bytes; never execute repo pyc caches."""
    global GUARD,DICTIONARY
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    require(role in ('parent','worker','validate'),'arguments')
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
    chosen=['arv2_relocation_security','arv2_r298_fixed_data_guard','arv2_r335_action_types']
    modules={}
    for name in chosen:
        full='scripts.'+name;relative='scripts/'+name+'.py';path=ROOT/relative
        spec=PathFinder.find_spec(full,[str(ROOT/'scripts')])
        require(spec is not None and spec.origin==str(path) and full not in sys.modules,'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__='scripts'
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(package,name,module)
        exec(compile(raw_by_name[name],str(path),'exec'),module.__dict__)
        modules[name]=module
    DICTIONARY=modules['arv2_r335_action_types'];GUARD=modules['arv2_r298_fixed_data_guard']
    require(DICTIONARY.FINITE==DICTIONARY_CODES and GUARD.FINITE==GUARD_CODES,'source_pin')
    require(not any(name=='AlgorithmImports' or name.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298'))
        for name in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'dictionary':DICTIONARY,'guard':GUARD}


def allowed_name(name):
    return type(name) is str and name in ('claim.json','review-intent.json','worker-observation.json','report.json')


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':BRANCH,'python':PYTHON,'control':str(CONTROL),
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'I_provenance':I_PROVENANCE,'J_provenance':J_PROVENANCE,
        'maximum_seconds':SECONDS,'worker_seconds':WORKER_SECONDS,'reader_seconds':30,'reap_seconds':5,
        'definition_count_limit':33,'definition_field_character_limit':MAX_FIELD,'generic_packet_bytes_limit':MAX_PACKET,
        'worker_native_policy_sha256':sha(native_profile().encode('utf8')),
        'purpose':'generic_normative_schema_documentation_for_exact_observed_action_codes_no_instrument_associations',
        'matches':'exact_code_strings_only_all_matching_dictionary_rows_preserved_no_heuristics_or_default_interpretation',
        'publication':'guard_normal_return_and_worker_actual0_before_parent_report_external_parent0_required',
        'source_authentication':'selected_repo_bytes_compiled_from_held_pins_no_repo_pyc_not_whole_interpreter_integrity',
        'provenance_scope':'retained_I_and_J_current_DATA_authentication_not_fresh_original_security_or_history_admission',
        'deadline_limitation':'uninterruptible_IO_host_suspension_and_own5s_reap_qualification',**FALSE_FLAGS}


def inspect_definitions(event_raw,dictionary_raw,transport_raw,dictionary):
    """Pure private-input reduction; only generic documentation is returned."""
    for role,raw in (('events',event_raw),('dictionary',dictionary_raw),('transport',transport_raw)):
        require(type(raw) is bytes and pin(raw)=={key:DATA_PLAN[role][key] for key in ('byte_count','sha256')},'source_pin')
    events=parse(event_raw,DATA_PLAN['events']['byte_count']);transport=parse(transport_raw,8192)
    require(canonical(events)==event_raw and type(events) is dict
        and set(events)=={'schema','input_DATA_pins','original_G_plan','projected_v2_plan','original_G_transport','all_original_rows',
            'cases','inspection','retained_H_observation',*I_FALSE_FLAGS}
        and events['schema']=='arv2-r335-offline-actions-metadata-links-v1-private'
        and all(events[key] is False for key in I_FALSE_FLAGS),'events')
    rows=events['all_original_rows'];require(type(rows) is list and len(rows)==33,'events')
    codes=set()
    for ordinal,event in enumerate(rows):
        require(type(event) is dict and set(event)=={'source_row_ordinal','row','action_family','primary_owner_case_ordinals',
            'shared_primary_ticker_ownership','literal_counterparty_metadata_lead','opaque_contraticker_verbatim','ticker_change_search_lead',
            'same_security_or_share_class_proven','alias_admitted','corporate_action_applied'}
            and type(event['source_row_ordinal']) is int and event['source_row_ordinal']==ordinal
            and event['same_security_or_share_class_proven'] is event['alias_admitted'] is event['corporate_action_applied'] is False
            and event['ticker_change_search_lead'] is None and type(event['row']) is dict
            and set(event['row'])=={'date','action','ticker','name','value','contraticker','contraname'},'events')
        code=event['row']['action'];require(type(code) is str and code and len(code)<=128 and code.isascii()
            and code.strip()==code and all(ord(c)>=32 and ord(c)!=127 for c in code),'events');codes.add(code)
    require(0<len(codes)<=33,'events')
    require(canonical(transport)==transport_raw and type(transport) is dict
        and set(transport)=={'schema','plan_sha256','request_ordinal','role','http_status','body_pin','CSV_validation_complete'}
        and transport['schema']==dictionary.SCHEMA+'-private-transport' and transport['plan_sha256']==J_PROVENANCE['plan_sha256']
        and transport['plan_sha256']==sha(canonical(dictionary.plan_record()))
        and type(transport['request_ordinal']) is int and transport['request_ordinal']==0 and transport['role']=='actiontypes'
        and type(transport['http_status']) is int and transport['http_status']==200
        and transport['body_pin']==pin(dictionary_raw) and transport['CSV_validation_complete'] is False,'transport')
    captured={'schema':dictionary.SCHEMA+'-capture','plan_sha256':transport['plan_sha256'],'application_dispatch_attempts':1,
        'provider_request_count':None,'http_status':200,'response_pin':pin(dictionary_raw),'CSV_validation_complete':False,**dictionary.FALSE_FLAGS}
    dictionary.validate_capture_receipt(captured,dictionary.plan_record())
    require(sha(canonical(captured))==J_PROVENANCE['capture_receipt_sha256'],'transport')
    original_rows,counts=dictionary._parse_dictionary(dictionary_raw)
    require(counts['row_count']==75 and counts['empty_indicator_count']==0
        and counts['empty_description_count']==0,'dictionary')
    by_code={code:[] for code in sorted(codes)}
    for ordinal,original in enumerate(original_rows):
        logical={dictionary.VARIANTS[key]:value for key,value in original.items()}
        if logical['indicator'] in by_code:
            item={'dictionary_row_ordinal':ordinal,'indicator':logical['indicator'],'title':logical['title'],
                'definition':logical['description'],'full_generic_row_pin':pin(canonical(original))}
            by_code[logical['indicator']].append(item)
    result={'schema':SCHEMA+'-documentation','generic_documentation_only':True,'dictionary_DATA_pin':dict(DATA_PLAN['dictionary']),
        'requested_code_count':len(codes),'dictionary_row_count':75,'matched_code_count':sum(bool(items) for items in by_code.values()),
        'missing_code_count':sum(not items for items in by_code.values()),'matched_definition_row_count':sum(map(len,by_code.values())),
        'repeated_indicator_row_count':sum(max(0,len(items)-1) for items in by_code.values()),
        'conflicting_definition_code_count':sum(len({item['full_generic_row_pin']['sha256'] for item in items})>1 for items in by_code.values()),
        # An unmatched action string has no dictionary provenance and remains
        # private. Only its aggregate missing-code count crosses this boundary.
        'definitions':{code:items for code,items in by_code.items() if items},**FALSE_FLAGS}
    validate_documentation(result);return result


def validate_documentation(value):
    require(type(value) is dict and set(value)=={'schema','generic_documentation_only','dictionary_DATA_pin','requested_code_count',
        'dictionary_row_count','matched_code_count','missing_code_count','matched_definition_row_count','repeated_indicator_row_count',
        'conflicting_definition_code_count','definitions',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-documentation' and value['generic_documentation_only'] is True
        and value['dictionary_DATA_pin']==DATA_PLAN['dictionary'] and value['dictionary_row_count']==75
        and all(value[key] is False for key in FALSE_FLAGS)
        and all(type(value[key]) is int for key in ('requested_code_count','dictionary_row_count','matched_code_count','missing_code_count',
            'matched_definition_row_count','repeated_indicator_row_count','conflicting_definition_code_count'))
        and 1<=value['requested_code_count']<=33 and type(value['definitions']) is dict
        and len(value['definitions'])<=value['requested_code_count'],'output')
    total=0;ordinals=[]
    for code,items in value['definitions'].items():
        require(type(code) is str and 0<len(code)<=128 and code.isascii() and code.strip()==code
            and all(ord(c)>=32 and ord(c)!=127 for c in code) and type(items) is list and 0<len(items)<=75,'output')
        for item in items:
            require(type(item) is dict and set(item)=={'dictionary_row_ordinal','indicator','title','definition','full_generic_row_pin'}
                and type(item['dictionary_row_ordinal']) is int and 0<=item['dictionary_row_ordinal']<75
                and item['indicator']==code and all(type(item[key]) is str and len(item[key])<=MAX_FIELD for key in ('title','definition')),'output')
            checked_pin(item['full_generic_row_pin'],MAX_OUTPUT)
            ordinals.append(item['dictionary_row_ordinal']);total+=1
    require(total<=33 and len(set(ordinals))==len(ordinals)
        and value['matched_code_count']==sum(bool(items) for items in value['definitions'].values())
        and value['missing_code_count']==value['requested_code_count']-value['matched_code_count']
        and value['matched_code_count']+value['missing_code_count']==value['requested_code_count']
        and value['matched_definition_row_count']==total and value['repeated_indicator_row_count']==total-value['matched_code_count']
        and value['conflicting_definition_code_count']==sum(len({item['full_generic_row_pin']['sha256'] for item in items})>1 for items in value['definitions'].values())
        and len(canonical(value))<=MAX_PACKET,'output')
    return value


def native_profile():
    value='(version 1)(allow default)(deny network*)(deny file-read* file-write* (subpath "/Volumes"))'
    value+=''.join('(deny file-read* file-write* (subpath "'+path+'"))' for path in ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (literal "'+str(CONTROL/'review-started.json')+'"))'
    value+='(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
    leaves=[ROOT/row['relative_path'] for row in DATA_PLAN.values()]
    leaves.extend(CONTROL/name for name in ('claim.json','review-intent.json','review-started.json'))
    allowed={path for leaf in leaves for path in (*leaf.parents,leaf) if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
    return value+''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed))+'))'


def failure_packet(code):
    return {'schema':SCHEMA+'-failure','binding':ACTIVE_BINDING,'failure_code':code,'stage':STAGE,
        'claim_state':CLAIM_STATE,'attempt_reusable':False,'child_observation':CHILD_OBSERVATION,**FALSE_FLAGS}


def validate_failure(value,args):
    require(type(value) is dict and set(value)=={'schema','binding','failure_code','stage','claim_state','attempt_reusable','child_observation',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-failure' and value['binding']==binding(args)
        and type(value['failure_code']) is str and value['failure_code'] in FINITE
        and value['stage'] in ('preflight','claim','retained_DATA','documentation','publication')
        and value['claim_state'] in ('unallocated','allocated_unknown','consumed_or_unknown','consumed')
        and value['attempt_reusable'] is False and all(value[name] is False for name in FALSE_FLAGS),'output')
    if value['child_observation'] is not None:validate_observation(value['child_observation'])
    return value


def worker(args,deadline):
    global STAGE,CLAIM_STATE
    preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('worker',sources,deadline);security=modules['security']
        require(type(args.control_fd) is int and args.control_fd>=3,'worker_claim')
        info=meta(os.fstat(args.control_fd))
        require(stat.S_ISDIR(info[2]) and info[3]==os.getuid() and stat.S_IMODE(info[2])==0o700
            and info==meta(os.stat(CONTROL,follow_symlinks=False)),'worker_claim')
        claim=_regular_fd(args.claim_fd,'claim.json',args.control_fd,MAX_OUTPUT,security)
        require(claim==canonical({'binding':binding(args),'profile':profile_record()}),'worker_claim')
        intent=_regular_fd(args.intent_fd,'review-intent.json',args.control_fd,8192,security)
        require(intent==canonical({'binding':binding(args),'phase':'review','claim_pin':pin(claim)}),'worker_claim')
        CLAIM_STATE='consumed';STAGE='claim'
        marker=canonical({'binding':binding(args),'phase':'review','intent_pin':pin(intent)})
        fd=os.open('review-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=args.control_fd)
        try:require(os.write(fd,marker)==len(marker),'worker_marker');os.fsync(fd);os.fsync(args.control_fd)
        finally:os.close(fd)
        STAGE='retained_DATA'
        with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as data:
            raw=data.read_all_once();STAGE='documentation'
            documentation=inspect_definitions(raw['events'],raw['dictionary'],raw['transport'],modules['dictionary'])
            data.verify();receipt=data.receipt()
        require(_regular_fd(args.claim_fd,'claim.json',args.control_fd,MAX_OUTPUT,security)==claim
            and _regular_fd(args.intent_fd,'review-intent.json',args.control_fd,8192,security)==intent,'changed')
        sources.close()
        return {'schema':SCHEMA+'-worker','binding':binding(args),'documentation':documentation,
            'guard_receipt':receipt,'guard_normal_return':True,**FALSE_FLAGS}


def validate_worker(value,args,guard):
    require(type(value) is dict and set(value)=={'schema','binding','documentation','guard_receipt','guard_normal_return',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-worker' and value['binding']==binding(args) and value['guard_normal_return'] is True
        and all(value[name] is False for name in FALSE_FLAGS),'output')
    validate_documentation(value['documentation']);guard.validate_receipt(value['guard_receipt'],DATA_PLAN);return value


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
                    else:count+=len(chunk);stderr.update(chunk);require(count<=MAX_WORKER_STDERR,'worker_stderr')
        child.wait(timeout=min(5,budget(deadline)))
    except BaseException as error:problem=finite(error)
    finally:
        if child is not None:
            if child.poll() is None:child.kill()
            child.wait(timeout=5);child.stdout.close();child.stderr.close()
    return (None if child is None else child.returncode),bytes(output),count,stderr.hexdigest(),problem


def parent(args,deadline):
    global STAGE,CHILD_OBSERVATION
    CHILD_OBSERVATION=None
    preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('parent',sources,deadline)
        with Store(modules['security']) as store:
            STAGE='claim';claim=canonical({'binding':binding(args),'profile':profile_record()});store.write('claim.json',claim)
            intent=canonical({'binding':binding(args),'phase':'review','claim_pin':pin(claim)});store.write('review-intent.json',intent)
            descriptors=(store.fd,_held_fd(store,'claim.json'),_held_fd(store,'review-intent.json'))
            command=['/usr/bin/sandbox-exec','-p',native_profile(),PYTHON,'-I','-B',str(SOURCE),'worker',
                '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
                '--control-fd',str(descriptors[0]),'--claim-fd',str(descriptors[1]),'--intent-fd',str(descriptors[2]),
                '--outer-deadline',repr(min(deadline,time.monotonic()+WORKER_SECONDS))]
            actual,raw,stderr_count,stderr_sha,problem=run_child(command,descriptors,min(deadline,time.monotonic()+WORKER_SECONDS))
            observed={'actual_child_exit':actual,'child_stdout_pin':pin(raw),'child_stderr_byte_count':stderr_count,
                'child_stderr_sha256':stderr_sha,'failure_code':problem,
                'marker_authenticated':False}
            CHILD_OBSERVATION=observed
            try:
                marker=adopt_marker(store,'review')
                observed['marker_authenticated']=marker==canonical({'binding':binding(args),'phase':'review','intent_pin':pin(intent)})
            except BaseException as error:
                if observed['failure_code'] is None:observed['failure_code']=finite(error)
                raise
            store.write('worker-observation.json',canonical(observed))
            require(problem is None,problem if problem in FINITE else 'worker_failure')
            require(type(actual) is int and actual in (0,2) and stderr_count==0 and stderr_sha==sha(b'')
                and raw.endswith(b'\n') and raw.count(b'\n')==1,'worker_output')
            packet=parse(raw[:-1],MAX_OUTPUT);require(canonical(packet)+b'\n'==raw,'worker_output')
            if actual==0:validate_worker(packet,args,modules['guard']);require(observed['marker_authenticated'] is True,'worker_marker')
            else:validate_failure(packet,args)
            STAGE='publication'
            report={'binding':binding(args),'observation':observed,'worker_packet':packet,'accepted':actual==0}
            report_pin=store.write('report.json',canonical(report))
            return {**report,'report_pin':report_pin}


def validate_output(raw,actual,args,guard):
    require(type(actual) is int and actual in (0,2) and type(raw) is bytes and raw.endswith(b'\n') and raw.count(b'\n')==1,'output')
    packet=parse(raw[:-1],MAX_OUTPUT);require(canonical(packet)+b'\n'==raw and type(packet) is dict,'output')
    if packet.get('schema')==SCHEMA+'-failure':
        require(actual==2,'output');validate_failure(packet,args)
        return {'binding':binding(args),'output_authenticated':True,'accepted':False,'failure':packet}
    require(set(packet)=={'binding','observation','worker_packet','accepted','report_pin'} and packet['binding']==binding(args)
        and type(packet['accepted']) is bool and actual==(0 if packet['accepted'] else 2)
        and packet['report_pin']==pin(canonical({key:value for key,value in packet.items() if key!='report_pin'})),'output')
    observed=packet['observation']
    validate_observation(observed)
    require(type(observed['actual_child_exit']) is int and observed['actual_child_exit']==actual
        and type(observed['child_stderr_byte_count']) is int and observed['child_stderr_byte_count']==0
        and observed['child_stderr_sha256']==sha(b'') and type(observed['marker_authenticated']) is bool
        and observed['failure_code'] is None
        and observed['child_stdout_pin']==pin(canonical(packet['worker_packet'])+b'\n'),'output')
    if actual==0:validate_worker(packet['worker_packet'],args,guard);require(observed['marker_authenticated'] is True,'output')
    else:validate_failure(packet['worker_packet'],args)
    return {'binding':binding(args),'output_authenticated':True,'accepted':packet['accepted'],'report_pin':packet['report_pin'],
        **({'documentation':packet['worker_packet']['documentation']} if actual==0 else {'failure':packet['worker_packet']})}


def validate_observation(value):
    require(type(value) is dict and set(value)=={'actual_child_exit','child_stdout_pin','child_stderr_byte_count',
        'child_stderr_sha256','marker_authenticated','failure_code'}
        and (value['actual_child_exit'] is None or type(value['actual_child_exit']) is int)
        and type(value['child_stderr_byte_count']) is int and 0<=value['child_stderr_byte_count']<=MAX_WORKER_STDERR+8192
        and type(value['child_stderr_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['child_stderr_sha256'])
        and type(value['marker_authenticated']) is bool
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE),'output')
    checked_pin(value['child_stdout_pin'],MAX_OUTPUT,empty=True);return value


class Parser(argparse.ArgumentParser):
    def error(self,message):raise Refused('arguments')


def main():
    global ACTIVE_BINDING
    parser=Parser(add_help=False);parser.add_argument('mode',choices=('launch','worker','validate','profile'))
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name)
    for name in ('control-fd','claim-fd','intent-fd','actual-parent-exit'):parser.add_argument('--'+name,type=int)
    parser.add_argument('--outer-deadline',type=float);args=parser.parse_args()
    if args.mode=='profile':
        require(all(getattr(args,key) is None for key in ('expected_head','caller_sha256','profile_sha256',
            'control_fd','claim_fd','intent_fd','actual_parent_exit','outer_deadline')),'arguments');return profile_record()
    ACTIVE_BINDING=binding(args);deadline=ENTRY_DEADLINE
    if args.mode=='worker':
        require(args.actual_parent_exit is None and type(args.outer_deadline) in (int,float) and math.isfinite(args.outer_deadline),'arguments')
        deadline=min(deadline,args.outer_deadline);budget(deadline)
    else:require(args.control_fd is args.claim_fd is args.intent_fd is args.outer_deadline is None,'arguments')
    def expired(*args):raise Refused('deadline')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,min(30,budget(deadline)) if args.mode=='validate' else budget(deadline))
    if args.mode=='launch':require(args.actual_parent_exit is None,'arguments');return parent(args,deadline)
    if args.mode=='worker':return worker(args,deadline)
    require(type(args.actual_parent_exit) is int and args.actual_parent_exit in (0,2),'arguments');preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('validate',sources,deadline)
        return validate_output(sys.stdin.buffer.read(MAX_OUTPUT+1),args.actual_parent_exit,args,modules['guard'])


if __name__=='__main__':
    try:
        value=main();raw=canonical(value)+b'\n';require(len(raw)<=MAX_OUTPUT,'bound');sys.stdout.buffer.write(raw)
        raise SystemExit(2 if 'failure' in value or value.get('accepted') is False else 0)
    except SystemExit:raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical(failure_packet(finite(error)))+b'\n');raise SystemExit(2)
