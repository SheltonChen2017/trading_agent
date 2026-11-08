"""One current-vintage ACTIONS discovery after two native-denied F-only guards.

The parent claims and fsyncs before source, Keychain or network. Source workers
have no credential/network/USB access and consume only one fixed retained DATA
leaf. Successful HTTP bodies and finite events survive later refusal. No old
caller, source claim, price acquisition, QC or strategy run is invoked.
"""
import argparse
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
SOURCE=ROOT/'scripts/run_arv2_r335_sharadar_actions.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R335-20261103-G'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r335-sharadar-actions-diagnostic-v1'
F_SCHEMA='arv2-r335-offline-firstrate-gap-metadata-v1-private'
DATA_PLAN={'metadata':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-F/private-diagnosis.json',
 'byte_count':87170,'sha256':'0e41dca1d48955f83bcd5dcb2ae6192d85d9cf9f9ff40593bceeb0b5a601ccab'}}
I_DATA_PIN={'byte_count':4984462,'sha256':'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'}
F_OBSERVATION={'clean_head':'eb3a3d3ad3c6bc48ba0add1ce330584c01bc583a','actual_parent_exit':0,'actual_child_exit':0,'actual_validator_exit':0,
 'caller_pin':{'byte_count':58937,'sha256':'fd41a4d434503edc15d71d25775b520e98728a0e0d2e455c5bc03c69dabbbfa0'},
 'profile_pin':{'byte_count':4683,'sha256':'be389b2f95163b85df17c263b37dd186203e890a7e1c60dc9efcb5b1fa53e735'},
 'report_pin':{'byte_count':5141,'sha256':'c87f59f8ff1c1eed330a6699c1c133d659734846f2fd7a38453db61d0da37f5d'},
 'private_DATA':DATA_PLAN['metadata']}
SOURCE_PINS={
 'scripts/arv2_r298_fixed_data_guard.py':'00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145',
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_keychain_connections.py':'bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227',
 'scripts/inspect_arv2_r335_firstrate_gap_metadata.py':'fd41a4d434503edc15d71d25775b520e98728a0e0d2e455c5bc03c69dabbbfa0',
 'scripts/arv2_r335_sharadar_actions.py':'2d40d2c260a3fa2b484608df5ec43eaaad901848c345e1a60a215bf164c23d29',
}
SECONDS,WORKER_SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,60,131072,4*1024*1024
MAX_WORKER_OUTPUT,MAX_WORKER_STDERR,MAX_AGGREGATE=32768,8192,16*1024*1024
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
META_FIELDS=('table','ticker','permaticker','exchange','isdelisted','category','cusips','figi','currency','firstpricedate','lastpricedate','lastupdated')
EXPECTED_WHOLES=('f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986',
 'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8',
 'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7',
 '1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331',
 'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9')
GUARD_CODES=frozenset(('scope','plan','deadline','state','shape','path_open','metadata','named_changed','security','security_changed','read_spent','byte_pin','close','receipt'))
PROVIDER_CODES=frozenset(('plan','credential','session','deadline','journal','event','prepared_identity','request_failed',
 'http_status_unavailable','http_status','response_identity','response_headers','response_encoding','response_bound',
 'response_stream','response_close','credential_echo','retention','csv','row_cap','row_scope','row_date','row_value',
 'changed','receipt','private','aggregate_bound','unknown'))
FINITE=frozenset(('arguments','host','environment','git_state','source_pin','source_changed','scope','deadline','bound',
 'claim_spent','control','path','shape','metadata','changed','input','original_row','plan','worker_claim','worker_marker',
 'worker_output','worker_failure','worker_stderr','worker_deadline','credential','session','retention','output','unknown')) \
 |frozenset('guard_'+code for code in GUARD_CODES)|frozenset('provider_'+code for code in PROVIDER_CODES)
GUARD_MODULE=OBSERVER_MODULE=KEYCHAIN_MODULE=None
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
ENTRY_DEADLINE=time.monotonic()+SECONDS

F_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'native_book_read': False, 'exact_missing_QC_book_cells_recovered': False, 'genuine_full_package_freshly_authenticated': False, 'actual_target_or_holdings_path_proven': False, 'identity_admitted': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'known_native_gap_resolved': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False, 'historical_or_continuous_integrity_proven': False, 'price_archive_read': False, 'price_rows_read': False, 'metadata_alias_admitted': False, 'actions_evidence_supplied': False, 'relatedtickers_parsed': False}
FALSE_FLAGS={'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'old_control_read': False, 'old_operation_replayed': False, 'I_or_E_DATA_read': False, 'provider_request_count_measured': False, 'credential_persisted': False, 'licensed_rows_disclosed': False, 'new_aliases_generated': False, 'corporate_action_semantics_interpreted': False, 'identity_admitted': False, 'terminal_payoff_proven': False, 'price_acquired': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'strategy_run_invoked': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'historical_or_continuous_integrity_proven': False}


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
    if GUARD_MODULE is not None and type(error) is GUARD_MODULE.Refused:
        code=GUARD_MODULE.finite(error)
        return 'guard_'+code if code in GUARD_CODES else 'unknown'
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
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'retained_F_observation':F_OBSERVATION,
        'observer_profile_pin':{'byte_count':2563,'sha256':'cc17301092d8f799e297f522db17297fc50288caada88a255cfdc38e3e177930'},
        'source_worker_policy_sha256':sha(worker_native_profile('source').encode()),
        'reauth_worker_policy_sha256':sha(worker_native_profile('reauth').encode()),
        'maximum_seconds':SECONDS,'maximum_worker_seconds':WORKER_SECONDS,'maximum_worker_output_bytes':MAX_WORKER_OUTPUT,
        'maximum_worker_stderr_bytes':MAX_WORKER_STDERR,'maximum_output_bytes':MAX_OUTPUT,
        'maximum_response_bytes':MAX_PRIVATE,'maximum_aggregate_response_bytes':MAX_AGGREGATE,
        'purpose':'current_vintage_ACTIONS_discovery_for_original5_identity_leads_not_replacement_prices_or_strategy',
        'explicit_tokens':'sorted_unique_supported_binding_original_current_ticker_fields_only_max16_no_relatedtickers',
        'window':['2023-11-01','2026-10-13'],'endpoint':'https://api.sharadar.com/v1.0/data/actions',
        'request_plan':'one_documented_ticker_comma_union_GET_then_one_contraticker_GET_per_explicit_token_max17',
        'bounded_queries':'limit1000_require_less_than1000_rows_skip0_no_retry_pagination_or_alias_recursion',
        'credentials':'one_memory_only_login_Keychain_sharadar_lookup_max20s_no_environment_or_file_fallback',
        'workers':'two_separate_credential_USB_allnetwork_denied_F_only_guards_normal_return_before_contact_and_acceptance',
        'partial_evidence':'exclusive_fsynced_finite_events_and_complete_authenticated_HTTP200_CSV_before_parse_preserved_on_later_refusal',
        'status':'validated_numeric_status_journal_before_failed_body_refusal_no_failed_body_read',
        'actual_exit':'parent0_and_authenticated_success_output_required_nonzero_unknown_malformed_is_spent',
        'source_pins_scope':'selected_sources_not_whole_interpreter_or_arbitrary_same_user_sandbox',
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
    return type(name) is str and (name in ('claim.json','plan-private.json','source-intent.json','source-observed.json',
        'reauth-intent.json','reauth-observed.json','report.json','failure.json')
        or re.fullmatch(r'request-(?:0[0-9]|1[0-6])-(?:intent|status|terminal)\.json',name) is not None
        or re.fullmatch(r'(?:response-(?:0[0-9]|1[0-6])\.csv|transport-(?:0[0-9]|1[0-6])\.json)',name) is not None)


def bootstrap(role,stack,deadline):
    """Compile exact held selected source bytes; never execute repo pyc caches."""
    global GUARD_MODULE,OBSERVER_MODULE,KEYCHAIN_MODULE
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    require(role in ('parent','source','reauth','validate'),'arguments')
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
    if role in ('source','reauth'):chosen.append('arv2_r298_fixed_data_guard')
    chosen.append('arv2_r335_sharadar_actions')
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
    OBSERVER_MODULE=modules['arv2_r335_sharadar_actions']
    require(OBSERVER_MODULE.FINITE==PROVIDER_CODES
        and pin(canonical(OBSERVER_MODULE.profile_record()))=={'byte_count':2563,'sha256':'cc17301092d8f799e297f522db17297fc50288caada88a255cfdc38e3e177930'},'source_pin')
    if role=='parent':KEYCHAIN_MODULE=modules['arv2_keychain_connections']
    elif role in ('source','reauth'):
        GUARD_MODULE=modules['arv2_r298_fixed_data_guard'];require(GUARD_MODULE.FINITE==GUARD_CODES,'source_pin')
    require(not any(name=='AlgorithmImports' or name.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298'))
        for name in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'observer':OBSERVER_MODULE,
        **({'keychain':KEYCHAIN_MODULE} if role=='parent' else {'guard':GUARD_MODULE} if role in ('source','reauth') else {})}


def safe_runtime():
    allowed={'PATH','LANG','LC_ALL','TMPDIR','PYTHONPYCACHEPREFIX','PYTHONDONTWRITEBYTECODE',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD','GIT_OPTIONAL_LOCKS','__CF_USER_TEXT_ENCODING'}
    require(set(os.environ)<=allowed and sys.gettrace() is None and sys.getprofile() is None,'environment')
    require(http.client.HTTPConnection.debuglevel==0 and http.client.HTTPSConnection.debuglevel==0,'environment')
    root=logging.getLogger()
    require(not root.handlers and all(type(handler) is logging.NullHandler
        for name in ('requests','urllib3','http.client') for handler in logging.getLogger(name).handlers),'environment')


def derive_plan(value,observer):
    require(type(value) is dict and set(value)=={'schema','input_DATA_pins','retained_E_observation','cases',*F_FLAGS}
        and value['schema']==F_SCHEMA and all(value[key] is False for key in F_FLAGS)
        and type(value['cases']) is list and len(value['cases'])==5,'input')
    identity=value['input_DATA_pins'].get('identity') if type(value['input_DATA_pins']) is dict else None
    require(type(identity) is dict and {key:identity.get(key) for key in ('byte_count','sha256')}==I_DATA_PIN,'input')
    cases=sorted(value['cases'],key=lambda row:row['case_ordinal']);tokens=set();lineage=[]
    for ordinal,(row,whole) in enumerate(zip(cases,EXPECTED_WHOLES,strict=True)):
        require(type(row) is dict and set(row)=={'case_ordinal','whole_binding_sha256','binding','original_row','current_candidate_rows',
            'metadata_leads','optional_relatedtickers_raw','relatedtickers_parse_state','required_sessions','potential_reference_sessions',
            'candidates','no_candidate_gap','source_assignment_changed','original_metadata_hash_rechecked'}
            and type(row['case_ordinal']) is int and row['case_ordinal']==ordinal and row['whole_binding_sha256']==whole
            and row['source_assignment_changed'] is False and row['original_metadata_hash_rechecked'] is True,'input')
        binding=row['binding'];original=row['original_row'];current=row['current_candidate_rows']
        require(type(binding) is dict and sha(canonical(binding))==whole
            and type(binding.get('diagnostic_current_ticker')) is str
            and type(original) is dict and len(original)==28
            and all(type(key) is str and 0<len(key)<=128 and type(item) is str and len(item)<=8192 for key,item in original.items())
            and type(current) is list and len(current)<=4096,'original_row')
        raw=(json.dumps(original,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf8')
        require(len(raw)<=65536 and sha(raw)==binding.get('source_row_sha256'),'original_row')
        for item in current:
            require(type(item) is dict and set(item)==set(META_FIELDS)
                and all(type(text) is str and len(text)<=8192 for text in item.values()),'input')
        leads=[('binding.diagnostic_current_ticker',None,binding['diagnostic_current_ticker']),
            ('original_row.ticker',None,original.get('ticker'))]
        leads.extend(('current_candidate_rows.ticker',index,item['ticker']) for index,item in enumerate(current))
        require(type(row['metadata_leads']) is list and len(row['metadata_leads'])==len(leads),'input')
        source_leads=[]
        for retained,(origin,index,token) in zip(row['metadata_leads'],leads,strict=True):
            supported=type(token) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}',token) is not None and '..' not in token
            require(type(retained) is dict and set(retained)=={'field_origin','current_row_ordinal','token','token_supported',
                'listing_matches','metadata_only_not_identity_or_price_coverage'}
                and retained['field_origin']==origin and retained['current_row_ordinal']==index
                and (index is None or type(retained['current_row_ordinal']) is int)
                and retained['token']==token and retained['token_supported'] is bool(supported)
                and retained['metadata_only_not_identity_or_price_coverage'] is True,'input')
            if supported:tokens.add(token)
            source_leads.append({'field_origin':origin,'current_row_ordinal':index,'token':token,'supported':bool(supported)})
        require(row['optional_relatedtickers_raw']==original.get('relatedtickers')
            and row['relatedtickers_parse_state']==('retained_unparsed' if 'relatedtickers' in original else 'absent'),'input')
        lineage.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'original_source_row_sha256':sha(raw),
            'current_metadata_sha256':sha(canonical(current)),'explicit_leads_sha256':sha(canonical(source_leads))})
    require(1<=len(tokens)<=16,'plan')
    return observer.validate_plan({'schema':observer.PLAN_SCHEMA,
        'F_DATA_pin':{key:DATA_PLAN['metadata'][key] for key in ('byte_count','sha256')},
        'I_DATA_pin':I_DATA_PIN,'explicit_tokens':sorted(tokens),'binding_lineage_sha256':sha(canonical(lineage))})


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


def worker(args,deadline):
    require(args.mode in ('source','reauth') and type(args.control_fd) is int and args.control_fd>=3,'arguments')
    preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap(args.mode,sources,deadline);security=modules['security']
        info=meta(os.fstat(args.control_fd))
        require(stat.S_ISDIR(info[2]) and stat.S_IMODE(info[2])==0o700 and info[3]==os.getuid()
            and info==meta(os.stat(CONTROL,follow_symlinks=False)),'worker_claim')
        claim=_regular_fd(args.claim_fd,'claim.json',args.control_fd,MAX_OUTPUT,security)
        require(claim==canonical({'binding':binding(args),'profile':profile_record()}),'worker_claim')
        intent=_regular_fd(args.intent_fd,args.mode+'-intent.json',args.control_fd,8192,security)
        expected={'binding':binding(args),'phase':args.mode,'claim_pin':pin(claim)}
        require(intent==canonical(expected),'worker_claim')
        marker=canonical({'binding':binding(args),'phase':args.mode,'intent_pin':pin(intent)})
        fd=os.open(args.mode+'-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=args.control_fd)
        try:
            require(os.write(fd,marker)==len(marker),'worker_marker');os.fsync(fd);os.fsync(args.control_fd)
        finally:os.close(fd)
        with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as guarded:
            raw=guarded.read_all_once()['metadata'];plan=derive_plan(parse(raw,DATA_PLAN['metadata']['byte_count']),modules['observer'])
            guarded.verify();receipt=guarded.receipt();budget(deadline)
        result={'plan':plan,'plan_sha256':sha(canonical(plan)),'source_receipt_sha256':sha(canonical(receipt)),
            'F_DATA_guard_normal_return':True,'credential_access':False,'network_access':False,'USB_access':False}
        sources.close()
        return {'schema':SCHEMA+'-worker','binding':binding(args),'phase':args.mode,'result':result}


def worker_failure(args,code):
    return {'schema':SCHEMA+'-worker','binding':ACTIVE_BINDING,'phase':args.mode,'failure_code':code,
        'attempt_reusable':False}


def adopt_marker(store,phase):
    require(phase in ('source','reauth'),'worker_marker');name=phase+'-started.json'
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


def worker_native_profile(phase):
    require(phase in ('source','reauth'),'arguments')
    value='(version 1)(allow default)(deny network*)(deny file-read* file-write* (subpath "/Volumes"))'
    value+=''.join('(deny file-read* file-write* (subpath "'+path+'"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value+='(deny file-write* (require-all (require-not (literal "'+str(CONTROL/(phase+'-started.json'))+'"))'
    value+='(require-not (subpath "'+str(ROOT/'.pytest_cache')+'"))(require-not (literal "/dev/null"))))'
    leaves=[ROOT/DATA_PLAN['metadata']['relative_path'],CONTROL/'claim.json',CONTROL/(phase+'-intent.json'),CONTROL/(phase+'-started.json')]
    allowed={path for leaf in leaves for path in (*leaf.parents,leaf) if path==ROOT/'artifacts' or ROOT/'artifacts' in path.parents}
    value+='(deny file-read* (require-all (subpath "'+str(ROOT/'artifacts')+'")'
    value+=''.join('(require-not (literal "'+str(path)+'"))' for path in sorted(allowed))+'))'
    return value
def checked_pin(value,maximum,*,empty=False):
    require(type(value) is dict and set(value)=={'byte_count','sha256'}
        and type(value['byte_count']) is int and (0 if empty else 1)<=value['byte_count']<=maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),'output')
    return value


def _held_fd(store,name):
    found=[entry[1] for entry in store.held if entry[0]==name]
    require(len(found)==1,'control');return found[0]


def capture_worker(args,store,phase,deadline,observer):
    require(phase in ('source','reauth'),'arguments');store.verify();budget(deadline)
    claim=os.pread(_held_fd(store,'claim.json'),MAX_OUTPUT+1,0)
    intent={'binding':binding(args),'phase':phase,'claim_pin':pin(claim)}
    store.write(phase+'-intent.json',canonical(intent))
    inherited=(store.fd,_held_fd(store,'claim.json'),_held_fd(store,phase+'-intent.json'))
    command=['/usr/bin/sandbox-exec','-p',worker_native_profile(phase),PYTHON,'-I','-B',str(SOURCE),phase,
        '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256,
        '--control-fd',str(inherited[0]),'--claim-fd',str(inherited[1]),'--intent-fd',str(inherited[2]),
        '--outer-deadline',repr(min(deadline,time.monotonic()+WORKER_SECONDS))]
    child=None;output=bytearray();errors=hashlib.sha256();stderr_bytes=0;problem=None
    observed={'phase':phase,'spawn_observed':False,'actual_exit':None,'stdout_pin':pin(b''),
        'stderr_byte_count':0,'stderr_sha256':sha(b''),'marker_created':False,'marker_authenticated':False,
        'output_authenticated':False,'failure_code':None,'F_guard_normal_return':False,
        'source_receipt_sha256':None,'plan_sha256':None}
    require(len(STATE['source_workers'])==(0 if phase=='source' else 1),'scope')
    STATE['source_workers'].append(observed)
    capture_deadline=min(deadline,time.monotonic()+WORKER_SECONDS)
    try:
        child=subprocess.Popen(command,cwd=ROOT,env=safe_env(),stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,pass_fds=inherited)
        observed['spawn_observed']=True
        with selectors.DefaultSelector() as selected:
            for stream,label in ((child.stdout,'stdout'),(child.stderr,'stderr')):
                os.set_blocking(stream.fileno(),False);selected.register(stream,selectors.EVENT_READ,label)
            while selected.get_map() or child.poll() is None:
                for key,_ in selected.select(min(.1,budget(capture_deadline))):
                    chunk=os.read(key.fileobj.fileno(),8192)
                    if not chunk:selected.unregister(key.fileobj)
                    elif key.data=='stderr':
                        stderr_bytes+=len(chunk);errors.update(chunk)
                        require(stderr_bytes<=MAX_WORKER_STDERR,'worker_stderr')
                    else:
                        require(len(output)+len(chunk)<=MAX_WORKER_OUTPUT,'bound');output.extend(chunk)
        child.wait(timeout=min(5,budget(capture_deadline)))
    except BaseException as error:problem=finite(error)
    finally:
        if child is not None:
            if child.poll() is None:child.kill()
            child.wait(timeout=5);observed['actual_exit']=child.returncode
            child.stdout.close();child.stderr.close()
        observed.update(stdout_pin=pin(bytes(output)),stderr_byte_count=stderr_bytes,stderr_sha256=errors.hexdigest())
    try:marker=adopt_marker(store,phase)
    except BaseException as error:
        observed['failure_code']=finite(error);raise
    observed['marker_created']=marker is not None
    expected_marker=canonical({'binding':binding(args),'phase':phase,'intent_pin':pin(canonical(intent))})
    observed['marker_authenticated']=marker==expected_marker
    result=None
    if problem is None:
        try:
            require(stderr_bytes==0,'worker_stderr')
            require(observed['actual_exit'] in (0,2) and type(observed['actual_exit']) is int
                and bytes(output).endswith(b'\n') and bytes(output).count(b'\n')==1,'worker_output')
            packet=parse(bytes(output)[:-1],MAX_WORKER_OUTPUT)
            require(canonical(packet)+b'\n'==bytes(output) and type(packet) is dict
                and packet.get('schema')==SCHEMA+'-worker' and packet.get('binding')==binding(args)
                and packet.get('phase')==phase,'worker_output')
            if observed['actual_exit']==2:
                require(set(packet)=={'schema','binding','phase','failure_code','attempt_reusable'}
                    and type(packet['failure_code']) is str and packet['failure_code'] in FINITE
                    and packet['attempt_reusable'] is False,'worker_output')
                observed['output_authenticated']=True;problem=packet['failure_code']
            else:
                require(set(packet)=={'schema','binding','phase','result'} and observed['marker_authenticated'] is True,'worker_output')
                value=packet['result']
                require(type(value) is dict and set(value)=={'plan','plan_sha256','source_receipt_sha256','F_DATA_guard_normal_return',
                    'credential_access','network_access','USB_access'}
                    and value['F_DATA_guard_normal_return'] is True
                    and value['credential_access'] is value['network_access'] is value['USB_access'] is False,'worker_output')
                plan=observer.validate_plan(value['plan'])
                require(value['plan_sha256']==sha(canonical(plan)) and type(value['source_receipt_sha256']) is str
                    and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256']),'worker_output')
                observed.update(output_authenticated=True,F_guard_normal_return=True,
                    source_receipt_sha256=value['source_receipt_sha256'],plan_sha256=value['plan_sha256'])
                result=value
        except BaseException as error:problem=finite(error)
    observed['failure_code']=problem
    store.write(phase+'-observed.json',canonical(observed))
    return result,observed


def new_state():
    return {'stage':'preflight','claim_state':'unallocated','complete':False,'accepted':False,'failure_code':None,
        'source_workers':[],'plan_pin':None,'binding_lineage_sha256':None,'explicit_token_count':None,
        'keychain_lookup_attempts':0,'keychain_lookup_completed':0,'http_events':[],'retained_bodies':[],
        'observer_receipt':None,'provider_request_count':None,**FALSE_FLAGS}


STATE=new_state()


def launch(args,deadline):
    global STATE
    STATE=new_state();preflight(args,deadline);safe_runtime()
    with ExitStack() as sources:
        modules=bootstrap('parent',sources,deadline);observer=modules['observer'];security=modules['security']
        safe_runtime()
        with Store(security) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
            STATE['claim_state']=CLAIM_STATE;key=None;session=None;plan=None;bodies=[]
            try:
                STATE['stage']='source'
                first,observed=capture_worker(args,store,'source',deadline,observer)
                if not any(item is observed for item in STATE['source_workers']):STATE['source_workers'].append(observed)
                require(first is not None,observed['failure_code'] if observed['failure_code'] in FINITE else 'worker_failure')
                plan=observer.validate_plan(first['plan']);plan_raw=canonical(plan)
                STATE['plan_pin']=store.write('plan-private.json',plan_raw)
                STATE['binding_lineage_sha256']=plan['binding_lineage_sha256'];STATE['explicit_token_count']=len(plan['explicit_tokens'])
                budget(deadline);safe_runtime();STATE['stage']='credential'
                STATE['keychain_lookup_attempts']+=1
                key=modules['keychain'].load_key('sharadar',timeout_seconds=min(20,budget(deadline)))
                STATE['keychain_lookup_completed']+=1
                STATE['stage']='provider';safe_runtime()
                session=observer.configure_owned_session(observer.requests.Session())
                def journal(marker,event):
                    budget(deadline);safe_runtime()
                    checked=observer.validate_event(event)
                    require(marker=='request-'+format(checked['request_ordinal'],'02d')+'-'+checked['event'],'output')
                    pending=observer.validate_events([*STATE['http_events'],checked],plan)
                    store.write(marker+'.json',canonical(checked));STATE['http_events']=pending
                def retain_response(ordinal,raw,transport):
                    budget(deadline);safe_runtime()
                    require(type(ordinal) is int and ordinal==len(bodies) and 0<=ordinal<17
                        and type(raw) is bytes and 0<len(raw)<=MAX_PRIVATE
                        and sum(map(len,bodies))+len(raw)<=MAX_AGGREGATE,'retention')
                    expected=pin(raw);sequence=observer.request_plan(plan)
                    require(type(transport) is dict and set(transport)=={'schema','plan_sha256','request_ordinal','role','query_token',
                        'http_status','body_pin','CSV_validation_complete'}
                        and transport['schema']==observer.SCHEMA+'-private-transport'
                        and transport['plan_sha256']==sha(plan_raw) and type(transport['request_ordinal']) is int
                        and transport['request_ordinal']==ordinal and transport['role']==sequence[ordinal][1]
                        and transport['query_token']==sequence[ordinal][2] and type(transport['http_status']) is int
                        and transport['http_status']==200 and transport['body_pin']==expected
                        and transport['CSV_validation_complete'] is False,'retention')
                    observed=store.write('response-'+format(ordinal,'02d')+'.csv',raw)
                    record={'request_ordinal':ordinal,'body_pin':observed,'transport_pin':None}
                    STATE['retained_bodies'].append(record);bodies.append(raw)
                    record['transport_pin']=store.write('transport-'+format(ordinal,'02d')+'.json',canonical(transport))
                    return observed
                receipt,opaque=observer.observe(plan,session=session,api_key=key,journal=journal,
                    retain_response=retain_response,deadline=deadline)
                # The opaque return is never rendered, serialized, inspected or printed.
                opaque=None
                observer.validate_receipt(receipt,plan);observer.validate_events(STATE['http_events'],plan,receipt)
                observer.validate_capture(plan,receipt,tuple(bodies));STATE['observer_receipt']=receipt
                session.close();session=None;key=None
                STATE['stage']='reauth'
                second,observed=capture_worker(args,store,'reauth',deadline,observer)
                if not any(item is observed for item in STATE['source_workers']):STATE['source_workers'].append(observed)
                require(second is not None,observed['failure_code'] if observed['failure_code'] in FINITE else 'worker_failure')
                require(canonical(second['plan'])==plan_raw and second['plan_sha256']==STATE['plan_pin']['sha256'],'changed')
                budget(deadline);STATE.update(complete=True,accepted=True,stage='complete')
            except BaseException as error:
                STATE['failure_code']=finite(error);STATE['complete']=STATE['accepted']=False
            finally:
                key=None
                if session is not None:
                    try:session.close()
                    except BaseException:
                        STATE['failure_code']='session';STATE['complete']=STATE['accepted']=False
            STATE['claim_state']=CLAIM_STATE
            validate_state(STATE,observer)
            report={'binding':binding(args),'result':STATE}
            observed=store.write('report.json',canonical(report))
            return {**report,'report_pin':observed}


def validate_worker_observation(value):
    require(type(value) is dict and set(value)=={'phase','spawn_observed','actual_exit','stdout_pin','stderr_byte_count','stderr_sha256',
        'marker_created','marker_authenticated','output_authenticated','failure_code','F_guard_normal_return','source_receipt_sha256','plan_sha256'}
        and value['phase'] in ('source','reauth') and type(value['spawn_observed']) is bool
        and (value['actual_exit'] is None or type(value['actual_exit']) is int)
        and all(type(value[key]) is bool for key in ('marker_created','marker_authenticated','output_authenticated','F_guard_normal_return'))
        and type(value['stderr_byte_count']) is int and 0<=value['stderr_byte_count']<=MAX_WORKER_STDERR+8192
        and type(value['stderr_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['stderr_sha256'])
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE),'output')
    checked_pin(value['stdout_pin'],MAX_WORKER_OUTPUT,empty=True)
    for name in ('source_receipt_sha256','plan_sha256'):
        require(value[name] is None or type(value[name]) is str and re.fullmatch('[0-9a-f]{64}',value[name]),'output')
    require(not value['marker_authenticated'] or value['marker_created'],'output')
    if value['output_authenticated']:
        require(value['spawn_observed'] is True and type(value['actual_exit']) is int
            and value['actual_exit'] in (0,2) and value['stdout_pin']['byte_count']>0
            and value['stderr_byte_count']==0 and value['stderr_sha256']==sha(b''),'output')
        if not value['F_guard_normal_return']:
            require(value['actual_exit']==2 and value['failure_code'] is not None,'output')
    if value['F_guard_normal_return']:
        require(value['spawn_observed'] is value['marker_created'] is value['marker_authenticated'] is value['output_authenticated'] is True
            and type(value['actual_exit']) is int and value['actual_exit']==0 and value['stderr_byte_count']==0
            and value['failure_code'] is None and value['plan_sha256'] is not None and value['source_receipt_sha256'] is not None
            and value['stdout_pin']['byte_count']>0 and value['stderr_sha256']==sha(b''),'output')
    return value


def validate_state(value,observer):
    base=new_state()
    require(type(value) is dict and set(value)==set(base)
        and value['stage'] in ('preflight','source','credential','provider','reauth','complete')
        and value['claim_state'] in ('unallocated','allocated_unknown','consumed','consumed_or_unknown')
        and type(value['complete']) is type(value['accepted']) is bool and value['complete'] is value['accepted']
        and (value['failure_code'] is None or type(value['failure_code']) is str and value['failure_code'] in FINITE)
        and value['provider_request_count'] is None and all(value[key] is False for key in FALSE_FLAGS)
        and type(value['source_workers']) is list and len(value['source_workers'])<=2
        and type(value['keychain_lookup_attempts']) is type(value['keychain_lookup_completed']) is int
        and 0<=value['keychain_lookup_completed']<=value['keychain_lookup_attempts']<=1
        and type(value['http_events']) is list and len(value['http_events'])<=51
        and type(value['retained_bodies']) is list and len(value['retained_bodies'])<=17,'output')
    for index,row in enumerate(value['source_workers']):
        validate_worker_observation(row);require(row['phase']==('source' if index==0 else 'reauth'),'output')
    if value['plan_pin'] is not None:
        checked_pin(value['plan_pin'],8192)
        require(type(value['explicit_token_count']) is int and 1<=value['explicit_token_count']<=16
            and type(value['binding_lineage_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['binding_lineage_sha256'])
            and value['source_workers'] and value['source_workers'][0]['F_guard_normal_return'] is True
            and value['plan_pin']['sha256']==value['source_workers'][0]['plan_sha256'],'output')
    else:
        require(value['explicit_token_count'] is value['binding_lineage_sha256'] is None
            and value['keychain_lookup_attempts']==0 and not value['http_events'] and not value['retained_bodies'],'output')
    if value['source_workers'] or value['plan_pin'] is not None or value['keychain_lookup_attempts']:
        require(value['claim_state']=='consumed','output')
    if value['http_events'] or value['retained_bodies'] or value['observer_receipt'] is not None:
        require(value['keychain_lookup_attempts']==value['keychain_lookup_completed']==1
            and value['source_workers'] and value['source_workers'][0]['F_guard_normal_return'] is True
            and value['plan_pin'] is not None,'output')
    ordinal,phase,last_status,stopped=0,'intent',None,False
    for event in value['http_events']:
        row=observer.validate_event(event)
        require(not stopped and row['request_ordinal']==ordinal
            and value['explicit_token_count'] is not None and ordinal<value['explicit_token_count']+1,'output')
        if phase=='intent':require(row['event']=='intent','output');phase='status_or_terminal'
        elif phase=='status_or_terminal' and row['event']=='status':last_status=row['http_status'];phase='terminal'
        else:
            require(row['event']=='terminal' and row['http_status']==last_status
                and (row['terminal_state']=='refused' if phase=='status_or_terminal' else True),'output')
            if row['terminal_state']=='refused':stopped=True
            else:ordinal+=1;phase='intent';last_status=None
    total=0
    for index,row in enumerate(value['retained_bodies']):
        require(type(row) is dict and set(row)=={'request_ordinal','body_pin','transport_pin'}
            and type(row['request_ordinal']) is int and row['request_ordinal']==index,'output')
        checked_pin(row['body_pin'],MAX_PRIVATE);total+=row['body_pin']['byte_count']
        require(total<=MAX_AGGREGATE,'output')
        if row['transport_pin'] is not None:checked_pin(row['transport_pin'],8192)
        require(any(event['event']=='status' and event['request_ordinal']==index and event['http_status']==200
            for event in value['http_events']),'output')
    if value['observer_receipt'] is not None:
        receipt=observer.validate_receipt(value['observer_receipt'])
        require(receipt['plan_sha256']==value['plan_pin']['sha256']
            and receipt['binding_lineage_sha256']==value['binding_lineage_sha256']
            and receipt['explicit_token_count']==value['explicit_token_count']
            and len(receipt['responses'])==len(value['retained_bodies'])
            and receipt['retained_success_body_bytes']==total,'output')
        for body,response in zip(value['retained_bodies'],receipt['responses'],strict=True):
            require(body['body_pin']==response['body_pin'] and body['transport_pin'] is not None,'output')
            terminal=[event for event in value['http_events'] if event['event']=='terminal'
                and event['request_ordinal']==response['request_ordinal']]
            require(len(terminal)==1 and terminal[0]['terminal_state']=='validated_body'
                and terminal[0]['response_pin']==response['body_pin'] and terminal[0]['row_count']==response['row_count'],'output')
    if value['accepted']:
        require(value['stage']=='complete' and value['claim_state']=='consumed' and value['failure_code'] is None
            and len(value['source_workers'])==2 and all(row['F_guard_normal_return'] is True for row in value['source_workers'])
            and value['source_workers'][0]['plan_sha256']==value['source_workers'][1]['plan_sha256']
            and value['keychain_lookup_attempts']==value['keychain_lookup_completed']==1
            and value['observer_receipt'] is not None and not stopped and phase=='intent'
            and ordinal==value['explicit_token_count']+1 and len(value['http_events'])==3*ordinal,'output')
    else:require(value['failure_code'] is not None,'output')
    return value


def failure_packet(code):
    return {'binding':ACTIVE_BINDING,'failure_code':code,'attempt_reusable':False,'state':STATE}


def validate_output(raw,actual_exit,args,observer):
    require(type(actual_exit) is int and actual_exit in (0,2) and raw.endswith(b'\n') and raw.count(b'\n')==1,'output')
    packet=parse(raw[:-1],MAX_OUTPUT);require(canonical(packet)+b'\n'==raw and type(packet) is dict
        and packet.get('binding')==binding(args),'output')
    if set(packet)=={'binding','result','report_pin'}:
        validate_state(packet['result'],observer)
        require(actual_exit==(0 if packet['result']['accepted'] else 2)
            and packet['report_pin']==pin(canonical({'binding':binding(args),'result':packet['result']})),'output')
        return {'binding':binding(args),'output_authenticated':True,'accepted':packet['result']['accepted'],
            'actual_parent_exit':actual_exit,'report_pin':packet['report_pin'],'result':packet['result']}
    require(actual_exit==2 and set(packet)=={'binding','failure_code','attempt_reusable','state'}
        and packet['attempt_reusable'] is False and type(packet['failure_code']) is str and packet['failure_code'] in FINITE,'output')
    # Outer failures can prevent a final durable report; they never become success.
    validate_state(packet['state'],observer)
    require(packet['state']['accepted'] is False,'output')
    return {'binding':binding(args),'output_authenticated':True,'accepted':False,'actual_parent_exit':actual_exit,
        'failure_code':packet['failure_code'],'report_pin':None}


class Parser(argparse.ArgumentParser):
    def error(self,message):raise Refused('arguments')


def main():
    global ACTIVE_BINDING,ACTIVE_MODE
    parser=Parser(add_help=False)
    parser.add_argument('mode',choices=('launch','source','reauth','validate','profile'))
    for key in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+key)
    for key in ('control-fd','claim-fd','intent-fd','actual-parent-exit'):parser.add_argument('--'+key,type=int)
    parser.add_argument('--outer-deadline',type=float)
    args=parser.parse_args();ACTIVE_MODE=args.mode
    if args.mode=='profile':
        require(all(getattr(args,key) is None for key in ('expected_head','caller_sha256','profile_sha256',
            'control_fd','claim_fd','intent_fd','actual_parent_exit','outer_deadline')),'arguments')
        return profile_record()
    ACTIVE_BINDING=binding(args)
    deadline=ENTRY_DEADLINE
    if args.mode in ('source','reauth'):
        require(args.actual_parent_exit is None and type(args.outer_deadline) in (int,float)
            and math.isfinite(args.outer_deadline),'arguments')
        deadline=min(deadline,args.outer_deadline);budget(deadline)
    else:require(args.control_fd is args.claim_fd is args.intent_fd is args.outer_deadline is None,'arguments')
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
    try:return worker(args,deadline)
    except BaseException as error:return worker_failure(args,finite(error))


ACTIVE_MODE=None
if __name__=='__main__':
    try:
        value=main();raw=canonical(value)+b'\n';require(len(raw)<=MAX_OUTPUT,'bound')
        sys.stdout.buffer.write(raw)
        if ACTIVE_MODE=='profile':code=0
        elif ACTIVE_MODE in ('source','reauth'):code=0 if 'result' in value else 2
        elif ACTIVE_MODE=='validate':code=0 if value['accepted'] else 2
        else:code=0 if value['result']['accepted'] else 2
        raise SystemExit(code)
    except SystemExit:raise
    except BaseException as error:
        code=finite(error);STATE.update(complete=False,accepted=False,failure_code=code,claim_state=CLAIM_STATE)
        sys.stdout.buffer.write(canonical(failure_packet(code))+b'\n')
        raise SystemExit(2)
