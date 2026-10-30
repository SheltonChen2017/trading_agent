"""One prospective AR parent-path correction and offline common-price sidecar.

Only four explicitly pinned AP DATA leaves and fresh genuine original input
are read. Provisional spools precede source guard normal return. Final shards
rotate their own original spool descriptors, and the private manifest is last.
Actual producer zero plus separate native stdin validation remain mandatory.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import stat
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_raw_price_acquisition_v3 as ap
from scripts import arv2_r298_ap_source_binding as anchor
from scripts import arv2_r298_aq_failure_binding as failure_anchor
from scripts import arv2_r298_price_corpus_guard as source_guard
from scripts import arv2_r298_common_price_sidecar as codec
from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt

SOURCE = ROOT / 'scripts/prepare_arv2_r298_common_price_sidecar_v2.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR'
SCHEMA = 'arv2-r298-offline-common-price-sidecar-ar-v2'
PYTHON, worker, admitted, environment = ap.PYTHON, ap.worker, ap.admitted, ap.environment
canonical, sha, parse, pin, metadata = ap.canonical, ap.sha, ap.parse, ap.pin, ap.metadata
SECONDS, VALIDATOR_SECONDS, MAX_OUTPUT = 1800, 30, 128 * 1024
MONTH_COUNT, MAX_MONTH, MAX_PROVISIONAL, MAX_FINAL = 71, 32 * 1024 * 1024, 512 * 1024 * 1024, 512 * 1024 * 1024
FREE_DISK_BYTES, FD_WINDOW, MAX_BASELINE_FDS, MAX_NEW_FDS = 1536 * 1024 * 1024, 128, 16, 112
AP_SHA256 = 'c6c68118713844979e1865ed7b6cc919640dc38516179e9513eb457f36cbc4e4'
AP_PROFILE_SHA256 = 'cf230b9d4db6dd2574da4cdaf3762538341fdc9b7974d14b870040f626d53175'
AQ_FAILURE_FACT_SHA256 = '180cdc04c62564fbd0f85dad984731555c3d18d6aba5ce19199f0a9614532ce0'
NEW_PINS = {'scripts/run_arv2_r298_raw_price_acquisition_v3.py': AP_SHA256,
    'scripts/prepare_arv2_r298_common_price_sidecar.py': 'a454259816eb5ad97aa3d4143d65abc8c96f7c77331071c864f696f396c8c056',
    'scripts/arv2_r298_aq_failure_binding.py': '923b0e976dbf60168033a3b8ce1b2eb42e91c5fe9030137e74bef75c4b0caaf6',
    'scripts/arv2_r298_ap_source_binding.py': 'fc14178438cb5d891da0f71321e3a4e04c804e8adcc6eadd86d24b4ab1554652',
    'scripts/arv2_r298_price_corpus_guard.py': 'ba0460f5d3d1e42f8a59b9c2bc7e2c7babc2502544f2c80d4905e180d8971f9c',
    'scripts/arv2_r298_common_price_sidecar.py': 'bd1c92c0512d320c13108c23a7d50529a8bde777116604b62d7ee3b61e0865d3',
    'research/analyst_revisions_v2_qc/newrule_common_price_format.py': 'd254b3e3a6a52445e4422f03885ec58a3d2b30e8ce902cb80ed8f841c374f873'}
FALSE_FLAGS = {**fmt.FALSE_FLAGS, 'provider_contact': False, 'credential_access': False,
    'QC_contact': False, 'QC_data_exported': False, 'QC_transfer_granted': False,
    'strategy_reference_or_NAV_admitted': False, 'terminal_payoff_proven': False,
    'executable_quote_substitution': False, 'old_control_read': False,
    'continuous_or_historical_integrity_proven': False}
FINITE = frozenset(('host', 'arguments', 'environment', 'git_state', 'source_pin', 'source_binding',
    'deadline', 'disk_budget', 'descriptor_budget', 'claim_spent', 'output_path', 'output_changed',
    'output_security', 'output_bound', 'output_write', 'phase', 'journal', 'input', 'plan',
    'spool', 'month', 'manifest', 'output', 'postflight', 'os_error', 'unknown')) \
    | frozenset('source_' + code for code in source_guard.FINITE) \
    | frozenset('codec_' + code for code in fmt.FINITE) \
    | frozenset('original_' + code for code in worker.previous.FINITE | {'unknown'})


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    if type(error) is admitted.helpers.Deadline:return 'deadline'
    if type(error) is environment.EnvironmentRefused:return 'environment'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is source_guard.Refused: return 'source_' + source_guard.finite(error)
    if type(error) is fmt.Refused: return 'codec_' + fmt.finite(error)
    if type(error) is worker.previous.Refused: return 'original_' + worker.previous.finite(error)
    if isinstance(error, OSError): return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')
    return deadline - time.monotonic()


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def source_context():
    fact, source, authentication = anchor.observed_fact(), anchor.source_summary(), anchor.authentication_summary()
    require(fmt.digest(fact) == fmt.AP_FACT_SHA256 and fmt.digest(source) == fmt.AP_SOURCE_SHA256
        and fmt.digest(authentication) == fmt.AP_AUTH_SHA256, 'source_binding')
    require(fact['binding'] == {'schema': ap.SCHEMA, 'expected_head': '6b86972a78d09d1d6aabd087edfe3b2248c7b291',
        'caller_sha256': AP_SHA256, 'profile_sha256': AP_PROFILE_SHA256}, 'source_binding')
    for name in ('producer', 'validator'):
        try: ap.public_transport._actual_metadata(fact[name])
        except BaseException: raise Refused('source_binding') from None
        require(type(fact[name]['actual_exit']) is int and fact[name]['actual_exit'] == 0
            and fact[name]['spawn_observed'] is True and fact[name]['bound'] is None
            and fact[name]['stderr_bytes'] == 0 and fact[name]['stderr_sha256'] == sha(b''), 'source_binding')
    require(fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes'] == 250498
        and fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256']
        == '82005db3095c93390318e9541452e541dcb77f520d6847780162bb1b404f493b', 'source_binding')
    for name in ('source_actual', 'provider_actual', 'authentication_actual'):
        try: ap._actual(fact[name], zero=True)
        except BaseException: raise Refused('source_binding') from None
    require(fact['application_dispatch_intents'] == fact['completed_HTTP200_bodies'] == 1256
        and fact['provider_request_count'] is None and fact['post_checks_complete'] is True
        and fact['source_guard_normal_return'] is True and fact['all_CSV_schemas_validated'] is True
        and fact['corpus_authenticated'] is True and source['source_guard_normal_return'] is True
        and source['all_6151_full_bindings_equal'] is True
        and fact['data_plan'] == source_guard.checked_plan(anchor.data_plan()), 'source_binding')
    for name in ('new_operation_or_read_granted', 'QC_transfer_granted', 'price_input_admitted'):
        require(anchor.profile_record()[name] is False, 'source_binding')
    return {'fact': fact, 'source_summary': source, 'authentication_summary': authentication}


def failure_context():
    """Inert failed-AQ provenance, never validated data or renewed authority."""
    fact=failure_anchor.observed_fact()
    require(fmt.digest(fact)==AQ_FAILURE_FACT_SHA256
        and fact['schema']=='arv2-r326-AQ-public-failure-binding-v1'
        and fact['binding']=={'schema':'arv2-r298-offline-common-price-sidecar-aq-v1',
            'expected_head':'95a2d5a186566831ad020f7503a74a4c01147869',
            'caller_sha256':NEW_PINS['scripts/prepare_arv2_r298_common_price_sidecar.py'],
            'profile_sha256':'136dd2c838b06eaa22ae61f362ffb1b7a3aeb9bc1f21953d97408550d85291bc'},'source_binding')
    for name,exit_code in (('producer',2),('validator',71)):
        actual=fact[name]
        try:ap.public_transport._actual_metadata(actual)
        except BaseException:raise Refused('source_binding') from None
        require(type(actual['actual_exit']) is int and actual['actual_exit']==exit_code
            and actual['spawn_observed'] is True and actual['bound'] is None,'source_binding')
    require(fact['producer']['stdout_bytes']==327 and fact['producer']['stdout_sha256']
        =='38e2561181b2cdd62e3327440748949fb4a64b1fcea18377d46948244de60892'
        and fact['validator']['stdout_bytes']==0 and fact['validator']['stderr_bytes']==53
        and fact['validator']['stderr_sha256']=='d34a4e4359a4dc36526cf5b363da32f7b7594a3a09eea17cbdfd6425b052d93e'
        and fact['finite_stdout_reconstruction']['native_reader_accepted'] is False
        and fact['accepted_sidecar'] is False and fact['allocation_and_private_read_stage_known'] is False
        and fact['attempt_spent'] is True,'source_binding')
    for key in ('old_control_read_granted','new_operation_granted','price_input_admitted',
            'point_in_time_proven','formal_forward_ready','paper_or_live_ready'):
        require(fact[key] is False,'source_binding')
    public=failure_anchor.profile_record()
    require(public['observed_fact_sha256']==AQ_FAILURE_FACT_SHA256
        and public['old_control_read_granted'] is public['new_operation_granted'] is False,'source_binding')
    return {'AQ_failure_fact_sha256':AQ_FAILURE_FACT_SHA256,'producer_actual_exit':2,
        'validator_actual_exit':71,'native_reader_accepted':False,
        'allocation_and_private_read_stage_known':False,'attempt_spent':True,
        'old_control_read_granted':False,'new_operation_granted':False,'price_input_admitted':False}


def pins():
    values = ap.pins()
    for name, value in NEW_PINS.items():
        require(_hash(value) and value != '0' * 64 and (name not in values or values[name] == value), 'source_pin')
        values[name] = value
    return values


def profile_record():
    context = source_context()
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH, 'source': str(SOURCE),
        'control': str(CONTROL), 'python': str(PYTHON), 'source_pins': pins(),
        'purpose': 'verified_parent_literal_permission_correction_before_first_accepted_offline_common_price_sidecar',
        'spent_AQ_failure_binding': failure_context(),
        'outer_orchestration': 'ordinary_metadata_only_outer_separate_independent_native_producer_and_validator',
        'sole_file_permission_delta': 'write_exact_literal_CONTROL_parent_no_parent_subtree_read_or_write',
        'outside_body_failure_allocation_is_unknown_not_proved_preflight_only': True,
        'AP_fact_sha256': fmt.AP_FACT_SHA256, 'AP_source_sha256': fmt.AP_SOURCE_SHA256,
        'AP_authentication_sha256': fmt.AP_AUTH_SHA256, 'data_plan': context['fact']['data_plan'],
        'seconds': SECONDS, 'maximum_output_bytes': MAX_OUTPUT, 'months': MONTH_COUNT,
        'month_bytes_maximum': MAX_MONTH, 'provisional_bytes_maximum': MAX_PROVISIONAL,
        'final_shard_bytes_maximum': MAX_FINAL, 'minimum_free_disk_bytes': FREE_DISK_BYTES,
        'fd_budget': {'first_descriptor_window': FD_WINDOW, 'maximum_baseline_open': MAX_BASELINE_FDS,
            'maximum_new_descriptors': MAX_NEW_FDS, 'soft_limit_at_least': FD_WINDOW,
            'spool_and_final_descriptors_at_once': 72, 'no_RLIMIT_change': True,
            'reserve_includes_source_ancestors_leaves_genuine_reader_directory_claim_catalog_manifest_report_stdio': True},
        'source_read_schedule': source_guard.profile_record(anchor.data_plan()),
        'private_intermediate_spools_only_before_source_normal_return': True,
        'finalize_one_original_held_spool_into_one_held_final_FD_then_close_only_consumed_spool': True,
        'retained_provisional_files_not_deleted_or_reopened': True, 'manifest_last_private_production_file': True,
        'append_checks': 'original_target_FD_named_security_and_directory_inventory_full_checks_at_phase_boundaries',
        'all_original_bindings_and_full_axis_reauthenticated': True,
        'native_five_prices_remain_QC_only': True, 'serialized_month_cap_not_total_Python_RAM_guarantee': True,
        'codec_profile_sha256': fmt.digest(codec.profile_record()),
        'deadline_uninterruptible_IO_host_suspension_qualification': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}


def _credential_free():
    require(not {'QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY',
        'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY'} & set(os.environ), 'environment')


def preflight(args, deadline):
    require(not admitted.v5._under_test() and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and Path(sys.executable) == PYTHON
        and Path.cwd() == ROOT and ROOT.resolve() == ROOT and Path(__file__).absolute() == SOURCE, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256), 'arguments')
    _credential_free(); environment._require_environment(); source_context(); failure_context()
    for cmd, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], admitted.frozen.BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(admitted.v5._git(cmd, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, expected in pins().items(): require(sha((ROOT / name).read_bytes()) == expected, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256 and sha(admitted.v5._git(
        ['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline, 256 * 1024))
        == args.caller_sha256 and sha(canonical(profile_record())) == args.profile_sha256, 'source_pin'); remaining(deadline)


def budgets():
    soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    require(soft == resource.RLIM_INFINITY or soft >= FD_WINDOW, 'descriptor_budget')
    occupied = 0
    for fd in range(FD_WINDOW):
        try: fcntl.fcntl(fd, fcntl.F_GETFD); occupied += 1
        except OSError as error:
            import errno
            require(error.errno == errno.EBADF, 'descriptor_budget')
    require(occupied <= MAX_BASELINE_FDS and FD_WINDOW - occupied >= MAX_NEW_FDS, 'descriptor_budget')
    info = os.statvfs(ROOT)
    require(info.f_bavail * info.f_frsize >= FREE_DISK_BYTES, 'disk_budget')


def native_profile(mode):
    require(mode in ('produce', 'validate'), 'arguments')
    value = '(version 1)(allow default)(deny network*)'
    value += ''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
        ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))'
    allowed = f'(require-not (subpath "{ROOT / ".pytest_cache"}"))(require-not (literal "/dev/null"))'
    if mode == 'produce': allowed += f'(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))'
    value += '(deny file-write* (require-all ' + allowed + '))'
    if mode == 'validate': return value + f'(deny file-read* (subpath "{ROOT / "artifacts"}"))'
    leaves = [ROOT / row['relative_path'] for row in anchor.data_plan().values()]
    leaves += [worker.previous.LINEAGE, CONTROL.parent]
    policy = ap.previous._artifact_policy(leaves, package=worker.previous.PACKAGE)
    needle = f'(require-all (subpath "{ROOT / "artifacts"}")'
    require(policy.count(needle) == 1, 'source_binding')
    return value + policy.replace(needle, needle + f' (require-not (subpath "{CONTROL}"))', 1)


def _security(fd):
    try: return ap.security.snapshot(fd)
    except ap.security.Refusal: raise Refused('output_security') from None


def _write(fd, raw):
    view = memoryview(raw)
    while view:
        count = os.write(fd, view); require(count > 0, 'output_write'); view = view[count:]
    os.fsync(fd)


class Store:
    """Own original spools rotate into final originals; no input is reopened."""
    def __init__(self):
        self.fd, self.chain, self.files = None, [], {}
        self.provisional_bytes = self.final_bytes = 0
        self.source_returned = self.manifest_written = False
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try: os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    except FileExistsError: require(here != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt; self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd, self.security = fd, _security(fd); self.verify()
        except BaseException: os.close(fd); raise

    def __enter__(self): return self
    def __exit__(self, *_):
        for row in self.files.values():
            if row['fd'] is not None: os.close(row['fd'])
        os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(other)) == metadata(os.fstat(self.fd))
                and _security(self.fd) == self.security and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and os.fstat(other).st_uid == os.getuid() and set(os.listdir(other)) == set(self.files), 'output_changed')
            for name, row in self.files.items():
                named = os.stat(name, dir_fd=other, follow_symlinks=False)
                require(metadata(named) == row['metadata'] and stat.S_ISREG(named.st_mode)
                    and named.st_uid == os.getuid() and named.st_nlink == 1 and stat.S_IMODE(named.st_mode) == 0o600, 'output_changed')
                if row['fd'] is not None:
                    require(metadata(os.fstat(row['fd'])) == row['metadata']
                        and _security(row['fd']) == row['security'], 'output_changed')
            require(sum(row['fd'] is not None and row['kind'] in ('spool','month') for row in self.files.values()) <= 72, 'descriptor_budget')
        finally: os.close(other)

    def create(self, name, kind):
        self.verify()
        require(name not in self.files and len(self.files) < 2 * MONTH_COUNT + 5
            and kind in ('spool','month','catalog','manifest','claim','report')
            and re.fullmatch('[a-z0-9-]{1,80}\\.(?:json|jsonl)', name), 'output_path')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.files[name] = {'fd': fd, 'metadata': metadata(os.fstat(fd)), 'security': _security(fd),
            'hasher': hashlib.sha256(), 'kind': kind, 'consumed': False}
        os.fsync(self.fd); self.verify(); return fd

    def verify_target(self, name):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(other)) == metadata(os.fstat(self.fd))
                and _security(self.fd) == self.security and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and os.fstat(other).st_uid == os.getuid() and set(os.listdir(other)) == set(self.files), 'output_changed')
            row=self.files[name];named=os.stat(name,dir_fd=other,follow_symlinks=False)
            require(row['fd'] is not None and metadata(named)==row['metadata']==metadata(os.fstat(row['fd']))
                and stat.S_ISREG(named.st_mode) and named.st_uid==os.getuid() and named.st_nlink==1
                and stat.S_IMODE(named.st_mode)==0o600 and _security(row['fd'])==row['security'],'output_changed')
        finally:os.close(other)

    def append(self, name, raw):
        row = self.files[name]; require(type(raw) is bytes and row['fd'] is not None, 'output_write')
        self.verify_target(name); old = row['metadata']; size = old[6]
        maximum = MAX_MONTH if row['kind'] in ('spool','month') else fmt.MAX_CATALOG_BYTES if row['kind'] == 'catalog' else fmt.MAX_MANIFEST_BYTES if row['kind'] == 'manifest' else MAX_OUTPUT
        require(size + len(raw) <= maximum, 'output_bound')
        if row['kind'] == 'spool': require(not self.source_returned and self.provisional_bytes + len(raw) <= MAX_PROVISIONAL, 'output_bound')
        elif row['kind'] in ('month','catalog','manifest'): require(self.source_returned and not self.manifest_written, 'phase')
        if row['kind'] == 'month': require(self.final_bytes + len(raw) <= MAX_FINAL, 'output_bound')
        require(os.lseek(row['fd'], 0, os.SEEK_END) == size, 'output_changed'); _write(row['fd'], raw)
        fresh = metadata(os.fstat(row['fd']))
        require(fresh[:6] == old[:6] and fresh[9] == old[9] and fresh[6] == size + len(raw)
            and fresh == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
            and _security(row['fd']) == row['security'], 'output_changed')
        row['hasher'].update(raw); row['metadata'] = fresh
        if row['kind'] == 'spool': self.provisional_bytes += len(raw)
        if row['kind'] == 'month': self.final_bytes += len(raw)
        self.verify_target(name)

    def write(self, name, kind, raw):
        self.create(name, kind); self.append(name, raw); self.check_bytes(name); return self.file_pin(name)

    def check_bytes(self, name):
        row = self.files[name]; require(row['fd'] is not None, 'phase')
        self.verify(); hasher, offset = hashlib.sha256(), 0
        while offset < row['metadata'][6]:
            raw = os.pread(row['fd'], min(65536,row['metadata'][6]-offset),offset)
            require(raw, 'output_write'); hasher.update(raw); offset += len(raw)
        require(hasher.hexdigest() == row['hasher'].hexdigest(), 'output_write'); self.verify()

    def file_pin(self, name):
        row = self.files[name]
        return {'byte_count': row['metadata'][6], 'sha256': row['hasher'].hexdigest()}

    def initialize_spools(self):
        require(not self.source_returned and not any(row['kind']=='spool' for row in self.files.values()), 'phase')
        for month in range(MONTH_COUNT): self.create('provisional-' + str(month).zfill(3) + '.jsonl', 'spool')

    def source_normal_return(self):
        require(not self.source_returned and sum(row['kind']=='spool' for row in self.files.values()) == MONTH_COUNT, 'phase')
        self.verify(); self.source_returned = True

    def read_spool(self, month, deadline):
        require(self.source_returned and type(month) is int and 0 <= month < MONTH_COUNT, 'phase')
        name = 'provisional-' + str(month).zfill(3) + '.jsonl'; row = self.files[name]
        require(row['fd'] is not None and not row['consumed'] and row['metadata'][6] <= MAX_MONTH, 'spool')
        self.verify(); raw = bytearray(); offset = 0
        while offset < row['metadata'][6]:
            remaining(deadline); chunk = os.pread(row['fd'], min(65536,row['metadata'][6]-offset),offset)
            require(chunk, 'spool'); raw.extend(chunk); offset += len(chunk)
        require(pin(bytes(raw)) == self.file_pin(name), 'spool'); self.verify(); return bytes(raw)

    def consume_into_final(self, month, raw):
        spool = 'provisional-' + str(month).zfill(3) + '.jsonl'; final = 'month-' + str(month).zfill(3) + '.jsonl'
        require(self.source_returned and self.files[spool]['fd'] is not None
            and not self.files[spool]['consumed'], 'phase')
        result = self.write(final, 'month', raw)
        require(result == pin(raw), 'output_write'); self.verify()
        os.close(self.files[spool]['fd']); self.files[spool]['fd'] = None; self.files[spool]['consumed'] = True
        self.verify(); return result

    def manifest(self, raw):
        require(self.source_returned and not self.manifest_written
            and sum(row['kind']=='month' for row in self.files.values()) == MONTH_COUNT
            and all(row['consumed'] for row in self.files.values() if row['kind']=='spool'), 'phase')
        result = self.write('manifest-private.json','manifest',raw); self.manifest_written = True; self.verify(); return result

    def receipt(self):
        self.verify(); require(self.manifest_written, 'phase')
        return {'schema': SCHEMA + '-output-receipt', 'catalog_pin': self.file_pin('catalog-private.json'),
            'manifest_pin': self.file_pin('manifest-private.json'),
            'month_pins': [self.file_pin('month-'+str(index).zfill(3)+'.jsonl') for index in range(MONTH_COUNT)],
            'provisional_byte_count': self.provisional_bytes, 'final_byte_count': self.final_bytes,
            'original_spools_consumed': MONTH_COUNT,
            'provisional_pin_stream_sha256': sha(canonical([self.file_pin('provisional-'+str(index).zfill(3)+'.jsonl') for index in range(MONTH_COUNT)])),
            'final_original_descriptors_held': True, 'closed_spool_security_scope_ended_after_authenticated_consumption': True}


def _journals(raw, count):
    require(type(raw) is bytes and raw.endswith(b'\n'), 'journal')
    rows = raw.splitlines(); require(len(rows) == count, 'journal')
    return [parse(line) for line in rows]


def _bind_original(plan_raw, rows, public, selected, context):
    require(pin(plan_raw) == context['source_summary']['plan_pin'] and public == context['source_summary']['input_binding'], 'input')
    plan = parse(plan_raw)
    require(len(rows) == 6151 and len(plan['assignments']) == 6159, 'input')
    for index, row in enumerate(rows):
        item = plan['assignments'][index]
        require(item['binding_ordinal'] == index and item['security_id'] == row['security_id']
            and item['whole_binding_sha256'] == ap.prices.digest(row)
            and item['semantic_binding_sha256'] == row['row_sha256'], 'input')
    axis = worker.previous.identity.evaluator._parse_sessions(tuple(selected['session_axis']))
    require(len(axis) == 3466 and ap.prices.digest(list(axis)) == fmt.FULL_AXIS_SHA256
        and plan['price_sessions'] == ap.prices._axis(axis), 'input')
    return plan


def _public_months():
    sessions=[day for day in worker.previous.october._sessions() if fmt.FIRST<=day<=fmt.LAST]
    require(len(sessions)==1452 and len(fmt.months(sessions))==MONTH_COUNT,'manifest')
    return fmt.months(sessions)


def _manifest_descriptor(manifest):
    fmt.validate_manifest(manifest)
    return {'schema':SCHEMA+'-manifest-descriptor',**pin(canonical(manifest)),
        'catalog_pin':manifest['catalog_pin'],
        **{key:manifest[key] for key in ('AP_fact_sha256','AP_authentication_sha256','binding_stream_sha256',
            'full_axis_sha256','assignment_count','vendor_slot_count','session_count','row_count','valid_count',
            'absent_count','total_shard_bytes')},
        'months':[{key:row[key] for key in ('month_ordinal','month','row_count','valid_count','absent_count','byte_count','sha256')}
            | {'session_count':len(row['session_indexes'])} for row in manifest['months']],**fmt.FALSE_FLAGS}


def _descriptor_manifest(value):
    keys={'schema','byte_count','sha256','catalog_pin','AP_fact_sha256','AP_authentication_sha256',
        'binding_stream_sha256','full_axis_sha256','assignment_count','vendor_slot_count','session_count',
        'row_count','valid_count','absent_count','total_shard_bytes','months',*fmt.FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA+'-manifest-descriptor'
        and type(value['months']) is list and len(value['months'])==MONTH_COUNT,'output')
    months=[]
    for expected,row in zip(_public_months(),value['months'],strict=True):
        require(type(row) is dict and set(row)=={'month_ordinal','month','session_count','row_count','valid_count',
            'absent_count','byte_count','sha256'} and type(row['session_count']) is int
            and row['session_count']==len(expected['session_indexes']) and row['month_ordinal']==expected['month_ordinal']
            and row['month']==expected['month'],'output')
        months.append({key:child for key,child in row.items() if key!='session_count'}
            | {'session_indexes':expected['session_indexes']})
    manifest={key:child for key,child in value.items() if key not in ('schema','byte_count','sha256','months')}
    manifest.update(schema=fmt.SCHEMA+'-manifest',months=months)
    fmt.validate_manifest(manifest)
    require(pin(canonical(manifest))=={'byte_count':value['byte_count'],'sha256':value['sha256']},'output')
    return manifest


def construct(store, context, deadline):
    _credential_free(); environment.require_safe_environment()
    plain = worker._load_plain(deadline)
    initial, original, selected, rows, public = worker._catalog(plain, deadline)
    with source_guard.PriceCorpusGuard(context['fact']['data_plan'], deadline=deadline) as guard:
        guard.authenticate_all()
        plan_raw, dispatch_raw, captures_raw = (guard.read_small(role) for role in ('plan','dispatch','captures'))
        plan = _bind_original(plan_raw, rows, public, selected, context)
        layout_summary, layout = codec.make_layout(plan_raw,
            expected_plan_summary=context['source_summary']['plan_summary'], frozen_AP_context=context, deadline=deadline)
        store.initialize_spools()
        dispatches, captures = _journals(dispatch_raw,1256), _journals(captures_raw,1256)
        offset = 0
        for dispatch, ordinal in enumerate(ap.ORDER):
            remaining(deadline); request = ap._request(plan, context['source_summary']['plan_pin'], ordinal)
            expected = {'dispatch_ordinal':dispatch,'plan_ordinal':ordinal,'request_sha256':request.sha256}
            item = captures[dispatch]
            require(dispatches[dispatch] == expected and type(item) is dict
                and set(item) == {*expected,'offset','body_pin','HTTP_status'}
                and all(item[key] == value for key,value in expected.items())
                and type(item['offset']) is int and item['offset'] == offset
                and type(item['HTTP_status']) is int and item['HTTP_status'] == 200, 'journal')
            ap._pin(item['body_pin'],ap.MAX_BODY)
            raw = guard.read_range(dispatch, offset, item['body_pin']['byte_count'], item['body_pin']['sha256'])
            offset += len(raw)
            for month, fragment in codec.split_response(layout, ordinal, raw, deadline=deadline):
                require(type(month) is int and 0 <= month < MONTH_COUNT, 'month')
                store.append('provisional-'+str(month).zfill(3)+'.jsonl',fragment)
        require(offset == context['fact']['data_plan']['corpus']['byte_count'], 'journal')
        worker._catalog_unchanged(plain,initial,original,selected,deadline)
        guard.verify(); source_receipt = guard.receipt()
    # Source consumers do not execute beyond this normal-return boundary.
    store.source_normal_return()
    catalog_raw = layout.catalog_raw(); fmt.validate_catalog(layout.catalog_record())
    require(store.write('catalog-private.json','catalog',catalog_raw) == layout.catalog_pin(), 'output_write')
    summaries = []
    for month in range(MONTH_COUNT):
        remaining(deadline); fragment = store.read_spool(month,deadline)
        summary, shard = codec.finalize_month(layout,month,fragment,deadline=deadline)
        raw = shard.bytes(); require(store.consume_into_final(month,raw) == {'byte_count':summary['byte_count'],'sha256':summary['sha256']}, 'output_write')
        summaries.append(summary)
    complete, opaque_manifest = codec.finish_manifest(layout,summaries,deadline=deadline)
    manifest_raw = opaque_manifest.bytes(); manifest = parse(manifest_raw); fmt.validate_manifest(manifest)
    require(store.manifest(manifest_raw) == complete['manifest_pin'], 'manifest')
    return {'input_binding':public,'source_guard_receipt':source_receipt,'codec_summary':complete,
        'manifest_descriptor':_manifest_descriptor(manifest),'output_receipt':store.receipt(),
        'source_guards_normal_return':True,'genuine_input_unchanged':True}


def run(args, deadline):
    context = source_context(); budgets()
    with Store() as store:
        store.write('claim.json','claim',canonical(binding(args)))
        stage = 'source'
        try:
            result = construct(store,context,deadline); stage = 'postflight'
            preflight(args,deadline); environment.require_safe_environment(); store.verify()
            result = {'schema':SCHEMA,**result,'AP_fact_sha256':fmt.AP_FACT_SHA256,
                'AP_source_sha256':fmt.AP_SOURCE_SHA256,'AP_authentication_sha256':fmt.AP_AUTH_SHA256,
                'post_checks_complete':True,**FALSE_FLAGS}
            validate_result(result,args)
            report = store.write('report.json','report',canonical({**binding(args),'result':result})); store.verify()
            return {'result':result,'report':report}
        except BaseException as error:
            failure = {'failure_code':finite(error),'stage':stage,'claim_consumed':True,
                'provisional_byte_count':store.provisional_bytes,'final_byte_count':store.final_bytes,
                'manifest_may_exist':store.manifest_written,**FALSE_FLAGS}
            try: store.write('report.json','report',canonical({**binding(args),'failure':failure}))
            except BaseException: pass
            return {'failure':failure}


def validate_result(value,args):
    fields = {'schema','input_binding','source_guard_receipt','codec_summary','manifest_descriptor','output_receipt',
        'source_guards_normal_return','genuine_input_unchanged','AP_fact_sha256','AP_source_sha256',
        'AP_authentication_sha256','post_checks_complete',*FALSE_FLAGS}
    require(type(value) is dict and set(value) == fields and value['schema'] == SCHEMA
        and all(value[key] is False for key in FALSE_FLAGS)
        and value['source_guards_normal_return'] is value['genuine_input_unchanged'] is value['post_checks_complete'] is True
        and value['AP_fact_sha256'] == fmt.AP_FACT_SHA256 and value['AP_source_sha256'] == fmt.AP_SOURCE_SHA256
        and value['AP_authentication_sha256'] == fmt.AP_AUTH_SHA256, 'output')
    context = source_context(); require(value['input_binding'] == context['source_summary']['input_binding'], 'output')
    source_guard.validate_receipt(value['source_guard_receipt'],context['fact']['data_plan'])
    manifest = _descriptor_manifest(value['manifest_descriptor']); receipt = value['output_receipt']; complete = value['codec_summary']
    require(type(receipt) is dict and set(receipt) == {'schema','catalog_pin','manifest_pin','month_pins',
        'provisional_byte_count','final_byte_count','original_spools_consumed','provisional_pin_stream_sha256',
        'final_original_descriptors_held','closed_spool_security_scope_ended_after_authenticated_consumption'}
        and receipt['schema'] == SCHEMA+'-output-receipt' and receipt['catalog_pin'] == manifest['catalog_pin']
        and receipt['manifest_pin'] == pin(canonical(manifest))
        and receipt['month_pins'] == [{'byte_count':row['byte_count'],'sha256':row['sha256']} for row in manifest['months']]
        and type(receipt['provisional_byte_count']) is int and 0 <= receipt['provisional_byte_count'] <= MAX_PROVISIONAL
        and type(receipt['final_byte_count']) is int and receipt['final_byte_count'] == manifest['total_shard_bytes'] <= MAX_FINAL
        and type(receipt['original_spools_consumed']) is int and receipt['original_spools_consumed'] == MONTH_COUNT
        and _hash(receipt['provisional_pin_stream_sha256']) and receipt['final_original_descriptors_held'] is True
        and receipt['closed_spool_security_scope_ended_after_authenticated_consumption'] is True, 'output')
    require(type(complete) is dict and set(complete) == {'schema','manifest_pin','catalog_pin','month_count',
        'row_count','valid_count','absent_count','total_shard_bytes',*fmt.FALSE_FLAGS}
        and complete['schema'] == codec.SCHEMA+'-complete' and complete['manifest_pin'] == receipt['manifest_pin']
        and complete['catalog_pin'] == receipt['catalog_pin'] and complete['month_count'] == MONTH_COUNT
        and all(complete[key] is False for key in fmt.FALSE_FLAGS)
        and all(complete[key] == manifest[key] for key in ('row_count','valid_count','absent_count','total_shard_bytes'))
        and complete['valid_count'] == 5541040 and complete['absent_count'] == 2654048, 'output')


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT and raw.endswith(b'\n')
        and type(actual_exit) is int and actual_exit in (0,2), 'output')
    value = parse(raw[:-1]); require(value.get('binding') == binding(args), 'output')
    if set(value) == {'binding','outside_body_failure'}:
        outside=value['outside_body_failure']
        require(actual_exit==2 and type(outside) is dict and set(outside)=={'operation','code','allocation_unknown'}
            and outside['operation']=='produce' and outside['code'] in FINITE
            and outside['allocation_unknown'] is True,'output');return value
    require(set(value) == {'binding','outcome'} and type(value['outcome']) is dict,'output'); outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failure = outcome['failure']
        require(actual_exit == 2 and type(failure) is dict and set(failure) == {'failure_code','stage',
            'claim_consumed','provisional_byte_count','final_byte_count','manifest_may_exist',*FALSE_FLAGS}
            and failure['failure_code'] in FINITE and failure['stage'] in ('source','postflight')
            and failure['claim_consumed'] is True and type(failure['manifest_may_exist']) is bool
            and type(failure['provisional_byte_count']) is int and 0 <= failure['provisional_byte_count'] <= MAX_PROVISIONAL
            and type(failure['final_byte_count']) is int and 0 <= failure['final_byte_count'] <= MAX_FINAL
            and all(failure[key] is False for key in FALSE_FLAGS),'output')
    else:
        require(actual_exit == 0 and set(outcome) == {'result','report'},'output')
        validate_result(outcome['result'],args)
        require(outcome['report'] == pin(canonical({**binding(args),'result':outcome['result']})),'output')
    return value


def outside_body_failure(args,error):
    require(args.operation in ('produce','validate'),'arguments')
    return {'binding':binding(args),'outside_body_failure':{'operation':args.operation,
        'code':finite(error),'allocation_unknown':True}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('produce','validate'))
    parser.add_argument('--expected-head',required=True); parser.add_argument('--caller-sha256',required=True)
    parser.add_argument('--profile-sha256',required=True)
    parser.add_argument('--actual-exit',type=int); args=parser.parse_args(argv)
    deadline=time.monotonic()+(VALIDATOR_SECONDS if args.operation=='validate' else SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline); environment._bootstrap_cli_logging()
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_OUTPUT+1);validate_output(raw,args.actual_exit,args)
                sys.stdout.buffer.write(raw);return 0
            outcome=run(args,deadline);raw=canonical({'binding':binding(args),'outcome':outcome})+b'\n'
            require(len(raw)<=MAX_OUTPUT,'output');sys.stdout.buffer.write(raw);return 2 if 'failure' in outcome else 0
    except BaseException as error:
        sys.stdout.buffer.write(canonical(outside_body_failure(args,error))+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
