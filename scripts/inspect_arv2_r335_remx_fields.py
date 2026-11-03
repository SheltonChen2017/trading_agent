"""One exact REMX field-shape observation; no normalization or price admission.

The fixed full member is authenticated before all rows are examined. Volume
classes are counts only over two exact source eras. Unsafe volume shapes are
observations, never accepted or repaired inputs. Shape, date, price and OHLC
errors refuse. No retained identity DATA, stock archives, QC or credentials.
"""
import argparse
import csv
from contextlib import ExitStack
from datetime import date
from decimal import Decimal, InvalidOperation
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
SOURCE = ROOT / 'scripts/inspect_arv2_r335_remx_fields.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/firstrate/R335-20261103-D'
USB = Path('/Volumes/SANDISK/firstrate')
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r335-offline-REMX-fields-v1'
SOURCE_PINS = {
 'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
 'scripts/arv2_r335_remx_identity.py': '8f124b390a3f81a0f50354d99f34b12d4c1cd8d5d2270661e58da5da4fefae63',
}
ETF_DIR = 'market/ETF-Complete_5000+_Tickers/'
USB_PINS = {
 'manifest.json': {'byte_count': 327907, 'sha256': 'c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8'},
 ETF_DIR + 'Ticker_Listing.txt': {'byte_count': 355087, 'sha256': '4532194e351a00a51b0e379b4df86f20bd92aa9a98f8110f81ff9d90c112f559'},
}
REMX_ARCHIVE = ETF_DIR + 'Tickers_R_Day_Unadjusted_Full_Dataset.zip'
REMX_MEMBER = 'REMX_full_1day_UNADJUSTED.txt'
REMX_PIN = {'byte_count': 181222, 'sha256': 'b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e'}
ARCHIVES = (REMX_ARCHIVE,)
ERAS = ((0, '2005-01-04', '2006-06-30', 323), (1, '2010-10-28', '2026-10-16', 4016))
VOLUME_CLASSES = ('integer_nonnegative_count', 'fractional_nonnegative_count', 'negative_finite_count', 'nonfinite_count', 'malformed_count')
VOLUME_LEXICAL_COUNTS = ('unsigned_decimal_lexical_count', 'decimal_point_lexical_count', 'exponent_lexical_count', 'signed_lexical_count')
SECONDS, MAX_OUTPUT, MAX_PRIVATE = 300, 131072, 131072
MAX_ZIP_BYTES, MAX_MEMBERS, MAX_MEMBER_BYTES = 64 * 1024 * 1024, 20000, 4 * 1024 * 1024
MAX_LINE_BYTES = 640
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FALSE_FLAGS = {'provider_contact': False, 'QC_contact': False, 'Safari_access': False,
 'credential_access': False, 'old_control_read': False, 'old_operation_replayed': False,
 'retained_identity_DATA_read': False, 'stock_archive_read': False, 'native_book_read': False,
 'original_member_modified': False, 'volume_normalized': False, 'price_input_admitted': False,
 'identity_admitted': False, 'source_assignment_changed': False, 'source_or_processing_rights_granted': False,
 'known_native_gap_resolved': False, 'strategy_result_accepted': False, 'point_in_time_proven': False,
 'formal_forward_ready': False, 'paper_or_live_ready': False, 'licensed_rows_disclosed': False,
 'historical_or_continuous_integrity_proven': False}
FINITE = frozenset(('arguments', 'host', 'environment', 'git_state', 'source_pin', 'source_changed',
 'scope', 'deadline', 'bound', 'claim_spent', 'control', 'path', 'shape', 'metadata', 'changed',
 'input', 'listing', 'manifest', 'archive', 'member', 'bytes', 'encoding', 'line_ending', 'row_bound',
 'row_shape', 'session', 'timestamp', 'date_order', 'number', 'price', 'OHLC', 'partition',
 'output', 'child_stderr', 'child_failure', 'unknown'))
ENTRY_DEADLINE = time.monotonic() + SECONDS
ACTIVE_BINDING = None
CLAIM_STATE = 'unallocated'
FAILURE_STAGE, FAILURE_CASE, PARSER_FAILURE_CODE = 'preflight', None, None
LEXICAL_EVIDENCE = None
STAGES = frozenset(('preflight', 'USB_manifest', 'USB_listing', 'REMX_fields', 'output'))


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
        'lexical_evidence': LEXICAL_EVIDENCE,
        'attempt_reusable': False, 'claim_state': CLAIM_STATE, **FALSE_FLAGS}

def validate_failure(value, args):
    require(type(value) is dict and set(value) == {'schema', 'binding', 'failure_code',
        'stage', 'case_ordinal', 'parser_failure_code', 'lexical_evidence', 'attempt_reusable', 'claim_state', *FALSE_FLAGS}
        and value['schema'] == SCHEMA
        and value['binding'] == binding(args) and type(value['failure_code']) is str
        and value['failure_code'] in FINITE and value['attempt_reusable'] is False
        and value['claim_state'] in ('unallocated', 'allocated_unknown', 'consumed', 'consumed_or_unknown')
        and value['stage'] in STAGES and value['case_ordinal'] is None
        and value['parser_failure_code'] is None
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
        and value['schema'] == SCHEMA + '-line-ending-evidence'
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

def line_ending_evidence(raw):
    """Return lexical counts only; six fields do not prove a valid market row.

    This may explain a current source shape after a separately authorized read.
    It neither authenticates bytes nor diagnoses a historical failed invocation.
    No field, timestamp, ticker, price, row fingerprint or raw exception escapes.
    """
    require(type(raw) is bytes and 0 < len(raw) <= MAX_MEMBER_BYTES, 'bytes')
    lf, crlf = raw.count(b'\n'), raw.count(b'\r\n')
    bare = raw.count(b'\r') - crlf
    ends_lf, ends_crlf = raw.endswith(b'\n'), raw.endswith(b'\r\n')
    final = raw.rsplit(b'\n', 2)[-2] if ends_lf else raw.rsplit(b'\n', 1)[-1]
    if ends_crlf:
        final = final[:-1]
    field_count = final.count(b',') + 1
    complete = (0 < len(final) <= MAX_LINE_BYTES and field_count == 6
        and not final.startswith(b',') and not final.endswith(b',') and b',,' not in final)
    return {'schema': SCHEMA + '-line-ending-evidence', 'byte_count': len(raw),
        'LF_count': lf, 'CRLF_count': crlf, 'bare_CR_count': bare,
        'ends_LF': ends_lf, 'ends_CRLF': ends_crlf,
        'physical_record_count': lf + (0 if ends_lf else 1),
        'unterminated_final_record': not ends_lf,
        'complete_final_record': bool(complete), 'final_record_field_count': field_count,
        'line_endings_consistent': bare == 0 and (crlf == 0 or crlf == lf),
        'line_endings_supported': bare == 0}

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
        'control': str(CONTROL), 'source_pins': SOURCE_PINS,
        'USB_root': str(USB), 'USB_pins': USB_PINS, 'allowed_archives': list(ARCHIVES),
        'member_name': REMX_MEMBER, 'member_pin': REMX_PIN,
        'maximum_seconds': SECONDS, 'maximum_output_bytes': MAX_OUTPUT,
        'maximum_archive_bytes': MAX_ZIP_BYTES, 'maximum_members_per_archive': MAX_MEMBERS,
        'maximum_member_bytes': MAX_MEMBER_BYTES, 'maximum_line_bytes': MAX_LINE_BYTES,
        'scope': 'all_4339_original_REMX_rows_in_exact_two_eras_field_shape_counts_only',
        'eras': [{'era_ordinal': ordinal, 'first_date': first, 'last_date': last, 'row_count': count}
            for ordinal, first, last, count in ERAS],
        'volume_classes': list(VOLUME_CLASSES), 'volume_lexical_counts': list(VOLUME_LEXICAL_COUNTS),
        'numeric_scope': 'volume_nonfinite_negative_fractional_or_malformed_are_counted_never_admitted_or_normalized',
        'strict_predicates': 'six_fields_strict_date_order_exact_eras_unsigned_finite_positive_OHLC_prices',
        'line_endings': 'per_record_LF_or_CRLF_optional_complete_EOF_no_bare_CR_or_arbitrary_strip',
        'archive_integrity': 'externally_pinned_local_manifest_MD5_then_current_held_container_SHA256_and_member_CRC_SHA256',
        'local_manifest_is_vendor_authentication': False, 'USB_native_ACL_xattr_authentication_claimed': False,
        'claim_before_USB_read': True, 'normal_source_guard_return_before_publication': True,
        'outputs': ['claim.json', 'report.json'],
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
    for key, name in (('security', 'arv2_relocation_security'), ('remx', 'arv2_r335_remx_identity')):
        full = 'scripts.' + name
        module = importlib.import_module(full)
        require(Path(module.__file__) == ROOT / 'scripts' / (name + '.py'), 'source_pin'); modules[key] = module
    return modules

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
        require(name in ('claim.json', 'report.json')
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

def volume_class(value):
    """Finite lexical/numeric categories only; never return or normalize a value."""
    require(type(value) is str, 'row_shape')
    lexical = {key: 0 for key in VOLUME_LEXICAL_COUNTS}
    if not 0 < len(value) <= 128:
        return 'malformed_count', lexical
    unsigned = re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value) is not None
    lexical['unsigned_decimal_lexical_count'] = int(unsigned)
    nonfinite = re.fullmatch(r'[+-]?(?:s?nan|inf(?:inity)?)', value, re.IGNORECASE) is not None
    numeric = re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,4})?', value) is not None
    lexical['decimal_point_lexical_count'] = int(numeric and '.' in value)
    lexical['exponent_lexical_count'] = int(numeric and 'e' in value.lower())
    lexical['signed_lexical_count'] = int((numeric or nonfinite) and value.startswith(('+', '-')))
    if not numeric and not nonfinite:
        return 'malformed_count', lexical
    try:
        number = Decimal(value)
    except InvalidOperation:
        return 'malformed_count', lexical
    if not number.is_finite():
        return 'nonfinite_count', lexical
    if number < 0:
        return 'negative_finite_count', lexical
    if number != number.to_integral_value():
        return 'fractional_nonnegative_count', lexical
    return 'integer_nonnegative_count', lexical


def timestamp(value):
    require(type(value) is str and len(value) in (10, 19), 'timestamp')
    require(len(value) == 10 or value[10:] == ' 00:00:00', 'timestamp')
    session = value[:10]
    require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', session), 'session')
    try:
        require(date.fromisoformat(session).isoformat() == session, 'session')
    except ValueError:
        raise Refused('session') from None
    return session


def price_number(value):
    require(type(value) is str and 0 < len(value) <= 128
        and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value), 'number')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise Refused('number') from None
    require(number.is_finite() and number > 0, 'price')
    return number


def inspect_member(raw, listing, remx):
    """Authenticate exact bytes and count both full eras without price admission."""
    global LEXICAL_EVIDENCE
    require(type(raw) is bytes and pin(raw) == REMX_PIN, 'source_pin')
    LEXICAL_EVIDENCE = validate_lexical(line_ending_evidence(raw))
    require(LEXICAL_EVIDENCE['line_endings_supported'] is True, 'line_ending')
    try:
        raw.decode('ascii')
    except UnicodeDecodeError:
        raise Refused('encoding') from None
    lines = raw.split(b'\n'); terminated = raw.endswith(b'\n')
    if terminated: lines = lines[:-1]
    require(len(lines) == 4339, 'partition')
    observed, previous, width = [], None, None
    for ordinal, first, last, count in ERAS:
        observed.append({'era_ordinal': ordinal, 'first_date': None, 'last_date': None, 'row_count': 0,
            **{key: 0 for key in (*VOLUME_CLASSES, *VOLUME_LEXICAL_COUNTS)}})
    for index, line in enumerate(lines):
        separated = index < len(lines) - 1 or terminated
        if separated and line.endswith(b'\r'): line = line[:-1]
        require(0 < len(line) <= MAX_LINE_BYTES, 'row_bound')
        fields = line.decode('ascii').split(','); require(len(fields) == 6, 'row_shape')
        current = timestamp(fields[0])
        if width is None: width = len(fields[0])
        require(len(fields[0]) == width, 'timestamp')
        require(previous is None or previous < current, 'date_order')
        opening, high, low, close = tuple(price_number(value) for value in fields[1:5])
        require(low <= min(opening, close) <= max(opening, close) <= high, 'OHLC')
        era = observed[0 if index < ERAS[0][3] else 1]
        if era['first_date'] is None: era['first_date'] = current
        era['last_date'] = current; era['row_count'] += 1
        category, lexical = volume_class(fields[5]); era[category] += 1
        for key in VOLUME_LEXICAL_COUNTS: era[key] += lexical[key]
        previous = current
    metadata = {'raw_member_pin': REMX_PIN, 'ticker': 'REMX', 'listing': listing,
        'segments': [{key: era[key] for key in ('first_date', 'last_date', 'row_count')} for era in observed],
        'total_row_count': len(lines)}
    try:
        partition = remx.validate_partition(metadata).to_record()
    except BaseException:
        raise Refused('partition') from None
    require(partition['metadata_partition_matches_policy'] is True, 'partition')
    result = {'row_count': len(lines), 'eras': observed, 'lexical_evidence': LEXICAL_EVIDENCE,
        'all_row_shapes_dates_prices_OHLC_validated': True, 'exact_era_boundaries_validated': True,
        'volume_values_accepted': False, 'partition_policy_sha256': remx.profile_sha256()}
    validate_inspection(result)
    return result


def validate_inspection(value):
    require(type(value) is dict and set(value) == {'row_count', 'eras', 'lexical_evidence',
        'all_row_shapes_dates_prices_OHLC_validated', 'exact_era_boundaries_validated',
        'volume_values_accepted', 'partition_policy_sha256'}
        and type(value['row_count']) is int and value['row_count'] == 4339
        and value['all_row_shapes_dates_prices_OHLC_validated'] is True
        and value['exact_era_boundaries_validated'] is True and value['volume_values_accepted'] is False
        and value['partition_policy_sha256'] == '4674c20222e26c369abbd654c61ed14f08a7e49861d34251b129db49d392632e'
        and type(value['eras']) is list and len(value['eras']) == 2, 'output')
    evidence = validate_lexical(value['lexical_evidence'])
    require(evidence['physical_record_count'] == 4339 and evidence['line_endings_supported'] is True
        and evidence['final_record_field_count'] == 6, 'output')
    for actual, (ordinal, first, last, count) in zip(value['eras'], ERAS, strict=True):
        require(type(actual) is dict and set(actual) == {'era_ordinal', 'first_date', 'last_date', 'row_count',
            *VOLUME_CLASSES, *VOLUME_LEXICAL_COUNTS}
            and type(actual['era_ordinal']) is int and actual['era_ordinal'] == ordinal
            and type(actual['row_count']) is int and actual['row_count'] == count
            and actual['first_date'] == first and actual['last_date'] == last
            and all(type(actual[key]) is int and 0 <= actual[key] <= count for key in (*VOLUME_CLASSES, *VOLUME_LEXICAL_COUNTS))
            and sum(actual[key] for key in VOLUME_CLASSES) == count, 'output')
    return value


def worker(args, deadline):
    global FAILURE_STAGE, LEXICAL_EVIDENCE
    require(type(args.intent_fd) is int and args.intent_fd >= 3, 'arguments')
    try: intent = os.read(args.intent_fd, 4097)
    finally: os.close(args.intent_fd)
    require(intent == canonical(binding(args)), 'arguments')
    preflight(args, deadline)
    with ExitStack() as sources:
        modules = load_modules(sources, deadline)
        with Store(modules['security']) as store:
            store.write('claim.json', canonical({'binding': binding(args), 'profile': profile_record()}))
            fixed = {}
            for relative, expected in USB_PINS.items():
                FAILURE_STAGE = 'USB_manifest' if relative == 'manifest.json' else 'USB_listing'
                held = sources.enter_context(HeldFile(USB / relative, maximum=2 * 1024 * 1024,
                    expected=expected, deadline=deadline)); fixed[relative] = held.read()
            manifest = parse(fixed['manifest.json'], USB_PINS['manifest.json']['byte_count'])
            rows = listings(fixed[ETF_DIR + 'Ticker_Listing.txt'])
            matches = [row for row in rows if row['Ticker'] == 'REMX']
            require(len(matches) == 1, 'listing')
            listing = {'name': matches[0]['Name'], 'first_date': matches[0]['First Date'], 'last_date': matches[0]['Last Date']}
            expected = manifest_entry(manifest, REMX_ARCHIVE)
            held = sources.enter_context(HeldFile(USB / REMX_ARCHIVE, maximum=MAX_ZIP_BYTES, deadline=deadline))
            archive = sources.enter_context(Archive(held, expected))
            FAILURE_STAGE = 'REMX_fields'
            raw = archive.member(REMX_MEMBER); require(raw is not None, 'member')
            inspection = inspect_member(raw, listing, modules['remx'])
            container_pin = archive.container_pin
            sources.close()
            FAILURE_STAGE = 'output'; LEXICAL_EVIDENCE = None
            result = {'schema': SCHEMA, 'complete': True, 'inspection': inspection,
                'original_member_pin': REMX_PIN, 'archive_pin': container_pin,
                'source_guard_normal_return': True, **FALSE_FLAGS}
            validate_result(result)
            preflight(args, deadline)
            report = {'binding': binding(args), 'result': result}
            report_pin = store.write('report.json', canonical(report)); budget(deadline)
            return {**report, 'report_pin': report_pin}


def validate_result(value):
    require(type(value) is dict and set(value) == {'schema', 'complete', 'inspection',
        'original_member_pin', 'archive_pin', 'source_guard_normal_return', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['complete'] is True
        and value['source_guard_normal_return'] is True and all(value[key] is False for key in FALSE_FLAGS), 'output')
    validate_inspection(value['inspection'])
    require(type(value['original_member_pin']) is dict and set(value['original_member_pin']) == {'byte_count', 'sha256'}
        and type(value['original_member_pin']['byte_count']) is int and value['original_member_pin'] == REMX_PIN, 'output')
    item = value['archive_pin']
    require(type(item) is dict and set(item) == {'byte_count', 'sha256'}
        and type(item['byte_count']) is int and 0 < item['byte_count'] <= MAX_ZIP_BYTES
        and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'output')
    return value


def native_profile():
    value = '(version 1)(allow default)(deny network*)(deny file-write* (subpath "/Volumes/SANDISK"))'
    value += ''.join('(deny file-read* file-write* (subpath "' + path + '"))' for path in
        ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath "' + str(CONTROL) + '"))'
    value += '(require-not (literal "' + str(CONTROL.parent) + '"))(require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))(require-not (literal "/dev/null"))))'
    paths = [CONTROL]
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
