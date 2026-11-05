"""One new offline FirstRate coverage observation, never price admission.

Only one fixed retained identity-demand DATA leaf and the explicitly named USB
sources are consumed. A native child exclusively claims before reading DATA.
All old callers/claims, QC books, providers and credentials remain unavailable.
The complete five potential exposure envelopes are examined, not actual holdings
or a reconstructed list of missing QC book cells. Ticker candidates stay private
and unresolved: finding a dated bar does not identify a security or admit it.
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
import zipfile

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'scripts/inspect_arv2_r335_firstrate_coverage.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/firstrate/R335-20261103-A'
USB = Path('/Volumes/SANDISK/firstrate')
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r335-offline-firstrate-coverage-v1'
DATA_PLAN = {'identity': {
    'relative_path': 'artifacts/analyst_revisions_v2/newrule_available_history_identity/R327-20261027-I/identity-demand-private.json',
    'byte_count': 4984462, 'sha256': 'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'}}
USB_PINS = {
    'manifest.json': {'byte_count': 327907, 'sha256': 'c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8'},
    'market/Stocks_Complete_10_000+_Tickers/Ticker_Listing.txt': {
        'byte_count': 889580, 'sha256': '584718095d81d576af0f83d6f31d5cda565e59ea2c6677e5b164e0db39e93464'},
    'market/ETF-Complete_5000+_Tickers/Ticker_Listing.txt': {
        'byte_count': 355087, 'sha256': '4532194e351a00a51b0e379b4df86f20bd92aa9a98f8110f81ff9d90c112f559'}}
# Filled from the exact pre-use public implementation, never refreshed at runtime.
SOURCE_PINS = {
    'scripts/arv2_r298_fixed_data_guard.py': '00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145',
    'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
    'scripts/arv2_r327_i_source_binding.py': '44405001183804020d8b211d79846d8ea70019758059cc73878cca883bac6416',
    'scripts/arv2_r335_remx_identity.py': '8f124b390a3f81a0f50354d99f34b12d4c1cd8d5d2270661e58da5da4fefae63',
    'scripts/arv2_r335_firstrate_prices.py': '53a136d12f5e2979cfbec6395e57923078a398316fb6bab0678fb50db79d3868',
}
EXPECTED_DEMAND = {
    '1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331': ('2025-01-24', 432, 90),
    'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8': ('2025-02-14', 417, 87),
    'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9': ('2025-08-01', 302, 63),
    'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7': ('2025-02-14', 417, 87),
    'f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986': ('2023-12-01', 718, 150),
}
PERIOD_SHA256 = '88113155d49f74e00a89ba743aaa314d718cfd0d29b017ac501058460fe5d11a'
STOCK_DIR = 'market/Stocks_Complete_10_000+_Tickers/'
ETF_DIR = 'market/ETF-Complete_5000+_Tickers/'
CURRENT_ARCHIVES = tuple(STOCK_DIR + f'Tickers_{letter}_Day_Unadjusted_Full_Dataset.zip' for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
DELISTED_ARCHIVES = tuple(STOCK_DIR + f'1-Day_Unadjusted_Archive_{number}.zip' for number in range(1, 6)) + (
    STOCK_DIR + '1-Day_Unadjusted_2025+_Delisted_tickers.txt',)
REMX_ARCHIVE = ETF_DIR + 'Tickers_R_Day_Unadjusted_Full_Dataset.zip'
REMX_MEMBER = 'REMX_full_1day_UNADJUSTED.txt'
REMX_PIN = {'byte_count': 181222, 'sha256': 'b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e'}
ARCHIVES = (*CURRENT_ARCHIVES, *DELISTED_ARCHIVES, REMX_ARCHIVE)
SECONDS, MAX_OUTPUT, MAX_PRIVATE = 300, 131072, 1024 * 1024
MAX_ZIP_BYTES, MAX_MEMBERS, MAX_MEMBER_BYTES = 64 * 1024 * 1024, 20000, 4 * 1024 * 1024
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FALSE_FLAGS = {'provider_contact': False, 'QC_contact': False, 'Safari_access': False,
    'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False,
    'native_book_read': False, 'exact_missing_QC_book_cells_recovered': False,
    'genuine_full_package_freshly_authenticated': False, 'actual_target_or_holdings_path_proven': False,
    'identity_admitted': False, 'price_input_admitted': False, 'source_assignment_changed': False,
    'source_or_processing_rights_granted': False, 'known_native_gap_resolved': False,
    'strategy_result_accepted': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False,
    'historical_or_continuous_integrity_proven': False}
FINITE = frozenset(('arguments', 'host', 'environment', 'git_state', 'source_pin', 'source_changed',
    'scope', 'deadline', 'bound', 'claim_spent', 'control', 'path', 'shape', 'metadata', 'changed',
    'input', 'period', 'demand', 'listing', 'manifest', 'archive', 'member', 'price_parse',
    'partition', 'output', 'child_stderr', 'child_failure', 'unknown'))
ENTRY_DEADLINE = time.monotonic() + SECONDS
ACTIVE_BINDING = None
CLAIM_STATE = 'unallocated'
FAILURE_STAGE, FAILURE_CASE, PARSER_FAILURE_CODE = 'preflight', None, None
STAGES = frozenset(('preflight', 'retained_identity', 'USB_manifest', 'USB_listings',
    'stock_candidate', 'REMX_partition', 'output'))
PRICE_CODES = frozenset(('bytes', 'pin', 'member', 'encoding', 'line_ending', 'row_bound',
    'row_shape', 'session', 'timestamp', 'date_order', 'number', 'price', 'OHLC',
    'volume', 'series', 'calendar', 'reference_scope', 'partition', 'partition_once', 'unknown'))


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
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
        return args[0]
    return 'deadline' if isinstance(error, TimeoutError) else 'unknown'


def failure_packet(code):
    require(type(code) is str and code in FINITE, 'output')
    return {'schema': SCHEMA, 'binding': ACTIVE_BINDING, 'failure_code': code,
        'stage': FAILURE_STAGE, 'case_ordinal': FAILURE_CASE, 'parser_failure_code': PARSER_FAILURE_CODE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE, **FALSE_FLAGS}


def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'parser_failure_code', 'attempt_reusable', 'claim_state', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
        and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
        and value['stage'] in STAGES and (value['case_ordinal'] is None or
            type(value['case_ordinal']) is int and 0 <= value['case_ordinal'] < 5)
        and (value['parser_failure_code'] is None or type(value['parser_failure_code']) is str
            and value['parser_failure_code'] in PRICE_CODES)
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
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': PYTHON,
        'control': str(CONTROL), 'source_pins': SOURCE_PINS, 'data_plan': DATA_PLAN,
        'USB_root': str(USB), 'USB_pins': USB_PINS, 'allowed_archives': list(ARCHIVES),
        'maximum_seconds': SECONDS, 'maximum_output_bytes': MAX_OUTPUT,
        'maximum_private_bytes': MAX_PRIVATE, 'maximum_archive_bytes': MAX_ZIP_BYTES,
        'maximum_members_per_archive': MAX_MEMBERS, 'maximum_member_bytes': MAX_MEMBER_BYTES,
        'selection': 'exact_five_original_ticker_or_ticker_DELISTED_members_no_alias_or_fuzzy_match',
        'scope': 'all_five_W5_dense_envelopes_and_hash_verified_potential_reference_sessions_plus_exact_REMX_partition',
        'archive_integrity': 'externally_pinned_local_manifest_MD5_then_current_held_container_SHA256_and_member_CRC_SHA256',
        'local_manifest_is_vendor_authentication': False, 'USB_native_ACL_xattr_authentication_claimed': False,
        'claim_before_retained_DATA_or_USB_read': True, 'normal_source_guard_return_before_publication': True,
        'private_output': 'candidate_names_listing_matches_date_gaps_only_no_price_marks_or_admission',
        'deadline_limitation': 'uninterruptible_IO_or_host_suspension_not_bounded', **FALSE_FLAGS}


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
    for key, name in (('guard', 'arv2_r298_fixed_data_guard'), ('anchor', 'arv2_r327_i_source_binding'),
            ('prices', 'arv2_r335_firstrate_prices')):
        full = 'scripts.' + name
        module = importlib.import_module(full)
        require(Path(module.__file__) == ROOT / 'scripts' / (name + '.py'), 'source_pin'); modules[key] = module
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


def manifest_entry(manifest, relative):
    require(relative in ARCHIVES, 'scope')
    key = relative[:-4] if relative.endswith(('.zip', '.txt')) else relative
    value = manifest.get(key)
    require(type(value) is dict and set(value) == {'path', 'bytes', 'md5', 'ok', 'fetched', 'url'}
        and value['ok'] is True and type(value['bytes']) is int and 0 < value['bytes'] <= MAX_ZIP_BYTES
        and type(value['md5']) is str and re.fullmatch('[0-9a-fA-F]{32}', value['md5']), 'manifest')
    return {'byte_count': value['bytes'], 'md5': value['md5'].lower()}


class Archive:
    def __init__(self, held, expected):
        self.held, self.expected, self.zip, self.file, self.container_pin = held, expected, None, None, None

    def __enter__(self):
        require(self.held.info[6] == self.expected['byte_count'], 'archive')
        self.held.verify(); digest, transport, offset = hashlib.sha256(), hashlib.md5(), 0
        while offset < self.held.info[6]:
            budget(self.held.deadline); raw = os.pread(self.held.fd, min(65536, self.held.info[6] - offset), offset)
            require(raw, 'archive'); digest.update(raw); transport.update(raw); offset += len(raw)
        require(offset == self.expected['byte_count'] and transport.hexdigest() == self.expected['md5'], 'archive')
        self.container_pin = {'byte_count': offset, 'sha256': digest.hexdigest()}
        self.held.verify(); self.file = os.fdopen(os.dup(self.held.fd), 'rb')
        try:
            self.zip = zipfile.ZipFile(self.file)
            infos = self.zip.infolist()
            require(0 < len(infos) <= MAX_MEMBERS and len({item.filename for item in infos}) == len(infos), 'archive')
            return self
        except BaseException:
            self.__exit__(None, None, None); raise

    def member(self, name):
        self.held.verify()
        found = [item for item in self.zip.infolist() if item.filename == name]
        require(len(found) <= 1, 'member')
        if not found: return None
        item = found[0]
        require(not item.is_dir() and '/' not in name and '\\' not in name and not item.flag_bits & 1
            and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            and not stat.S_ISLNK(item.external_attr >> 16) and 0 < item.file_size <= MAX_MEMBER_BYTES
            and item.file_size <= max(1, item.compress_size) * 1000, 'member')
        try: raw = self.zip.read(item)
        except (zipfile.BadZipFile, RuntimeError, OSError, ValueError): raise Refused('member') from None
        require(len(raw) == item.file_size, 'member'); self.held.verify(); return raw

    def __exit__(self, *_):
        if self.zip is not None: self.zip.close()
        if self.file is not None: self.file.close()
        self.held.verify()


def study(cases, axis, stock_rows, etf_rows, archive_for, prices):
    global FAILURE_STAGE, FAILURE_CASE, PARSER_FAILURE_CODE
    public, private = [], []
    for case in cases:
        FAILURE_STAGE, FAILURE_CASE = 'stock_candidate', case['case_ordinal']
        ticker = case['ticker']; candidates = []
        relevant = (STOCK_DIR + f'Tickers_{ticker[0]}_Day_Unadjusted_Full_Dataset.zip', *DELISTED_ARCHIVES)
        for relative in relevant:
            archive = archive_for(relative)
            for alias in (ticker, ticker + '-DELISTED'):
                member = alias + '_full_1day_UNADJUSTED.txt'; raw = archive.member(member)
                if raw is None: continue
                try:
                    series = prices.parse_daily(raw, expected_pin=pin(raw), member_name=member, expected_ticker=alias)
                    coverage = prices.assess_coverage(series, case['required'], reference_sessions=case['references'])
                    missing = prices.private_missing_sessions(series, case['required'])
                except Exception as error:
                    if type(error) is getattr(prices, 'Refused', None):
                        code = prices.finite(error)
                        if type(code) is str and code in PRICE_CODES: PARSER_FAILURE_CODE = code
                    raise Refused('price_parse') from None
                candidates.append({'archive': relative, 'container_pin': archive.container_pin,
                    'member_name': member, 'member_pin': pin(raw), 'coverage': coverage,
                    'missing_required_sessions': list(missing), 'alias_is_original_identity_proof': False})
        complete = sum(item['coverage']['observed_date_coverage_complete'] is True for item in candidates)
        public.append({'case_ordinal': case['case_ordinal'], 'required_session_count': len(case['required']),
            'potential_reference_count': len(case['references']), 'candidate_count': len(candidates),
            'date_complete_candidate_count': complete, 'source_state': 'finite_missing' if not candidates else
                'one_candidate_unadmitted' if len(candidates) == 1 else 'ambiguous_candidates_unadmitted',
            'candidate_counts': [{key: item['coverage'][key] for key in ('present_required_count',
                'missing_required_count', 'present_reference_count', 'missing_reference_count')} for item in candidates],
            'identity_admitted': False, 'price_input_admitted': False})
        private.append({'case_ordinal': case['case_ordinal'], 'whole_binding_sha256': case['whole_binding_sha256'],
            'ticker': ticker, 'listing_matches': [row for row in stock_rows if row['Ticker'] in (ticker, ticker + '-DELISTED')],
            'candidates': candidates})
    FAILURE_STAGE, FAILURE_CASE = 'REMX_partition', None
    remx_rows = [row for row in etf_rows if row['Ticker'] == 'REMX']; require(len(remx_rows) == 1, 'listing')
    archive = archive_for(REMX_ARCHIVE); raw = archive.member(REMX_MEMBER)
    require(type(raw) is bytes and pin(raw) == REMX_PIN, 'partition')
    listing = remx_rows[0]
    try:
        series = prices.parse_daily(raw, expected_pin=REMX_PIN, member_name=REMX_MEMBER, expected_ticker='REMX')
        series = prices.apply_remx_partition(series, listing={'name': listing['Name'],
            'first_date': listing['First Date'], 'last_date': listing['Last Date']})
        coverage = prices.assess_coverage(series, axis)
    except Exception as error:
        if type(error) is getattr(prices, 'Refused', None):
            code = prices.finite(error)
            if type(code) is str and code in PRICE_CODES: PARSER_FAILURE_CODE = code
        raise Refused('partition') from None
    remx_public = {key: coverage[key] for key in ('row_count', 'selected_row_count', 'quarantined_row_count',
        'required_session_count', 'present_required_count', 'missing_required_count', 'observed_date_coverage_complete')}
    remx_public.update({'exact_partition_validated': True, 'identity_admitted': False, 'price_input_admitted': False})
    return public, {'schema': SCHEMA + '-private', 'cases': private, 'REMX': {
        'container_pin': archive.container_pin, 'member_pin': REMX_PIN, 'partition': remx_public,
        'original_USB_member_preserved': True}, **FALSE_FLAGS}, remx_public


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


def worker(args, deadline):
    global FAILURE_STAGE, FAILURE_CASE
    require(type(args.intent_fd) is int and args.intent_fd >= 3, 'arguments')
    try: intent = os.read(args.intent_fd, 4097)
    finally: os.close(args.intent_fd)
    require(intent == canonical(binding(args)), 'arguments')
    preflight(args, deadline)
    with ExitStack() as sources:
        modules = load_modules(sources, deadline)
        with Store(modules['guard'].security) as store:
            store.write('claim.json', canonical({'binding': binding(args), 'profile': profile_record()}))
            FAILURE_STAGE = 'retained_identity'
            with modules['guard'].FixedDataGuard(DATA_PLAN, deadline=deadline) as guarded:
                identity_raw = guarded.read_all_once()['identity']
                record = parse(identity_raw, DATA_PLAN['identity']['byte_count'])
                fact = modules['anchor'].observed_fact()
                require(fact['private_data'] == DATA_PLAN['identity'], 'input')
                cases, axis = demands(record, fact['result']['identity_summary'])
                fixed = {}
                for relative, expected in USB_PINS.items():
                    FAILURE_STAGE = 'USB_manifest' if relative == 'manifest.json' else 'USB_listings'
                    held = sources.enter_context(HeldFile(USB / relative, maximum=2 * 1024 * 1024,
                        expected=expected, deadline=deadline)); fixed[relative] = held.read()
                manifest = parse(fixed['manifest.json'], USB_PINS['manifest.json']['byte_count'])
                stock_rows = listings(fixed[STOCK_DIR + 'Ticker_Listing.txt'])
                etf_rows = listings(fixed[ETF_DIR + 'Ticker_Listing.txt'])
                archives = {}
                def archive_for(relative):
                    require(relative in ARCHIVES, 'scope')
                    if relative not in archives:
                        expected = manifest_entry(manifest, relative)
                        held = sources.enter_context(HeldFile(USB / relative, maximum=MAX_ZIP_BYTES, deadline=deadline))
                        archives[relative] = sources.enter_context(Archive(held, expected))
                    return archives[relative]
                public, private, remx = study(cases, axis, stock_rows, etf_rows, archive_for, modules['prices'])
                guarded.verify(); receipt = guarded.receipt()
                budget(deadline)
            # Normal DATA guard return is necessary, but current USB/public
            # descriptors must also return normally before publication.
            archive_count = len(archives)
            sources.close()
            FAILURE_STAGE, FAILURE_CASE = 'output', None
            private_raw = canonical(private); require(len(private_raw) <= MAX_PRIVATE, 'output')
            private_pin = store.write('private-diagnosis.json', private_raw)
            result = {'schema': SCHEMA, 'complete': True, 'case_count': len(public), 'cases': public,
                'required_session_count': sum(row['required_session_count'] for row in public),
                'potential_reference_count': sum(row['potential_reference_count'] for row in public),
                'archive_count': archive_count, 'REMX': remx, 'private_pin': private_pin,
                'retained_identity_DATA_authenticated': True, 'source_guard_normal_return': True,
                'retained_identity_receipt_sha256': sha(canonical(receipt)), **FALSE_FLAGS}
            validate_result(result)
            preflight(args, deadline)
            report = {'binding': binding(args), 'result': result}
            report_pin = store.write('report.json', canonical(report)); budget(deadline)
            return {**report, 'report_pin': report_pin}


def validate_result(value):
    require(type(value) is dict and set(value) == {'schema', 'complete', 'case_count', 'cases', 'required_session_count',
        'potential_reference_count', 'archive_count', 'REMX', 'private_pin', 'retained_identity_DATA_authenticated',
        'source_guard_normal_return', 'retained_identity_receipt_sha256', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['complete'] is True and type(value['case_count']) is int and value['case_count'] == 5
        and type(value['required_session_count']) is int and value['required_session_count'] == 2286
        and type(value['potential_reference_count']) is int and value['potential_reference_count'] == 477
        and type(value['archive_count']) is int and 1 <= value['archive_count'] <= 12
        and value['retained_identity_DATA_authenticated'] is value['source_guard_normal_return'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    require(type(value['cases']) is list and len(value['cases']) == 5
        and all(type(row['case_ordinal']) is int for row in value['cases'])
        and sorted(row['case_ordinal'] for row in value['cases']) == list(range(5))
        and sorted((row['required_session_count'], row['potential_reference_count']) for row in value['cases'])
            == sorted((row[1], row[2]) for row in EXPECTED_DEMAND.values()), 'output')
    for row in value['cases']:
        require(set(row) == {'case_ordinal', 'required_session_count', 'potential_reference_count', 'candidate_count',
            'date_complete_candidate_count', 'source_state', 'candidate_counts', 'identity_admitted', 'price_input_admitted'}
            and type(row['required_session_count']) is type(row['potential_reference_count']) is int
            and type(row['candidate_count']) is int and 0 <= row['candidate_count'] <= 14
            and type(row['date_complete_candidate_count']) is int
            and 0 <= row['date_complete_candidate_count'] <= row['candidate_count']
            and len(row['candidate_counts']) == row['candidate_count']
            and row['identity_admitted'] is row['price_input_admitted'] is False
            and row['source_state'] == ('finite_missing' if row['candidate_count'] == 0 else
                'one_candidate_unadmitted' if row['candidate_count'] == 1 else 'ambiguous_candidates_unadmitted')
            and row['date_complete_candidate_count'] == sum(item['missing_required_count'] == 0
                for item in row['candidate_counts']), 'output')
        for item in row['candidate_counts']:
            require(set(item) == {'present_required_count', 'missing_required_count', 'present_reference_count', 'missing_reference_count'}
                and all(type(count) is int and count >= 0 for count in item.values())
                and item['present_required_count'] + item['missing_required_count'] == row['required_session_count']
                and item['present_reference_count'] + item['missing_reference_count'] == row['potential_reference_count']
                and item['missing_reference_count'] <= item['missing_required_count']
                and item['present_reference_count'] <= item['present_required_count'], 'output')
    require(value['REMX'] == {'row_count': 4339, 'selected_row_count': 4016, 'quarantined_row_count': 323,
        'required_session_count': 1243, 'present_required_count': 1243, 'missing_required_count': 0,
        'observed_date_coverage_complete': True, 'exact_partition_validated': True,
        'identity_admitted': False, 'price_input_admitted': False}, 'output')
    require(all(type(value['REMX'][key]) is int for key in ('row_count', 'selected_row_count',
        'quarantined_row_count', 'required_session_count', 'present_required_count', 'missing_required_count'))
        and value['REMX']['observed_date_coverage_complete'] is value['REMX']['exact_partition_validated'] is True
        and value['REMX']['identity_admitted'] is value['REMX']['price_input_admitted'] is False, 'output')
    require(type(value['private_pin']) is dict and set(value['private_pin']) == {'byte_count', 'sha256'}
        and type(value['private_pin']['byte_count']) is int and 0 < value['private_pin']['byte_count'] <= MAX_PRIVATE
        and type(value['private_pin']['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['private_pin']['sha256'])
        and type(value['retained_identity_receipt_sha256']) is str
        and re.fullmatch('[0-9a-f]{64}', value['retained_identity_receipt_sha256']), 'output')
    return value


def native_profile():
    value = '(version 1)(allow default)(deny network*)(deny file-write* (subpath "/Volumes/SANDISK"))'
    value += ''.join('(deny file-read* file-write* (subpath "' + path + '"))' for path in
        ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath "' + str(CONTROL) + '"))'
    value += '(require-not (literal "' + str(CONTROL.parent) + '"))(require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))(require-not (literal "/dev/null"))))'
    paths = [ROOT / DATA_PLAN['identity']['relative_path'], CONTROL]
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
