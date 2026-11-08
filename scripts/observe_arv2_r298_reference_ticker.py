"""One native offline original-TICKERS-row authentication; no data acquisition.

Within the original Sharadar capture, only its fixed TICKERS archive, manifest
and marker may be read. The separate frozen input-admission scope is unchanged.
Fresh genuine input/catalog authentication and a new full-security source guard
precede any redacted row receipt. No provider, credential, QC, strategy, repair
or routing operation is available. Opaque private routes never leave memory.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import zipfile

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_a19_error_after_session_stop as previous
from scripts import capture_arv2_sharadar as capture_source
from scripts import arv2_r298_reference_ticker_source_guard as source_guard
from scripts import arv2_r298_reference_ticker_evidence as evidence
from scripts import arv2_r298_launch_admission as admission
from scripts import arv2_r298_reference_identity_join as identity_join

admitted, environment, capture_support = previous.admitted, previous.environment, previous.capture_support
SOURCE = ROOT / 'scripts/observe_arv2_r298_reference_ticker.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_reference_ticker/R323-20261025-M'
PYTHON = previous.PYTHON
SCHEMA = 'arv2-r298-reference-ticker-authentication-v1'
DEADLINE_SECONDS = 300
MAX_OUTPUT, MAX_PACKET, MAX_FILES = 128 * 1024, 128 * 1024, 16
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
MAX_ROWS, MAX_FIELD_CHARS = 250000, 65536
CONTEXT = {'calendar_status': 'valid', 'cause_authenticated': False,
    'decision_session': '2022-10-24', 'decision_time': '09:20', 'diagnostic_only': True,
    'extra_history_call': False, 'missing': 1,
    'missing_holdings': {'held': 1, 'unheld_target': 0, 'unknown': 0},
    'missing_kind': {'own_etf': 0, 'stock': 1, 'unknown': 0},
    'missing_sid_date': {'after_decision': 0, 'after_reference_through_decision': 0,
        'on_or_before_reference': 1, 'unknown': 0},
    'predicate': 'raw_reference_census_incomplete', 'probe_prices_used': False,
    'probe_repeated': False, 'reference_session': '2022-10-21', 'requested': 48,
    'returned': 47, 'schema': 'arv2-raw-reference-identity-context-v2',
    'session_axis_sha256': '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585',
    'sizing_repaired': False, 'witness_status': 'complete',
    'witnesses': [{'holding': 'held', 'identity_sha256': '9daff6253d858c3762ecb0f5fbe9d62cef6cb896afcb027693b5e3ea59dceb75',
        'kind': 'stock', 'sid_date': 'on_or_before_reference'}]}
CONTEXT_SHA256 = 'e9f74508de4027874305296ddbf8ef325e6dbf7e2c7f0e2b55fb76fade9bd8b0'
JOIN_SHA256 = '5ee8bf62329f85a24a91ed7bd3828313c386ea38c59a2e678dad57af7c86886e'
BINDING_ROW_SHA256 = '1975b7c6f03af2f2dc22a8986144686c31cb468cf41db5849ba75e710e08e8b8'
SOURCE_ROW_SHA256 = '5d9097a2c0dfe4dc736eb28d38b8adbc9e2f6e1b6c2adfd1c67d00505adb0ef9'
VINTAGE_PATH = ROOT / 'artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z'
MANIFEST_SHA256 = '94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b'
ARCHIVE_NAME, ARCHIVE_BYTES = '01-tickers-years-full.zip', 4937076
ARCHIVE_SHA256 = 'a7b129f159631ee50f1eefd2be8d4215c1c7818880570c0ad0a79c76c25e51bf'
MEMBER_BYTES = 24939614
MEMBER_SHA256 = '562577ea331805c4d50229b783e37216c9422c09d921b17dc950cf267ecf7697'
HEADER_BYTES = 291
HEADER_SHA256 = 'c9186ed191f4e51d5142287016dc99e3f80ecebed49aa63c3fa1ecf09e5d26f7'
NEW_PINS = {
    'scripts/run_arv2_r298_a19_error_after_session_stop.py': 'c2ec1a0551a95ee4f7f82f97e212106c0766962b00b499408771129c81dc360a',
    'scripts/capture_arv2_sharadar.py': '17e516b4cc721c7f97c4690f54dfcc9d2d11d8cebd413100f2e2ffa68e663ca2',
    'scripts/arv2_relocation_security.py': '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30',
    'scripts/arv2_relocation_security_v4.py': '3d20990b1df38f6aac04990c01c4fa752af6bc8b14b0bf0b8372b0daa0047fa7',
    'scripts/audit_arv2_relocation.py': '6e411fca07ca4a2904a1de9337876fcac560cf38cbaf9f3501b00a57c8d117a3',
    'scripts/arv2_r298_reference_ticker_source_guard.py': '9dd41136a8daca1ac01de823d8f9bb9fb1a5b0c27cfd85a02a725dac5274201f',
    'scripts/arv2_r298_reference_ticker_evidence.py': '7153d0d44db66d93ea4a0fb9921c58276e56ad8a46274841c99aa3abaf67712f'}
FALSE_FLAGS = {**previous.FALSE_FLAGS, 'provider_contact': False, 'credential_access': False,
    'qc_contact': False, 'source_repair_performed': False, 'provider_route_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin',
    'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'output', 'output_bound', 'parent_failed', 'validator_failed', 'refused', 'unknown_exception',
    'source_binding', 'archive_binding', 'member_binding', 'header_binding', 'csv',
    'row_census', 'row_match', 'catalog_binding', 'admission_changed', 'credentials_present', 'os_error'))
canonical, parse, sha, metadata = previous.canonical, previous.parse, previous.sha, previous.metadata
capture = previous.capture


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition: raise Refused(code)


def remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, 'deadline')
    return value


def finite(error):
    for module, prefix in ((source_guard, 'security_'), (evidence, 'evidence_'),
            (identity_join, 'join_'), (admission, 'admission_')):
        if type(error) is module.Refused:
            code = module.finite(error)
            return prefix + code if type(code) is str and code in module.FINITE | {'unknown'} else 'refused'
    if type(error) is Refused:
        values = BaseException.args.__get__(error)
        return values[0] if len(values) == 1 and type(values[0]) is str and values[0] in FINITE else 'refused'
    if type(error) is capture_source.SharadarCaptureError: return 'archive_binding'
    if isinstance(error, (csv.Error, UnicodeError, zipfile.BadZipFile)): return 'csv'
    if isinstance(error, OSError): return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    inventory = set(FINITE)
    for module, prefix in ((source_guard, 'security_'), (evidence, 'evidence_'),
            (identity_join, 'join_'), (admission, 'admission_')):
        inventory.update(prefix + code for code in module.FINITE | {'unknown'})
    return type(value) is str and value in inventory


def pins():
    return {**previous.pins(), **NEW_PINS}


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'deadline_seconds': DEADLINE_SECONDS, 'max_output': MAX_OUTPUT, 'max_rows': MAX_ROWS,
        'max_columns': 28, 'max_field_chars': MAX_FIELD_CHARS, 'source_path': str(VINTAGE_PATH),
        'manifest_sha256': MANIFEST_SHA256, 'archive_name': ARCHIVE_NAME,
        'archive_bytes': ARCHIVE_BYTES, 'archive_sha256': ARCHIVE_SHA256,
        'member_bytes': MEMBER_BYTES, 'member_sha256': MEMBER_SHA256,
        'header_bytes': HEADER_BYTES, 'header_sha256': HEADER_SHA256,
        'context_sha256': CONTEXT_SHA256, 'expected_join_sha256': JOIN_SHA256,
        'whole_binding_row_sha256': BINDING_ROW_SHA256, 'source_row_sha256': SOURCE_ROW_SHA256,
        'source_guard_profile_sha256': sha(canonical(source_guard.profile_record())),
        'evidence_profile_sha256': sha(canonical(evidence.profile_record())),
        'l_spent': True, 'l_control_read': False, 'l_head': '001cbcb4f9bded1bc3e85e5519410a8699fc2eac',
        'l_actual_exit': 0, 'l_report_bytes': 9346,
        'l_report_sha256': '471ccccc268b223576f8aa5cd4518bf4ac6a720a71f5653a565150c9c63231fe',
        'l_evidence_documentary_only': True, 'new_strategy_looks': 0, 'result_cell': 0,
        'only_original_TICKERS_archive_opened': True, 'actions_or_fundamentals_opened': False,
        'three_leaf_limit_scope': 'additional_original_Sharadar_capture_only',
        'private_input_admission_scope': 'fresh_frozen_October_D2_A11_native_consumer',
        'current_source_security_only': True, 'historical_security_continuity_proven': False,
        'opaque_route_serialized_or_persisted': False, 'opaque_route_discarded_after_verification': True,
        'native_network_denial_required': True, 'same_user_sandbox': False,
        'uninterruptible_io_or_suspension_bounded': False, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record()))}


def preflight(args, deadline):
    require(not admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], admitted.frozen.BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(pin != '0' * 64 and sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    blob = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
                           deadline, 128 * 1024)
    require(sha(blob) == args.caller_sha256, 'source_pin')
    remaining(deadline)


class Store:
    """Exclusive immutable records, held directory and checked named metadata.

    Leaf descriptors close after verification. This bounded consumer normally
    retains only its claim and report; endpoint checks are not continuity proof.
    """
    def __init__(self):
        self.fd, self.chain, self.files = None, [], {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        require(here != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self): return self
    def __exit__(self, *_): os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(other)
            require(chain == tuple(self.chain) and metadata(held) == metadata(named)
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and held.st_nlink == 2 + len(self.files),
                'control_changed')
            for name, baseline in self.files.items():
                require(metadata(os.stat(name, dir_fd=other, follow_symlinks=False)) == baseline,
                        'control_changed')
        finally:
            os.close(other)

    def write(self, name, value):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-z0-9-]{1,100}\\.json', name)
            and name not in self.files and len(self.files) < MAX_FILES, 'control_name')
        raw = canonical(value)
        require(0 < len(raw) <= MAX_PACKET, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                n = os.write(fd, view)
                require(n > 0, 'control_write')
                view = view[n:]
            os.fsync(fd)
            os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            os.lseek(fd, 0, os.SEEK_SET)
            reread = bytearray()
            while len(reread) <= len(raw):
                chunk = os.read(fd, min(65536, len(raw) + 1 - len(reread)))
                if not chunk: break
                reread.extend(chunk)
            require(bytes(reread) == raw and metadata(info) == metadata(os.fstat(fd)), 'control_changed')
            self.files[name] = metadata(info)
        finally:
            os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}


def native_profile(*, artifacts=False):
    value = previous.native_profile(artifacts=artifacts)
    if not artifacts:
        old = (f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
            ' (require-not (literal "/dev/null"))))')
        new = (f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
            f' (require-not (literal "/dev/null")) (require-not (literal "{CONTROL.parent}"))'
            f' (require-not (subpath "{CONTROL}"))))')
        require(value.count(old) == 1, 'source_binding')
        value = value.replace(old, new)
    return value + ''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in (
        previous.CONTROL, VINTAGE_PATH / '02-actions-years-full.zip',
        VINTAGE_PATH / '03-fundamentals-years-full.zip'))


def context():
    value = identity_join.witness.validate_complete_witness(CONTEXT)
    require(identity_join.context_digest(value) == CONTEXT_SHA256, 'source_binding')
    return value


def _catalog(plain, joined):
    require(identity_join.sha(identity_join.canonical(joined)) == JOIN_SHA256
        and joined['context_sha256'] == CONTEXT_SHA256
        and joined['matched_count'] == 1 and len(joined['matches']) == 1, 'catalog_binding')
    match = joined['matches'][0]
    require(match['whole_binding_row_sha256'] == BINDING_ROW_SHA256
        and match['source_row_sha256'] == SOURCE_ROW_SHA256, 'catalog_binding')
    selected = identity_join._streams(plain, plain.to_record())['runtime_symbol_bindings']
    rows = []
    for value in selected:
        row = identity_join.figi._input_row(value, joined['security_master_admission_sha256'])
        if identity_join.legacy._sha(row) == BINDING_ROW_SHA256:
            rows.append(row)
    require(len(rows) == 1 and rows[0]['source_row_sha256'] == SOURCE_ROW_SHA256, 'catalog_binding')
    return rows[0], match


def original_row(manifest_raw, marker_raw, archive_raw, deadline):
    """Authenticate all member bytes before interpreting even a CSV field."""
    remaining(deadline)
    require(type(manifest_raw) is bytes and sha(manifest_raw) == MANIFEST_SHA256
        and marker_raw == (MANIFEST_SHA256 + '\n').encode('ascii')
        and type(archive_raw) is bytes and len(archive_raw) == ARCHIVE_BYTES
        and sha(archive_raw) == ARCHIVE_SHA256, 'archive_binding')
    manifest, archives = capture_source._parse_manifest(manifest_raw, VINTAGE_PATH)
    require(manifest['capture_transport'] == capture_source.PRODUCTION_TRANSPORT, 'archive_binding')
    declared_archive = archives[0]
    require(declared_archive.dataset is capture_source.SharadarDataset.TICKERS
        and declared_archive.archive_file == ARCHIVE_NAME
        and declared_archive.archive_byte_count == ARCHIVE_BYTES
        and declared_archive.archive_sha256 == ARCHIVE_SHA256
        and len(declared_archive.members) == 1, 'archive_binding')
    declared = declared_archive.members[0]
    require(declared.uncompressed_byte_count == MEMBER_BYTES
        and declared.content_sha256 == MEMBER_SHA256
        and 1 <= declared.row_count <= MAX_ROWS, 'member_binding')
    with zipfile.ZipFile(io.BytesIO(archive_raw), 'r') as zipped:
        infos = zipped.infolist()
        require(len(infos) == 1, 'member_binding')
        info = infos[0]
        capture_source._safe_zip_member(info)
        require(info.filename == declared.name and info.compress_size == declared.compressed_byte_count
            and info.file_size == MEMBER_BYTES and info.CRC == declared.crc32
            and info.file_size <= max(1, info.compress_size) * capture_source.MAX_COMPRESSION_RATIO,
            'member_binding')
        with zipped.open(info) as member:
            payload = member.read(MEMBER_BYTES + 1)
        require(len(payload) == MEMBER_BYTES and sha(payload) == MEMBER_SHA256, 'member_binding')
    remaining(deadline)
    first, separator, _ = payload.partition(b'\n')
    raw_header = first + separator
    require(separator == b'\n' and len(raw_header) == HEADER_BYTES and sha(raw_header) == HEADER_SHA256,
        'header_binding')
    old_limit = csv.field_size_limit()
    selected, count = [], 0
    try:
        csv.field_size_limit(MAX_FIELD_CHARS)
        reader = csv.reader(io.StringIO(payload.decode('utf-8-sig'), newline=''), strict=True)
        header = next(reader)
        require(len(header) == 28 and len(set(header)) == 28
            and tuple(header) == declared.columns and all(type(name) is str and name for name in header),
            'header_binding')
        for values in reader:
            remaining(deadline)
            count += 1
            require(count <= MAX_ROWS and count <= declared.row_count and len(values) == 28
                and all(type(value) is str and len(value) <= MAX_FIELD_CHARS for value in values), 'row_census')
            row = dict(zip(header, values, strict=True))
            if evidence.source_row_digest(row) == SOURCE_ROW_SHA256:
                selected.append(row)
                require(len(selected) == 1, 'row_match')
        require(count == declared.row_count and len(selected) == 1, 'row_match')
    finally:
        csv.field_size_limit(old_limit)
    return selected[0], count


def consume(args, deadline):
    require(not any(key in os.environ for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY',
        'MASSIVE_API_KEY', 'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY')), 'credentials_present')
    dated = context()
    route = None
    try:
        with source_guard.SourceGuard(deadline=deadline) as guard:
            old_packet = admission.admit(deadline)
            plain, projected = admitted.prep.construct(deadline)
            snapshot = previous._constructed_matches(plain, projected, old_packet)
            joined = identity_join.join(plain, dated, old_packet)
            binding_row, match = _catalog(plain, joined)
            original, count = original_row(guard.read('manifest.json', deadline),
                guard.read('manifest.sha256', deadline), guard.read(ARCHIVE_NAME, deadline), deadline)
            receipt, route = evidence.verify(original, binding_row, dated, expected_match=match)
            receipt = evidence.validate_receipt(receipt)
            require(receipt['source_row_sha256'] == SOURCE_ROW_SHA256
                and receipt['whole_binding_row_sha256'] == BINDING_ROW_SHA256
                and receipt['context_sha256'] == CONTEXT_SHA256, 'source_binding')
            fresh_plain, fresh_projected = admitted.prep.construct(deadline)
            require(previous._constructed_matches(fresh_plain, fresh_projected, old_packet) == snapshot,
                'admission_changed')
            require(admission.admit(deadline) == old_packet, 'admission_changed')
            preflight(args, deadline)
            environment.require_safe_environment()
            guard.verify()
            result = {'schema': SCHEMA, 'original_row_authenticated': True, 'source_guard_completed': True,
                'fresh_private_postcheck_passed': True, 'csv_row_count': count,
                'context_sha256': CONTEXT_SHA256, 'join_sha256': JOIN_SHA256,
                'source_row_sha256': SOURCE_ROW_SHA256, 'binding_row_sha256': BINDING_ROW_SHA256,
                'manifest_sha256': MANIFEST_SHA256, 'archive_sha256': ARCHIVE_SHA256,
                'member_sha256': MEMBER_SHA256, 'header_sha256': HEADER_SHA256,
                'receipt': receipt, 'result_cell': 0, **FALSE_FLAGS}
        return result
    finally:
        # Only the closed redacted receipt can escape.  Never format the route.
        route = None


def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'offline': True, 'old_attempts_spent': True})
        try:
            result = consume(args, deadline)
            pin = directory.write('report.json', {**binding(args), 'result': result})
            return {'result': result, 'report': pin}
        except BaseException as error:
            failure = {'failure_code': finite(error), 'claim_consumed': True, **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failure})
            except BaseException: pass
            return {'failure': failure}


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2)
        and type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    require(value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and _finite_code(value['preflight_failure']), 'output')
        return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failure = outcome['failure']
        require(actual_exit == 2 and type(failure) is dict
            and set(failure) == {'failure_code', 'claim_consumed', *FALSE_FLAGS}
            and _finite_code(failure['failure_code']) and failure['claim_consumed'] is True
            and all(failure[key] is False for key in FALSE_FLAGS), 'output')
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        result = outcome['result']
        expected = {'schema': SCHEMA, 'context_sha256': CONTEXT_SHA256, 'join_sha256': JOIN_SHA256,
            'source_row_sha256': SOURCE_ROW_SHA256, 'binding_row_sha256': BINDING_ROW_SHA256,
            'manifest_sha256': MANIFEST_SHA256, 'archive_sha256': ARCHIVE_SHA256,
            'member_sha256': MEMBER_SHA256, 'header_sha256': HEADER_SHA256, 'result_cell': 0,
            'original_row_authenticated': True, 'source_guard_completed': True,
            'fresh_private_postcheck_passed': True, **FALSE_FLAGS}
        require(type(result) is dict and set(result) == {*expected, 'csv_row_count', 'receipt'}
            and all(type(result[key]) is type(item) and result[key] == item for key, item in expected.items())
            and type(result['csv_row_count']) is int and 1 <= result['csv_row_count'] <= MAX_ROWS, 'output')
        receipt = evidence.validate_receipt(result['receipt'])
        require(receipt['context_sha256'] == CONTEXT_SHA256 and receipt['source_row_sha256'] == SOURCE_ROW_SHA256
            and receipt['whole_binding_row_sha256'] == BINDING_ROW_SHA256
            and all(receipt[key] == CONTEXT['witnesses'][0][key]
                for key in ('identity_sha256', 'holding', 'kind', 'sid_date')), 'output')
        report = canonical({**binding(args), 'result': result})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def observe(args):
    outer = {'schema': SCHEMA + '-observer', 'parent': None, 'validator': None,
        'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        runtime = Path(tempfile.mkdtemp(prefix='r323-m-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY',
                'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY'):
            safe.pop(key, None)
        raw, errors, observed = capture(['/usr/bin/sandbox-exec', '-p', native_profile(), str(PYTHON), '-B',
            str(SOURCE), 'run', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            safe, DEADLINE_SECONDS + 30, stdout_limit=MAX_OUTPUT)
        outer['parent'] = observed
        require(type(observed['actual_exit']) is int and observed['actual_exit'] in (0, 2)
            and observed['bound'] is None and not errors, 'parent_failed')
        valid, errors, checked = capture(['/usr/bin/sandbox-exec', '-p', native_profile(artifacts=True),
            str(PYTHON), '-B', str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(observed['actual_exit'])],
            safe, 30, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = checked
        require(checked['actual_exit'] == 0 and checked['bound'] is None and not errors, 'validator_failed')
        outer['output'] = parse(valid)
        outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OBSERVER_OUTPUT, 'output_bound')
        return outer, observed['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error)
        return outer, 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'validate'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        result, code = observe(args)
        sys.stdout.buffer.write(canonical(result))
        return code
    deadline = time.monotonic() + (30 if args.operation == 'validate' else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline)
            environment._bootstrap_cli_logging()
            if args.operation == 'validate':
                result, code = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args), 0
            else:
                outcome = run(args, deadline)
                result, code = {'binding': binding(args), 'outcome': outcome}, 2 if 'failure' in outcome else 0
            raw = canonical(result)
            require(len(raw) <= MAX_OUTPUT, 'output_bound')
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
