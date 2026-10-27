"""One prospective AM session-representation repair and RAW source acquisition.

The broker does not read the private plan or corpus. A credential-free source
worker authenticates all original bindings and AC; a fixed provider worker
retains secret-scanned HTTP200 bytes before semantics; a separate network-
denied worker authenticates the exact contiguous corpus and validates CSVs.
No retries, cleanup, fallback, failed-body reads or strategy execution exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode

import requests

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import observe_arv2_r298_native_qc_rights as previous
from scripts import arv2_r298_raw_price_acquisition as prices
from scripts import arv2_r298_ac_source_binding as ac_anchor
from scripts import arv2_r298_ak_source_binding as ak_anchor
from scripts import arv2_r298_fixed_data_guard as data_guard
from scripts import arv2_keychain_connections as keychain
from scripts import arv2_r298_sharadar_reference_observation as transport

admitted, environment, security, worker = previous.admitted, previous.environment, previous.security, previous.worker
capture_support, PYTHON = previous.capture_support, previous.PYTHON
canonical, sha, metadata = prices.canonical, prices.sha, previous.metadata
SOURCE = ROOT / 'scripts/run_arv2_r298_raw_price_acquisition_v2.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_raw_price_acquisition/R326-20261027-AM'
SCHEMA = 'arv2-r298-raw-price-acquisition-am-v2'
DEADLINE_SECONDS, SOURCE_SECONDS, AUTH_SECONDS, VALIDATOR_SECONDS = 7200, 600, 900, 30
REQUEST_COUNT, MAX_BODY, MAX_CORPUS = 1256, 4 * 1024 * 1024, 2 * 1024 * 1024 * 1024
MAX_FRAME, MAX_EXTERNAL, MAX_JOURNAL, DISK_RESERVE = 128 * 1024, 2 * 1024 * 1024, 2 * 1024 * 1024, 256 * 1024 * 1024
ORDER = (1254, 1255, *range(1254))
DATA_PLAN = {'ac': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_price_lineage/R326-20261027-AC/price-lineage-private.json',
    'byte_count': 16344399, 'sha256': '4366e1e8a218fb21afc6ef3d88dfed9c2ab8b784a7718a405616850e1a4d6ddc'}}
DATA_FILES = ('plan-private.json', 'corpus.bin', 'dispatch.jsonl', 'captures.jsonl')
ROLES = ('source', 'provider', 'authenticate')
NEW_PINS = {
    'scripts/run_arv2_r298_raw_price_acquisition.py': '4a3f51135a4ecfe9cf5b7242a95bc4bf89ca332ba3d88bd73b07e93c9a790169',
    'scripts/observe_arv2_r298_native_qc_rights.py': 'b3a9d74363018e0a2064ae3dd5ab1bbfb4914d0f772363d07eb3be86221e8443',
    'scripts/arv2_r298_raw_price_acquisition.py': '229b3be993a111ac82ebfe4c68e67928b2eedd6cc2c9222de6ae2190a4dd71af',
    'scripts/arv2_r298_ac_source_binding.py': '112221b42d0c35065fec96ea55dc124c2e66101d8e6011bd91160d4a97576d0b',
    'scripts/arv2_r298_ak_source_binding.py': '2eab16f58809f2af9eb10b1507a04796c3630c555cb0689acf61b2cdea4737ce',
    'scripts/arv2_keychain_connections.py': 'bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227',
    'scripts/arv2_r298_sharadar_reference_observation.py': '72329cc48ce39eb2ccc3d61bca8fc79624a685704f1fa7fd96c5198dd882950f'}
FALSE_FLAGS = {'price_input_admitted': False, 'complete_price_coverage_proven': False,
    'strategy_nav_admitted': False, 'strategy_result_accepted': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False,
    'QC_contact': False, 'new_paid_rights': False, 'licensed_rows_disclosed': False,
    'credentials_persisted': False, 'physical_request_count_measured': False,
    'vendor_quota_or_rate_proven': False, 'native_book_read_or_exported': False,
    'old_controls_read': False, 'executable_quote_substitution': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin', 'source_binding', 'input',
    'plan', 'worker_scope', 'worker_packet', 'worker_failed', 'worker_credentials', 'inherited',
    'claim_spent', 'control_changed', 'control_security', 'control_bound', 'control_write',
    'credential_handoff', 'disk_headroom', 'descriptor_budget', 'request', 'response', 'http_status',
    'http_refused', 'credential_echo', 'body_bound', 'journal', 'corpus', 'csv', 'output',
    'postflight', 'os_error', 'unknown_exception', 'execution_environment_refused',
    'transport_connect_timeout', 'transport_read_timeout', 'transport_tls', 'transport_proxy',
    'transport_redirect', 'transport_connection', 'transport_timeout', 'transport_request',
    'transport_os', 'transport_unknown')) | frozenset('price_' + code for code in prices.FINITE) \
    | frozenset('data_guard_' + code for code in data_guard.FINITE) \
    | frozenset('original_' + code for code in worker.previous.FINITE | {'unknown'})


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    if type(error) is admitted.helpers.Deadline: return 'deadline'
    if type(error) is environment.EnvironmentRefused: return 'execution_environment_refused'
    if type(error) is keychain.KeychainUnavailable: return 'credential_handoff'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown_exception'
    if type(error) is prices.Refused: return 'price_' + prices.finite(error)
    if type(error) is data_guard.Refused: return 'data_guard_' + data_guard.finite(error)
    if type(error) is worker.previous.Refused: return 'original_' + worker.previous.finite(error)
    if isinstance(error, OSError): return 'os_error'
    return 'unknown_exception'


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= DEADLINE_SECONDS, 'deadline')
    return deadline - time.monotonic()


def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'output'); result[key] = value
        return result
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('output')))
        require(type(value) is dict and canonical(value) == raw, 'output')
        return value
    except (ValueError, UnicodeError, RecursionError): raise Refused('output') from None


def _pin(value, maximum, *, empty=False):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and (0 if empty else 1) <= value['byte_count'] <= maximum
        and _hash(value['sha256']) and (value['byte_count'] != 0 or value['sha256'] == sha(b'')), 'output')
    return value


def pins():
    result = previous.pins()
    for name, value in NEW_PINS.items():
        require(name not in result or result[name] == value, 'source_pin'); result[name] = value
    return result


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'verified_canonical_session_record_bridge_before_first_full_window_RAW_provider_use',
        'session_representation_policy': 'unchanged_frozen_evaluator_parser_then_unchanged_full_3466_axis_hash',
        'data_plan': DATA_PLAN, 'source_seconds': SOURCE_SECONDS, 'parent_seconds': DEADLINE_SECONDS,
        'offline_auth_seconds': AUTH_SECONDS, 'request_count': REQUEST_COUNT,
        'dispatch_plan_ordinals': list(ORDER), 'courtesy_spacing_seconds': 1,
        'courtesy_spacing_is_not_vendor_quota': True, 'request_timeout_maximum_seconds': 30,
        'maximum_body_bytes': MAX_BODY, 'maximum_corpus_bytes': MAX_CORPUS,
        'minimum_free_disk_bytes': MAX_CORPUS + DISK_RESERVE, 'minimum_descriptor_soft_limit': 128,
        'descriptor_strategy': 'one_held_append_only_corpus_and_fsynced_range_manifests_no_RLIMIT_change',
        'successful_body_secret_scanned_and_fsynced_before_any_CSV_semantics': True,
        'CSV_semantics_only_in_separate_network_denied_worker_after_provider_actual_zero': True,
        'source_before_credentials': True, 'keychain_provider': 'sharadar', 'keychain_lookups': 1,
        'keychain_service': 'trading-agent-sharadar', 'keychain_account': 'sharadar',
        'keychain_path': keychain.KEYCHAIN, 'keychain_seconds': 20,
        'key_in_inherited_pipe_only': True, 'HTTP_retries': 0, 'redirects': False,
        'failed_HTTP_body_read': False, 'post_authentication_is_not_continuous_source_integrity': True,
        'uncommitted_tail_inadmissible': True, 'cleanup_or_truncation': False,
        'partial_claim_or_nonzero_or_unknown_is_spent': True,
        'uninterruptible_IO_or_host_suspension_can_exceed_deadline': True,
        'plan_profile_sha256': prices.digest(prices.profile_record()), **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': sha(canonical(profile_record()))}


def preflight(args, deadline):
    require(not admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and _hash(args.caller_sha256), 'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
            (['branch', '--show-current'], admitted.frozen.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
            (['status', '--porcelain'], '')):
        require(admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, value in pins().items(): require(sha((ROOT / name).read_bytes()) == value, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256
        and sha(admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
            deadline, 256 * 1024)) == args.caller_sha256, 'source_pin')
    remaining(deadline)


def _security(fd):
    try: return security.snapshot(fd)
    except security.Refusal: raise Refused('control_security') from None


def _write(fd, raw):
    view = memoryview(raw)
    while view:
        count = os.write(fd, view); require(count > 0, 'control_write'); view = view[count:]
    os.fsync(fd)


def _read(fd, maximum, *, deadline):
    info = os.fstat(fd); require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= maximum, 'control_bound')
    before, snapshot = metadata(info), _security(fd)
    raw, offset = bytearray(), 0
    while offset < info.st_size:
        remaining(deadline); chunk = os.pread(fd, min(65536, info.st_size - offset), offset)
        require(chunk, 'control_changed'); raw.extend(chunk); offset += len(chunk)
    require(metadata(os.fstat(fd)) == before and _security(fd) == snapshot, 'control_changed')
    return bytes(raw)


class Store:
    """One exclusive private directory; original descriptors held to return."""
    def __init__(self):
        self.fd, self.chain, self.held = None, [], {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try: os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    except FileExistsError: require(here != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt; self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd, self.snapshot = fd, _security(fd); self.verify()
        except BaseException: os.close(fd); raise

    def __enter__(self): return self
    def __exit__(self, *_):
        for row in self.held.values(): os.close(row['fd'])
        os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(other)) == metadata(os.fstat(self.fd))
                and os.fstat(other).st_uid == os.getuid() and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and _security(self.fd) == self.snapshot and set(os.listdir(other)) == set(self.held), 'control_changed')
            for name, row in self.held.items():
                require(metadata(os.fstat(row['fd'])) == row['metadata']
                    == metadata(os.stat(name, dir_fd=other, follow_symlinks=False))
                    and _security(row['fd']) == row['security'], 'control_changed')
        finally: os.close(other)

    def create(self, name, raw=b''):
        self.verify()
        require(name not in self.held and len(self.held) < 24
            and (name in DATA_FILES or re.fullmatch('[a-z-]{1,40}\\.json', name)), 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.held[name] = {'fd': fd, 'metadata': metadata(os.fstat(fd)), 'security': _security(fd)}
        self.refresh((name,))
        if raw: _write(fd, raw); self.refresh((name,))
        os.fsync(self.fd); self.verify(); return fd

    def refresh(self, names):
        # Only the declared child-owned output FDs may grow. This authenticates
        # endpoints/security; the offline child independently authenticates bytes.
        for name in names:
            row = self.held[name]; old, new = row['metadata'], metadata(os.fstat(row['fd']))
            require(new[:6] == old[:6] and new[9] == old[9] and new[6] >= old[6]
                and new == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and _security(row['fd']) == row['security'], 'control_changed')
            row['metadata'] = new
        self.verify()

    def write(self, name, value):
        raw = canonical(value); require(0 < len(raw) <= MAX_FRAME, 'control_bound')
        self.create(name, raw); return pin(raw)


def headroom():
    soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    require(soft == resource.RLIM_INFINITY or soft >= 128, 'descriptor_budget')
    info = os.statvfs(ROOT)
    require(info.f_bavail * info.f_frsize >= MAX_CORPUS + DISK_RESERVE, 'disk_headroom')


def native_profile(role):
    require(role in (*ROLES, 'validate'), 'arguments')
    base = '(version 1)(allow default)'
    base += ('(deny network-bind)(deny network-inbound)'
        '(deny network-outbound (require-all (require-not (remote tcp "*:443"))'
        ' (require-not (remote tcp "*:53")) (require-not (remote udp "*:53"))))') if role == 'provider' else '(deny network*)'
    base += ''.join(f'(deny file-read* file-write* (subpath "{path}"))'
        for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    base += '(deny process-exec (literal "/usr/bin/security"))'
    base += (f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
        f' (require-not (subpath "{CONTROL}")) (require-not (literal "/dev/null"))))')
    if role == 'validate': return base + f'(deny file-read* (subpath "{ROOT / "artifacts"}"))'
    leaves = [CONTROL, *(CONTROL / name for name in DATA_FILES), CONTROL / 'claim.json',
        *(CONTROL / (name + '-intent.json') for name in ROLES), *(CONTROL / (name + '-started.json') for name in ROLES)]
    if role == 'source': leaves += [ROOT / DATA_PLAN['ac']['relative_path'], worker.previous.LINEAGE]
    return base + previous._artifact_policy(leaves, package=worker.previous.PACKAGE if role == 'source' else None)


def _credential_free():
    require(not any(name in os.environ for name in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY',
        'MASSIVE_API_KEY', 'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY')), 'worker_credentials')


def _inherited(args, role, packet, deadline):
    fds = (args.control_fd, args.claim_fd, args.intent_fd, args.started_fd, *args.data_fds)
    require(role in ROLES and all(type(fd) is int and fd > 2 for fd in fds)
        and len(set(fds)) == len(fds) and len(args.data_fds) == len(DATA_FILES), 'inherited')
    info = os.fstat(args.control_fd)
    require(metadata(info) == metadata(os.stat(CONTROL, follow_symlinks=False))
        and stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid(), 'inherited')
    _security(args.control_fd)
    for fd, name in zip(fds[1:], ('claim.json', role + '-intent.json', role + '-started.json', *DATA_FILES), strict=True):
        value = os.fstat(fd)
        require(stat.S_ISREG(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o600
            and value.st_uid == os.getuid() and value.st_nlink == 1
            and metadata(value) == metadata(os.stat(name, dir_fd=args.control_fd, follow_symlinks=False)), 'inherited')
        _security(fd)
    require(_read(args.claim_fd, MAX_FRAME, deadline=deadline) == canonical(binding(args)), 'inherited')
    expected = {**binding(args), 'role': role, 'input_pin': pin(packet)}
    require(_read(args.intent_fd, MAX_FRAME, deadline=deadline) == canonical(expected)
        and os.fstat(args.started_fd).st_size == 0, 'worker_scope')
    _write(args.started_fd, canonical(expected)); os.fsync(args.control_fd)


def source_observation(plan_fd, deadline):
    _credential_free(); environment.require_safe_environment()
    plain = worker._load_plain(deadline)
    initial, record, selected, rows, public = worker._catalog(plain, deadline)
    expected = ac_anchor.expected_summary()
    require(prices.digest(expected) == prices.AC_SUMMARY_SHA256
        and public['binding_contract'] == expected['binding_contract'], 'source_binding')
    source_fact = ac_anchor.observed_fact()
    require(source_fact['private_file'] == DATA_PLAN['ac'] and all(type(source_fact[role]['actual_exit']) is int
        and source_fact[role]['actual_exit'] == 0 and source_fact[role]['bound'] is None for role in ('producer', 'validator')), 'source_binding')
    with data_guard.FixedDataGuard(DATA_PLAN, deadline=deadline) as guard:
        raw = guard.read_all_once()['ac']; current = prices._source_ac(raw, expected)
        require(len(rows) == 6151 and [item['binding'] for item in current['stocks']] == rows, 'input')
        summary, opaque = prices.prepare_plan(raw, expected_ac_summary=expected,
            native_specification=previous.source_binding(), session_axis=worker.previous.identity.evaluator._parse_sessions(
                tuple(selected['session_axis'])), deadline=deadline)
        worker._catalog_unchanged(plain, initial, record, selected, deadline); guard.verify()
        plan_raw = opaque._raw
    # Neither the plan nor provider contact exists before the guard returns.
    require(os.fstat(plan_fd).st_size == 0, 'worker_scope'); _write(plan_fd, plan_raw)
    environment.require_safe_environment()
    return {'input_binding': public, 'plan_summary': summary, 'plan_pin': pin(plan_raw),
        'all_6151_full_bindings_equal': True, 'full_axis_sha256': prices.FULL_AXIS_SHA256,
        'source_guard_normal_return': True, 'native_source_observation_fact_sha256': prices.digest(ak_anchor.observed_fact())}


def validate_source(value):
    require(type(value) is dict and set(value) == {'input_binding', 'plan_summary', 'plan_pin',
        'all_6151_full_bindings_equal', 'full_axis_sha256', 'source_guard_normal_return', 'native_source_observation_fact_sha256'}
        and value['all_6151_full_bindings_equal'] is True and value['source_guard_normal_return'] is True
        and value['full_axis_sha256'] == prices.FULL_AXIS_SHA256
        and value['native_source_observation_fact_sha256'] == prices.digest(ak_anchor.observed_fact()), 'output')
    worker.previous._validate_input(value['input_binding'])
    checked = prices.validate_plan_summary(value['plan_summary'])
    require(value['input_binding']['binding_contract'] == ac_anchor.expected_summary()['binding_contract']
        and value['plan_pin'] == {'byte_count': checked['private_plan_byte_count'], 'sha256': checked['private_plan_sha256']}, 'output')
    return value


def _load_plan(fd, source, deadline):
    validate_source(source)
    raw = _read(fd, prices.MAX_PRIVATE_BYTES, deadline=deadline)
    require(pin(raw) == source['plan_pin'], 'plan')
    value = parse(raw); require(canonical(value) == raw and type(value) is dict
        and value.get('schema') == prices.PLAN_PRIVATE_SCHEMA and len(value.get('requests', ())) == REQUEST_COUNT
        and prices.digest(value['requests']) == source['plan_summary']['request_inventory_sha256']
        and prices.digest(value['assignments']) == source['plan_summary']['assignment_inventory_sha256']
        and value['full_axis_sha256'] == prices.FULL_AXIS_SHA256, 'plan')
    return value


def _request(plan, plan_pin, ordinal):
    item = plan['requests'][ordinal]
    request = prices.PrivatePriceRequest({'schema': prices.REQUEST_SCHEMA, 'plan_sha256': plan_pin['sha256'],
        'request_ordinal': ordinal, 'table': item['table'], 'tickers': item['tickers'],
        'endpoint': prices.ENDPOINTS[item['table']], 'first': item['first'], 'last': item['last'],
        'parameters': item['parameters'],
        'expected_sessions': [day for day in plan['price_sessions'] if item['first'] <= day <= item['last']]})
    prices._request(request); return request


def _append(fd, value):
    require(os.lseek(fd, 0, os.SEEK_END) == os.fstat(fd).st_size < MAX_JOURNAL, 'journal')
    _write(fd, canonical(value) + b'\n')


def _progress(completed, intents, corpus_bytes):
    return {'schema': SCHEMA + '-progress', 'completed_HTTP200_bodies': completed,
        'application_dispatch_intents': intents, 'retained_corpus_bytes': corpus_bytes,
        'provider_request_count': None}


def validate_progress(value):
    require(type(value) is dict and set(value) == {'schema', 'completed_HTTP200_bodies',
        'application_dispatch_intents', 'retained_corpus_bytes', 'provider_request_count'}
        and value['schema'] == SCHEMA + '-progress' and value['provider_request_count'] is None
        and all(type(value[key]) is int for key in ('completed_HTTP200_bodies', 'application_dispatch_intents', 'retained_corpus_bytes'))
        and 0 <= value['completed_HTTP200_bodies'] <= value['application_dispatch_intents'] <= REQUEST_COUNT
        and 0 <= value['retained_corpus_bytes'] <= MAX_CORPUS, 'output')
    return value


def emit(value):
    raw = canonical(value); require(len(raw) <= MAX_FRAME, 'output')
    sys.stdout.buffer.write(raw + b'\n'); sys.stdout.buffer.flush()


class OwnedSession(requests.Session):
    def resolve_redirects(self, *args, **kwargs): return iter(())


def _session():
    value = OwnedSession()
    value.trust_env, value.auth, value.verify, value.cert, value.max_redirects = False, None, True, None, 0
    value.headers.clear(); value.cookies.clear(); value.proxies.clear(); value.params.clear()
    value.hooks = {'response': []}; value.adapters.clear()
    value.mount('https://', requests.adapters.HTTPAdapter(max_retries=0)); return value


def _session_check(value):
    require(type(value) is OwnedSession and value.trust_env is False and value.auth is None
        and value.verify is True and value.cert is None and value.max_redirects == 0
        and not value.headers and not value.cookies and not value.proxies and not value.params
        and value.hooks == {'response': []} and set(value.adapters) == {'https://'}
        and type(value.adapters['https://']) is requests.adapters.HTTPAdapter
        and value.adapters['https://'].max_retries.total == 0, 'request')


def _errno(error):
    # No str/repr/args or URL disclosure. Only a finite integer OS-code vocabulary.
    import errno
    allowed = {getattr(errno, key, -1) for key in ('ECONNREFUSED', 'ECONNRESET', 'ECONNABORTED', 'ENETUNREACH',
        'EHOSTUNREACH', 'ETIMEDOUT', 'EPIPE', 'ENOSPC', 'EACCES', 'EPERM')}
    queue, seen = [error], set()
    while queue and len(seen) < 8:
        item = queue.pop()
        if id(item) in seen: continue
        seen.add(id(item))
        if isinstance(item, OSError):
            code = OSError.errno.__get__(item)
            if type(code) is int and code in allowed: return code
        for name in ('__cause__', '__context__'):
            child = BaseException.__getattribute__(item, name)
            if isinstance(child, BaseException): queue.append(child)
    return None


def fetch(request, key, state, deadline):
    record = prices._request(request); params = {**record['parameters'], 'api_key': key}
    url = record['endpoint'] + '?' + urlencode(params)
    with _session() as session:
        _session_check(session)
        prepared = session.prepare_request(requests.Request('GET', record['endpoint'], params=params,
            headers={'Accept-Encoding': 'identity'}))
        require(prepared.method == 'GET' and prepared.url == url and prepared.body is None
            and dict(prepared.headers) == {'Accept-Encoding': 'identity'}
            and prepared.hooks == {'response': []}, 'request')
        try:
            with session.send(prepared, timeout=min(30, remaining(deadline)), allow_redirects=False,
                    stream=True, verify=True, proxies={}) as response:
                status = response.status_code
                state['HTTP_status_type'] = 'int' if type(status) is int else 'other'
                require(type(status) is int and 100 <= status <= 599, 'http_status')
                state['HTTP_status'] = status
                require(response.url == url and response.request is prepared and not response.history, 'response')
                if status != 200: raise Refused('http_refused')
                _session_check(session); environment.require_safe_environment()
                headers = response.headers
                require(len(headers) <= 64 and not headers.get('Set-Cookie')
                    and headers.get('Content-Encoding', 'identity').casefold() == 'identity', 'response')
                secrets = transport._encodings(key)
                for name, value in headers.items():
                    require(type(name) is str and type(value) is str and len(name) + len(value) <= 8192
                        and not any(secret in (name + ':' + value).encode('utf-8') for secret in secrets), 'credential_echo')
                length = headers.get('Content-Length')
                require(length is None or (type(length) is str and length.isdecimal() and len(length) <= 10
                    and 0 < int(length) <= MAX_BODY), 'body_bound')
                body = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    remaining(deadline)
                    require(type(chunk) is bytes and len(body) + len(chunk) <= MAX_BODY, 'body_bound'); body.extend(chunk)
                require(0 < len(body) <= MAX_BODY and (length is None or len(body) == int(length)), 'body_bound')
                require(not any(secret in body for secret in secrets), 'credential_echo')
                return bytes(body)
        except requests.exceptions.RequestException as error:
            state['transport_failure'], state['OS_errno'] = previous.transport_failure(error), _errno(error)
            raise Refused(state['transport_failure']) from None


def provider_observation(fds, source, key, state, deadline):
    _credential_free(); environment.require_safe_environment(); headroom()
    plan = _load_plan(fds[0], source, deadline)
    require(all(os.fstat(fd).st_size == 0 for fd in fds[1:]) and type(key) is str
        and 8 <= len(key) <= keychain.MAX_KEY_BYTES and all(33 <= ord(char) <= 126 for char in key), 'worker_scope')
    corpus_hash, next_contact = hashlib.sha256(), time.monotonic()
    for dispatch, ordinal in enumerate(ORDER):
        remaining(deadline)
        delay = next_contact - time.monotonic()
        if delay > 0: time.sleep(min(delay, remaining(deadline)))
        request = _request(plan, source['plan_pin'], ordinal)
        item = {'dispatch_ordinal': dispatch, 'plan_ordinal': ordinal, 'request_sha256': request.sha256}
        _append(fds[2], item)  # durable intent precedes any possible request
        state.update(application_dispatch_intents=dispatch + 1, current_plan_ordinal=ordinal,
            HTTP_status=None, HTTP_status_type='not_observed', transport_failure=None, OS_errno=None)
        next_contact = time.monotonic() + 1
        body = fetch(request, key, state, deadline)
        require(state['retained_corpus_bytes'] + len(body) <= MAX_CORPUS, 'body_bound')
        offset = os.lseek(fds[1], 0, os.SEEK_END)
        require(offset == state['retained_corpus_bytes'], 'corpus')
        _write(fds[1], body); corpus_hash.update(body)
        capture_row = {**item, 'offset': offset, 'body_pin': pin(body), 'HTTP_status': 200}
        _append(fds[3], capture_row)  # a crash before this leaves an inadmissible tail
        state.update(completed_HTTP200_bodies=dispatch + 1, retained_corpus_bytes=offset + len(body))
        emit(_progress(dispatch + 1, dispatch + 1, offset + len(body)))
    environment.require_safe_environment()
    return {**state, 'corpus_pin': {'byte_count': state['retained_corpus_bytes'], 'sha256': corpus_hash.hexdigest()},
        'dispatch_pin': pin(_read(fds[2], MAX_JOURNAL, deadline=deadline)),
        'captures_pin': pin(_read(fds[3], MAX_JOURNAL, deadline=deadline)), 'provider_request_count': None}


def _journal(fd, expected, deadline):
    raw = _read(fd, MAX_JOURNAL, deadline=deadline); require(pin(raw) == expected and raw.endswith(b'\n'), 'journal')
    rows = [parse(line) for line in raw.splitlines()]
    require(len(rows) == REQUEST_COUNT and all(canonical(row) == line for row, line in zip(rows, raw.splitlines(), strict=True)), 'journal')
    return rows


def authenticate_observation(fds, source, supplied, deadline):
    _credential_free(); environment.require_safe_environment()
    plan = _load_plan(fds[0], source, deadline)
    validate_provider(supplied, success=True)
    dispatches = _journal(fds[2], supplied['dispatch_pin'], deadline)
    captures = _journal(fds[3], supplied['captures_pin'], deadline)
    size = os.fstat(fds[1]).st_size
    require(size == supplied['corpus_pin']['byte_count'] <= MAX_CORPUS, 'corpus')
    before, snapshot, total, rows, absent = metadata(os.fstat(fds[1])), _security(fds[1]), 0, 0, 0
    full_hash, summary_hash = hashlib.sha256(), hashlib.sha256()
    for dispatch, ordinal in enumerate(ORDER):
        remaining(deadline); request = _request(plan, source['plan_pin'], ordinal)
        identity = {'dispatch_ordinal': dispatch, 'plan_ordinal': ordinal, 'request_sha256': request.sha256}
        require(dispatches[dispatch] == identity, 'journal')
        item = captures[dispatch]
        require(type(item) is dict and set(item) == {*identity, 'offset', 'body_pin', 'HTTP_status'}
            and all(item[key] == value for key, value in identity.items())
            and type(item['offset']) is int and item['offset'] == total and type(item['HTTP_status']) is int
            and item['HTTP_status'] == 200, 'corpus')
        length = _pin(item['body_pin'], MAX_BODY)['byte_count']
        body = os.pread(fds[1], length, total); require(pin(body) == item['body_pin'], 'corpus')
        full_hash.update(body); total += length
        observed, _private = prices.analyze_response(request, body, http_status=200, deadline=deadline)
        prices.validate_response_summary(observed, request=request)
        rows += observed['row_count']; absent += observed['absent_cell_count']
        summary_hash.update(canonical(observed) + b'\n')
    require(total == size and full_hash.hexdigest() == supplied['corpus_pin']['sha256']
        and metadata(os.fstat(fds[1])) == before and _security(fds[1]) == snapshot, 'corpus')
    environment.require_safe_environment()
    return {'complete_contiguous_corpus_authenticated': True, 'all_CSV_schemas_validated': True,
        'request_count': REQUEST_COUNT, 'observed_price_rows': rows, 'absent_expected_cells': absent,
        'response_summary_stream_sha256': summary_hash.hexdigest(), 'corpus_pin': supplied['corpus_pin'],
        'dispatch_pin': supplied['dispatch_pin'], 'captures_pin': supplied['captures_pin']}


def _provider_state():
    return {'application_dispatch_intents': 0, 'completed_HTTP200_bodies': 0, 'retained_corpus_bytes': 0,
        'current_plan_ordinal': None, 'HTTP_status': None, 'HTTP_status_type': 'not_observed',
        'transport_failure': None, 'OS_errno': None}


def validate_provider(value, *, success=False):
    base = set(_provider_state())
    extras = {'corpus_pin', 'dispatch_pin', 'captures_pin', 'provider_request_count'} if success else set()
    require(type(value) is dict and set(value) == base | extras, 'output')
    validate_progress(_progress(value['completed_HTTP200_bodies'], value['application_dispatch_intents'], value['retained_corpus_bytes']))
    require(value['current_plan_ordinal'] is None or (type(value['current_plan_ordinal']) is int
        and 0 <= value['current_plan_ordinal'] < REQUEST_COUNT), 'output')
    require(value['HTTP_status_type'] in ('not_observed', 'int', 'other')
        and (value['HTTP_status'] is None or type(value['HTTP_status']) is int and 100 <= value['HTTP_status'] <= 599)
        and (value['transport_failure'] is None or value['transport_failure'] in FINITE)
        and (value['OS_errno'] is None or type(value['OS_errno']) is int and -10000 < value['OS_errno'] < 10000), 'output')
    if success:
        require(value['application_dispatch_intents'] == value['completed_HTTP200_bodies'] == REQUEST_COUNT
            and value['HTTP_status'] == 200 and value['HTTP_status_type'] == 'int'
            and value['provider_request_count'] is None and value['transport_failure'] is None and value['OS_errno'] is None, 'output')
        _pin(value['corpus_pin'], MAX_CORPUS); _pin(value['dispatch_pin'], MAX_JOURNAL); _pin(value['captures_pin'], MAX_JOURNAL)
    return value


def _capture_child(command, safe, packet, inherited, seconds, *, progress=False):
    """Own child only: bounded streaming framing, stderr refusal, kill/reap."""
    deadline = time.monotonic() + seconds; output, errors, pending, final = bytearray(), bytearray(), bytearray(), None
    progress_previous = (0, 0, 0)
    observed = {'actual_exit': None, 'spawn_observed': False, 'bound': None,
        'stdout_bytes': 0, 'stdout_sha256': sha(b''), 'stderr_bytes': 0, 'stderr_sha256': sha(b'')}
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=safe, pass_fds=tuple(inherited), close_fds=True)
    observed['spawn_observed'] = True
    try:
        process.stdin.write(packet); process.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 'stdout'); selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map():
                if time.monotonic() >= deadline: observed['bound'] = 'deadline'; raise Refused('deadline')
                for event, _ in selector.select(min(1, deadline - time.monotonic())):
                    chunk = os.read(event.fileobj.fileno(), 65536)
                    if not chunk: selector.unregister(event.fileobj); continue
                    target = output if event.data == 'stdout' else errors; target.extend(chunk)
                    require(len(target) <= (MAX_EXTERNAL if event.data == 'stdout' else MAX_FRAME), 'worker_packet')
                    if event.data == 'stdout':
                        pending.extend(chunk)
                        while b'\n' in pending:
                            line, _, tail = pending.partition(b'\n'); pending = bytearray(tail)
                            require(0 < len(line) <= MAX_FRAME, 'worker_packet'); value = parse(line)
                            require(canonical(value) == line and final is None, 'worker_packet')
                            if progress and type(value) is dict and value.get('schema') == SCHEMA + '-progress':
                                validate_progress(value)
                                now = tuple(value[key] for key in ('completed_HTTP200_bodies', 'application_dispatch_intents', 'retained_corpus_bytes'))
                                require(now[0] == progress_previous[0] + 1 and now[1] == now[0]
                                    and now[2] > progress_previous[2], 'worker_packet')
                                progress_previous = now; emit(value)
                            else: final = value
                        require(len(pending) <= MAX_FRAME, 'worker_packet')
        process.wait(timeout=max(.01, deadline - time.monotonic()))
        require(not pending and final is not None and not errors, 'worker_packet')
    except BaseException as error:
        # Broker-owned finite capture evidence is distinct from a child packet;
        # preserve the actual reaped exit even for a noisy/partial/timeout child.
        final = {'capture_failure': finite(error)}
    finally:
        if process.poll() is None: process.kill()
        process.wait()
        observed.update(actual_exit=process.returncode, stdout_bytes=len(output), stdout_sha256=sha(bytes(output)),
            stderr_bytes=len(errors), stderr_sha256=sha(bytes(errors)))
        process.stdout.close(); process.stderr.close()
    return final, observed


def _actual(value, *, zero=False):
    require(type(value) is dict and set(value) == {'actual_exit', 'spawn_observed', 'bound',
        'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256'}
        and (value['actual_exit'] is None or type(value['actual_exit']) is int)
        and type(value['spawn_observed']) is bool and value['bound'] in (None, 'deadline')
        and all(type(value[key]) is int and value[key] >= 0 for key in ('stdout_bytes', 'stderr_bytes'))
        and _hash(value['stdout_sha256']) and _hash(value['stderr_sha256']), 'output')
    if zero: require(value['actual_exit'] == 0 and value['spawn_observed'] is True and value['bound'] is None
        and value['stderr_bytes'] == 0 and value['stderr_sha256'] == sha(b''), 'output')


def _packet_actual(actual, args, role, result, *, prefix=b''):
    _actual(actual, zero=True)
    raw = prefix + canonical({'binding': binding(args), 'role': role, 'result': result}) + b'\n'
    require(actual['stdout_bytes'] == len(raw) and actual['stdout_sha256'] == sha(raw), 'output')


def _child(args, store, role, payload, runtime, deadline, *, key=None):
    packet = canonical(payload)
    store.write(role + '-intent.json', {**binding(args), 'role': role, 'input_pin': pin(packet)})
    started = store.create(role + '-started.json')
    data_fds = [store.held[name]['fd'] for name in DATA_FILES]
    inherited = [store.fd, store.held['claim.json']['fd'], store.held[role + '-intent.json']['fd'], started, *data_fds]
    command = ['/usr/bin/sandbox-exec', '-p', native_profile(role), str(PYTHON), '-B', str(SOURCE), role,
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(inherited[0]), '--claim-fd', str(inherited[1]), '--intent-fd', str(inherited[2]),
        '--started-fd', str(started), '--data-fds', ','.join(map(str, data_fds))]
    credential_read = credential_write = None
    try:
        if role == 'provider':
            require(type(key) is str, 'credential_handoff')
            credential_read, credential_write = os.pipe()
            require(os.write(credential_write, key.encode('ascii')) == len(key), 'credential_handoff')
            os.close(credential_write); credential_write = None
            command += ['--credential-fd', str(credential_read)]; inherited.append(credential_read)
        final, actual = _capture_child(command, capture_support._environment(runtime, None), packet, inherited,
            min({'source': SOURCE_SECONDS, 'provider': DEADLINE_SECONDS, 'authenticate': AUTH_SECONDS}[role], remaining(deadline)),
            progress=role == 'provider')
    finally:
        if credential_read is not None: os.close(credential_read)
        if credential_write is not None: os.close(credential_write)
        store.refresh((role + '-started.json', *(('plan-private.json',) if role == 'source' else DATA_FILES[1:] if role == 'provider' else ())))
    final = _safe_child_packet(final, args, role, payload)
    store.write(role + '-observed.json', {'actual': actual, 'closed_packet_pin': pin(canonical(final))})
    return final, actual


def _safe_child_packet(value, args, role, payload):
    try:
        require(type(value) is dict, 'worker_packet')
        if set(value) == {'capture_failure'}:
            require(value['capture_failure'] in FINITE, 'worker_packet'); return value
        require(value.get('binding') == binding(args), 'worker_packet')
        if set(value) == {'binding', 'preflight_failure'}:
            require(value['preflight_failure'] in FINITE, 'worker_packet'); return value
        require(value.get('role') == role, 'worker_packet')
        if set(value) == {'binding', 'role', 'failure_code', 'provider_state'}:
            require(value['failure_code'] in FINITE, 'worker_packet')
            if role == 'provider': validate_provider(value['provider_state'])
            else: require(value['provider_state'] is None, 'worker_packet')
        else:
            require(set(value) == {'binding', 'role', 'result'}, 'worker_packet')
            if role == 'source': validate_source(value['result'])
            elif role == 'provider': validate_provider(value['result'], success=True)
            else: _authentication(value['result'], payload['provider'])
        return value
    except BaseException:
        return {'capture_failure': 'worker_packet'}


def _accept_child(value, actual, role, args):
    _actual(actual)
    require(type(value) is dict and set(value) in ({'binding', 'role', 'result'}, {'binding', 'role', 'failure_code', 'provider_state'})
        and value['binding'] == binding(args) and value['role'] == role, 'worker_packet')
    if 'failure_code' in value:
        require(actual['actual_exit'] == 2 and value['failure_code'] in FINITE, 'worker_packet')
        if value['provider_state'] is not None: validate_provider(value['provider_state'])
        raise Refused(value['failure_code'])
    _actual(actual, zero=True); return value['result']


def run(args, deadline):
    key = None
    headroom()
    with Store() as store:
        store.write('claim.json', binding(args))
        for name in DATA_FILES: store.create(name)
        state = {'stage': 'source', 'source': None, 'source_actual': None, 'provider': None,
            'provider_actual': None, 'authentication': None, 'authentication_actual': None,
            'provider_failure_state': None, 'credential_handoff_complete': False, 'child_packets': {}}
        try:
            runtime = Path(tempfile.mkdtemp(prefix='r326-am-runtime-', dir=ROOT / '.pytest_cache'))
            result, actual = _child(args, store, 'source', {}, runtime, deadline)
            state['source_actual'] = actual; state['child_packets']['source'] = result
            source = _accept_child(result, actual, 'source', args); validate_source(source); state['source'] = source
            require(os.fstat(store.held['plan-private.json']['fd']).st_size == source['plan_pin']['byte_count'], 'plan')
            state['stage'] = 'credential_handoff'; environment._require_logging(); headroom()
            key = keychain.load_key('sharadar', timeout_seconds=min(20, remaining(deadline)))
            state['credential_handoff_complete'] = True; state['stage'] = 'provider'
            result, actual = _child(args, store, 'provider', {'source': source}, runtime, deadline, key=key)
            key = None; state['provider_actual'] = actual; state['child_packets']['provider'] = result
            if 'failure_code' in result: state['provider_failure_state'] = result['provider_state']
            provider = _accept_child(result, actual, 'provider', args); validate_provider(provider, success=True); state['provider'] = provider
            state['stage'] = 'authenticate'
            result, actual = _child(args, store, 'authenticate', {'source': source, 'provider': provider}, runtime, deadline)
            state['authentication_actual'] = actual; state['child_packets']['authenticate'] = result
            state['authentication'] = _accept_child(result, actual, 'authenticate', args)
            state['stage'] = 'postflight'; preflight(args, deadline); store.verify(); environment._require_logging()
            result = {'schema': SCHEMA, **state, 'all_requested_source_observations_retained': True,
                'provider_request_count': None, 'post_checks_complete': True, **FALSE_FLAGS}
            validate_result(result, args)
            report = store.write('report.json', {**binding(args), 'result': result}); store.verify()
            return {'result': result, 'report': report}
        except BaseException as error:
            failure = {'failure_code': finite(error), 'state': state, 'claim_consumed': True,
                'provider_request_count': None, **FALSE_FLAGS}
            try: store.write('failure.json', {**binding(args), **failure})
            except BaseException: pass
            return {'failure': failure}
        finally: key = None


def _state(value):
    keys = {'stage', 'source', 'source_actual', 'provider', 'provider_actual', 'authentication',
        'authentication_actual', 'provider_failure_state', 'credential_handoff_complete', 'child_packets'}
    require(type(value) is dict and set(value) == keys and value['stage'] in (*ROLES, 'credential_handoff', 'postflight')
        and type(value['credential_handoff_complete']) is bool, 'output')
    for name in ('source_actual', 'provider_actual', 'authentication_actual'):
        if value[name] is not None: _actual(value[name])
    if value['source'] is not None: validate_source(value['source']); _actual(value['source_actual'], zero=True)
    if value['credential_handoff_complete']: require(value['source'] is not None, 'output')
    if value['provider'] is not None:
        require(value['credential_handoff_complete'], 'output'); validate_provider(value['provider'], success=True); _actual(value['provider_actual'], zero=True)
    if value['provider_failure_state'] is not None: validate_provider(value['provider_failure_state'])
    if value['authentication'] is not None:
        require(value['provider'] is not None, 'output'); _actual(value['authentication_actual'], zero=True)
        _authentication(value['authentication'], value['provider'])
    require(type(value['child_packets']) is dict and set(value['child_packets']) in
        (set(), {'source'}, {'source', 'provider'}, {'source', 'provider', 'authenticate'}), 'output')


def _child_packet_joins(state, args, *, provider_prefix=None):
    for role, packet in state['child_packets'].items():
        actual_name = 'authentication_actual' if role == 'authenticate' else role + '_actual'
        actual = state[actual_name]; _actual(actual)
        require(type(packet) is dict, 'output')
        if set(packet) == {'capture_failure'}:
            # This is the broker's finite capture refusal, not a fabricated
            # canonical child envelope. Raw/noisy/partial output is hash-only.
            require(packet['capture_failure'] in FINITE, 'output')
            continue
        require(packet.get('binding') == binding(args), 'output')
        if set(packet) == {'binding', 'preflight_failure'}:
            require(packet['preflight_failure'] in FINITE and actual['actual_exit'] == 2, 'output')
        elif set(packet) == {'binding', 'role', 'failure_code', 'provider_state'}:
            require(packet['role'] == role and packet['failure_code'] in FINITE and actual['actual_exit'] == 2, 'output')
            if role == 'provider':
                validate_provider(packet['provider_state'])
                require(packet['provider_state'] == state['provider_failure_state'], 'output')
            else: require(packet['provider_state'] is None, 'output')
        else:
            require(set(packet) == {'binding', 'role', 'result'} and packet['role'] == role, 'output')
            result = packet['result']
            if role == 'source': validate_source(result)
            elif role == 'provider': validate_provider(result, success=True)
            else:
                require(state['provider'] is not None, 'output'); _authentication(result, state['provider'])
            accepted = state['authentication' if role == 'authenticate' else role]
            if accepted is not None: require(accepted == result, 'output')
        if role == 'provider' and provider_prefix is None: continue
        raw = (provider_prefix if role == 'provider' else b'') + canonical(packet) + b'\n'
        require(actual['stdout_bytes'] == len(raw) and actual['stdout_sha256'] == sha(raw), 'output')


def _authentication(value, provider):
    require(type(value) is dict and set(value) == {'complete_contiguous_corpus_authenticated', 'all_CSV_schemas_validated',
        'request_count', 'observed_price_rows', 'absent_expected_cells', 'response_summary_stream_sha256',
        'corpus_pin', 'dispatch_pin', 'captures_pin'} and value['complete_contiguous_corpus_authenticated'] is True
        and value['all_CSV_schemas_validated'] is True and type(value['request_count']) is int and value['request_count'] == REQUEST_COUNT
        and all(type(value[key]) is int and value[key] >= 0 for key in ('observed_price_rows', 'absent_expected_cells'))
        and value['observed_price_rows'] + value['absent_expected_cells'] == (5636 + 8) * prices.PRICE_SESSION_COUNT
        and _hash(value['response_summary_stream_sha256'])
        and all(value[key] == provider[key] for key in ('corpus_pin', 'dispatch_pin', 'captures_pin')), 'output')


def validate_result(value, args):
    require(type(value) is dict and set(value) == {'schema', *{'stage', 'source', 'source_actual', 'provider', 'provider_actual',
        'authentication', 'authentication_actual', 'provider_failure_state', 'credential_handoff_complete', 'child_packets'},
        'all_requested_source_observations_retained', 'provider_request_count', 'post_checks_complete', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['all_requested_source_observations_retained'] is True
        and value['post_checks_complete'] is True and value['provider_request_count'] is None
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    _state({key: value[key] for key in ('stage', 'source', 'source_actual', 'provider', 'provider_actual',
        'authentication', 'authentication_actual', 'provider_failure_state', 'credential_handoff_complete', 'child_packets')})
    require(value['stage'] == 'postflight' and value['authentication'] is not None
        and value['provider_failure_state'] is None, 'output')
    _packet_actual(value['source_actual'], args, 'source', value['source'])
    _packet_actual(value['authentication_actual'], args, 'authenticate', value['authentication'])
    _child_packet_joins(value, args)


def validate_output(raw, actual_exit, args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_EXTERNAL and raw.endswith(b'\n')
        and type(actual_exit) is int and actual_exit in (0, 2), 'output')
    lines = raw.splitlines(); require(1 <= len(lines) <= REQUEST_COUNT + 1, 'output')
    previous_progress = (0, 0, 0)
    for line in lines[:-1]:
        value = parse(line); require(canonical(value) == line, 'output'); validate_progress(value)
        now = tuple(value[key] for key in ('completed_HTTP200_bodies', 'application_dispatch_intents', 'retained_corpus_bytes'))
        require(now[0] == previous_progress[0] + 1 and now[1] == now[0] and now[2] > previous_progress[2], 'output')
        previous_progress = now
    value = parse(lines[-1]); require(canonical(value) == lines[-1] and type(value) is dict
        and value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and len(lines) == 1 and value['preflight_failure'] in FINITE, 'output'); return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failed = outcome['failure']
        require(actual_exit == 2 and type(failed) is dict and set(failed) == {'failure_code', 'state', 'claim_consumed',
            'provider_request_count', *FALSE_FLAGS} and failed['failure_code'] in FINITE
            and failed['claim_consumed'] is True and failed['provider_request_count'] is None
            and all(failed[key] is False for key in FALSE_FLAGS), 'output'); _state(failed['state'])
        state = failed['state']
        _child_packet_joins(state, args, provider_prefix=b''.join(line + b'\n' for line in lines[:-1]))
        if state['source'] is not None: _packet_actual(state['source_actual'], args, 'source', state['source'])
        if state['authentication'] is not None:
            _packet_actual(state['authentication_actual'], args, 'authenticate', state['authentication'])
        if state['provider'] is not None:
            _packet_actual(state['provider_actual'], args, 'provider', state['provider'], prefix=b''.join(line + b'\n' for line in lines[:-1]))
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'} and len(lines) == REQUEST_COUNT + 1, 'output')
        validate_result(outcome['result'], args)
        require(outcome['report'] == pin(canonical({**binding(args), 'result': outcome['result']}))
            and previous_progress == (REQUEST_COUNT, REQUEST_COUNT, outcome['result']['provider']['retained_corpus_bytes']), 'output')
        _packet_actual(outcome['result']['provider_actual'], args, 'provider', outcome['result']['provider'],
            prefix=b''.join(line + b'\n' for line in lines[:-1]))
        _child_packet_joins(outcome['result'], args, provider_prefix=b''.join(line + b'\n' for line in lines[:-1]))
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('run', *ROLES, 'validate'))
    parser.add_argument('--expected-head', required=True); parser.add_argument('--caller-sha256', required=True)
    for name in ('control-fd', 'claim-fd', 'intent-fd', 'started-fd', 'credential-fd', 'actual-exit'):
        parser.add_argument('--' + name, type=int)
    parser.add_argument('--data-fds'); args = parser.parse_args(argv)
    seconds = {'run': DEADLINE_SECONDS, 'source': SOURCE_SECONDS, 'provider': DEADLINE_SECONDS,
        'authenticate': AUTH_SECONDS, 'validate': VALIDATOR_SECONDS}[args.operation]
    deadline = time.monotonic() + seconds
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline)
            if args.operation == 'run':
                previous._bootstrap_broker_logging(); outcome = run(args, deadline)
                emit({'binding': binding(args), 'outcome': outcome}); return 2 if 'failure' in outcome else 0
            environment._bootstrap_cli_logging()
            if args.operation == 'validate':
                raw = sys.stdin.buffer.read(MAX_EXTERNAL + 1); validate_output(raw, args.actual_exit, args)
                sys.stdout.buffer.write(raw); return 0
            _credential_free(); raw = sys.stdin.buffer.read(MAX_FRAME + 1)
            require(len(raw) <= MAX_FRAME and type(args.data_fds) is str, 'arguments')
            args.data_fds = tuple(int(value) for value in args.data_fds.split(','))
            _inherited(args, args.operation, raw, deadline); packet = parse(raw)
            provider_state = _provider_state()
            try:
                if args.operation == 'source':
                    require(packet == {}, 'worker_scope'); result = source_observation(args.data_fds[0], deadline)
                elif args.operation == 'provider':
                    require(type(packet) is dict and set(packet) == {'source'} and type(args.credential_fd) is int
                        and args.credential_fd > 2 and args.credential_fd not in (*args.data_fds,
                            args.control_fd, args.claim_fd, args.intent_fd, args.started_fd)
                        and stat.S_ISFIFO(os.fstat(args.credential_fd).st_mode)
                        and os.fstat(args.credential_fd).st_uid == os.getuid(), 'worker_scope')
                    secret = os.read(args.credential_fd, keychain.MAX_KEY_BYTES + 1); os.close(args.credential_fd)
                    require(8 <= len(secret) <= keychain.MAX_KEY_BYTES, 'credential_handoff')
                    result = provider_observation(args.data_fds, packet['source'], secret.decode('ascii'), provider_state, deadline)
                    secret = None
                else:
                    require(type(packet) is dict and set(packet) == {'source', 'provider'}, 'worker_scope')
                    result = authenticate_observation(args.data_fds, packet['source'], packet['provider'], deadline)
                preflight(args, deadline); environment.require_safe_environment()
                emit({'binding': binding(args), 'role': args.operation, 'result': result}); return 0
            except BaseException as error:
                emit({'binding': binding(args), 'role': args.operation, 'failure_code': finite(error),
                    'provider_state': provider_state if args.operation == 'provider' else None}); return 2
    except BaseException as error:
        emit({'binding': binding(args), 'preflight_failure': finite(error)}); return 2


if __name__ == '__main__': raise SystemExit(main())
