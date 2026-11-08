"""One fixed-data preparation of qualified current price-acquisition lineages.

This new purpose consumes four fixed DATA leaves, never prior controls.
It authenticates acquisition identities and preserves unresolved rows; no
price, coverage, permanent identity or strategy readiness is admitted.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import inspect_arv2_r298_route_dispositions as previous
from scripts import arv2_r298_ab_source_binding as anchor
from scripts import arv2_r298_price_lineage_routes as routes
from scripts import arv2_r298_fixed_data_guard as data_guard

admitted, environment, security = previous.admitted, previous.environment, previous.security
capture_support, canonical, parse, sha, metadata, capture = (
    previous.capture_support, previous.canonical, previous.parse, previous.sha, previous.metadata, previous.capture)
PYTHON = previous.PYTHON
SOURCE = ROOT / 'scripts/prepare_arv2_r298_price_lineage.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_price_lineage/R326-20261027-AC'
SCHEMA = 'arv2-r298-current-price-acquisition-lineage-ac-v1'
DEADLINE_SECONDS, OUTER_SECONDS, PREPARE_SECONDS, VALIDATOR_SECONDS = 600, 630, 450, 20
MAX_SOURCE, MAX_PRIVATE, MAX_OUTPUT, MAX_FILES = 32 * 1024 * 1024, 32 * 1024 * 1024, 128 * 1024, 12
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
FILE_PLAN = {
    'aa_frame': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_all_routes_offline/R326-20261027-AA/routes-private.json',
        'byte_count': 19895631, 'sha256': '3776f03b4941d8e6d014dee19f5ee8a05080f214ab7f502d10738f00a689f561'},
    'ab_demand': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_route_dispositions/R326-20261027-AB/membership-demand-private.json',
        'byte_count': 4760647, 'sha256': '1196778dd1d217c707f5ae0ff3dcd72bcba9b23919e9ffab242ac3226a705201'},
    'stocks_metadata': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z/stocks-metadata.csv',
        'byte_count': 2340169, 'sha256': '354f578dd11ab0cebe1ff5b6f9ddb596b2d776f4e3161b34b8d4e1723ffe60e6'},
    'funds_metadata': {'relative_path': 'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z/funds-metadata.csv',
        'byte_count': 904679, 'sha256': 'a85d60f8699ae4b606ee11b7a70fd48e683fd8de223f14f5b4e2599434bdefac'},
}
PRIVATE_NAME = 'price-lineage-private.json'
AB_HEAD = '845fdce655907c44db6c362e41f5a932b4720d76'
AB_CALLER_SHA256 = '7d6d152d7cf8ca302658f40ce0909fd947ee2b525db02d719bbb4844c31a94e6'
AB_PROFILE_SHA256 = '3849711d7f4330e9a095edaf308c0f41dd9236c2dfed431c0761e18738df6cc2'
NEW_PINS = {
    'scripts/inspect_arv2_r298_route_dispositions.py': AB_CALLER_SHA256,
    'scripts/arv2_r298_ab_source_binding.py': '817ea451899e61da3f3ee911cd5f8a11bb3dc6463dc1dfacebb5f71bd7ede1dd',
    'scripts/arv2_r298_price_lineage_routes.py': '5a7a289a9f09cc30dc2155a00d23726cb8238d75993cb6d7c40049862e977d5a',
    'scripts/arv2_r298_fixed_data_guard.py': '00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145',
}
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
    'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FALSE_FLAGS = {'provider_contact': False, 'credential_access': False, 'qc_contact': False,
    'old_controls_read': False, 'original_TICKERS_reread': False,
    'refused_bindings_dropped': False, 'old_operation_invoked': False, 'new_paid_rights': False,
    'price_acquired': False, 'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'licensed_rows_disclosed': False,
    'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin', 'source_scope',
    'source_state', 'source_shape', 'source_open', 'source_changed', 'source_bytes', 'source_security',
    'source_read_spent', 'source_receipt', 'claim_spent', 'control_changed', 'control_name',
    'control_bound', 'control_write', 'capture_changed', 'capture_security', 'source_binding',
    'helper_binding', 'private_binding', 'output', 'output_bound',
    'parent_failed', 'validator_failed', 'execution_environment_refused', 'os_error',
    'refused', 'unknown_exception'))


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
    for module, prefix in ((routes, 'routes_'), (data_guard, 'guard_')):
        if type(error) is module.Refused:
            code = module.finite(error)
            return prefix + code if code in module.FINITE else 'refused'
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    return type(value) is str and value in FINITE | {
        prefix + code for module, prefix in ((routes, 'routes_'), (data_guard, 'guard_')) for code in module.FINITE}


def pins():
    result = previous.pins()
    require(len(result) == 171, 'source_pin')
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
    """Only the new AC leaf and original descriptors; no old control reader."""
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
            and ((private is True and name == PRIVATE_NAME)
                or (private is False and re.fullmatch(r'[a-z0-9-]{1,100}\.json', name))), 'control_name')
        require(type(raw) is bytes and 0 < len(raw) <= (MAX_PRIVATE if private else MAX_OUTPUT), 'control_bound')
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


AB_FACT_SHA256 = '7a8380f17b2ba65682061ebaf599a966cbb22326a1f5fda4c5949b8cec71dfb3'
AB_EVIDENCE_SHA256 = 'ca0d661b11597bbc9a41383eb3fc0f5cf501d888866a0f8efe8776d55c04c1c0'
AB_DEMAND_SHA256 = '71043f8d0d0a71e307507e1479675d55ce1bbf25199e650ad8279099854171f0'


def _file_pin(role):
    require(type(role) is str and role in FILE_PLAN, 'source_binding')
    row = FILE_PLAN[role]
    return {'byte_count': row['byte_count'], 'sha256': row['sha256']}


def capture_pins():
    return {'stocks': _file_pin('stocks_metadata'), 'funds': _file_pin('funds_metadata')}


def source_binding():
    """Only immutable public prior observations; no old DATA or control read."""
    fact = anchor.observed_fact()
    evidence_summary, demand_summary = anchor.expected_evidence_summary(), anchor.expected_demand_summary()
    require(sha(routes.canonical(fact)) == AB_FACT_SHA256
        and sha(routes.canonical(evidence_summary)) == AB_EVIDENCE_SHA256
        and sha(routes.canonical(demand_summary)) == AB_DEMAND_SHA256, 'source_binding')
    require(fact['expected_head'] == AB_HEAD and fact['caller_sha256'] == AB_CALLER_SHA256
        and fact['profile_sha256'] == AB_PROFILE_SHA256
        and fact['private_files']['membership-demand-private.json'] == {
            'relative_path': FILE_PLAN['ab_demand']['relative_path'], **_file_pin('ab_demand')}, 'source_binding')
    for name in ('producer', 'validator'):
        actual = fact[name]
        require(type(actual['actual_exit']) is int and actual['actual_exit'] == 0
            and actual['spawn_observed'] is True and actual['bound'] is None
            and actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == sha(b''), 'source_binding')
    require(fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes']
        and fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256'], 'source_binding')
    previous._summaries(evidence_summary, demand_summary)
    aa = previous.aa_summary()
    require(aa['private_frame_byte_count'] == _file_pin('aa_frame')['byte_count']
        and aa['private_frame_sha256'] == _file_pin('aa_frame')['sha256']
        and aa['current_metadata'] == capture_pins()
        and demand_summary['private_frame_byte_count'] == _file_pin('ab_demand')['byte_count']
        and demand_summary['private_frame_sha256'] == _file_pin('ab_demand')['sha256'], 'source_binding')
    return {'aa_routing_summary': aa['routing_summary'], 'demand_summary': demand_summary}


def profile_record():
    source_binding()
    require(set(FILE_PLAN) == {'aa_frame', 'ab_demand', 'stocks_metadata', 'funds_metadata'}
        and sum(row['byte_count'] for row in FILE_PLAN.values()) <= MAX_SOURCE, 'source_binding')
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'source': str(SOURCE), 'control': str(CONTROL),
        'purpose': 'first_primary_field_corrected_current_price_acquisition_lineage_preparation',
        'fixed_data_plan': data_guard.checked_plan(FILE_PLAN), 'source_pins': pins(),
        'technical_guard_profile': data_guard.profile_record(FILE_PLAN),
        'price_lineage_profile': routes.profile_record(), 'AB_public_binding': anchor.profile_record(),
        'AB_observed_fact_sha256': AB_FACT_SHA256, 'AB_evidence_summary_sha256': AB_EVIDENCE_SHA256,
        'AB_demand_summary_sha256': AB_DEMAND_SHA256,
        'producer_seconds': DEADLINE_SECONDS, 'outer_seconds': OUTER_SECONDS,
        'direct_prepare_seconds': PREPARE_SECONDS, 'validator_seconds': VALIDATOR_SECONDS,
        'maximum_total_source_bytes': MAX_SOURCE, 'maximum_private_bytes': MAX_PRIVATE,
        'maximum_public_bytes': MAX_OUTPUT, 'maximum_control_files': MAX_FILES,
        'claim_consumes_even_without_source_read': True, 'partial_claim_is_ambiguous_spent': True,
        'persistent_source_start_before_any_data_open': True,
        'persistent_analysis_start_before_single_direct_price_lineage_preparation': True,
        'all_four_original_descriptors_held_until_normal_guard_return': True,
        'private_publication_only_after_normal_guard_return': True,
        'ordinary_native_ACL_xattrs_and_full_ten_field_endpoints': True,
        'original_SF1_reporting_currency_not_price_quote_currency': True,
        'current_EOD_USD_price_currency_mandatory': True,
        'current_display_differences_observed_only_under_stable_perma_FIGI_all_CUSIP_and_collision_proof': True,
        'current_metadata_date_bounds_are_observations_never_history_clipping': True,
        'identity_disagreement_or_global_collision_remains_a_stop': True,
        'all_original_bindings_retained_without_strategy_identity_rewriting': True,
        'prior_actual_zero_is_external_fact_not_new_authority_or_security_authentication': True,
        'no_original_TICKERS_package_lineage_or_old_controls_read': True,
        'one_native_producer_no_nested_sandbox_or_inner_child': True,
        'private_bytes_never_cross_producer_stdout_or_observer': True,
        'producer_native_network_Keychain_security_CLI_denial': True,
        'producer_writes_only_new_AC_control_root_cache_or_null': True,
        'selected_pins_not_whole_interpreter_integrity': True,
        'actual_exit_and_external_output_validation_required': True,
        'deadline_host_suspension_uninterruptible_IO_qualification': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record()))}


def native_profile(*, mode):
    require(mode in ('producer', 'validator'), 'arguments')
    base = '(version 1)(allow default)(deny network*)'
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
        *(CONTROL / name for name in ('claim.json', 'source-start.json', 'analysis-start.json',
            PRIVATE_NAME, 'report.json', 'failure.json'))])


def _summary(value):
    routes.validate_summary(value)
    expected = source_binding()
    require(value['source_pins'] == {'aa_frame': _file_pin('aa_frame'), 'demand_frame': _file_pin('ab_demand'),
        **capture_pins()} and value['aa_routing_summary_sha256'] == sha(routes.canonical(expected['aa_routing_summary']))
        and value['demand_summary_sha256'] == AB_DEMAND_SHA256
        and value['binding_contract'] == expected['aa_routing_summary']['binding_contract'], 'helper_binding')
    return value


def _private(value, summary):
    require(type(value) is routes.PrivatePriceRoutes, 'private_binding')
    record = value.private_record()
    routes.validate_private_record(record, expected_summary=summary)
    raw = routes.canonical(record)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PRIVATE
        and summary['private_frame_byte_count'] == len(raw)
        and summary['private_frame_sha256'] == sha(raw), 'private_binding')
    return raw


def run(args, deadline):
    """Four fixed DATA leaves in one native process; never a price API call."""
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'local_only': True, 'old_controls_spent': True})
        state = {'stage': 'source', 'source_receipt': None, 'price_route_summary': None,
            'analysis_returned': False, 'source_guard_returned': False, 'private_pin': None}
        buffers = private = private_raw = None
        try:
            directory.write('source-start.json', {**binding(args), 'stage': 'four-fixed-data-leaves'})
            environment.require_safe_environment()
            with data_guard.FixedDataGuard(FILE_PLAN, deadline=deadline) as guard:
                buffers = guard.read_all_once()
                receipt = guard.receipt()
                state['source_receipt'] = receipt
                directory.write('analysis-start.json', {**binding(args), 'stage': 'qualified-current-price-lineages'})
                state['stage'] = 'analysis'
                prepare_deadline = time.monotonic() + min(PREPARE_SECONDS, remaining(deadline))
                expected = source_binding()
                environment.require_safe_environment()
                summary, private = routes.prepare(buffers['aa_frame'], buffers['ab_demand'],
                    buffers['stocks_metadata'], buffers['funds_metadata'],
                    aa_routing_summary=expected['aa_routing_summary'], demand_summary=expected['demand_summary'],
                    capture_pins=capture_pins(), deadline=prepare_deadline)
                environment.require_safe_environment()
                _summary(summary)
                private_raw = _private(private, summary)
                remaining(prepare_deadline)
                state['price_route_summary'] = summary
                state['analysis_returned'] = True
                require(guard.receipt() == receipt, 'source_changed')
                remaining(deadline)
            state['source_guard_returned'] = True
            state['stage'] = 'publication'
            buffers = private = None
            environment.require_safe_environment()
            state['private_pin'] = directory.write_bytes(PRIVATE_NAME, private_raw, private=True)
            require(state['private_pin'] == {'byte_count': summary['private_frame_byte_count'],
                'sha256': summary['private_frame_sha256']}, 'private_binding')
            private_raw = None
            state['stage'] = 'postflight'
            environment.require_safe_environment()
            preflight(args, deadline); environment.require_safe_environment(); directory.verify()
            result = {'schema': SCHEMA, **state, 'post_checks_complete': True,
                'AB_observed_fact_sha256': AB_FACT_SHA256, 'AB_demand_summary_sha256': AB_DEMAND_SHA256,
                'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
            validate_result(result)
            state['stage'] = 'report'
            report = directory.write('report.json', {**binding(args), 'result': result})
            directory.verify()
            return {'result': result, 'report': report}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state, 'claim_consumed': True, **FALSE_FLAGS}
            try:
                directory.write('failure.json', {**binding(args), **failed})
            except BaseException:
                pass
            return {'failure': failed}
        finally:
            buffers = private = private_raw = None


def _source_receipt(value):
    return data_guard.validate_receipt(value, FILE_PLAN)


def _state(value, *, success=False):
    require(type(value) is dict and set(value) == {'stage', 'source_receipt', 'price_route_summary',
        'analysis_returned', 'source_guard_returned', 'private_pin'}
        and value['stage'] in ('source', 'analysis', 'publication', 'postflight', 'report')
        and type(value['analysis_returned']) is bool and type(value['source_guard_returned']) is bool, 'output')
    if value['source_receipt'] is not None:
        _source_receipt(value['source_receipt'])
    if value['price_route_summary'] is not None:
        _summary(value['price_route_summary'])
        require(value['source_receipt'] is not None, 'output')
    if value['analysis_returned']:
        require(value['price_route_summary'] is not None, 'output')
    if value['source_guard_returned']:
        require(value['analysis_returned'] is True, 'output')
    if value['stage'] == 'source':
        require(value['price_route_summary'] is None and value['analysis_returned'] is False
            and value['source_guard_returned'] is False and value['private_pin'] is None, 'output')
    if value['stage'] == 'analysis':
        require(value['source_receipt'] is not None and value['source_guard_returned'] is False
            and value['private_pin'] is None, 'output')
    if value['stage'] in ('publication', 'postflight', 'report'):
        require(value['source_guard_returned'] is True, 'output')
    if value['private_pin'] is not None:
        require(type(value['private_pin']) is dict and set(value['private_pin']) == {'byte_count', 'sha256'}
            and type(value['private_pin']['byte_count']) is int and 0 < value['private_pin']['byte_count'] <= MAX_PRIVATE
            and value['source_guard_returned'] is True and value['private_pin'] == {
                'byte_count': value['price_route_summary']['private_frame_byte_count'],
                'sha256': value['price_route_summary']['private_frame_sha256']}, 'private_binding')
    if value['stage'] in ('postflight', 'report') or success:
        require(value['private_pin'] is not None, 'output')


def validate_result(result):
    fields = {'stage', 'source_receipt', 'price_route_summary', 'analysis_returned', 'source_guard_returned', 'private_pin'}
    require(type(result) is dict and set(result) == {'schema', *fields, 'post_checks_complete',
        'AB_observed_fact_sha256', 'AB_demand_summary_sha256', 'diagnostic_only', 'result_cell', *FALSE_FLAGS}
        and result['schema'] == SCHEMA and result['stage'] == 'postflight' and result['post_checks_complete'] is True
        and result['AB_observed_fact_sha256'] == AB_FACT_SHA256
        and result['AB_demand_summary_sha256'] == AB_DEMAND_SHA256
        and result['diagnostic_only'] is True and type(result['result_cell']) is int and result['result_cell'] == 0
        and all(result[key] is False for key in FALSE_FLAGS), 'output')
    _state({name: result[name] for name in fields}, success=True)


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
        require(actual_exit == 2 and type(failed) is dict and set(failed) == {
            'failure_code', 'state', 'claim_consumed', *FALSE_FLAGS}
            and _finite_code(failed['failure_code']) and failed['claim_consumed'] is True
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
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
        runtime = Path(tempfile.mkdtemp(prefix='r326-ac-observer-', dir=ROOT / '.pytest_cache'))
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
