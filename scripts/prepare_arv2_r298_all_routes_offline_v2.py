"""One prospective offline full-catalog compatibility recovery.

Only the two fixed retained metadata CSVs may be reused. No old claim,
report, journal, status response or acquisition function is consumed. All
source rows remain private; current-vintage compatibility is not PIT proof.
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
from scripts import prepare_arv2_r298_all_routes as previous
from scripts import arv2_r298_all_route_worker_v2 as worker

admitted, environment, security = previous.admitted, previous.environment, previous.security
capture_support, canonical, parse, sha, metadata, capture = (
    previous.capture_support, previous.canonical, previous.parse, previous.sha, previous.metadata, previous.capture)
PYTHON = previous.PYTHON
SOURCE = ROOT / 'scripts/prepare_arv2_r298_all_routes_offline_v2.py'
SOURCE_DIRECTORY = ROOT / 'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_all_routes_offline/R326-20261027-AA'
SCHEMA = 'arv2-r298-offline-all-route-preparation-aa-v2'
DEADLINE_SECONDS, OUTER_SECONDS, PREPARE_SECONDS, VALIDATOR_SECONDS = 600, 630, 450, 20
MAX_METADATA = 16 * 1024 * 1024
MAX_OUTPUT, MAX_PRIVATE, MAX_FILES = 128 * 1024, 129 * 1024 * 1024, 12
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
SOURCE_PINS = {
    'stocks-metadata.csv': {'byte_count': 2340169,
        'sha256': '354f578dd11ab0cebe1ff5b6f9ddb596b2d776f4e3161b34b8d4e1723ffe60e6'},
    'funds-metadata.csv': {'byte_count': 904679,
        'sha256': 'a85d60f8699ae4b606ee11b7a70fd48e683fd8de223f14f5b4e2599434bdefac'},
}
SOURCE_NAMES = tuple(SOURCE_PINS)
PRIVATE_NAME = 'routes-private.json'
NEW_PINS = {
    'scripts/prepare_arv2_r298_all_routes.py': '0b46e5048c86e764494106efd22b419c1c800401be207691274db5f8cae476d3',
    'scripts/arv2_r298_sharadar_all_routes_v2.py': '6fe5ec74c4e241fc554183d8ecbdc663c0e63e3f476deb180e37304b7c033ab1',
    'scripts/arv2_r298_all_route_worker_v2.py': 'd236e3f0113046ca638296823d880ac8a93e8d31e65047b57c26fcba5dc35da1',
}
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
    'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
FALSE_FLAGS = {'provider_contact': False, 'credential_access': False, 'qc_contact': False,
    'old_controls_read': False, 'old_operation_invoked': False, 'new_paid_rights': False,
    'price_acquired': False, 'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'licensed_rows_disclosed': False,
    'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin', 'source_scope',
    'source_state', 'source_shape', 'source_open', 'source_changed', 'source_bytes', 'source_security',
    'source_read_spent', 'source_receipt', 'claim_spent', 'control_changed', 'control_name',
    'control_bound', 'control_write', 'capture_changed', 'capture_security', 'worker_input',
    'worker_binding', 'worker_failed', 'private_binding', 'output', 'output_bound',
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
    if type(error) is worker.Refused:
        code = worker.finite(error)
        return 'worker_' + code if code in worker.FINITE else 'refused'
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    return type(value) is str and value in FINITE | {'worker_' + code for code in worker.FINITE}


def pins():
    result = previous.pins()
    require(len(result) == 164, 'source_pin')
    for name, pin in NEW_PINS.items():
        require(name not in result or result[name] == pin, 'source_pin')
        require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64, 'source_pin')
        result[name] = pin
    return result


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'source': str(SOURCE), 'control': str(CONTROL),
        'purpose': 'first_compatibility_correct_full_join_of_fixed_retained_current_metadata_only',
        'source_directory': str(SOURCE_DIRECTORY), 'retained_data': SOURCE_PINS,
        'source_pins': pins(), 'worker_profile': worker.profile_record(),
        'parent_seconds': DEADLINE_SECONDS, 'outer_seconds': OUTER_SECONDS,
        'direct_prepare_seconds': PREPARE_SECONDS, 'validator_seconds': VALIDATOR_SECONDS,
        'maximum_metadata_file_bytes': MAX_METADATA,
        'maximum_private_bytes': MAX_PRIVATE, 'maximum_public_bytes': MAX_OUTPUT,
        'maximum_control_files': MAX_FILES, 'claim_consumes_even_without_source_read': True,
        'partial_claim_is_ambiguous_spent': True,
        'persistent_source_start_before_any_metadata_open': True,
        'persistent_join_start_before_single_direct_prepare': True,
        'both_original_metadata_descriptors_held_through_direct_prepare_and_normal_outer_return': True,
        'private_publication_after_both_normal_guard_returns': True,
        'source_metadata_fields': list(FIELDS), 'ordinary_native_empty_ACL_and_xattrs': True,
        'all_source_reads_fixed_external_byte_pins': True,
        'new_current_use_not_old_security_history': True,
        'no_unused_original_column_name_guessing': True,
        'selected_pins_not_whole_interpreter_integrity': True,
        'actual_exit_and_external_output_validation_required': True,
        'producer_native_network_Keychain_and_security_CLI_denial': True,
        'producer_writes_only_own_AA_control_root_cache_or_null': True,
        'observer_is_no_data_stage_broker': True,
        'one_native_producer_no_nested_sandbox_or_inner_child': True,
        'private_bytes_never_cross_producer_stdout_or_observer': True,
        'native_policy_not_arbitrary_same_user_or_interpreter_integrity': True,
        'only_own_children_killed_and_reaped_by_observer': True,
        'deadline_host_suspension_uninterruptible_IO_qualification': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


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


class SourceGuard:
    """Hold every no-follow path component and both fixed ordinary CSV leaves."""
    def __init__(self, *, deadline):
        remaining(deadline)
        self.deadline, self.objects, self.by_path, self.reads = deadline, [], {}, set()
        self.active, self.spent = False, False

    def _policy(self, path, info, leaf):
        require(len(info) == len(FIELDS) and all(type(value) is int and value >= 0 for value in info),
            'source_shape')
        if path == ROOT or ROOT in path.parents:
            require(info[3] == os.getuid() and not info[9] & ~(stat.UF_TRACKED | stat.UF_HIDDEN), 'source_shape')
            if leaf:
                require(stat.S_ISREG(info[2]) and stat.S_IMODE(info[2]) == 0o600
                    and info[5] == 1 and info[6] == SOURCE_PINS[path.name]['byte_count']
                    and 0 < info[6] <= MAX_METADATA, 'source_shape')
            else:
                require(stat.S_ISDIR(info[2]) and stat.S_IMODE(info[2]) ==
                    (0o755 if path == ROOT else 0o700), 'source_shape')
        else:
            require(not leaf and stat.S_ISDIR(info[2]), 'source_shape')

    def _snapshot(self, row):
        return security_snapshot(row['fd'], source=True) if row['path'] == ROOT or ROOT in row['path'].parents else None

    def _hold(self, path, parent, name, *, leaf=False):
        remaining(self.deadline)
        try:
            named = metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
            self._policy(path, named, leaf)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
                | (os.O_NONBLOCK if leaf else os.O_DIRECTORY), dir_fd=parent)
        except OSError:
            raise Refused('source_open') from None
        row = {'path': path, 'fd': fd, 'parent': parent, 'name': name, 'metadata': named, 'leaf': leaf}
        self.objects.append(row); self.by_path[path] = row
        require(metadata(os.fstat(fd)) == named, 'source_changed')
        row['security'] = self._snapshot(row)
        require(metadata(os.fstat(fd)) == named
            == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'source_changed')

    def __enter__(self):
        require(not self.active and not self.spent, 'source_state')
        self.spent = True
        require(type(ROOT) is type(Path()) and type(SOURCE_DIRECTORY) is type(Path())
            and ROOT.is_absolute() and SOURCE_DIRECTORY == ROOT
                / 'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z'
            and Path.cwd() == ROOT and tuple(SOURCE_PINS) == SOURCE_NAMES, 'source_scope')
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0))
            first = {'path': Path('/'), 'fd': fd, 'parent': fd, 'name': '.',
                'metadata': metadata(os.fstat(fd)), 'leaf': False, 'security': None}
            self.objects.append(first); self.by_path[Path('/')] = first
            path = Path('/')
            for component in SOURCE_DIRECTORY.parts[1:]:
                path = path / component
                self._hold(path, self.objects[-1]['fd'], component)
            parent = self.by_path[SOURCE_DIRECTORY]['fd']
            for name in SOURCE_NAMES:
                self._hold(SOURCE_DIRECTORY / name, parent, name, leaf=True)
            self.active = True
            self.verify()
            return self
        except BaseException:
            self.close()
            raise

    def verify(self):
        require(self.active, 'source_state')
        for row in self.objects:
            remaining(self.deadline)
            require(metadata(os.fstat(row['fd'])) == row['metadata']
                == metadata(os.stat(row['name'], dir_fd=row['parent'], follow_symlinks=False)), 'source_changed')
            self._policy(row['path'], row['metadata'], row['leaf'])
            require(self._snapshot(row) == row['security'], 'source_changed')
            require(metadata(os.fstat(row['fd'])) == row['metadata']
                == metadata(os.stat(row['name'], dir_fd=row['parent'], follow_symlinks=False)), 'source_changed')

    def read_once(self):
        require(self.active and not self.reads, 'source_read_spent')
        self.verify()
        values = {}
        for name in SOURCE_NAMES:
            self.reads.add(name)
            row, pin = self.by_path[SOURCE_DIRECTORY / name], SOURCE_PINS[name]
            remaining(self.deadline)
            raw = Store._read(row['fd'], pin['byte_count'], deadline=self.deadline)
            require(len(raw) == pin['byte_count'] and sha(raw) == pin['sha256'], 'source_bytes')
            values[name] = raw
        self.verify()
        return values

    def receipt(self):
        self.verify()
        require(self.reads == set(SOURCE_NAMES), 'source_state')
        value = {'schema': SCHEMA + '-retained-metadata-current-source',
            'files': {name: {**SOURCE_PINS[name],
                'current_metadata_sha256': sha(canonical(list(self.by_path[SOURCE_DIRECTORY / name]['metadata']))),
                'current_security_sha256': sha(canonical(self.by_path[SOURCE_DIRECTORY / name]['security']))}
                for name in SOURCE_NAMES}, 'fresh_current_security_authenticated': True,
            'fixed_retained_bytes_authenticated': True,
            'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}
        return validate_source_receipt(value)

    def close(self):
        failed = False
        for row in reversed(self.objects):
            try:
                os.close(row['fd'])
            except OSError:
                failed = True
        self.objects.clear(); self.by_path.clear(); self.active = False
        if failed:
            raise Refused('source_changed')

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()


def validate_source_receipt(value):
    require(type(value) is dict and set(value) == {'schema', 'files',
        'fresh_current_security_authenticated', 'fixed_retained_bytes_authenticated',
        'historical_metadata_preservation_proven', 'continuous_security_proven'}
        and value['schema'] == SCHEMA + '-retained-metadata-current-source'
        and value['fresh_current_security_authenticated'] is True
        and value['fixed_retained_bytes_authenticated'] is True
        and value['historical_metadata_preservation_proven'] is False
        and value['continuous_security_proven'] is False and type(value['files']) is dict
        and set(value['files']) == set(SOURCE_NAMES), 'source_receipt')
    for name, row in value['files'].items():
        require(type(row) is dict and set(row) == {'byte_count', 'sha256',
            'current_metadata_sha256', 'current_security_sha256'}
            and type(row['byte_count']) is int and row['byte_count'] == SOURCE_PINS[name]['byte_count']
            and row['sha256'] == SOURCE_PINS[name]['sha256']
            and all(type(row[key]) is str and re.fullmatch('[0-9a-f]{64}', row[key])
                for key in ('sha256', 'current_metadata_sha256', 'current_security_sha256')), 'source_receipt')
    return json.loads(canonical(value))


class Store:
    """Only the new AA leaf and original descriptors; no old control reader."""
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
    from scripts import run_arv2_newrule_comparison as inputs
    from scripts import arv2_r298_reference_ticker_source_guard as original_guard
    return base + _artifact_policy([*(SOURCE_DIRECTORY / name for name in SOURCE_NAMES), CONTROL,
        *(CONTROL / name for name in ('claim.json', 'source-start.json', 'join-start.json',
            PRIVATE_NAME, 'report.json', 'failure.json')), inputs.LINEAGE,
        *(original_guard.CAPTURE / name for name in original_guard.LEAVES),
        ], package=inputs.PACKAGE)


def _summary(value):
    worker.validate_summary(value)
    require(value['current_metadata'] == {table: SOURCE_PINS[name]
        for table, name in zip(('stocks', 'funds'), SOURCE_NAMES, strict=True)}, 'worker_binding')
    return value


def _private(value, summary):
    require(type(value) is dict, 'private_binding')
    raw = worker.canonical(value)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_PRIVATE
        and summary['private_frame_byte_count'] == len(raw)
        and summary['private_frame_sha256'] == sha(raw), 'private_binding')
    return raw


def run(args, deadline):
    """One native producer; both source guards finish before publication."""
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'local_only': True, 'old_controls_spent': True})
        state = {'stage': 'source', 'source_receipt': None, 'summary': None,
            'direct_prepare_returned': False, 'source_guard_returned': False, 'private_pin': None}
        buffers = private = private_raw = None
        try:
            directory.write('source-start.json', {**binding(args), 'stage': 'fixed-retained-metadata'})
            environment.require_safe_environment()
            with SourceGuard(deadline=deadline) as guard:
                buffers = guard.read_once()
                receipt = guard.receipt()
                state['source_receipt'] = receipt
                directory.write('join-start.json', {**binding(args), 'stage': 'native-direct-full-binding-join'})
                state['stage'] = 'join'
                prepare_deadline = time.monotonic() + min(PREPARE_SECONDS, remaining(deadline))
                environment.require_safe_environment()
                summary, private = worker.prepare(*(buffers[name] for name in SOURCE_NAMES),
                    deadline=prepare_deadline)
                environment.require_safe_environment()
                state['direct_prepare_returned'] = True
                _summary(summary)
                private_raw = _private(private, summary)
                state['summary'] = summary
                require(guard.receipt() == receipt, 'source_changed')
                remaining(deadline)
            # This line is reached only after the original guard inside
            # worker.prepare AND this outer retained-metadata guard RETURN.
            state['source_guard_returned'] = True
            buffers = private = None
            environment.require_safe_environment()
            state['stage'] = 'publication'
            state['private_pin'] = directory.write_bytes(PRIVATE_NAME, private_raw, private=True)
            require(state['private_pin'] == {'byte_count': summary['private_frame_byte_count'],
                'sha256': summary['private_frame_sha256']}, 'private_binding')
            private_raw = None
            state['stage'] = 'postflight'
            environment.require_safe_environment()
            preflight(args, deadline); environment.require_safe_environment(); directory.verify()
            result = {'schema': SCHEMA, **state, 'post_checks_complete': True,
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


def _pin(value):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= MAX_PRIVATE
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'private_binding')


def _state(value, *, success=False):
    require(type(value) is dict and set(value) == {'stage', 'source_receipt', 'summary',
        'direct_prepare_returned', 'source_guard_returned', 'private_pin'}
        and value['stage'] in ('source', 'join', 'publication', 'postflight', 'report')
        and type(value['direct_prepare_returned']) is bool
        and type(value['source_guard_returned']) is bool, 'output')
    if value['source_receipt'] is not None:
        validate_source_receipt(value['source_receipt'])
    if value['summary'] is not None:
        _summary(value['summary'])
        require(value['direct_prepare_returned'] is True and value['source_receipt'] is not None, 'output')
    if value['source_guard_returned']:
        require(value['direct_prepare_returned'] is True and value['summary'] is not None, 'output')
    if value['stage'] == 'source':
        require(value['summary'] is None and value['direct_prepare_returned'] is False
            and value['source_guard_returned'] is False and value['private_pin'] is None, 'output')
    if value['stage'] == 'join':
        require(value['source_receipt'] is not None and value['source_guard_returned'] is False
            and value['private_pin'] is None, 'output')
    if value['stage'] in ('publication', 'postflight', 'report'):
        require(value['source_guard_returned'] is True, 'output')
    if value['private_pin'] is not None:
        _pin(value['private_pin'])
        require(value['source_guard_returned'] is True and value['private_pin'] == {
            'byte_count': value['summary']['private_frame_byte_count'],
            'sha256': value['summary']['private_frame_sha256']}, 'private_binding')
    if value['stage'] in ('postflight', 'report') or success:
        require(value['private_pin'] is not None, 'output')


def validate_result(result):
    fields = {'stage', 'source_receipt', 'summary', 'direct_prepare_returned',
        'source_guard_returned', 'private_pin'}
    require(type(result) is dict and set(result) == {'schema', *fields, 'post_checks_complete',
        'diagnostic_only', 'result_cell', *FALSE_FLAGS} and result['schema'] == SCHEMA
        and result['stage'] == 'postflight' and result['post_checks_complete'] is True
        and result['diagnostic_only'] is True and type(result['result_cell']) is int
        and result['result_cell'] == 0 and all(result[key] is False for key in FALSE_FLAGS), 'output')
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
        runtime = Path(tempfile.mkdtemp(prefix='r326-aa-observer-', dir=ROOT / '.pytest_cache'))
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
