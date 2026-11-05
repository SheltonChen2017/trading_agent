"""One offline predicate diagnosis over three exact retained ACTIONS DATA leaves.

No old control, producer, claim, credential, provider, QC or browser is used.
The original G refusal remains spent. A separate native-denied child claims
before reading the fixed bytes, counts every row independently and reproduces
only the pure frozen parser on supplied bytes. Counts do not imply G reached
later rows, a unique cause, grammar admission, corporate-action semantics or
historical identity. Original strings are never normalized or published.
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
SOURCE=ROOT/'scripts/inspect_arv2_r335_sharadar_scope.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R335-20261103-H'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r335-offline-actions-row-scope-v1'
DATA_PLAN={
 'plan':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-G/plan-private.json','byte_count':443,
  'sha256':'a091a39da8e26905b9a6aa6833c0e7b9c4dc655797045b799d7f14a6347e6c40'},
 'body':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-G/response-00.csv','byte_count':2388,
  'sha256':'20411a9b177645aa441a40a5021f88095808f7aa39e1b1db0a4731235983ac09'},
 'transport':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-G/transport-00.json','byte_count':400,
  'sha256':'5520e213fa87353fef6246bf26a81648771d30f52b6f2720682b431f7db1a271'},
}
G_OBSERVATION={'clean_head':'cd3fd302e53a40a8478ea36c07899d53c1f62d87','actual_parent_exit':2,'actual_source_worker_exit':0,
 'actual_validator_exit':2,'original_failure_code':'provider_row_scope','accepted':False,'observed_HTTP_status':200,
 'application_intent_count':1,'contraticker_requests_started':0,'post_source_worker_started':False,
 'caller_pin':{'byte_count':59132,'sha256':'2d23cfef4e3fb3fb890ef5f8868457de8c4bb402672fa08f6dcc618b57525df4'},
 'profile_pin':{'byte_count':4329,'sha256':'1ff19609d02ea284f4a04663e25aaef699db33e46c3f12c66083d6623b48a80d'},
 'report_pin':{'byte_count':3211,'sha256':'30b28adc179bcc8edd44fbecd2f7e3955b9fe06d52b55a3b3cb18e181853acd0'},
 'retained_DATA_plan':DATA_PLAN}
SOURCE_PINS={
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_r298_fixed_data_guard.py':'00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145',
 'scripts/arv2_r335_sharadar_actions.py':'2d40d2c260a3fa2b484608df5ec43eaaad901848c345e1a60a215bf164c23d29',
 'scripts/run_arv2_r335_sharadar_actions.py':'2d23cfef4e3fb3fb890ef5f8868457de8c4bb402672fa08f6dcc618b57525df4',
}
SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,131072,8*1024*1024
MAX_MEMBER_BYTES=4*1024*1024
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
FIELD_NAMES=('date','action','ticker','name','value','contraticker','contraname')
PREDICATES=('seven_fields','field_trim','field_control_free','field_length_bounded','frozen_field_shape',
 'date_canonical','date_in_window','date_nondecreasing','frozen_date_rule',
 'ticker_grammar','contraticker_grammar','request_role_filter','action_nonempty','action_ascii','action_length_bounded',
 'name_nonempty','frozen_row_scope_conjunction','value_rule')
SCOPE_PREDICATES=('ticker_grammar','contraticker_grammar','request_role_filter','action_nonempty','action_ascii','action_length_bounded','name_nonempty')
VALUE_CLASSES=('empty','finite_supported','finite_unsupported_grammar','nonfinite','unparseable','overlong','unexamined')
PARSER_CODES=frozenset(('csv','row_cap','row_date','row_scope','row_value','unknown'))
GUARD_CODES=frozenset(('scope','plan','deadline','state','shape','path_open','metadata','named_changed','security','security_changed','read_spent','byte_pin','close','receipt'))
OBSERVER_CODES=frozenset(('plan','credential','session','deadline','journal','event','prepared_identity','request_failed',
 'http_status_unavailable','http_status','response_identity','response_headers','response_encoding','response_bound',
 'response_stream','response_close','credential_echo','retention','csv','row_cap','row_scope','row_date','row_value',
 'changed','receipt','private','aggregate_bound','unknown'))
FINITE=frozenset(('arguments','host','environment','git_state','source_pin','source_changed','scope','deadline','bound','claim_spent',
 'control','path','shape','metadata','changed','input','transport','csv','row_bound','parser_reproduction','output','child_stderr','child_failure','unknown')) \
 |frozenset('guard_'+code for code in GUARD_CODES)|frozenset('observer_'+code for code in OBSERVER_CODES)
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE,PARSER_FAILURE_CODE='preflight',None,None
LEXICAL_EVIDENCE=None
STAGES=frozenset(('preflight','retained_DATA','predicate_diagnosis','output'))
PRICE_CODES=frozenset()
GUARD_MODULE=OBSERVER_MODULE=None

FALSE_FLAGS={'provider_contact': False, 'credential_access': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'old_control_read': False, 'old_operation_replayed': False, 'G_attempt_accepted': False, 'G_request_plan_completed': False, 'G_later_rows_processed_by_original_attempt_proven': False, 'unique_cause_proven': False, 'grammar_relaxed': False, 'rows_dropped_or_normalized': False, 'new_aliases_generated': False, 'corporate_action_semantics_interpreted': False, 'identity_admitted': False, 'terminal_payoff_proven': False, 'price_acquired': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False, 'historical_or_continuous_integrity_proven': False}


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
        return 'observer_'+code if code in OBSERVER_CODES else 'unknown'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    return 'deadline' if isinstance(error,TimeoutError) else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'stage': FAILURE_STAGE, 'case_ordinal': FAILURE_CASE, 'parser_failure_code': PARSER_FAILURE_CODE,
        'lexical_evidence': LEXICAL_EVIDENCE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE, **FALSE_FLAGS}

def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'parser_failure_code', 'lexical_evidence', 'attempt_reusable', 'claim_state', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
        and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
        and value['stage'] in STAGES and (value['case_ordinal'] is None or
            type(value['case_ordinal']) is int and 0 <= value['case_ordinal'] < 5)
        and (value['parser_failure_code'] is None or type(value['parser_failure_code']) is str
            and value['parser_failure_code'] in PRICE_CODES)
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    require(value['lexical_evidence'] is None,'output')
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
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'retained_G_failure_observation':G_OBSERVATION,
        'maximum_seconds':SECONDS,'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,
        'scope':'exact_three_retained_DATA_only_offline_row_scope_predicate_diagnosis_no_G_controls_or_provider',
        'predicates':list(PREDICATES),'scope_subpredicates':list(SCOPE_PREDICATES),'value_classes':list(VALUE_CLASSES),
        'count_unit':'one_csv_record_each_predicate_independently_not_G_processed_prefix',
        'first_failure':'finite_category_and_all_failed_scope_conditions_no_row_date_or_identifier_index_no_unique_cause_claim',
        'private_rows':'unchanged_parsed_field_strings_only_when_header_and_all_record_widths_unambiguous_no_admission',
        'frozen_parser':'pure_parse_response_once_on_supplied_retained_bytes_not_observe_or_old_claim',
        'validator':'same_exact_host_clean_HEAD_caller_profile_selected_source_pins_then_bounded_stdin_only_no_DATA_or_control_read',
        'deadline_limitation':'uninterruptible_IO_or_host_suspension_not_bounded',**FALSE_FLAGS}


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

def bootstrap(role,stack,deadline):
    """Compile exact held selected source bytes; never execute repo pyc caches."""
    global GUARD_MODULE,OBSERVER_MODULE
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
    chosen=['arv2_relocation_security']
    if role=='worker':chosen.append('arv2_r298_fixed_data_guard')
    chosen.append('arv2_r335_sharadar_actions')
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
    require(OBSERVER_MODULE.FINITE==OBSERVER_CODES
        and pin(canonical(OBSERVER_MODULE.profile_record()))=={'byte_count':2563,'sha256':'cc17301092d8f799e297f522db17297fc50288caada88a255cfdc38e3e177930'},'source_pin')
    if role=='worker':
        GUARD_MODULE=modules['arv2_r298_fixed_data_guard'];require(GUARD_MODULE.FINITE==GUARD_CODES,'source_pin')
    require(not any(name=='AlgorithmImports' or name.startswith(('QuantConnect','quantconnect','qc.client','scripts.run_arv2_r298'))
        for name in sys.modules),'environment')
    return {'security':modules['arv2_relocation_security'],'observer':OBSERVER_MODULE,
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

def value_class(text):
    if text=='':return 'empty',True
    if len(text)>128:return 'overlong',False
    grammar=re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]{1,4})?',text) is not None
    try:number=Decimal(text)
    except InvalidOperation:return 'unparseable',False
    if not number.is_finite():return 'nonfinite',False
    return ('finite_supported',True) if grammar else ('finite_unsupported_grammar',False)


def checked_session(text):
    try:return date.fromisoformat(text).isoformat()==text
    except (ValueError,TypeError):return False


def inspect_rows(raw,plan,transport,observer):
    checked=observer.validate_plan(plan)
    require(type(raw) is bytes and 0<len(raw)<=MAX_MEMBER_BYTES,'bound')
    require(type(transport) is dict and set(transport)=={'schema','plan_sha256','request_ordinal','role','query_token',
        'http_status','body_pin','CSV_validation_complete'}
        and transport['schema']==observer.SCHEMA+'-private-transport'
        and transport['plan_sha256']==sha(canonical(checked)) and type(transport['request_ordinal']) is int
        and transport['request_ordinal']==0 and transport['role']=='ticker_union'
        and transport['query_token']==','.join(checked['explicit_tokens'])
        and type(transport['http_status']) is int and transport['http_status']==200
        and transport['body_pin']==pin(raw) and transport['CSV_validation_complete'] is False,'transport')
    try:
        text=raw.decode('utf-8-sig',errors='strict');require('\x00' not in text,'csv')
        reader=csv.reader(io.StringIO(text,newline=''),strict=True)
        header=tuple(next(reader,()))
        require(len(header)==len(FIELD_NAMES) and set(header)==set(FIELD_NAMES),'csv')
        records=list(reader)
    except (UnicodeError,csv.Error):raise Refused('csv') from None
    require(len(records)<1000,'row_bound')
    counts={key:{'pass_count':0,'fail_count':0,'unexamined_count':0} for key in PREDICATES}
    classes={key:0 for key in VALUE_CLASSES}
    rows=[];unambiguous=True;previous=None;first_code=None;first_scope=[]
    for record_index,fields in enumerate(records):
        width=len(fields)==len(FIELD_NAMES)
        trimmed=all(value==value.strip() for value in fields)
        control_free=all(not any(ord(char)<32 or ord(char)==127 for char in value) for value in fields)
        length_bounded=all(len(value)<=observer.MAX_FIELD for value in fields)
        shape=width and trimmed and control_free and length_bounded
        predicates={key:None for key in PREDICATES}
        predicates.update(seven_fields=width,field_trim=trimmed,field_control_free=control_free,
            field_length_bounded=length_bounded,frozen_field_shape=shape)
        if not width:
            unambiguous=False;classes['unexamined']+=1;previous=None
            if first_code is None:first_code='csv'
        else:
            row=dict(zip(header,fields,strict=True));rows.append(row)
            canonical_date=checked_session(row['date'])
            in_window=observer.FIRST<=row['date']<=observer.LAST if canonical_date else None
            ordered=(True if record_index==0 else previous<=row['date'] if previous is not None else None) if canonical_date else None
            date_rule=False if not canonical_date or in_window is False or ordered is False else None if ordered is None else True
            predicates.update(date_canonical=canonical_date,date_in_window=in_window,date_nondecreasing=ordered,
                frozen_date_rule=date_rule)
            ticker=type(row['ticker']) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}',row['ticker']) is not None and '..' not in row['ticker']
            contra=(not row['contraticker']) or (re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}',row['contraticker']) is not None and '..' not in row['contraticker'])
            scope={'ticker_grammar':bool(ticker),'contraticker_grammar':bool(contra),
                'request_role_filter':row['ticker'] in checked['explicit_tokens'],
                'action_nonempty':bool(row['action']),'action_ascii':row['action'].isascii(),
                'action_length_bounded':len(row['action'])<=128,'name_nonempty':bool(row['name'])}
            conjunction=all(scope.values());predicates.update(scope,frozen_row_scope_conjunction=conjunction)
            category,value_rule=value_class(row['value']);classes[category]+=1;predicates['value_rule']=value_rule
            if first_code is None:
                if not shape:first_code='csv'
                elif not date_rule:first_code='row_date'
                elif not conjunction:
                    first_code='row_scope';first_scope=[key for key in SCOPE_PREDICATES if not scope[key]]
                elif not value_rule:first_code='row_value'
            previous=row['date'] if canonical_date else None
        for key,value in predicates.items():
            bucket='unexamined_count' if value is None else 'pass_count' if value else 'fail_count'
            counts[key][bucket]+=1
    try:
        observer.parse_response(raw,role=transport['role'],token=transport['query_token'],explicit_tokens=tuple(checked['explicit_tokens']))
        original_code=None
    except Exception as error:
        original_code=observer.finite(error)
        require(original_code in PARSER_CODES,'parser_reproduction')
    require(first_code==original_code,'parser_reproduction')
    public={'record_count':len(records),'header_schema_validated':True,
        'all_CSV_records_unambiguous':unambiguous,'all_frozen_field_shapes_valid':counts['frozen_field_shape']['fail_count']==0,
        'predicate_counts':counts,'value_class_counts':classes,'first_unsupported_code':first_code,
        'first_failed_scope_predicates':first_scope,'frozen_parser_failure_code':original_code,
        'frozen_parser_refusal_reproduced':original_code is not None,
        'all_bounded_rows_independently_examined':True,'original_G_processed_all_rows_proven':False,
        'private_parsed_rows_retained':unambiguous,'scope_or_grammar_admitted':False}
    validate_inspection(public)
    private={'schema':SCHEMA+'-private','plan_pin':pin(canonical(checked)),'body_pin':pin(raw),
        'transport_pin':pin(canonical(transport)),'parsed_rows':rows if unambiguous else None,
        'all_rows_retained_without_normalization':unambiguous,'all_CSV_records_unambiguous':unambiguous,
        'inspection':public,**FALSE_FLAGS}
    return public,private


def validate_inspection(value):
    require(type(value) is dict and set(value)=={'record_count','header_schema_validated','all_CSV_records_unambiguous',
        'all_frozen_field_shapes_valid','predicate_counts','value_class_counts','first_unsupported_code','first_failed_scope_predicates',
        'frozen_parser_failure_code','frozen_parser_refusal_reproduced','all_bounded_rows_independently_examined',
        'original_G_processed_all_rows_proven','private_parsed_rows_retained','scope_or_grammar_admitted'}
        and type(value['record_count']) is int and 0<=value['record_count']<1000
        and value['header_schema_validated'] is True and value['all_bounded_rows_independently_examined'] is True
        and value['original_G_processed_all_rows_proven'] is value['scope_or_grammar_admitted'] is False
        and all(type(value[key]) is bool for key in ('all_CSV_records_unambiguous','all_frozen_field_shapes_valid',
            'frozen_parser_refusal_reproduced','private_parsed_rows_retained'))
        and value['private_parsed_rows_retained'] is value['all_CSV_records_unambiguous']
        and (value['first_unsupported_code'] is None or type(value['first_unsupported_code']) is str and value['first_unsupported_code'] in PARSER_CODES)
        and value['first_unsupported_code']==value['frozen_parser_failure_code']
        and value['frozen_parser_refusal_reproduced'] is (value['frozen_parser_failure_code'] is not None),'output')
    count=value['record_count']
    require(type(value['predicate_counts']) is dict and set(value['predicate_counts'])==set(PREDICATES)
        and type(value['value_class_counts']) is dict and set(value['value_class_counts'])==set(VALUE_CLASSES),'output')
    for row in value['predicate_counts'].values():
        require(type(row) is dict and set(row)=={'pass_count','fail_count','unexamined_count'}
            and all(type(item) is int and 0<=item<=count for item in row.values()) and sum(row.values())==count,'output')
    require(all(type(item) is int and 0<=item<=count for item in value['value_class_counts'].values())
        and sum(value['value_class_counts'].values())==count
        and value['all_CSV_records_unambiguous'] is (value['predicate_counts']['seven_fields']['fail_count']==0)
        and value['all_frozen_field_shapes_valid'] is (value['predicate_counts']['frozen_field_shape']['fail_count']==0)
        and type(value['first_failed_scope_predicates']) is list
        and value['first_failed_scope_predicates']==[key for key in SCOPE_PREDICATES if key in value['first_failed_scope_predicates']]
        and (bool(value['first_failed_scope_predicates']) if value['first_unsupported_code']=='row_scope' else not value['first_failed_scope_predicates']),'output')
    predicates=value['predicate_counts'];width_failed=predicates['seven_fields']['fail_count']
    for key in ('seven_fields','field_trim','field_control_free','field_length_bounded','frozen_field_shape'):
        require(predicates[key]['unexamined_count']==0,'output')
    shape_failures=[predicates[key]['fail_count'] for key in ('seven_fields','field_trim','field_control_free','field_length_bounded')]
    require(max(shape_failures,default=0)<=predicates['frozen_field_shape']['fail_count']<=sum(shape_failures),'output')
    for key in (*SCOPE_PREDICATES,'frozen_row_scope_conjunction','date_canonical','value_rule'):
        require(predicates[key]['unexamined_count']==width_failed,'output')
    scope_failures=[predicates[key]['fail_count'] for key in SCOPE_PREDICATES]
    require(max(scope_failures,default=0)<=predicates['frozen_row_scope_conjunction']['fail_count']<=sum(scope_failures),'output')
    if value['first_unsupported_code']=='row_scope':
        require(predicates['frozen_row_scope_conjunction']['fail_count']>=1
            and all(predicates[key]['fail_count']>=1 for key in value['first_failed_scope_predicates']),'output')
    classes=value['value_class_counts']
    require(classes['unexamined']==width_failed
        and predicates['value_rule']['pass_count']==classes['empty']+classes['finite_supported']
        and predicates['value_rule']['fail_count']==sum(classes[key] for key in ('finite_unsupported_grammar','nonfinite','unparseable','overlong')),'output')
    return value


def worker(args,deadline):
    global FAILURE_STAGE
    require(type(args.intent_fd) is int and args.intent_fd>=3,'arguments')
    try:intent=os.read(args.intent_fd,4097)
    finally:os.close(args.intent_fd)
    require(intent==canonical(binding(args)),'arguments')
    preflight(args,deadline)
    with ExitStack() as sources:
        modules=bootstrap('worker',sources,deadline)
        with Store(modules['security']) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
            FAILURE_STAGE='retained_DATA'
            with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as guarded:
                raw=guarded.read_all_once()
                plan=modules['observer'].validate_plan(parse(raw['plan'],DATA_PLAN['plan']['byte_count']))
                transport=parse(raw['transport'],DATA_PLAN['transport']['byte_count'])
                require(canonical(plan)==raw['plan'] and canonical(transport)==raw['transport']
                    and len(plan['explicit_tokens'])==9,'input')
                FAILURE_STAGE='predicate_diagnosis'
                inspection,private=inspect_rows(raw['body'],plan,transport,modules['observer'])
                require(inspection['frozen_parser_failure_code']=='row_scope','parser_reproduction')
                guarded.verify();receipt=guarded.receipt();budget(deadline)
            sources.close();FAILURE_STAGE='output'
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'output')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'inspection':inspection,'private_pin':private_pin,
                'retained_G_failure_sha256':sha(canonical(G_OBSERVATION)),
                'all_three_DATA_authenticated':True,'source_guard_normal_return':True,
                'source_receipt_sha256':sha(canonical(receipt)),**FALSE_FLAGS}
            validate_result(result);preflight(args,deadline)
            report={'binding':binding(args),'result':result};report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','complete','inspection','private_pin','retained_G_failure_sha256',
        'all_three_DATA_authenticated','source_guard_normal_return','source_receipt_sha256',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['complete'] is True
        and value['all_three_DATA_authenticated'] is value['source_guard_normal_return'] is True
        and value['retained_G_failure_sha256']==sha(canonical(G_OBSERVATION))
        and type(value['source_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256'])
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    validate_inspection(value['inspection'])
    require(value['inspection']['frozen_parser_failure_code']=='row_scope','output')
    item=value['private_pin']
    require(type(item) is dict and set(item)=={'byte_count','sha256'} and type(item['byte_count']) is int and 0<item['byte_count']<=MAX_PRIVATE
        and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']),'output')
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
