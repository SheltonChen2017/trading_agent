"""One exact missing-pair and explicit metadata-lead diagnosis, never acquisition.

Only two fixed retained DATA leaves and one pinned USB stock listing are read.
No price archive, price row, provider, QC book or old control is available.
Every candidate remains separate. Ticker leads are explicit retained fields,
not identity assignments; optional relatedtickers stays raw and unparsed.
"""
import argparse
import csv
from contextlib import ExitStack
from datetime import date
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
SOURCE=ROOT/'scripts/inspect_arv2_r335_firstrate_gap_metadata.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/firstrate/R335-20261103-F'
USB=Path('/Volumes/SANDISK/firstrate')
PYTHON='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH='codex/strategy-analyst-revisions-v2'
SCHEMA='arv2-r335-offline-firstrate-gap-metadata-v1'
DATA_PLAN={
 'identity':{'relative_path':'artifacts/analyst_revisions_v2/newrule_available_history_identity/R327-20261027-I/identity-demand-private.json',
  'byte_count':4984462,'sha256':'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'},
 'coverage':{'relative_path':'artifacts/analyst_revisions_v2/firstrate/R335-20261103-E/private-diagnosis.json',
  'byte_count':17445,'sha256':'abb076cbfe46bdf0290cfb2299c923d0d822df168ea7e5a4fcd98bac1b3068d8'},
}
STOCK_DIR='market/Stocks_Complete_10_000+_Tickers/'
USB_PINS={STOCK_DIR+'Ticker_Listing.txt':{'byte_count':889580,'sha256':'584718095d81d576af0f83d6f31d5cda565e59ea2c6677e5b164e0db39e93464'}}
ARCHIVES=()
ORIGINAL_SERIALIZATION_REFERENCE={'relative_path':'research/analyst_revisions_v2/canonical.py','byte_count':14651,'sha256':'c1d1d1aab633b16868fccc371de7c4cf4f3a692943e04a8d785109110e17ae6e'}
SOURCE_PINS={
 'scripts/arv2_r298_fixed_data_guard.py':'00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145',
 'scripts/arv2_relocation_security.py':'3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_r327_i_source_binding.py':'44405001183804020d8b211d79846d8ea70019758059cc73878cca883bac6416',
 'scripts/inspect_arv2_r335_firstrate_stock_coverage.py':'cc804e71d86d1e4fbe792a841379db7acb41080d092f6a8b7e16c60a23435c7d',
}
E_SCHEMA='arv2-r335-offline-firstrate-stock-coverage-v1'
E_OBSERVATION={'clean_head':'7699f6b6d619bc77410432a4fe4de4d1512767f7',
 'caller_pin':{'byte_count':50133,'sha256':'cc804e71d86d1e4fbe792a841379db7acb41080d092f6a8b7e16c60a23435c7d'},
 'profile_pin':{'byte_count':5955,'sha256':'50c0b836867a11d826e9f184f9524d7bdec8c350c9d4d9e0329868a9d0a35280'},
 'report_pin':{'byte_count':5139,'sha256':'2c393ee25d03b54686f3645785063ba8566db0ea3ccbce4301bcdf5ff4b3b8b6'},
 'actual_parent_exit':0,'actual_child_exit':0,'actual_validator_exit':0,
 'private_DATA_pin':DATA_PLAN['coverage']}
# Original I case order, deliberately not sorted by whole-binding digest.
E_CASES=(
 (0,'f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986',718,150,((0,0),)),
 (1,'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8',417,87,((73,14),)),
 (2,'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7',417,87,()),
 (3,'1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331',432,90,((151,28),)),
 (4,'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9',302,63,((46,10),(302,63))),
)
META_FIELDS=('table','ticker','permaticker','exchange','isdelisted','category','cusips','figi','currency','firstpricedate','lastpricedate','lastupdated')
PRICE_FLAGS=('identity_admitted','source_admission_granted','price_input_admitted','source_assignment_changed',
 'source_or_processing_rights_granted','point_in_time_proven','formal_forward_ready','paper_or_live_ready','backtest_authority_granted')
SECONDS,MAX_OUTPUT,MAX_PRIVATE=300,131072,8*1024*1024
MAX_MEMBER_BYTES=4*1024*1024
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
ENTRY_DEADLINE=time.monotonic()+SECONDS
ACTIVE_BINDING=None
CLAIM_STATE='unallocated'
FAILURE_STAGE,FAILURE_CASE,PARSER_FAILURE_CODE='preflight',None,None
LEXICAL_EVIDENCE=None
STAGES=frozenset(('preflight','retained_DATA','USB_listing','case_metadata','output'))
PRICE_CODES=frozenset()
GUARD_MODULE=None
GUARD_CODES=frozenset(('scope','plan','deadline','state','shape','path_open','metadata','named_changed','security','security_changed','read_spent','byte_pin','close','receipt'))

EXPECTED_DEMAND={'1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331': ('2025-01-24', 432, 90), 'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8': ('2025-02-14', 417, 87), 'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9': ('2025-08-01', 302, 63), 'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7': ('2025-02-14', 417, 87), 'f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986': ('2023-12-01', 718, 150)}
PERIOD_SHA256='88113155d49f74e00a89ba743aaa314d718cfd0d29b017ac501058460fe5d11a'
E_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'native_book_read': False, 'exact_missing_QC_book_cells_recovered': False, 'genuine_full_package_freshly_authenticated': False, 'actual_target_or_holdings_path_proven': False, 'identity_admitted': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'known_native_gap_resolved': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False, 'historical_or_continuous_integrity_proven': False}
FALSE_FLAGS={'provider_contact': False, 'QC_contact': False, 'Safari_access': False, 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False, 'native_book_read': False, 'exact_missing_QC_book_cells_recovered': False, 'genuine_full_package_freshly_authenticated': False, 'actual_target_or_holdings_path_proven': False, 'identity_admitted': False, 'price_input_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False, 'known_native_gap_resolved': False, 'strategy_result_accepted': False, 'point_in_time_proven': False, 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False, 'historical_or_continuous_integrity_proven': False, 'price_archive_read': False, 'price_rows_read': False, 'metadata_alias_admitted': False, 'actions_evidence_supplied': False, 'relatedtickers_parsed': False}
FINITE=frozenset(('arguments', 'bound', 'changed', 'child_failure', 'child_stderr', 'claim_spent', 'control', 'coverage_record', 'deadline', 'demand', 'environment', 'gap', 'git_state', 'host', 'input', 'listing', 'metadata', 'original_row', 'output', 'path', 'period', 'scope', 'shape', 'source_changed', 'source_pin', 'unknown')) | frozenset("guard_"+value for value in GUARD_CODES)


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
        value=GUARD_MODULE.finite(error)
        return 'guard_'+value if value in GUARD_CODES else 'unknown'
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
    validate_lexical(value['lexical_evidence'], optional=True)
    return value

def validate_lexical(value, *, optional=False):
    """Closed non-sensitive structural counts, never a row-content channel."""
    if optional and value is None:
        return None
    counts = ('byte_count', 'LF_count', 'CRLF_count', 'bare_CR_count',
        'physical_record_count', 'final_record_field_count')
    flags = ('ends_LF', 'ends_CRLF', 'unterminated_final_record',
        'complete_final_record', 'line_endings_consistent', 'line_endings_supported')
    require(type(value) is dict and set(value) == {'schema', *counts, *flags}
        and value['schema'] == 'arv2-r335-firstrate-raw-daily-v3-line-ending-evidence'
        and all(type(value[key]) is int and value[key] >= 0 for key in counts)
        and all(type(value[key]) is bool for key in flags)
        and 0 < value['byte_count'] <= MAX_MEMBER_BYTES
        and value['CRLF_count'] <= value['LF_count']
        and value['LF_count'] + value['CRLF_count'] + value['bare_CR_count'] <= value['byte_count']
        and value['physical_record_count'] == value['LF_count'] + (0 if value['ends_LF'] else 1)
        and value['physical_record_count'] >= 1 and (not value['ends_LF'] or value['LF_count'] > 0)
        and value['unterminated_final_record'] is (not value['ends_LF'])
        and (not value['ends_CRLF'] or value['ends_LF'] and value['CRLF_count'] > 0)
        and (not value['complete_final_record'] or value['final_record_field_count'] == 6)
        and value['final_record_field_count'] <= value['byte_count'] + 1
        and value['line_endings_consistent'] is (value['bare_CR_count'] == 0 and
            value['CRLF_count'] in (0, value['LF_count']))
        and value['line_endings_supported'] is (value['bare_CR_count'] == 0), 'output')
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
        'source_pins':SOURCE_PINS,'data_plan':DATA_PLAN,'USB_root':str(USB),'USB_pins':USB_PINS,
        'retained_E_observation':E_OBSERVATION,'retained_E_case_counts':[list(row[:4])+[[list(pair) for pair in row[4]]] for row in E_CASES],
        'maximum_seconds':SECONDS,'maximum_output_bytes':MAX_OUTPUT,'maximum_private_bytes':MAX_PRIVATE,
        'purpose':'exact_retained_missing_pairs_and_explicit_identity_metadata_leads_not_new_coverage_or_acquisition',
        'case_join':'both_original_case_ordinal_and_whole_binding_hash_never_sorted_digest_order',
        'gap_geometry':'consecutive_positions_in_original_dense_NYSE_required_axis_each_candidate_separate_no_union',
        'alias_leads':['binding.diagnostic_current_ticker','original_row.ticker','current_candidate_rows.ticker'],
        'relatedtickers':'optional_raw_unparsed_never_an_alias_or_identity',
        'listing':'exact_token_only_all_matching_rows_retained_no_name_or_CUSIP_fuzzy_match',
        'listing_match_count_unit':'lead_listing_row_relations_duplicate_tokens_preserved_not_distinct_physical_sources',
        'original_row_hash':'all28fields_frozen_composer_UTF8_ensure_asciiFalse_sorted_JSON_plus_LF',
        'original_serialization_reference':ORIGINAL_SERIALIZATION_REFERENCE,
        'outputs':['claim.json','private-diagnosis.json','report.json'],
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

def load_modules(stack, deadline):
    global GUARD_MODULE
    reference=ORIGINAL_SERIALIZATION_REFERENCE
    held=stack.enter_context(HeldFile(ROOT/reference['relative_path'],maximum=131072,
        expected={key:reference[key] for key in ('byte_count','sha256')},deadline=deadline))
    held.read()
    for relative, expected in SOURCE_PINS.items():
        require(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected), 'source_pin')
        held = stack.enter_context(HeldFile(ROOT / relative, maximum=131072, deadline=deadline))
        require(sha(held.read()) == expected, 'source_pin')
    sys.path[:] = [str(ROOT), *(value for value in sys.path if value and Path(value).is_absolute()
        and Path(value) != ROOT and ROOT not in Path(value).parents)]
    spec = PathFinder.find_spec('scripts', sys.path)
    require(spec is not None and spec.origin is None
        and tuple(spec.submodule_search_locations) == (str(ROOT / 'scripts'),), 'source_pin')
    for relative in SOURCE_PINS:
        name = 'scripts.' + Path(relative).stem
        spec = PathFinder.find_spec(name, [str(ROOT / 'scripts')])
        require(spec is not None and spec.origin == str(ROOT / relative)
            and (name not in sys.modules or getattr(sys.modules[name], '__file__', None) == str(ROOT / relative)), 'source_pin')
    package = importlib.import_module('scripts')
    require(tuple(package.__path__) == (str(ROOT / 'scripts'),), 'source_pin')
    modules = {}
    for key, name in (('guard', 'arv2_r298_fixed_data_guard'), ('anchor', 'arv2_r327_i_source_binding')):
        full = 'scripts.' + name
        module = importlib.import_module(full)
        require(Path(module.__file__) == ROOT / 'scripts' / (name + '.py'), 'source_pin'); modules[key] = module
    GUARD_MODULE=modules['guard']
    require(GUARD_MODULE.FINITE==GUARD_CODES, 'source_pin')
    return modules

def _sessions(values, *, count=None):
    require(type(values) is list and (count is None or len(values) == count)
        and all(type(value) is str and len(value) == 10 for value in values), 'period')
    try: require(all(date.fromisoformat(value).isoformat() == value for value in values), 'period')
    except ValueError: raise Refused('period') from None
    require(values == sorted(set(values)), 'period'); return tuple(values)

def demands(record, expected_summary):
    require(type(record) is dict and set(record) == {'schema', 'source_fingerprint', 'period', 'stock_demand',
        'fund_demand', 'cases', 'metadata_receipt'} and record['schema'] == 'arv2-r327-W5-identity-necessary-demand-i-v1-private'
        and record['source_fingerprint'] == expected_summary['source_fingerprint'], 'input')
    period = record['period']; seed = dict(period); declared = seed.pop('period_sha256')
    require(declared == PERIOD_SHA256 == sha(canonical(seed)), 'period')
    axis = _sessions(period['reference_and_valuation_price_sessions'], count=1243)
    decisions = _sessions(period['decision_sessions'], count=259)
    require(axis[0] == '2021-10-29' and axis[-1] == '2026-10-13'
        and sha(canonical(list(axis))) == period['reference_and_valuation_price_sessions_sha256'], 'period')
    require(type(record['stock_demand']) is list and len(record['stock_demand']) == 6151
        and type(record['fund_demand']) is list and len(record['fund_demand']) == 8
        and type(record['cases']) is list and len(record['cases']) == 5, 'demand')
    positions = {session: index for index, session in enumerate(axis)}; result = []; seen = set()
    for case in record['cases']:
        item = case['original_case']['aa_stock']; row = item['binding']; demand = case['demand']
        whole = sha(canonical(row)); seen.add(whole)
        require(type(case['case_ordinal']) is int and 0 <= case['case_ordinal'] < 5
            and whole == case['whole_binding_sha256'] == demand['whole_binding_sha256'] and whole in EXPECTED_DEMAND
            and demand == record['stock_demand'][item['binding_ordinal']] and demand['potential'] is True
            and demand['source_role'] == 'pending_native_original_identity_source'
            and demand['membership_or_binding_end_used_as_price_end'] is False, 'demand')
        first, required_count, ref_count = EXPECTED_DEMAND[whole]
        required = tuple(session for session in axis if first <= session <= axis[-1])
        eligible = tuple(session for session in decisions if demand['first_eligible_decision'] <= session <= demand['last_eligible_decision'])
        require(demand['required_price_first'] == first and demand['required_price_last'] == axis[-1]
            and len(required) == required_count and len(eligible) == ref_count == demand['eligible_decision_count']
            and sha(canonical(list(eligible))) == demand['eligible_decisions_sha256']
            and all(session in positions and positions[session] > 0 for session in eligible), 'demand')
        references = tuple(axis[positions[session] - 1] for session in eligible)
        ticker = row['diagnostic_current_ticker']
        require(type(ticker) is str and re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,19}', ticker)
            and not ticker.endswith('-DELISTED') and '..' not in ticker, 'demand')
        result.append({'case_ordinal': case['case_ordinal'], 'whole_binding_sha256': whole,
            'ticker': ticker, 'required': required, 'references': references})
    require(seen == set(EXPECTED_DEMAND) and sorted(row['case_ordinal'] for row in result) == list(range(5)), 'demand')
    return result, axis

def listings(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 2 * 1024 * 1024, 'listing')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        require(reader.fieldnames == ['Ticker', 'Name', 'First Date', 'Last Date'], 'listing')
        rows = list(reader)
    except (ValueError, UnicodeError, csv.Error): raise Refused('listing') from None
    require(0 < len(rows) <= 30000 and all(set(row) == set(reader.fieldnames)
        and all(type(value) is str and len(value) <= 1024 for value in row.values()) for row in rows), 'listing')
    return rows

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

def checked_pin(value, maximum):
    require(type(value) is dict and set(value)=={'byte_count','sha256'}
        and type(value['byte_count']) is int and 0<value['byte_count']<=maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']), 'coverage_record')
    return value


def metadata_row(value, *, original=False):
    require(type(value) is dict and (len(value)==28 if original else set(value)==set(META_FIELDS))
        and all(type(key) is str and 0<len(key)<=128 for key in value)
        and all(type(item) is str and len(item)<=8192 for item in value.values()), 'original_row' if original else 'metadata')
    require(all(key in value for key in ('ticker','permaticker','figi','cusips','exchange','currency','firstpricedate','lastpricedate')),
        'original_row' if original else 'metadata')
    return dict(value)


def original_row_bytes(value):
    metadata_row(value,original=True)
    raw=(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
    require(0<len(raw)<=65536,'original_row')
    return raw


def gap_geometry(missing, required, references):
    require(type(missing) is list and all(type(value) is str for value in missing)
        and missing==sorted(set(missing)) and set(missing)<=set(required), 'gap')
    positions={value:index for index,value in enumerate(required)}
    runs=[]
    for value in missing:
        index=positions[value]
        if not runs or index!=runs[-1]['last_position']+1:
            runs.append({'first_date':value,'last_date':value,'first_position':index,'last_position':index,'session_count':1})
        else:
            runs[-1]['last_date']=value;runs[-1]['last_position']=index;runs[-1]['session_count']+=1
    leading=runs[0]['session_count'] if runs and runs[0]['first_position']==0 else 0
    trailing=runs[-1]['session_count'] if runs and runs[-1]['last_position']==len(required)-1 else 0
    # A full-window run is both leading and trailing; count its dates once.
    interior=len(missing)-len({value for run in runs if run['first_position']==0 or run['last_position']==len(required)-1
        for value in required[run['first_position']:run['last_position']+1]})
    refs=[value for value in missing if value in set(references)]
    public={'missing_required_count':len(missing),'missing_reference_count':len(refs),
        'gap_run_count':len(runs),'longest_gap_run':max((run['session_count'] for run in runs),default=0),
        'leading_missing_count':leading,'trailing_missing_count':trailing,'interior_missing_count':interior}
    private={**public,'first_missing_date':missing[0] if missing else None,'last_missing_date':missing[-1] if missing else None,
        'missing_required_sessions':list(missing),'missing_reference_sessions':refs,'runs':runs}
    return public,private


def validate_coverage_record(value, cases, listing_rows):
    require(type(value) is dict and set(value)=={'schema','cases',*E_FLAGS}
        and value['schema']==E_SCHEMA+'-private' and all(value[key] is False for key in E_FLAGS)
        and type(value['cases']) is list and len(value['cases'])==5,'coverage_record')
    actual={}
    for row in value['cases']:
        require(type(row) is dict and set(row)=={'case_ordinal','whole_binding_sha256','ticker','listing_matches','candidates'}
            and type(row['case_ordinal']) is int and 0<=row['case_ordinal']<5
            and type(row['whole_binding_sha256']) is str,'coverage_record')
        key=(row['case_ordinal'],row['whole_binding_sha256'])
        require(key not in actual,'coverage_record');actual[key]=row
    for ordinal,whole,required_count,reference_count,expected_missing in E_CASES:
        key=(ordinal,whole);case=next((item for item in cases if (item['case_ordinal'],item['whole_binding_sha256'])==key),None)
        require(case is not None and key in actual,'coverage_record');row=actual[key]
        ticker=case['ticker']
        require(row['ticker']==ticker and len(case['required'])==required_count and len(case['references'])==reference_count
            and row['listing_matches']==[item for item in listing_rows if item['Ticker'] in (ticker,ticker+'-DELISTED')]
            and type(row['candidates']) is list and len(row['candidates'])==len(expected_missing),'coverage_record')
        allowed={STOCK_DIR+'Tickers_'+ticker[0]+'_Day_Unadjusted_Full_Dataset.zip',
            STOCK_DIR+'1-Day_Unadjusted_2025+_Delisted_tickers.txt',
            *(STOCK_DIR+'1-Day_Unadjusted_Archive_'+str(index)+'.zip' for index in range(1,6))}
        owners=set()
        for candidate,(missing_count,missing_ref_count) in zip(row['candidates'],expected_missing,strict=True):
            require(type(candidate) is dict and set(candidate)=={'archive','container_pin','member_name','member_pin','coverage',
                'lexical_evidence','missing_required_sessions','alias_is_original_identity_proof'}
                and type(candidate['archive']) is str and candidate['archive'] in allowed
                and type(candidate['member_name']) is str and candidate['member_name'] in
                    (ticker+'_full_1day_UNADJUSTED.txt',ticker+'-DELISTED_full_1day_UNADJUSTED.txt')
                and candidate['alias_is_original_identity_proof'] is False,'coverage_record')
            owner=(candidate['archive'],candidate['member_name']);require(owner not in owners,'coverage_record');owners.add(owner)
            checked_pin(candidate['container_pin'],64*1024*1024);checked_pin(candidate['member_pin'],MAX_MEMBER_BYTES)
            lexical=validate_lexical(candidate['lexical_evidence'])
            require(lexical['line_endings_supported'] is True and lexical['complete_final_record'] is True
                and lexical['byte_count']==candidate['member_pin']['byte_count'],'coverage_record')
            coverage=candidate['coverage']
            keys={'schema','member_pin','row_count','selected_row_count','quarantined_row_count','partition_policy_sha256',
                'required_session_count','present_required_count','missing_required_count','reference_session_count',
                'present_reference_count','missing_reference_count','observed_date_coverage_complete',*PRICE_FLAGS}
            count_keys=('row_count','selected_row_count','quarantined_row_count','required_session_count','present_required_count',
                'missing_required_count','reference_session_count','present_reference_count','missing_reference_count')
            require(type(coverage) is dict and set(coverage)==keys
                and coverage['schema']=='arv2-r335-firstrate-raw-daily-v3-coverage'
                and all(type(coverage[key]) is int and 0<=coverage[key]<=30000 for key in count_keys)
                and coverage['row_count']==coverage['selected_row_count']==lexical['physical_record_count']>0
                and coverage['quarantined_row_count']==0
                and coverage['present_required_count']<=coverage['selected_row_count']
                and coverage['partition_policy_sha256'] is None and coverage['member_pin']==candidate['member_pin']
                and coverage['required_session_count']==required_count and coverage['reference_session_count']==reference_count
                and coverage['missing_required_count']==missing_count and coverage['missing_reference_count']==missing_ref_count
                and coverage['present_required_count']==required_count-missing_count
                and coverage['present_reference_count']==reference_count-missing_ref_count
                and coverage['observed_date_coverage_complete'] is (missing_count==0)
                and all(coverage[key] is False for key in PRICE_FLAGS),'coverage_record')
            checked_pin(coverage['member_pin'],MAX_MEMBER_BYTES)
            public,_=gap_geometry(candidate['missing_required_sessions'],case['required'],case['references'])
            require(public['missing_required_count']==missing_count and public['missing_reference_count']==missing_ref_count,'coverage_record')
    require(set(actual)=={(row[0],row[1]) for row in E_CASES},'coverage_record')
    return actual


def parsed_listing_date(value):
    try:return value if type(value) is str and date.fromisoformat(value).isoformat()==value else None
    except ValueError:return None


def metadata_leads(binding, original, current, listing_rows, required):
    by_ticker={}
    for row in listing_rows:by_ticker.setdefault(row['Ticker'],[]).append(row)
    leads=[('binding.diagnostic_current_ticker',None,binding['diagnostic_current_ticker']),('original_row.ticker',None,original['ticker'])]
    leads.extend(('current_candidate_rows.ticker',index,row['ticker']) for index,row in enumerate(current))
    private=[]
    for origin,index,token in leads:
        supported=type(token) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}',token) is not None and '..' not in token
        matches=by_ticker.get(token,[]) if supported else []
        observations=[]
        for row in matches:
            first,last=parsed_listing_date(row['First Date']),parsed_listing_date(row['Last Date'])
            interval_known=first is not None and last is not None and first<=last
            observations.append({'listing_row':dict(row),'date_interval_valid':interval_known,
                'listing_interval_contains_dense_window':bool(interval_known and first<=required[0]<=required[-1]<=last),
                'listing_name_exactly_matches_original_name':None if 'name' not in original else row['Name']==original['name']})
        private.append({'field_origin':origin,'current_row_ordinal':index,'token':token,'token_supported':bool(supported),
            'listing_matches':observations,'metadata_only_not_identity_or_price_coverage':True})
    public={'alias_lead_count':len(private),'supported_alias_lead_count':sum(item['token_supported'] for item in private),
        'exact_listing_match_count':sum(len(item['listing_matches']) for item in private),
        'listing_interval_contains_window_count':sum(obs['listing_interval_contains_dense_window'] for item in private for obs in item['listing_matches'])}
    return public,private


def diagnose(identity, coverage, stock_rows, expected_summary):
    global FAILURE_STAGE,FAILURE_CASE
    cases,_=demands(identity,expected_summary)
    actual=validate_coverage_record(coverage,cases,stock_rows)
    originals={(row['case_ordinal'],row['whole_binding_sha256']):row for row in identity['cases']}
    public,private=[],[]
    for ordinal,whole,required_count,reference_count,expected_missing in E_CASES:
        FAILURE_STAGE,FAILURE_CASE='case_metadata',ordinal
        key=(ordinal,whole);case=next(item for item in cases if (item['case_ordinal'],item['whole_binding_sha256'])==key)
        retained=originals[key];item=retained['original_case']['aa_stock'];binding=item['binding']
        original=metadata_row(item['original_row'],original=True)
        require(sha(original_row_bytes(original))==binding['source_row_sha256'],'original_row')
        current=item['current_candidate_rows']
        require(type(current) is list and len(current)<=4096,'metadata')
        current=[metadata_row(row) for row in current]
        leads_public,leads_private=metadata_leads(binding,original,current,stock_rows,case['required'])
        candidate_public,candidate_private=[],[]
        for candidate_ordinal,candidate in enumerate(actual[key]['candidates']):
            summary,gaps=gap_geometry(candidate['missing_required_sessions'],case['required'],case['references'])
            candidate_public.append({'candidate_ordinal':candidate_ordinal,**summary})
            candidate_private.append({'candidate_ordinal':candidate_ordinal,'archive':candidate['archive'],
                'container_pin':candidate['container_pin'],'member_name':candidate['member_name'],'member_pin':candidate['member_pin'],
                'gap_geometry':gaps})
        no_public,no_private=gap_geometry(list(case['required']) if not candidate_private else [],case['required'],case['references'])
        public.append({'case_ordinal':ordinal,'required_session_count':required_count,'potential_reference_count':reference_count,
            'current_metadata_row_count':len(current),'candidate_count':len(candidate_public),'candidates':candidate_public,
            'no_candidate_gap':no_public,**leads_public,'metadata_leads_are_identity_proof':False})
        private.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'binding':binding,
            'original_row':original,'current_candidate_rows':current,'metadata_leads':leads_private,
            'optional_relatedtickers_raw':original.get('relatedtickers'),'relatedtickers_parse_state':'retained_unparsed' if 'relatedtickers' in original else 'absent',
            'required_sessions':list(case['required']),'potential_reference_sessions':list(case['references']),
            'candidates':candidate_private,'no_candidate_gap':no_private,'source_assignment_changed':False,
            'original_metadata_hash_rechecked':True})
    return public,{'schema':SCHEMA+'-private','input_DATA_pins':DATA_PLAN,'retained_E_observation':E_OBSERVATION,
        'cases':private,**FALSE_FLAGS}


def worker(args,deadline):
    global FAILURE_STAGE,FAILURE_CASE
    require(type(args.intent_fd) is int and args.intent_fd>=3,'arguments')
    try:intent=os.read(args.intent_fd,4097)
    finally:os.close(args.intent_fd)
    require(intent==canonical(binding(args)),'arguments')
    preflight(args,deadline)
    with ExitStack() as sources:
        modules=load_modules(sources,deadline)
        with Store(modules['guard'].security) as store:
            store.write('claim.json',canonical({'binding':binding(args),'profile':profile_record()}))
            FAILURE_STAGE='retained_DATA'
            with modules['guard'].FixedDataGuard(DATA_PLAN,deadline=deadline) as guarded:
                raw=guarded.read_all_once();identity=parse(raw['identity'],DATA_PLAN['identity']['byte_count'])
                coverage=parse(raw['coverage'],DATA_PLAN['coverage']['byte_count'])
                fact=modules['anchor'].observed_fact();require(fact['private_data']==DATA_PLAN['identity'],'input')
                FAILURE_STAGE='USB_listing'
                relative=next(iter(USB_PINS))
                held=sources.enter_context(HeldFile(USB/relative,maximum=2*1024*1024,expected=USB_PINS[relative],deadline=deadline))
                stock_rows=listings(held.read())
                public,private=diagnose(identity,coverage,stock_rows,fact['result']['identity_summary'])
                guarded.verify();receipt=guarded.receipt();budget(deadline)
            sources.close();FAILURE_STAGE,FAILURE_CASE='output',None
            private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE,'output')
            private_pin=store.write('private-diagnosis.json',private_raw)
            result={'schema':SCHEMA,'complete':True,'cases':public,'retained_DATA_authenticated':True,
                'source_guard_normal_return':True,'source_receipt_sha256':sha(canonical(receipt)),
                'retained_E_observation_sha256':sha(canonical(E_OBSERVATION)),'private_pin':private_pin,**FALSE_FLAGS}
            validate_result(result);preflight(args,deadline)
            report={'binding':binding(args),'result':result}
            report_pin=store.write('report.json',canonical(report));budget(deadline)
            return {**report,'report_pin':report_pin}


def validate_gap_summary(value,required_count,reference_count):
    keys=('missing_required_count','missing_reference_count','gap_run_count','longest_gap_run',
        'leading_missing_count','trailing_missing_count','interior_missing_count')
    require(type(value) is dict and set(value)==set(keys) and all(type(value[key]) is int and value[key]>=0 for key in keys)
        and value['missing_required_count']<=required_count and value['missing_reference_count']<=reference_count
        and value['missing_reference_count']<=value['missing_required_count']
        and value['gap_run_count']<=value['missing_required_count']
        and value['longest_gap_run']<=value['missing_required_count']
        and all(value[key]<=value['missing_required_count'] for key in keys[4:])
        and (value['missing_required_count']>0 or all(value[key]==0 for key in keys)), 'output')
    missing=value['missing_required_count']
    if missing:
        require(1<=value['gap_run_count']<=missing and 1<=value['longest_gap_run']<=missing
            and value['longest_gap_run']*value['gap_run_count']>=missing
            and value['longest_gap_run']>=max(value['leading_missing_count'],value['trailing_missing_count']), 'output')
        if missing==required_count:
            require(value['gap_run_count']==1 and value['longest_gap_run']==missing
                and value['leading_missing_count']==value['trailing_missing_count']==missing
                and value['interior_missing_count']==0,'output')
        else:
            require(value['leading_missing_count']+value['trailing_missing_count']+value['interior_missing_count']==missing,'output')
    return value


def validate_result(value):
    require(type(value) is dict and set(value)=={'schema','complete','cases','retained_DATA_authenticated',
        'source_guard_normal_return','source_receipt_sha256','retained_E_observation_sha256','private_pin',*FALSE_FLAGS}
        and value['schema']==SCHEMA and value['complete'] is True
        and value['retained_DATA_authenticated'] is value['source_guard_normal_return'] is True
        and value['retained_E_observation_sha256']==sha(canonical(E_OBSERVATION))
        and all(value[key] is False for key in FALSE_FLAGS)
        and type(value['source_receipt_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['source_receipt_sha256'])
        and type(value['cases']) is list and len(value['cases'])==5,'output')
    checked_pin(value['private_pin'],MAX_PRIVATE)
    for row,(ordinal,whole,required_count,reference_count,missing) in zip(value['cases'],E_CASES,strict=True):
        require(type(row) is dict and set(row)=={'case_ordinal','required_session_count','potential_reference_count',
            'current_metadata_row_count','candidate_count','candidates','no_candidate_gap','alias_lead_count',
            'supported_alias_lead_count','exact_listing_match_count','listing_interval_contains_window_count','metadata_leads_are_identity_proof'}
            and type(row['case_ordinal']) is int and row['case_ordinal']==ordinal
            and type(row['required_session_count']) is int and row['required_session_count']==required_count
            and type(row['potential_reference_count']) is int and row['potential_reference_count']==reference_count
            and type(row['candidate_count']) is int and row['candidate_count']==len(missing)
            and type(row['candidates']) is list and len(row['candidates'])==len(missing)
            and type(row['current_metadata_row_count']) is int and 0<=row['current_metadata_row_count']<=4096
            and type(row['alias_lead_count']) is int and row['alias_lead_count']==row['current_metadata_row_count']+2
            and type(row['supported_alias_lead_count']) is int and 0<=row['supported_alias_lead_count']<=row['alias_lead_count']
            and type(row['exact_listing_match_count']) is int and 0<=row['exact_listing_match_count']<=30000*row['alias_lead_count']
            and type(row['listing_interval_contains_window_count']) is int and 0<=row['listing_interval_contains_window_count']<=row['exact_listing_match_count']
            and row['metadata_leads_are_identity_proof'] is False,'output')
        for index,(candidate,(missing_count,missing_refs)) in enumerate(zip(row['candidates'],missing,strict=True)):
            require(type(candidate) is dict and set(candidate)=={'candidate_ordinal','missing_required_count','missing_reference_count','gap_run_count',
                'longest_gap_run','leading_missing_count','trailing_missing_count','interior_missing_count'}
                and type(candidate['candidate_ordinal']) is int and candidate['candidate_ordinal']==index,'output')
            summary={key:item for key,item in candidate.items() if key!='candidate_ordinal'}
            validate_gap_summary(summary,required_count,reference_count)
            require((summary['missing_required_count'],summary['missing_reference_count'])==(missing_count,missing_refs),'output')
        no=validate_gap_summary(row['no_candidate_gap'],required_count,reference_count)
        require(no['missing_required_count']==(required_count if not missing else 0)
            and no['missing_reference_count']==(reference_count if not missing else 0),'output')
    return value


def native_profile():
    value = '(version 1)(allow default)(deny network*)(deny file-write* (subpath "/Volumes/SANDISK"))'
    value += ''.join('(deny file-read* file-write* (subpath "' + path + '"))' for path in
        ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath "' + str(CONTROL) + '"))'
    value += '(require-not (literal "' + str(CONTROL.parent) + '"))(require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))(require-not (literal "/dev/null"))))'
    paths = [*(ROOT / item['relative_path'] for item in DATA_PLAN.values()), CONTROL]
    allowed = {path for leaf in paths for path in (*leaf.parents, leaf) if path == ROOT / 'artifacts' or ROOT / 'artifacts' in path.parents}
    value += '(deny file-read* (require-all (subpath "' + str(ROOT / 'artifacts') + '")'
    value += '(require-not (subpath "' + str(CONTROL) + '"))'
    value += ''.join('(require-not (literal "' + str(path) + '"))' for path in sorted(allowed)) + '))'
    usb_paths = [USB / name for name in (*USB_PINS, *ARCHIVES)]
    usb_allowed = {path for leaf in usb_paths for path in (*leaf.parents, leaf) if path == USB or USB in path.parents}
    value += '(deny file-read* (require-all (subpath "' + str(USB) + '")'
    value += ''.join('(require-not (literal "' + str(path) + '"))' for path in sorted(usb_allowed)) + '))'
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
