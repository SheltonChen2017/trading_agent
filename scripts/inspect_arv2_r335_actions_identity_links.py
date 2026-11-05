"""One offline current-vintage action/metadata link observation over four DATA leaves.

No old control, producer, claim, credential, provider, QC or browser is used.
The original G refusal remains spent. A separate native-denied child claims
before reading the fixed bytes, links every v2-validated retained row to explicit original metadata leads. Counts do not imply G reached
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
SOURCE=ROOT/'scripts/inspect_arv2_r335_actions_identity_links.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R335-20261103-I'
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r335-offline-actions-metadata-links-v1'
DATA_PLAN={
 'metadata':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-F/private-diagnosis.json','byte_count':87170,
  'sha256':'0e41dca1d48955f83bcd5dcb2ae6192d85d9cf9f9ff40593bceeb0b5a601ccab'},
 'plan':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-G/plan-private.json','byte_count':443,
  'sha256':'a091a39da8e26905b9a6aa6833c0e7b9c4dc655797045b799d7f14a6347e6c40'},
 'body':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-G/response-00.csv','byte_count':2388,
  'sha256':'20411a9b177645aa441a40a5021f88095808f7aa39e1b1db0a4731235983ac09'},
 'transport':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-G/transport-00.json','byte_count':400,
  'sha256':'5520e213fa87353fef6246bf26a81648771d30f52b6f2720682b431f7db1a271'},
}
SOURCE_PINS={
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_r298_fixed_data_guard.py':'00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145',
 'scripts/arv2_r335_sharadar_actions_v2.py':'71417807bb3fc74dc58e8c53024d402a769165c275e2693b287a1561e3127216',
 'scripts/run_arv2_r335_sharadar_actions.py':'2d23cfef4e3fb3fb890ef5f8868457de8c4bb402672fa08f6dcc618b57525df4',
 'scripts/inspect_arv2_r335_firstrate_gap_metadata.py':'fd41a4d434503edc15d71d25775b520e98728a0e0d2e455c5bc03c69dabbbfa0',
}
H_OBSERVATION={'clean_head':'347c8dc32fd57bf20a5fae69108707fe3ccc41e0','actual_parent_exit':0,'actual_child_exit':0,'actual_validator_exit':0,
 'report_pin':{'byte_count':3524,'sha256':'c17be9313e511403137f57ab0b2c50fd41e20619915d9cc4696b60a09b130e6d'},
 'record_count':33,'contraticker_grammar_failure_count':9,'other_scope_shape_date_value_predicates_failed':False,
 'H_DATA_read_by_this_contract':False}
KNOWN_ACTION_FAMILIES={'split':'split','acquisitioncash':'acquisition_consideration','acquisitionstock':'acquisition_consideration',
 'acquisitionelectcash':'acquisition_consideration','acquisitionelectstock':'acquisition_consideration',
 'sicchangefrom':'industry_change','sicchangeto':'industry_change','exchangefrom':'listing_venue_change','exchangeto':'listing_venue_change'}
DOCUMENTED_TICKER_CHANGE_CODES=()
ACTION_FAMILIES=('split','acquisition_consideration','industry_change','listing_venue_change','unknown')
INTERVALS=('before_required_window','at_first_required','inside_required_window','at_last_required','after_required_window')
GAP_RELATIONS=('no_missing_dates','before_missing_interval','at_missing_interval_first','inside_missing_interval','at_missing_interval_last','after_missing_interval')
GEOMETRY=((718,'2023-12-01'),(417,'2025-02-14'),(417,'2025-02-14'),(432,'2025-01-24'),(302,'2025-08-01'))
LAST='2026-10-13'
SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,131072,8*1024*1024
MAX_MEMBER_BYTES=4*1024*1024
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE,PARSER_FAILURE_CODE='preflight',None,None
LEXICAL_EVIDENCE=None
STAGES=frozenset(('preflight','retained_DATA','metadata_links','output'))
PRICE_CODES=frozenset()
GUARD_MODULE=OBSERVER_MODULE=None
F_SCHEMA='arv2-r335-offline-firstrate-gap-metadata-v1-private'
I_DATA_PIN={'byte_count': 4984462, 'sha256': 'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'}
META_FIELDS=('table', 'ticker', 'permaticker', 'exchange', 'isdelisted', 'category', 'cusips', 'figi', 'currency', 'firstpricedate', 'lastpricedate', 'lastupdated')
EXPECTED_WHOLES=('f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986', 'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8', 'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7', '1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331', 'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9')
F_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'native_book_read': False, 'exact_missing_QC_book_cells_recovered': False, 'genuine_full_package_freshly_authenticated': False, 'actual_target_or_holdings_path_proven': False, 'identity_admitted': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'known_native_gap_resolved': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False, 'historical_or_continuous_integrity_proven': False, 'price_archive_read': False, 'price_rows_read': False, 'metadata_alias_admitted': False, 'actions_evidence_supplied': False, 'relatedtickers_parsed': False}
GUARD_CODES=frozenset(('scope','plan','deadline','state','shape','path_open','metadata','named_changed','security','security_changed','read_spent','byte_pin','close','receipt'))
OBSERVER_CODES=frozenset(('plan','credential','session','deadline','journal','event','prepared_identity','request_failed',
 'http_status_unavailable','http_status','response_identity','response_headers','response_encoding','response_bound',
 'response_stream','response_close','credential_echo','retention','csv','row_cap','row_scope','row_date','row_value',
 'changed','receipt','private','aggregate_bound','unknown'))
FALSE_FLAGS={'provider_contact': False, 'credential_access': False, 'QC_contact': False, 'Safari_access': False, 'USB_read': False, 'old_control_read': False, 'old_operation_replayed': False, 'H_DATA_read': False, 'G_attempt_accepted': False, 'G_request_plan_completed': False, 'v2_producer_invoked': False, 'remaining_G_query_authority_granted': False, 'source_choice_changed': False, 'rows_dropped_or_normalized': False, 'new_aliases_generated': False, 'corporate_action_semantics_applied': False, 'identity_admitted': False, 'historical_ticker_continuity_proven': False, 'terminal_payoff_proven': False, 'synthetic_cash_created': False, 'price_acquired': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False, 'historical_or_continuous_integrity_proven': False, 'full_original_inventory_freshly_authenticated': False, 'price_coverage_proven': False, 'known_native_gap_resolved': False, 'actual_holdings_path_proven': False}
FINITE=frozenset(('arguments','host','environment','git_state','source_pin','source_changed','scope','deadline','bound','claim_spent','control','path','shape','metadata','changed','input','original_row','plan','transport','projection','links','output','child_stderr','child_failure','unknown'))|frozenset('guard_'+code for code in GUARD_CODES)|frozenset('observer_'+code for code in OBSERVER_CODES)


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
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'retained_H_observation':H_OBSERVATION,
        'G_failure_observation':{'clean_head':'cd3fd302e53a40a8478ea36c07899d53c1f62d87','actual_parent_exit':2,'actual_source_worker_exit':0,
            'actual_validator_exit':2,'accepted':False,'failure_code':'provider_row_scope','observed_HTTP_status':200,
            'caller_pin':{'byte_count':59132,'sha256':'2d23cfef4e3fb3fb890ef5f8868457de8c4bb402672fa08f6dcc618b57525df4'},
            'profile_pin':{'byte_count':4329,'sha256':'1ff19609d02ea284f4a04663e25aaef699db33e46c3f12c66083d6623b48a80d'},
            'report_pin':{'byte_count':3211,'sha256':'30b28adc179bcc8edd44fbecd2f7e3955b9fe06d52b55a3b3cb18e181853acd0'},
            'application_intent_count':1,'contraticker_requests_started':0,'post_source_worker_started':False},
        'maximum_seconds':SECONDS,'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,
        'known_action_families':KNOWN_ACTION_FAMILIES,'documented_ticker_change_codes':list(DOCUMENTED_TICKER_CHANGE_CODES),
        'action_families':list(ACTION_FAMILIES),'interval_labels':list(INTERVALS),'gap_labels':list(GAP_RELATIONS),
        'primary_docs':['https://sharadar.com/docs/actions','https://sharadar.com/docs/faqs'],
        'projection':'authenticate_original_G_v1_plan_then_change_schema_only_to_v2_no_request_or_producer',
        'join':'primary_ticker_exact_explicit_F_leads_per_original_whole_binding_all_shared_owners_retained',
        'units':'source_rows_count_once_per_case_event_links_count_each_owner_candidate_gap_relations_separate',
        'counterparty':'safe_single_literal_token_retained_as_metadata_lead_only_not_alias_direction_or_same_security',
        'opaque_contra':'verbatim_no_split_normalization_or_query_generation',
        'ticker_change_search':'withheld_empty_documented_code_set_no_invented_labels',
        'unknown_codes':'retain_all_raw_codes_privately_count_unknown_no_semantic_or_cash_application',
        'validator':'exact_host_clean_HEAD_self_profile_selected_source_pins_then_stdin_only_no_DATA_or_controls',
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
    chosen.append('arv2_r335_sharadar_actions_v2')
    modules={}
    for name in chosen:
        full='scripts.'+name;relative='scripts/'+name+'.py';path=ROOT/relative
        spec=PathFinder.find_spec(full,[str(ROOT/'scripts')])
        require(spec is not None and spec.origin==str(path) and full not in sys.modules,'source_pin')
        module=ModuleType(full);module.__file__=str(path);module.__package__='scripts'
        module.__spec__=ModuleSpec(full,loader=None,origin=str(path));sys.modules[full]=module;setattr(package,name,module)
        exec(compile(raw_by_name[name],str(path),'exec'),module.__dict__)
        modules[name]=module
    OBSERVER_MODULE=modules['arv2_r335_sharadar_actions_v2']
    require(OBSERVER_MODULE.FINITE==OBSERVER_CODES
        and pin(canonical(OBSERVER_MODULE.profile_record()))=={'byte_count':2952,'sha256':'af5caade64ddf6c93d5e58cd130f2c17c5e17f8d42f63f37fa32ed0f523d2676'},'source_pin')
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

def safe_token(value):
    return type(value) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}',value) is not None and '..' not in value


def relation(session,first,last):
    if session<first:return 'before_required_window'
    if session==first:return 'at_first_required'
    if session>last:return 'after_required_window'
    if session==last:return 'at_last_required'
    return 'inside_required_window'


def gap_relation(session,missing):
    if not missing:return 'no_missing_dates'
    if session<missing[0]:return 'before_missing_interval'
    if session==missing[0]:return 'at_missing_interval_first'
    if session>missing[-1]:return 'after_missing_interval'
    if session==missing[-1]:return 'at_missing_interval_last'
    return 'inside_missing_interval'


def dates(values,*,required=False):
    require(type(values) is list and (bool(values) or not required)
        and all(type(value) is str and len(value)==10 for value in values),'input')
    try:require(all(date.fromisoformat(value).isoformat()==value for value in values),'input')
    except ValueError:raise Refused('input') from None
    require(values==sorted(set(values)),'input');return values


def inspect_links(metadata,original_plan,body,transport,observer):
    require(type(original_plan) is dict and original_plan.get('schema')=='arv2-r335-sharadar-actions-v1-plan','projection')
    projected={**original_plan,'schema':observer.PLAN_SCHEMA};projected=observer.validate_plan(projected)
    require({key:value for key,value in projected.items() if key!='schema'}=={key:value for key,value in original_plan.items() if key!='schema'}
        and len(projected['explicit_tokens'])==9,'projection')
    derived=derive_plan(metadata,observer)
    require(canonical(derived)==canonical(projected),'plan')
    require(type(transport) is dict and set(transport)=={'schema','plan_sha256','request_ordinal','role','query_token',
        'http_status','body_pin','CSV_validation_complete'}
        and transport['schema']=='arv2-r335-sharadar-actions-v1-private-transport'
        and transport['plan_sha256']==sha(canonical(original_plan)) and type(transport['request_ordinal']) is int
        and transport['request_ordinal']==0 and transport['role']=='ticker_union'
        and transport['query_token']==','.join(original_plan['explicit_tokens'])
        and type(transport['http_status']) is int and transport['http_status']==200
        and transport['body_pin']==pin(body) and transport['CSV_validation_complete'] is False,'transport')
    rows,parse_counts=observer.parse_response(body,role=transport['role'],token=transport['query_token'],
        explicit_tokens=tuple(projected['explicit_tokens']))
    require(len(rows)==33,'input')
    original_cases=sorted(metadata['cases'],key=lambda row:row['case_ordinal'])
    owners={};case_inputs=[]
    for ordinal,(case,(required_count,first)) in enumerate(zip(original_cases,GEOMETRY,strict=True)):
        required=dates(case['required_sessions'],required=True)
        require(len(required)==required_count and required[0]==first and required[-1]==LAST,'input')
        explicit={lead['token'] for lead in case['metadata_leads'] if lead['token_supported'] is True}
        for token in explicit:owners.setdefault(token,set()).add(ordinal)
        candidates=[]
        require(type(case['candidates']) is list and len(case['candidates'])<=14,'input')
        for candidate in case['candidates']:
            require(type(candidate) is dict and type(candidate.get('gap_geometry')) is dict,'input')
            gap=candidate['gap_geometry'];missing=dates(gap['missing_required_sessions'])
            require(set(missing)<=set(required),'input')
            candidates.append({'candidate_ordinal':candidate['candidate_ordinal'],'missing_required_sessions':missing,
                'original_candidate':candidate})
        no_gap=case['no_candidate_gap'];require(type(no_gap) is dict,'input')
        missing=dates(no_gap['missing_required_sessions']);require(set(missing)<=set(required),'input')
        case_inputs.append({'case':case,'required':required,'candidates':candidates,'no_candidate_missing':missing})
    global_families={key:0 for key in ACTION_FAMILIES};private_events=[];per_case=[[] for _ in range(5)]
    matched=set();shared=0;shared_links=0;literal_rows=0;opaque_rows=0
    for event_ordinal,row in enumerate(rows):
        family=KNOWN_ACTION_FAMILIES.get(row['action'],'unknown');global_families[family]+=1
        owner_ordinals=sorted(owners.get(row['ticker'],set()))
        require(owner_ordinals,'links');matched.add(event_ordinal)
        if len(owner_ordinals)>1:shared+=1;shared_links+=len(owner_ordinals)
        supported=bool(row['contraticker']) and safe_token(row['contraticker'])
        literal_rows+=int(supported);opaque_rows+=int(bool(row['contraticker']) and not supported)
        # This raw token can identify a counterparty, acquirer or unrelated role.
        # It is a metadata search lead only; no alias, direction or query follows.
        event={'source_row_ordinal':event_ordinal,'row':dict(row),'action_family':family,
            'primary_owner_case_ordinals':owner_ordinals,'shared_primary_ticker_ownership':len(owner_ordinals)>1,
            'literal_counterparty_metadata_lead':row['contraticker'] if supported else None,
            'opaque_contraticker_verbatim':row['contraticker'],'ticker_change_search_lead':None,
            'same_security_or_share_class_proven':False,'alias_admitted':False,'corporate_action_applied':False}
        private_events.append(event)
        for ordinal in owner_ordinals:
            case=case_inputs[ordinal];required=case['required']
            candidate_links=[{'candidate_ordinal':candidate['candidate_ordinal'],
                'missing_interval_relation':gap_relation(row['date'],candidate['missing_required_sessions']),
                'event_on_recorded_missing_date':row['date'] in set(candidate['missing_required_sessions'])} for candidate in case['candidates']]
            per_case[ordinal].append({'source_row_ordinal':event_ordinal,'action_family':family,
                'required_window_relation':relation(row['date'],required[0],required[-1]),'candidate_gap_links':candidate_links,
                'no_candidate_gap_relation':gap_relation(row['date'],case['no_candidate_missing']),
                'literal_counterparty_metadata_lead_present':supported,'ticker_change_search_lead_present':False,
                'shared_primary_ticker_ownership':len(owner_ordinals)>1})
    public_cases=[];private_cases=[]
    for ordinal,links in enumerate(per_case):
        families={key:0 for key in ACTION_FAMILIES};intervals={key:0 for key in INTERVALS};gap_counts={key:0 for key in GAP_RELATIONS}
        on_missing=0
        for link in links:
            families[link['action_family']]+=1;intervals[link['required_window_relation']]+=1
            for gap in link['candidate_gap_links']:
                gap_counts[gap['missing_interval_relation']]+=1;on_missing+=int(gap['event_on_recorded_missing_date'])
        public_cases.append({'case_ordinal':ordinal,'event_link_count':len(links),'action_family_link_counts':families,
            'required_window_relation_link_counts':intervals,'candidate_missing_interval_link_counts':gap_counts,
            'candidate_gap_relation_link_count':sum(gap_counts.values()),'event_on_recorded_missing_date_link_count':on_missing,
            'shared_primary_ticker_event_link_count':sum(link['shared_primary_ticker_ownership'] for link in links),
            'literal_counterparty_metadata_lead_link_count':sum(link['literal_counterparty_metadata_lead_present'] for link in links),
            'ticker_change_search_lead_link_count':0,'admitted_alias_count':0})
        private_cases.append({'case_ordinal':ordinal,'whole_binding_sha256':original_cases[ordinal]['whole_binding_sha256'],
            'original_F_case':original_cases[ordinal],'event_links':links,'alias_admitted':False,'source_assignment_changed':False})
    public={'source_row_count':len(rows),'parse_counts':parse_counts,'source_action_family_counts':global_families,
        'distinct_matched_source_row_count':len(matched),'unmatched_source_row_count':len(rows)-len(matched),
        'shared_primary_ticker_source_row_count':shared,'shared_primary_ticker_event_link_count':shared_links,
        'case_event_link_count':sum(len(links) for links in per_case),'literal_counterparty_metadata_lead_source_row_count':literal_rows,
        'opaque_nonempty_contraticker_source_row_count':opaque_rows,'ticker_change_search_lead_count':0,'admitted_alias_count':0,
        'schema_only_plan_projection_validated':True,'original_G_plan_pin':pin(canonical(original_plan)),
        'projected_v2_plan_pin':pin(canonical(projected)),'classification_policy_sha256':classification_policy_sha256(),
        'cases':public_cases,'current_vintage_subset_only':True,'complete_ACTIONS_history_proven':False}
    validate_inspection(public)
    private={'schema':SCHEMA+'-private','input_DATA_pins':DATA_PLAN,'original_G_plan':original_plan,'projected_v2_plan':projected,
        'original_G_transport':transport,'all_original_rows':private_events,'cases':private_cases,
        'inspection':public,'retained_H_observation':H_OBSERVATION,**FALSE_FLAGS}
    return public,private


def classification_policy_sha256():
    return sha(canonical({'known_codes':KNOWN_ACTION_FAMILIES,'documented_ticker_change_codes':list(DOCUMENTED_TICKER_CHANGE_CODES),
        'counterparty_policy':'supported_single_literal_metadata_only_no_alias_or_direction','unknown':'retain_exact_uninterpreted'}))


def count_map(value,keys,total):
    require(type(value) is dict and set(value)==set(keys) and all(type(item) is int and 0<=item<=total for item in value.values())
        and sum(value.values())==total,'output')


def validate_inspection(value):
    require(type(value) is dict and set(value)=={'source_row_count','parse_counts','source_action_family_counts','distinct_matched_source_row_count',
        'unmatched_source_row_count','shared_primary_ticker_source_row_count','shared_primary_ticker_event_link_count','case_event_link_count',
        'literal_counterparty_metadata_lead_source_row_count','opaque_nonempty_contraticker_source_row_count','ticker_change_search_lead_count',
        'admitted_alias_count','schema_only_plan_projection_validated','original_G_plan_pin','projected_v2_plan_pin','classification_policy_sha256',
        'cases','current_vintage_subset_only','complete_ACTIONS_history_proven'}
        and type(value['source_row_count']) is int and value['source_row_count']==33
        and value['schema_only_plan_projection_validated'] is value['current_vintage_subset_only'] is True
        and value['complete_ACTIONS_history_proven'] is False
        and value['classification_policy_sha256']==classification_policy_sha256()
        and type(value['cases']) is list and len(value['cases'])==5,'output')
    for key in ('distinct_matched_source_row_count','unmatched_source_row_count','shared_primary_ticker_source_row_count',
        'literal_counterparty_metadata_lead_source_row_count','opaque_nonempty_contraticker_source_row_count','ticker_change_search_lead_count','admitted_alias_count'):
        require(type(value[key]) is int and 0<=value[key]<=33,'output')
    require(value['distinct_matched_source_row_count']==33 and value['unmatched_source_row_count']==0
        and value['ticker_change_search_lead_count']==value['admitted_alias_count']==0
        and value['literal_counterparty_metadata_lead_source_row_count']+value['opaque_nonempty_contraticker_source_row_count']<=33
        and value['opaque_nonempty_contraticker_source_row_count']==H_OBSERVATION['contraticker_grammar_failure_count']
        and type(value['case_event_link_count']) is int and 33<=value['case_event_link_count']<=165
        and type(value['shared_primary_ticker_event_link_count']) is int
        and 0<=value['shared_primary_ticker_event_link_count']<=value['case_event_link_count'],'output')
    count_map(value['source_action_family_counts'],ACTION_FAMILIES,33)
    counts=value['parse_counts'];require(type(counts) is dict and set(counts)=={'row_count','primary_key_count',
        'repeated_primary_key_row_count','conflicting_value_primary_key_count'}
        and all(type(item) is int and 0<=item<=33 for item in counts.values()) and counts['row_count']==33
        and counts['primary_key_count']>=1
        and counts['repeated_primary_key_row_count']==33-counts['primary_key_count']
        and counts['conflicting_value_primary_key_count']<=min(counts['primary_key_count'],counts['repeated_primary_key_row_count']),'output')
    for pin_name,role in (('original_G_plan_pin','plan'),('projected_v2_plan_pin',None)):
        item=value[pin_name];require(type(item) is dict and set(item)=={'byte_count','sha256'} and type(item['byte_count']) is int
            and 0<item['byte_count']<=8192 and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']),'output')
        if role:require(item=={key:DATA_PLAN[role][key] for key in ('byte_count','sha256')},'output')
    for ordinal,row in enumerate(value['cases']):
        require(type(row) is dict and set(row)=={'case_ordinal','event_link_count','action_family_link_counts','required_window_relation_link_counts',
            'candidate_missing_interval_link_counts','candidate_gap_relation_link_count','event_on_recorded_missing_date_link_count',
            'shared_primary_ticker_event_link_count','literal_counterparty_metadata_lead_link_count','ticker_change_search_lead_link_count','admitted_alias_count'}
            and type(row['case_ordinal']) is int and row['case_ordinal']==ordinal
            and type(row['event_link_count']) is int and 0<=row['event_link_count']<=33,'output')
        count=row['event_link_count'];count_map(row['action_family_link_counts'],ACTION_FAMILIES,count)
        count_map(row['required_window_relation_link_counts'],INTERVALS,count)
        require(type(row['candidate_gap_relation_link_count']) is int and 0<=row['candidate_gap_relation_link_count']<=14*count,'output')
        count_map(row['candidate_missing_interval_link_counts'],GAP_RELATIONS,row['candidate_gap_relation_link_count'])
        for name in ('event_on_recorded_missing_date_link_count','shared_primary_ticker_event_link_count',
            'literal_counterparty_metadata_lead_link_count','ticker_change_search_lead_link_count','admitted_alias_count'):
            maximum=row['candidate_gap_relation_link_count'] if name=='event_on_recorded_missing_date_link_count' else count
            require(type(row[name]) is int and 0<=row[name]<=maximum,'output')
        require(row['ticker_change_search_lead_link_count']==row['admitted_alias_count']==0,'output')
    shared=value['shared_primary_ticker_source_row_count'];shared_links=value['shared_primary_ticker_event_link_count']
    require(2*shared<=shared_links<=5*shared
        and value['case_event_link_count']==33-shared+shared_links,'output')
    literal_links=sum(row['literal_counterparty_metadata_lead_link_count'] for row in value['cases'])
    require(value['literal_counterparty_metadata_lead_source_row_count']<=literal_links
        <=value['literal_counterparty_metadata_lead_source_row_count']+shared_links-shared,'output')
    for family in ACTION_FAMILIES:
        links=sum(row['action_family_link_counts'][family] for row in value['cases'])
        require(value['source_action_family_counts'][family]<=links<=5*value['source_action_family_counts'][family],'output')
    require(sum(row['event_link_count'] for row in value['cases'])==value['case_event_link_count']
        and sum(row['shared_primary_ticker_event_link_count'] for row in value['cases'])==value['shared_primary_ticker_event_link_count'],'output')
    return value


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
            with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as guarded:
                raw=guarded.read_all_once()
                metadata=parse(raw['metadata'],DATA_PLAN['metadata']['byte_count'])
                original=parse(raw['plan'],DATA_PLAN['plan']['byte_count']);transport=parse(raw['transport'],DATA_PLAN['transport']['byte_count'])
                require(canonical(original)==raw['plan'] and canonical(transport)==raw['transport'],'input')
                FAILURE_STAGE='metadata_links'
                inspection,private=inspect_links(metadata,original,raw['body'],transport,modules['observer'])
                guarded.verify();receipt=guarded.receipt();budget(deadline)
            sources.close();FAILURE_STAGE='output'
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'output')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'inspection':inspection,'private_pin':private_pin,
                'all_four_DATA_authenticated':True,'source_guard_normal_return':True,'source_receipt_sha256':sha(canonical(receipt)),
                'retained_H_observation_sha256':sha(canonical(H_OBSERVATION)),**FALSE_FLAGS}
            validate_result(result);preflight(args,deadline)
            report={'binding':binding(args),'result':result};report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','complete','inspection','private_pin','all_four_DATA_authenticated',
        'source_guard_normal_return','source_receipt_sha256','retained_H_observation_sha256',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['complete'] is True
        and value['all_four_DATA_authenticated'] is value['source_guard_normal_return'] is True
        and type(value['source_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256'])
        and value['retained_H_observation_sha256']==sha(canonical(H_OBSERVATION))
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    validate_inspection(value['inspection'])
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
