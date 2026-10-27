"""One bounded anonymous public-FIGI observation for five retained blockers.

Only two fixed private DATA leaves are consumed. Public mapping requests carry
validated FIGIs only. Raw HTTP200 bodies are provisional private evidence;
the final case/provenance package requires normal source-guard return.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile
import time

import requests

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import prepare_arv2_r298_price_lineage as previous
from scripts import arv2_r298_ac_source_binding as anchor
from scripts import arv2_r298_public_figi_corroboration as figi
from scripts import arv2_r298_fixed_data_guard as data_guard

admitted, environment, security = previous.admitted, previous.environment, previous.security
capture_support, canonical, parse, sha, metadata, capture = (
    previous.capture_support, previous.canonical, previous.parse, previous.sha, previous.metadata, previous.capture)
PYTHON = previous.PYTHON
SOURCE = ROOT / 'scripts/inspect_arv2_r298_public_figi_lineage.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_public_figi_lineage/R326-20261027-AD'
SCHEMA = 'arv2-r298-public-figi-lineage-ad-v1'
DEADLINE_SECONDS, OUTER_SECONDS, VALIDATOR_SECONDS, REQUEST_SECONDS = 600, 630, 20, 30
MAX_SOURCE, MAX_PRIVATE, MAX_OUTPUT, MAX_FILES = 64 * 1024 * 1024, 32 * 1024 * 1024, 128 * 1024, 12
MAX_BODY, MAX_AGGREGATE, MAX_CASES, MAX_FIGIS, MAX_BATCHES = 2 * 1024 * 1024, 6 * 1024 * 1024, 4 * 1024 * 1024, 30, 3
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
ENDPOINT = 'https://api.openfigi.com/v3/mapping'
HEADERS = {'Accept': 'application/json', 'Content-Type': 'application/json',
    'Accept-Encoding': 'identity', 'User-Agent': 'research-identity-probe/1'}
FILE_PLAN = {
    'ac_plan': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_price_lineage/R326-20261027-AC/price-lineage-private.json',
        'byte_count': 16344399, 'sha256': '4366e1e8a218fb21afc6ef3d88dfed9c2ab8b784a7718a405616850e1a4d6ddc'},
    'aa_frame': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_all_routes_offline/R326-20261027-AA/routes-private.json',
        'byte_count': 19895631, 'sha256': '3776f03b4941d8e6d014dee19f5ee8a05080f214ab7f502d10738f00a689f561'},
}
PRIVATE_NAME = 'public-figi-private.json'
RESPONSE_NAMES = tuple('response-%02d.json' % index for index in range(1, MAX_BATCHES + 1))
AC_CALLER_SHA256 = '2b6de35e7115010573ba40221a85a29174db8004ff35faea5932799b963618d3'
AC_HEAD = 'd25ab8eaaa4a3abea39c41b7e3d6470b429c4e16'
AC_PROFILE_SHA256 = '50a927fc2ce78c79728594a28837c6b8de5d2b152366427e9fba269326a5562b'
AC_FACT_SHA256 = '1ca8c38addfd4dc98b86e425147a01633dac132bc3146902ac860754faabe775'
AC_SUMMARY_SHA256 = '112daa665daefaaef723e3fd3379196f4d85a7d920f80edf0b9d0fdb063ee5ef'
NEW_PINS = {
    'scripts/prepare_arv2_r298_price_lineage.py': AC_CALLER_SHA256,
    'scripts/arv2_r298_ac_source_binding.py': '112221b42d0c35065fec96ea55dc124c2e66101d8e6011bd91160d4a97576d0b',
    'scripts/arv2_r298_public_figi_corroboration.py': '1b7c3151266023286b4170b0b2412acc08c7bbb011d86a2ec012cfc3db4eb54e',
}
FALSE_FLAGS = {'vendor_global_collision_cleared': False, 'original_FIGI_replaced': False,
    'historical_identity_or_price_continuity_proven': False, 'credential_access': False, 'qc_contact': False,
    'old_controls_read': False, 'original_TICKERS_reread': False,
    'refused_bindings_dropped': False, 'old_operation_invoked': False, 'new_paid_rights': False,
    'price_acquired': False, 'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'licensed_rows_disclosed': False,
    'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin', 'source_changed',
    'source_binding', 'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'capture_changed', 'capture_security', 'frame', 'inventory', 'original_figi_invalid', 'candidate_rows_missing',
    'candidate_row_shape', 'candidate_figi_missing', 'candidate_figi_invalid', 'figi_inventory_bound',
    'case_bound', 'request', 'transport_unknown', 'http_status', 'http_status_shape', 'response_headers',
    'response_bound', 'cookie', 'mapping_binding', 'private_binding', 'output', 'output_bound',
    'parent_failed', 'validator_failed', 'execution_environment_refused', 'os_error', 'refused', 'unknown_exception'))


class Refused(ValueError):
    """Finite recovery predicate only, never rows or exception strings."""


def require(value, code):
    if not value:
        raise Refused(code)


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= DEADLINE_SECONDS, 'deadline')
    return value


def finite(error):
    if type(error) is admitted.helpers.Deadline:
        return 'deadline'
    for module, prefix in ((figi, 'figi_'), (data_guard, 'guard_')):
        if type(error) is module.Refused:
            code = module.finite(error)
            return prefix + code if code in module.FINITE else 'refused'
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, requests.exceptions.RequestException):
        return 'transport_unknown'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    return type(value) is str and value in FINITE | {
        prefix + code for module, prefix in ((figi, 'figi_'), (data_guard, 'guard_')) for code in module.FINITE}


def pins():
    result = previous.pins()
    require(len(result) == 175, 'source_pin')
    for name, pin in NEW_PINS.items():
        require(name not in result or result[name] == pin, 'source_pin')
        require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64, 'source_pin')
        result[name] = pin
    return result


def preflight(args, deadline):
    require(not admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], admitted.frozen.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        require(admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    committed = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':'
        + SOURCE.relative_to(ROOT).as_posix()], deadline, MAX_OUTPUT)
    require(sha(committed) == args.caller_sha256, 'source_pin')
    remaining(deadline)


def security_snapshot(fd, *, source=False):
    try:
        return security.snapshot(fd)
    except security.Refusal:
        raise Refused('source_security' if source else 'capture_security') from None


class Store:
    """Only the new AD leaf and original descriptors; no old control reader."""
    def __init__(self):
        self.fd, self.chain, self.files, self.held = None, [], {}, {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                path = Path(*CONTROL.parts[:index + 1])
                if path in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    except FileExistsError:
                        require(path != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt
                self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd
            self.directory_security = security_snapshot(fd)
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for fd, _ in self.held.values():
            os.close(fd)
        os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(self.fd)) == metadata(os.fstat(other))
                and os.fstat(other).st_uid == os.getuid() and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and security_snapshot(self.fd) == self.directory_security, 'control_changed')
            for name, baseline in self.files.items():
                fd, snapshot = self.held[name]
                require(baseline == metadata(os.fstat(fd))
                    == metadata(os.stat(name, dir_fd=other, follow_symlinks=False))
                    and security_snapshot(fd) == snapshot, 'capture_changed')
        finally:
            os.close(other)

    @staticmethod
    def _read(fd, size, *, deadline=None):
        os.lseek(fd, 0, os.SEEK_SET)
        result = bytearray()
        while len(result) <= size:
            if deadline is not None:
                remaining(deadline)
            chunk = os.read(fd, min(65536, size + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
        return bytes(result)

    def write(self, name, value):
        return self.write_bytes(name, canonical(value), private=False)

    def write_bytes(self, name, raw, *, private):
        self.verify()
        require(type(name) is str and name not in self.files and len(self.files) < MAX_FILES
            and ((private is True and name in (PRIVATE_NAME, *RESPONSE_NAMES))
                or (private is False and re.fullmatch(r'[a-z0-9-]{1,100}\.json', name))), 'control_name')
        require(type(raw) is bytes and 0 < len(raw) <= (MAX_BODY if name in RESPONSE_NAMES and private else MAX_PRIVATE if private else MAX_OUTPUT), 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        kept = False
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0, 'control_write')
            snapshot = security_snapshot(fd)
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); require(count > 0, 'control_write'); view = view[count:]
            os.fsync(fd); os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            require(self._read(fd, len(raw)) == raw and metadata(info) == metadata(os.fstat(fd))
                and security_snapshot(fd) == snapshot, 'capture_changed')
            self.files[name] = metadata(info); self.held[name] = (fd, snapshot); kept = True
        finally:
            if not kept:
                os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}


def _artifact_policy(leaves, *, package=None):
    directories = {ROOT / 'artifacts'}
    for path in [*leaves, *(() if package is None else (package,))]:
        directories.update(parent for parent in path.parents if ROOT / 'artifacts' == parent
            or ROOT / 'artifacts' in parent.parents)
    exceptions = ''.join(f'(require-not (literal "{path}"))' for path in sorted(directories | set(leaves)))
    subtree = '' if package is None else f'(require-not (subpath "{package}"))'
    return f'(deny file-read* (require-all (subpath "{ROOT / "artifacts"}") {subtree} {exceptions}))'


def _pin(role):
    row = FILE_PLAN[role]
    return {'byte_count': row['byte_count'], 'sha256': row['sha256']}


def source_binding():
    fact, summary = anchor.observed_fact(), anchor.expected_summary()
    require(sha(figi.canonical(fact)) == AC_FACT_SHA256
        and sha(figi.canonical(summary)) == AC_SUMMARY_SHA256, 'source_binding')
    require(fact['expected_head'] == AC_HEAD and fact['caller_sha256'] == AC_CALLER_SHA256
        and fact['profile_sha256'] == AC_PROFILE_SHA256
        and fact['private_file'] == {'relative_path': FILE_PLAN['ac_plan']['relative_path'], **_pin('ac_plan')},
        'source_binding')
    for name in ('producer', 'validator'):
        value = fact[name]
        require(type(value['actual_exit']) is int and value['actual_exit'] == 0
            and value['bound'] is None and value['spawn_observed'] is True
            and value['stderr_bytes'] == 0 and value['stderr_sha256'] == sha(b''), 'source_binding')
    require(fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes']
        and fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256'], 'source_binding')
    previous.routes.validate_summary(summary)
    aa = previous.previous.aa_summary()
    require(summary['private_frame_byte_count'] == _pin('ac_plan')['byte_count']
        and summary['private_frame_sha256'] == _pin('ac_plan')['sha256']
        and summary['source_pins']['aa_frame'] == _pin('aa_frame')
        and {'byte_count': aa['private_frame_byte_count'], 'sha256': aa['private_frame_sha256']} == _pin('aa_frame')
        and summary['disposition_counts']['stocks'] == {'routed': 5636, 'refused': 5, 'conditional_never_potential': 510}
        and summary['refusal_counts']['stocks'] == {'identity_missing': 4, 'global_collision': 1}, 'source_binding')
    return {'ac_summary': summary, 'aa_routing_summary': aa['routing_summary']}


def profile_record():
    source_binding()
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'source': str(SOURCE), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'one_independent_current_public_FIGI_observation_for_exact_five_retained_price_blockers',
        'fixed_data_plan': data_guard.checked_plan(FILE_PLAN),
        'source_guard_profile': data_guard.profile_record(FILE_PLAN),
        'AC_observation': anchor.profile_record(), 'AC_observed_fact_sha256': AC_FACT_SHA256,
        'AC_summary_sha256': AC_SUMMARY_SHA256, 'mapping_profile': figi.profile_record(),
        'source_data_leaf_count': 2, 'source_summary_old_four_input_pins_are_prior_observations_not_new_reads': True,
        'candidate_scope': 'ALL_RETAINED_AA_perma_FIGI_ticker_union_for_five_cases_not_vendor_global_CUSIP_or_poison_census',
        'source_global_collision_blocker_retained_regardless_mapping': True,
        'all_five_cases_and_all_retained_physical_candidates_counted_before_contact': True,
        'missing_invalid_or_overbound_inventory': 'refuse_entire_inventory_no_subset_or_alternate_identifier',
        'endpoint': ENDPOINT, 'job_identifier_type': 'ID_BB_GLOBAL',
        'request_fields': ['idType', 'idValue', 'includeUnlistedEquities'],
        'exchange_or_market_filters': False, 'API_key_auth_cookie_proxy_or_env_credentials': False,
        'headers': dict(HEADERS), 'maximum_unique_FIGIs': MAX_FIGIS, 'maximum_batches': MAX_BATCHES,
        'maximum_jobs_per_batch': 10, 'maximum_request_bytes': figi.MAX_REQUEST,
        'maximum_response_bytes': MAX_BODY, 'maximum_aggregate_response_bytes': MAX_AGGREGATE,
        'maximum_cases_before_contact_bytes': MAX_CASES, 'maximum_source_bytes': MAX_SOURCE,
        'maximum_private_bytes': MAX_PRIVATE, 'maximum_public_bytes': MAX_OUTPUT, 'maximum_control_files': MAX_FILES,
        'producer_seconds': DEADLINE_SECONDS, 'outer_seconds': OUTER_SECONDS,
        'request_seconds': REQUEST_SECONDS, 'validator_seconds': VALIDATOR_SECONDS,
        'request_alarm_preserves_existing_parent_timer': True,
        'claim_consumes_even_without_source_read_or_contact': True, 'partial_claim_is_ambiguous_spent': True,
        'dispatch_intent_durable_before_actual_send': True, 'dispatch_intent_is_not_server_contact_measurement': True,
        'response_bytes_measure': 'completed_end_validated_entity_bodies_not_partial_wire_bytes_or_contact_accounting',
        'non200_numeric_status_only_no_response_body_read': True,
        'successful_raw_responses_retained_before_semantics': True,
        'provisional_raw_response_files_are_not_accepted_corroboration': True,
        'final_private_package_after_normal_source_guard_return_only': True,
        'all_source_blockers_remain_and_original_FIGIs_are_never_rewritten': True,
        'no_retry_redirect_fallback_filter_change_or_truncation': True,
        'owned_session_redirect_resolution': 'empty_iterator_no_3xx_body_read_or_follow',
        'native_producer_outbound_HTTPS_DNS_ports_not_domain_fence': True,
        'application_exact_TLS_verified_endpoint_is_required': True,
        'producer_Keychain_and_security_CLI_denial': True,
        'producer_writes_only_own_AD_control_root_cache_or_null': True,
        'observer_is_public_only_no_data_stage_broker': True,
        'one_native_producer_no_nested_sandbox_or_inner_child': True,
        'selected_pins_not_whole_interpreter_integrity': True,
        'actual_exit_and_independent_native_output_validator_required': True,
        'deadline_uninterruptible_IO_host_suspension_qualification': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': sha(canonical(profile_record()))}


def native_profile(*, mode):
    require(mode in ('producer', 'validator'), 'arguments')
    base = '(version 1)(allow default)'
    if mode == 'validator':
        base += '(deny network*)'
    else:
        base += ('(deny network-bind)(deny network-inbound)'
            '(deny network-outbound (require-all (require-not (remote tcp "*:443"))'
            ' (require-not (remote tcp "*:53")) (require-not (remote udp "*:53"))))')
    base += ''.join(f'(deny file-read* file-write* (subpath "{path}"))'
        for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    base += '(deny process-exec (literal "/usr/bin/security"))'
    exceptions = f'(require-not (subpath "{ROOT / ".pytest_cache"}"))(require-not (literal "/dev/null"))'
    if mode == 'producer':
        exceptions += f'(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))'
    base += f'(deny file-write* (require-all {exceptions}))'
    if mode == 'validator':
        return base + f'(deny file-read* (subpath "{ROOT / "artifacts"}"))'
    return base + _artifact_policy([*(ROOT / row['relative_path'] for row in FILE_PLAN.values()), CONTROL,
        *(CONTROL / name for name in ('claim.json', 'source-start.json',
            *(('dispatch-%02d.json' % index) for index in range(1, MAX_BATCHES + 1)),
            *RESPONSE_NAMES, PRIVATE_NAME, 'report.json', 'failure.json'))])


def _decode_private(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'frame'); value[key] = item
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('frame')))
        require(type(value) is dict and figi.canonical(value) == raw, 'frame')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('frame') from None


def _frames(buffers, deadline):
    require(type(buffers) is dict and set(buffers) == set(FILE_PLAN), 'frame')
    # Both complete external byte pins are checked BEFORE either JSON decode.
    require(all(type(buffers[role]) is bytes and len(buffers[role]) == pin['byte_count']
        and sha(buffers[role]) == pin['sha256'] for role, pin in FILE_PLAN.items()), 'frame')
    expected = source_binding()
    ac = previous.routes.validate_private_record(_decode_private(buffers['ac_plan']),
        expected_summary=expected['ac_summary'])
    previous.routes.evidence.inspect(buffers['aa_frame'],
        expected_summary=expected['aa_routing_summary'], deadline=deadline)
    aa = _decode_private(buffers['aa_frame'])
    return _aligned_inventory(ac, aa, expected['aa_routing_summary']['binding_contract'], deadline)


def _aligned_inventory(ac, aa, contract, deadline):
    """Pure all-row alignment after both fixed production frames validate."""
    require(ac['binding_contract'] == aa['binding_contract'] == contract
        and type(ac['stocks']) is list and len(ac['stocks']) == 6151
        and type(aa['stocks']) is list and len(aa['stocks']) == 6151
        and type(ac['funds']) is list and len(ac['funds']) == 8
        and type(aa['funds']) is list and len(aa['funds']) == 8, 'inventory')
    for index, (left, right) in enumerate(zip(ac['stocks'], aa['stocks'], strict=True)):
        remaining(deadline)
        require(type(left['binding_ordinal']) is int and type(right['binding_ordinal']) is int
            and left['binding_ordinal'] == index == right['binding_ordinal']
            and left['binding'] == right['binding'], 'inventory')
    for index, (left, right) in enumerate(zip(ac['funds'], aa['funds'], strict=True)):
        require(type(left['fund_ordinal']) is int and type(right['fund_ordinal']) is int
            and left['fund_ordinal'] == index == right['fund_ordinal'] and left['ticker'] == right['ticker'], 'inventory')
    return ac, aa


def _valid_figi(value):
    try:
        jobs = figi.mapping_jobs([value])
    except figi.Refused:
        return False
    return type(jobs) is list and jobs == [{'idType': 'ID_BB_GLOBAL', 'idValue': value, 'includeUnlistedEquities': True}]


def _selection(ac, aa, deadline):
    selected = [(left, aa['stocks'][index]) for index, left in enumerate(ac['stocks'])
        if left['disposition'] == 'refused']
    require(len(selected) == 5 and Counter(left['reason'] for left, _ in selected)
        == {'identity_missing': 4, 'global_collision': 1}, 'inventory')
    cases, counts, ids, predicates = [], [], set(), Counter()
    for ordinal, (left, right) in enumerate(selected):
        remaining(deadline)
        original = left['binding']['composite_figi']
        valid_original = _valid_figi(original)
        predicates['original_figi_invalid'] += not valid_original
        if valid_original: ids.add(original)
        rows = right['current_candidate_rows']
        require(type(rows) is list, 'inventory')
        missing, invalid, malformed, current_ids = 0, 0, 0, set()
        if not rows: predicates['candidate_rows_missing'] += 1
        for row in rows:
            remaining(deadline)
            if type(row) is not dict:
                malformed += 1; continue
            value = row.get('figi')
            if value is None or value == '':
                missing += 1
            elif not _valid_figi(value):
                invalid += 1
            else:
                ids.add(value); current_ids.add(value)
        predicates['candidate_row_shape'] += malformed
        predicates['candidate_figi_missing'] += missing
        predicates['candidate_figi_invalid'] += invalid
        cases.append({'case_ordinal': ordinal, 'ac_stock': left, 'aa_stock': right,
            'original_figi': original, 'candidate_figis': sorted(current_ids)})
        counts.append({'case_ordinal': ordinal, 'retained_candidate_row_count': len(rows),
            'missing_figi_count': missing, 'invalid_figi_count': invalid, 'malformed_candidate_row_count': malformed,
            'original_figi_valid': valid_original})
    if len(ids) > MAX_FIGIS: predicates['figi_inventory_bound'] += 1
    case_record = {'schema': SCHEMA + '-private-selection', 'cases': cases, 'figis': sorted(ids)}
    case_raw = figi.canonical(case_record)
    if len(case_raw) > MAX_CASES: predicates['case_bound'] += 1
    codes = [code for code in ('original_figi_invalid', 'candidate_rows_missing', 'candidate_row_shape',
        'candidate_figi_missing', 'candidate_figi_invalid', 'figi_inventory_bound', 'case_bound') if predicates[code]]
    summary = {'case_count': 5, 'source_stock_count': 6151, 'source_fund_count': 8,
        'source_refusal_counts': {'identity_missing': 4, 'global_collision': 1},
        'candidate_scope': 'ALL_RETAINED_AA_perma_FIGI_ticker_union_not_global_counterparty_census',
        'case_counts': counts, 'unique_valid_figi_count': len(ids),
        'inventory_predicate_counts': {code: predicates[code] for code in codes},
        'inventory_refusal': codes[0] if codes else None,
        'planned_job_count': 0 if codes else len(ids),
        'planned_batch_count': 0 if codes else (len(ids) + 9) // 10,
        'private_case_byte_count': len(case_raw), 'private_case_sha256': sha(case_raw)}
    return summary, case_record


@contextmanager
def _request_alarm(deadline):
    """An inner request timer preserves the main producer's existing timer."""
    remaining(deadline)
    started, prior_handler = time.monotonic(), signal.getsignal(signal.SIGALRM)
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    target = min(deadline, started + prior_timer[0]) if prior_timer[0] > 0 else deadline
    def expired(signum, frame):
        raise admitted.helpers.Deadline()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.000001, target - time.monotonic()))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)
        if prior_timer[0] > 0:
            restored = prior_timer[0] - (time.monotonic() - started)
            if restored <= 0:
                raise admitted.helpers.Deadline()
            signal.setitimer(signal.ITIMER_REAL, restored, prior_timer[1])


class OwnedSession(requests.Session):
    """Even allow_redirects=False must not enter Requests' 3xx-body resolver."""
    def resolve_redirects(self, *args, **kwargs):
        return iter(())


def _session():
    session = OwnedSession()
    session.trust_env, session.auth, session.verify, session.cert, session.max_redirects = False, None, True, None, 0
    session.headers.clear(); session.headers.update(HEADERS)
    session.cookies.clear(); session.proxies.clear(); session.params.clear()
    session.hooks = {'response': []}
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
    return session


def _session_check(session):
    require(type(session) is OwnedSession and session.trust_env is False
        and session.auth is None and session.verify is True
        and session.cert is None and session.max_redirects == 0
        and dict(session.headers) == HEADERS and not session.cookies and not session.proxies
        and not session.params and session.hooks == {'response': []}
        and session.get_adapter(ENDPOINT).max_retries.total == 0, 'request')


def _prepared(session, raw):
    _session_check(session)
    prepared = session.prepare_request(requests.Request('POST', ENDPOINT, data=raw))
    expected = {key.casefold(): value for key, value in HEADERS.items()}
    expected['content-length'] = str(len(raw))
    require(prepared.method == 'POST' and prepared.url == ENDPOINT
        and type(prepared.body) is bytes and prepared.body == raw
        and prepared.hooks == {'response': []}
        and len(prepared.headers) == len(expected)
        and {key.casefold(): value for key, value in prepared.headers.items()} == expected, 'request')
    return prepared


def _fetch(session, batch, request_raw, index, directory, guard, state, args, deadline):
    environment.require_safe_environment(); guard.verify(); _session_check(session)
    prepared = _prepared(session, request_raw)
    intent = {'batch_ordinal': index, 'dispatch_intent_count': index + 1,
        'request_pin': {'byte_count': len(request_raw), 'sha256': sha(request_raw)}, 'job_count': len(batch)}
    state['dispatch_intents'].append(intent)
    directory.write('dispatch-%02d.json' % (index + 1), {**binding(args), 'intent': intent})
    request_deadline = time.monotonic() + min(REQUEST_SECONDS, remaining(deadline))
    with _request_alarm(request_deadline):
        with session.send(prepared, timeout=min(REQUEST_SECONDS, remaining(request_deadline)),
                allow_redirects=False, stream=True, verify=True, proxies={}) as response:
            guard.verify(); environment.require_safe_environment()
            status = response.status_code
            require(type(status) is int and 100 <= status <= 599, 'http_status_shape')
            state['http_statuses'].append(status)
            require(not session.cookies, 'cookie')
            _session_check(session)
            require(response.url == ENDPOINT and not response.history
                and response.request is prepared, 'response_headers')
            if status != 200:
                return status, None
            encoding = response.headers.get('Content-Encoding', 'identity')
            content_type = response.headers.get('Content-Type', '')
            require(type(encoding) is str and encoding.casefold() == 'identity'
                and type(content_type) is str and len(content_type) <= 100
                and [part.strip() for part in content_type.casefold().split(';')] in
                    (['application/json'], ['application/json', 'charset=utf-8'])
                and not response.headers.get('Set-Cookie'), 'response_headers')
            declared = response.headers.get('Content-Length')
            require(declared is None or (type(declared) is str and 0 < len(declared) <= 10 and declared.isdecimal()
                and 0 < int(declared) <= MAX_BODY), 'response_bound')
            chunks, count = [], 0
            for chunk in response.iter_content(chunk_size=65536, decode_unicode=False):
                remaining(request_deadline); guard.verify()
                require(type(chunk) is bytes, 'response_bound')
                count += len(chunk)
                require(count <= MAX_BODY and state['response_bytes'] + count <= MAX_AGGREGATE, 'response_bound')
                chunks.append(chunk)
            raw = b''.join(chunks)
            require(0 < len(raw) <= MAX_BODY and (declared is None or len(raw) == int(declared)), 'response_bound')
    remaining(deadline); guard.verify(); environment.require_safe_environment()
    state['response_bytes'] += len(raw)
    name = RESPONSE_NAMES[index]
    state['response_pins'][name] = directory.write_bytes(name, raw, private=True)
    require(state['response_pins'][name] == {'byte_count': len(raw), 'sha256': sha(raw)}, 'mapping_binding')
    return status, raw

def _selection_summary(value):
    keys = {'case_count', 'source_stock_count', 'source_fund_count', 'source_refusal_counts',
        'candidate_scope', 'case_counts', 'unique_valid_figi_count', 'inventory_predicate_counts',
        'inventory_refusal', 'planned_job_count', 'planned_batch_count', 'private_case_byte_count', 'private_case_sha256'}
    require(type(value) is dict and set(value) == keys and type(value['case_count']) is int and value['case_count'] == 5
        and type(value['source_stock_count']) is int and value['source_stock_count'] == 6151
        and type(value['source_fund_count']) is int and value['source_fund_count'] == 8
        and type(value['source_refusal_counts']) is dict
        and value['source_refusal_counts'] == {'identity_missing': 4, 'global_collision': 1}
        and all(type(count) is int for count in value['source_refusal_counts'].values())
        and value['candidate_scope'] == 'ALL_RETAINED_AA_perma_FIGI_ticker_union_not_global_counterparty_census'
        and type(value['case_counts']) is list and len(value['case_counts']) == 5
        and type(value['unique_valid_figi_count']) is int and 0 <= value['unique_valid_figi_count'] <= MAX_SOURCE
        and type(value['private_case_byte_count']) is int and 0 < value['private_case_byte_count'] <= MAX_PRIVATE
        and type(value['private_case_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['private_case_sha256']), 'output')
    observed = Counter()
    for index, case in enumerate(value['case_counts']):
        fields = {'case_ordinal', 'retained_candidate_row_count', 'missing_figi_count', 'invalid_figi_count',
            'malformed_candidate_row_count', 'original_figi_valid'}
        require(type(case) is dict and set(case) == fields and type(case['case_ordinal']) is int
            and case['case_ordinal'] == index and type(case['original_figi_valid']) is bool
            and all(type(case[key]) is int and 0 <= case[key] <= MAX_SOURCE for key in
                ('retained_candidate_row_count', 'missing_figi_count', 'invalid_figi_count', 'malformed_candidate_row_count'))
            and case['missing_figi_count'] + case['invalid_figi_count'] + case['malformed_candidate_row_count']
                <= case['retained_candidate_row_count'], 'output')
        observed['original_figi_invalid'] += not case['original_figi_valid']
        observed['candidate_rows_missing'] += not case['retained_candidate_row_count']
        observed['candidate_row_shape'] += case['malformed_candidate_row_count']
        observed['candidate_figi_missing'] += case['missing_figi_count']
        observed['candidate_figi_invalid'] += case['invalid_figi_count']
    observed['figi_inventory_bound'] = int(value['unique_valid_figi_count'] > MAX_FIGIS)
    observed['case_bound'] = int(value['private_case_byte_count'] > MAX_CASES)
    order = ('original_figi_invalid', 'candidate_rows_missing', 'candidate_row_shape',
        'candidate_figi_missing', 'candidate_figi_invalid', 'figi_inventory_bound', 'case_bound')
    expected = {key: observed[key] for key in order if observed[key]}
    require(value['inventory_predicate_counts'] == expected and value['inventory_refusal'] ==
        (next(iter(expected)) if expected else None)
        and type(value['planned_job_count']) is int and value['planned_job_count'] ==
            (0 if expected else value['unique_valid_figi_count'])
        and type(value['planned_batch_count']) is int and value['planned_batch_count'] ==
            (0 if expected else (value['unique_valid_figi_count'] + 9) // 10)
        and (expected or 0 < value['planned_job_count'] <= MAX_FIGIS), 'output')


def _jobs(values):
    jobs = figi.mapping_jobs(values)
    require(type(jobs) is list and len(jobs) == len(values) and all(job == {
        'idType': 'ID_BB_GLOBAL', 'idValue': value, 'includeUnlistedEquities': True}
        for job, value in zip(jobs, values, strict=True)), 'request')
    raw = figi.canonical(jobs)
    require(0 < len(raw) <= figi.MAX_REQUEST, 'request')
    return raw


def _observations(selection, batches, deadline):
    observations, counts = [], Counter()
    for case in selection['cases']:
        remaining(deadline)
        for candidate in case['candidate_figis']:
            observed = figi.corroborate(case['original_figi'], candidate, batches=batches, deadline=deadline)
            figi.validate_observation(observed)
            observations.append({'case_ordinal': case['case_ordinal'], 'original_figi': case['original_figi'],
                'candidate_figi': candidate, 'observation': observed})
            counts[observed['observation']] += 1
    return dict(sorted(counts.items())), observations


def _package(selection_summary, selection, batches, observations, state):
    require(sha(figi.canonical(selection)) == selection_summary['private_case_sha256']
        and len(figi.canonical(selection)) == selection_summary['private_case_byte_count'], 'private_binding')
    checked_batches = []
    for summary, record in batches:
        figi.validate_private_record(record, expected_summary=summary)
        checked_batches.append({'summary': summary, 'private_mapping': record})
    for item in observations:
        figi.validate_observation(item['observation'])
    value = {'schema': SCHEMA + '-private', 'source_pins': {
        role: _pin(role) for role in FILE_PLAN}, 'AC_summary_sha256': AC_SUMMARY_SHA256,
        'selection_summary': selection_summary, 'selection': selection,
        'mapping_batches': checked_batches, 'corroborations': observations,
        'response_pins': dict(state['response_pins']), 'terminal_failure_code': state['terminal_failure_code'],
        'vendor_source_blockers_remaining': 5,
        'candidate_scope': 'complete_retained_AA_subset_not_vendor_global_counterparty_census',
        'no_original_identifier_or_vendor_collision_clearance': True}
    raw = figi.canonical(value)
    require(0 < len(raw) <= MAX_PRIVATE, 'private_binding')
    return raw


def _failed(code, state, directory, args):
    require(_finite_code(code), 'output')
    failed = {'failure_code': code, 'state': state, 'claim_consumed': True,
        'provider_request_count': None, **FALSE_FLAGS}
    try:
        directory.write('failure.json', {**binding(args), **failed})
    except BaseException:
        pass
    return {'failure': failed}


def run(args, deadline):
    """One claim and source hold; only validated FIGIs can reach the owned HTTPS session."""
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'local_only_inputs': True, 'old_controls_spent': True})
        state = {'stage': 'source', 'source_receipt': None, 'selection_summary': None,
            'dispatch_intents': [], 'http_statuses': [], 'response_pins': {}, 'response_bytes': 0,
            'batch_summaries': [], 'corroboration_counts': {}, 'mapping_complete': False,
            'terminal_failure_code': None, 'source_guard_returned': False,
            'package_pin': None, 'private_pin': None}
        buffers = ac = aa = selection = package = None
        try:
            directory.write('source-start.json', {**binding(args), 'stage': 'two-fixed-DATA-leaves'})
            environment.require_safe_environment()
            with data_guard.FixedDataGuard(FILE_PLAN, deadline=deadline) as guard:
                buffers = guard.read_all_once()
                receipt = guard.receipt(); state['source_receipt'] = receipt
                state['stage'] = 'selection'
                environment.require_safe_environment()
                ac, aa = _frames(buffers, deadline)
                selection_summary, selection = _selection(ac, aa, deadline)
                _selection_summary(selection_summary); state['selection_summary'] = selection_summary
                batches, observations = [], []
                if selection_summary['inventory_refusal'] is not None:
                    state['terminal_failure_code'] = selection_summary['inventory_refusal']
                else:
                    state['stage'] = 'mapping'
                    planned = [selection['figis'][index:index + 10] for index in range(0, len(selection['figis']), 10)]
                    require(0 < len(planned) <= MAX_BATCHES
                        and sum(map(len, planned)) == selection_summary['planned_job_count'], 'inventory')
                    requests_raw = [_jobs(batch) for batch in planned]
                    try:
                        with _session() as session:
                            for index, (batch, request_raw) in enumerate(zip(planned, requests_raw, strict=True)):
                                status, raw = _fetch(session, batch, request_raw, index, directory, guard, state, args, deadline)
                                environment.require_safe_environment(); guard.verify()
                                summary, private = figi.analyze_batch(batch, request_raw=request_raw,
                                    response_raw=raw, http_status=status, deadline=deadline)
                                record = private.private_record()
                                figi.validate_private_record(record, expected_summary=summary, deadline=deadline)
                                require(summary['request_pin'] == state['dispatch_intents'][index]['request_pin']
                                    and summary['response_pin'] == state['response_pins'].get(RESPONSE_NAMES[index]), 'mapping_binding')
                                state['batch_summaries'].append(summary); batches.append((summary, record))
                                directory.verify(); guard.verify()
                                if status != 200:
                                    raise Refused('http_status')
                        state['corroboration_counts'], observations = _observations(selection, batches, deadline)
                        state['mapping_complete'] = True
                    except BaseException as error:
                        state['terminal_failure_code'] = finite(error)
                environment.require_safe_environment(); remaining(deadline)
                package = _package(selection_summary, selection, batches, observations, state)
                state['package_pin'] = {'byte_count': len(package), 'sha256': sha(package)}
                require(guard.receipt() == receipt, 'source_changed')
                remaining(deadline)
            state['source_guard_returned'] = True
            state['stage'] = 'publication'
            buffers = ac = aa = selection = None
            environment.require_safe_environment()
            state['private_pin'] = directory.write_bytes(PRIVATE_NAME, package, private=True)
            require(state['private_pin'] == state['package_pin'], 'private_binding')
            package = None
            if state['terminal_failure_code'] is not None:
                return _failed(state['terminal_failure_code'], state, directory, args)
            state['stage'] = 'postflight'
            environment.require_safe_environment()
            preflight(args, deadline); environment.require_safe_environment(); directory.verify()
            result = {'schema': SCHEMA, **state, 'AC_observed_fact_sha256': AC_FACT_SHA256,
                'AC_summary_sha256': AC_SUMMARY_SHA256, 'vendor_source_blockers_remaining': 5,
                'provider_request_count': None, 'post_checks_complete': True,
                'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
            validate_result(result)
            state['stage'] = 'report'
            report = directory.write('report.json', {**binding(args), 'result': result})
            directory.verify()
            return {'result': result, 'report': report}
        except BaseException as error:
            return _failed(finite(error), state, directory, args)
        finally:
            buffers = ac = aa = selection = package = None


def _public_pin(value, maximum):
    return type(value) is dict and set(value) == {'byte_count', 'sha256'} and type(value['byte_count']) is int \
        and 0 < value['byte_count'] <= maximum and type(value['sha256']) is str \
        and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None


def _state(value, *, success=False):
    fields = {'stage', 'source_receipt', 'selection_summary', 'dispatch_intents', 'http_statuses',
        'response_pins', 'response_bytes', 'batch_summaries', 'corroboration_counts', 'mapping_complete',
        'terminal_failure_code', 'source_guard_returned', 'package_pin', 'private_pin'}
    require(type(value) is dict and set(value) == fields
        and value['stage'] in ('source', 'selection', 'mapping', 'publication', 'postflight', 'report')
        and type(value['mapping_complete']) is bool and type(value['source_guard_returned']) is bool
        and (value['terminal_failure_code'] is None or _finite_code(value['terminal_failure_code'])), 'output')
    if value['source_receipt'] is not None:
        data_guard.validate_receipt(value['source_receipt'], FILE_PLAN)
    selection = value['selection_summary']
    if selection is not None:
        _selection_summary(selection); require(value['source_receipt'] is not None, 'output')
    intents, statuses = value['dispatch_intents'], value['http_statuses']
    require(type(intents) is list and len(intents) <= MAX_BATCHES
        and type(statuses) is list and len(statuses) <= len(intents)
        and all(type(status) is int and 100 <= status <= 599 for status in statuses)
        and all(status == 200 for status in statuses[:-1]), 'output')
    for index, intent in enumerate(intents):
        require(type(intent) is dict and set(intent) == {'batch_ordinal', 'dispatch_intent_count', 'request_pin', 'job_count'}
            and type(intent['batch_ordinal']) is int and intent['batch_ordinal'] == index
            and type(intent['dispatch_intent_count']) is int and intent['dispatch_intent_count'] == index + 1
            and type(intent['job_count']) is int and 0 < intent['job_count'] <= 10
            and _public_pin(intent['request_pin'], figi.MAX_REQUEST), 'output')
    if intents:
        require(selection is not None and selection['inventory_refusal'] is None
            and len(intents) <= selection['planned_batch_count']
            and sum(item['job_count'] for item in intents) <= selection['planned_job_count'], 'output')
    pins = value['response_pins']
    require(type(pins) is dict and set(pins) == set(RESPONSE_NAMES[:len(pins)])
        and len(pins) <= len(statuses) and all(statuses[index] == 200 and _public_pin(pins[name], MAX_BODY)
            for index, name in enumerate(RESPONSE_NAMES[:len(pins)]))
        and type(value['response_bytes']) is int
        and sum(pin['byte_count'] for pin in pins.values()) <= value['response_bytes'] <= MAX_AGGREGATE, 'output')
    summaries = value['batch_summaries']
    require(type(summaries) is list and len(summaries) <= len(statuses), 'output')
    for index, summary in enumerate(summaries):
        figi.validate_summary(summary)
        require(summary['request_pin'] == intents[index]['request_pin'] and summary['job_count'] == intents[index]['job_count']
            and summary['http_status'] == statuses[index]
            and summary['response_pin'] == pins.get(RESPONSE_NAMES[index]), 'output')
    require(type(value['corroboration_counts']) is dict and set(value['corroboration_counts']) <= figi.OBSERVATIONS
        and all(type(count) is int and 0 < count <= 150 for count in value['corroboration_counts'].values()), 'output')
    if value['mapping_complete']:
        require(selection is not None and selection['inventory_refusal'] is None
            and len(intents) == len(statuses) == len(summaries) == len(pins) == selection['planned_batch_count']
            and sum(item['job_count'] for item in intents) == selection['planned_job_count']
            and all(status == 200 for status in statuses)
            and value['response_bytes'] == sum(pin['byte_count'] for pin in pins.values())
            and value['terminal_failure_code'] is None and value['corroboration_counts'], 'output')
    if value['package_pin'] is not None:
        require(selection is not None and _public_pin(value['package_pin'], MAX_PRIVATE), 'private_binding')
    if value['source_guard_returned']:
        require(value['package_pin'] is not None and selection is not None, 'output')
    if value['private_pin'] is not None:
        require(value['source_guard_returned'] is True and value['private_pin'] == value['package_pin']
            and _public_pin(value['private_pin'], MAX_PRIVATE), 'private_binding')
    if value['stage'] in ('source', 'selection', 'mapping'):
        require(value['source_guard_returned'] is False and value['private_pin'] is None, 'output')
    if value['stage'] == 'source':
        require(selection is None and not intents and not statuses and not pins and not summaries
            and value['package_pin'] is None and value['mapping_complete'] is False, 'output')
    if value['stage'] in ('publication', 'postflight', 'report'):
        require(value['source_guard_returned'] is True, 'output')
    if value['stage'] in ('postflight', 'report') or success:
        require(value['private_pin'] is not None and value['mapping_complete'] is True
            and value['terminal_failure_code'] is None, 'output')


def validate_result(result):
    state_fields = {'stage', 'source_receipt', 'selection_summary', 'dispatch_intents', 'http_statuses',
        'response_pins', 'response_bytes', 'batch_summaries', 'corroboration_counts', 'mapping_complete',
        'terminal_failure_code', 'source_guard_returned', 'package_pin', 'private_pin'}
    require(type(result) is dict and set(result) == {'schema', *state_fields, 'AC_observed_fact_sha256',
        'AC_summary_sha256', 'vendor_source_blockers_remaining', 'provider_request_count', 'post_checks_complete',
        'diagnostic_only', 'result_cell', *FALSE_FLAGS} and result['schema'] == SCHEMA
        and result['stage'] == 'postflight' and result['AC_observed_fact_sha256'] == AC_FACT_SHA256
        and result['AC_summary_sha256'] == AC_SUMMARY_SHA256
        and type(result['vendor_source_blockers_remaining']) is int and result['vendor_source_blockers_remaining'] == 5
        and result['provider_request_count'] is None and result['post_checks_complete'] is True
        and result['diagnostic_only'] is True and type(result['result_cell']) is int and result['result_cell'] == 0
        and all(result[key] is False for key in FALSE_FLAGS), 'output')
    _state({key: result[key] for key in state_fields}, success=True)


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2)
        and type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    require(type(value) is dict and value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and _finite_code(value['preflight_failure']), 'output')
        return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failed = outcome['failure']
        require(actual_exit == 2 and type(failed) is dict and set(failed) ==
            {'failure_code', 'state', 'claim_consumed', 'provider_request_count', *FALSE_FLAGS}
            and _finite_code(failed['failure_code']) and failed['claim_consumed'] is True
            and failed['provider_request_count'] is None and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        _state(failed['state'])
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        validate_result(outcome['result'])
        report = canonical({**binding(args), 'result': outcome['result']})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value

def observe(args):
    """No-data stage broker: one native producer, then one native validator."""
    outer = {'schema': SCHEMA + '-observer', 'producer': None, 'validator': None,
        'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        runtime = Path(tempfile.mkdtemp(prefix='r326-ad-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        raw, errors, actual = capture(['/usr/bin/sandbox-exec', '-p', native_profile(mode='producer'),
            str(PYTHON), '-B', str(SOURCE), 'run', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256], safe, OUTER_SECONDS, stdout_limit=MAX_OUTPUT)
        outer['producer'] = actual
        require(type(actual['actual_exit']) is int and actual['actual_exit'] in (0, 2)
            and actual['spawn_observed'] is True and actual['bound'] is None and not errors
            and actual['stdout_bytes'] == len(raw) and actual['stdout_sha256'] == sha(raw)
            and actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == sha(b''), 'parent_failed')
        valid, errors, checked = capture(['/usr/bin/sandbox-exec', '-p', native_profile(mode='validator'),
            str(PYTHON), '-B', str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(actual['actual_exit'])],
            safe, VALIDATOR_SECONDS, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = checked
        require(type(checked['actual_exit']) is int and checked['actual_exit'] == 0
            and checked['spawn_observed'] is True and checked['bound'] is None and not errors
            and checked['stdout_bytes'] == len(valid) and checked['stdout_sha256'] == sha(valid)
            and checked['stderr_bytes'] == 0 and checked['stderr_sha256'] == sha(b''), 'validator_failed')
        outer['output'] = parse(valid)
        require(canonical(outer['output']) == raw and valid == raw, 'validator_failed')
        outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OBSERVER_OUTPUT, 'output_bound')
        return outer, actual['actual_exit']
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
        value, code = observe(args)
        sys.stdout.buffer.write(canonical(value))
        return code
    deadline = time.monotonic() + (VALIDATOR_SECONDS if args.operation == 'validate' else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline); environment._bootstrap_cli_logging()
            if args.operation == 'validate':
                value = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args)
                code = 0
            else:
                outcome = run(args, deadline)
                value = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome else 0
            raw = canonical(value)
            require(len(raw) <= MAX_OUTPUT, 'output_bound')
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
