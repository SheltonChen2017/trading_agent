"""One fresh, offline syntax consumer of exactly two pinned T data files.

No historical T control is read. The native producer authenticates current
held/named metadata and security plus the frozen T byte hashes, not historical
continuous preservation. CUSIPs remain private; output is a closed summary.
"""
from __future__ import annotations

import argparse
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
from scripts import run_arv2_r298_sharadar_probe_metadata as previous
from scripts import arv2_r298_sharadar_cusip_syntax as syntax

admitted, environment, capture_support = previous.admitted, previous.environment, previous.capture_support
canonical, parse, sha, capture = previous.canonical, previous.parse, previous.sha, previous.capture
security_snapshot, metadata = previous.security_snapshot, previous.metadata
SOURCE = ROOT / 'scripts/inspect_arv2_r298_sharadar_cusip_syntax.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_sharadar_cusip_syntax/R323-20261025-U'
SOURCE_DIRECTORY = ROOT / 'artifacts/analyst_revisions_v2/newrule_sharadar_probe_metadata/R323-20261025-T'
SOURCE_PINS = {
    'stocks-probe.csv': {'byte_count': 225, 'sha256': '0f0578e8f3067bfc40b3e32bcec8ad05d42087b3a4f1428a4d993cc9db7eb9bf'},
    'funds-probe.csv': {'byte_count': 899, 'sha256': '5e37400fd38313f4980f4947ef1e9aeafc52e4cf3566b64ee686bc91c9b9fdaa'},
}
SCHEMA = 'arv2-r298-sharadar-cusip-syntax-u-v1'
PYTHON = previous.PYTHON
DEADLINE_SECONDS, MAX_OUTPUT, MAX_FILES = 90, 128 * 1024, 8
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
NEW_PINS = {
    'scripts/run_arv2_r298_sharadar_probe_metadata.py': '4120779c745e4b6c38f4702d665a8e113018ddccad603efec68adeb5b4b62439',
    'scripts/arv2_r298_sharadar_cusip_syntax.py': 'cab79cb04bbc0788b37138b74526fdd518b7d0e90ee7ceeca546227f91a7b72b',
}
FALSE_FLAGS = {'provider_contact': False, 'qc_contact': False, 'keychain_access': False,
    'credentials_read': False, 'historical_control_state_read': False, 'new_paid_rights': False,
    'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'licensed_rows_disclosed': False, 'historical_metadata_preservation_proven': False,
    'continuous_security_proven': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin',
    'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'capture_changed', 'capture_security', 'source_shape', 'source_changed', 'source_bytes',
    'source_stage', 'output', 'output_bound', 'parent_failed', 'validator_failed',
    'refused', 'unknown_exception', 'os_error'))


class Refused(ValueError):
    """Closed finite caller predicate, never a raw exception rendering."""


def require(value, code):
    if not value:
        raise Refused(code)


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= DEADLINE_SECONDS, 'deadline')
    return value


def finite(error):
    if type(error) is syntax.Refused:
        code = syntax.finite(error)
        return 'syntax_' + code if type(code) is str and code in syntax.FINITE | {'unknown'} else 'refused'
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    if type(error) is previous.Refused:
        code = previous.finite(error)
        return code if code in FINITE else 'refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    return type(value) is str and value in FINITE | {'execution_environment_refused'} \
        | {'syntax_' + code for code in syntax.FINITE | {'unknown'}}


def pins():
    values = dict(previous.pins())
    for name, pin in NEW_PINS.items():
        require(name not in values or values[name] == pin, 'source_pin')
        values[name] = pin
    return values


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'fresh_offline_cusip_syntax_observation_not_identity_or_price_admission',
        'deadline_seconds': 90, 'outer_seconds': 120, 'validator_seconds': 20,
        'source_directory': str(SOURCE_DIRECTORY), 'source_data_pins': SOURCE_PINS,
        'source_stage_uses': 1, 'logical_bounded_source_passes_per_leaf': 1,
        'claim_fsync_before_source_data_read': True,
        'source_fds_held_through_analysis_publication_return': True,
        'security_policy': 'empty_extended_ACL;only_opaque_stable_com.apple.provenance_xattr',
        'full_metadata_fields': ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
            'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'],
        'metadata_policy': 'fresh_current_full_metadata_and_security_plus_frozen_T_bytes',
        'native_artifact_read_data': 'two_literal_T_leaves_and_own_U_control_only',
        'native_artifact_write': 'own_U_control_and_exact_parent_directory_creation_only',
        'ancestor_metadata_traversal_allowed': True,
        'source_directory_descriptor_mode': 'Darwin_O_SEARCH_no_read_data_or_listing',
        'other_artifact_data_or_directory_listing_allowed': False,
        'syntax_profile_sha256': sha(canonical(syntax.profile_record())),
        'max_output': MAX_OUTPUT, 'max_control_files': MAX_FILES,
        'actual_exit_and_supplied_output_validator_required': True,
        'selected_pins_are_whole_interpreter_integrity': False,
        'uninterruptible_io_or_host_suspension_bounded': False,
        'automatic_retry': False, 'cleanup_or_marker_repair': False,
        'result_cell': 0, 'qc_jobs': 0, 'new_strategy_looks': 0, **FALSE_FLAGS}


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
        require(pin != '0' * 64 and sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    committed = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':'
        + SOURCE.relative_to(ROOT).as_posix()], deadline, MAX_OUTPUT)
    require(sha(committed) == args.caller_sha256, 'source_pin')
    remaining(deadline)


def _walk(path, *, final_data=False):
    # Darwin O_SEARCH obtains a metadata/openat descriptor without asking
    # the native policy for directory read-data/listing permission.
    flags = os.O_SEARCH | os.O_NOFOLLOW
    fd, chain = os.open('/', flags), []
    try:
        for index, part in enumerate(path.parts[1:], 1):
            selected = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW \
                if final_data and index == len(path.parts) - 1 else flags
            nxt = os.open(part, selected, dir_fd=fd)
            os.close(fd)
            fd = nxt
            chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
        return fd, tuple(chain)
    except BaseException:
        os.close(fd)
        raise


def _source_walk():
    return _walk(SOURCE_DIRECTORY)


class SourceGuard:
    """Two current source leaves, never T state or a directory-data census."""
    def __init__(self):
        self.fd, self.held, self.used = None, {}, False

    def __enter__(self):
        try:
            self.fd, self.chain = _source_walk()
            self.directory_metadata = metadata(os.fstat(self.fd))
            self.directory_security = security_snapshot(self.fd)
            require(stat.S_ISDIR(os.fstat(self.fd).st_mode)
                and os.fstat(self.fd).st_uid == os.getuid()
                and stat.S_IMODE(os.fstat(self.fd).st_mode) == 0o700, 'source_shape')
            for name, pin in SOURCE_PINS.items():
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
                try:
                    info = os.fstat(fd)
                    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                        and info.st_uid == os.getuid() and info.st_nlink == 1
                        and info.st_size == pin['byte_count'], 'source_shape')
                    snapshot = security_snapshot(fd)
                    self.held[name] = (fd, metadata(info), snapshot)
                except BaseException:
                    os.close(fd)
                    raise
            self.verify()
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        for fd, _, _ in self.held.values():
            os.close(fd)
        self.held.clear()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()

    def verify(self):
        fd, chain = _source_walk()
        try:
            require(chain == self.chain and self.directory_metadata
                == metadata(os.fstat(self.fd)) == metadata(os.fstat(fd))
                and security_snapshot(self.fd) == self.directory_security, 'source_changed')
            for name, (held, baseline, snapshot) in self.held.items():
                require(baseline == metadata(os.fstat(held))
                    == metadata(os.stat(name, dir_fd=fd, follow_symlinks=False))
                    and security_snapshot(held) == snapshot, 'source_changed')
        finally:
            os.close(fd)

    def read_once(self, deadline):
        require(self.used is False, 'source_stage')
        self.used = True
        self.verify()
        values = {}
        for name, (fd, _, _) in self.held.items():
            remaining(deadline)
            raw = Store._read(fd, SOURCE_PINS[name]['byte_count'])
            require(len(raw) == SOURCE_PINS[name]['byte_count']
                and sha(raw) == SOURCE_PINS[name]['sha256'], 'source_bytes')
            values[name] = raw
        self.verify()
        return values

    def receipt(self):
        self.verify()
        return {'files': {name: {**SOURCE_PINS[name],
            'current_metadata_sha256': sha(canonical(list(meta))),
            'current_security_sha256': sha(canonical(snapshot))}
            for name, (_, meta, snapshot) in self.held.items()},
            'fresh_current_security_authenticated': True, 'frozen_T_bytes_authenticated': True,
            'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}


class Store:
    """Own U control descriptors; no private source is copied or persisted."""
    def __init__(self):
        self.fd, self.chain, self.files, self.held = None, [], {}, {}
        fd = os.open('/', os.O_SEARCH | os.O_NOFOLLOW)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        require(here != CONTROL, 'claim_spent')
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW \
                    if here == CONTROL else os.O_SEARCH | os.O_NOFOLLOW
                nxt = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = nxt
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
        other, chain = _walk(CONTROL, final_data=True)
        try:
            require(chain == tuple(self.chain)
                and metadata(os.fstat(self.fd)) == metadata(os.fstat(other))
                and os.fstat(other).st_uid == os.getuid()
                and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files)
                and len(self.files) <= MAX_FILES
                and security_snapshot(self.fd) == self.directory_security, 'control_changed')
            for name, baseline in self.files.items():
                fd, snapshot = self.held[name]
                require(baseline == metadata(os.fstat(fd))
                    == metadata(os.stat(name, dir_fd=other, follow_symlinks=False))
                    and security_snapshot(fd) == snapshot, 'capture_changed')
        finally:
            os.close(other)

    def write(self, name, value):
        return self.write_bytes(name, canonical(value))

    def write_bytes(self, name, raw):
        self.verify()
        require(type(name) is str and name not in self.files and len(self.files) < MAX_FILES
            and re.fullmatch(r'[a-z0-9-]{1,100}\.json', name), 'control_name')
        limit = MAX_OUTPUT
        require(type(raw) is bytes and 0 < len(raw) <= limit, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        kept = False
        try:
            empty = os.fstat(fd)
            require(stat.S_ISREG(empty.st_mode) and stat.S_IMODE(empty.st_mode) == 0o600
                and empty.st_uid == os.getuid() and empty.st_nlink == 1 and empty.st_size == 0, 'control_write')
            before_security = security_snapshot(fd)
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'control_write')
                view = view[count:]
            os.fsync(fd)
            os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            require(self._read(fd, len(raw)) == raw
                and metadata(info) == metadata(os.fstat(fd))
                and security_snapshot(fd) == before_security, 'capture_changed')
            self.files[name] = metadata(info)
            self.held[name] = (fd, before_security)
            kept = True
        finally:
            if not kept:
                os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}

    @staticmethod
    def _read(fd, size):
        os.lseek(fd, 0, os.SEEK_SET)
        result = bytearray()
        while len(result) <= size:
            chunk = os.read(fd, min(65536, size + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
        return bytes(result)


def native_validator_profile():
    return previous.native_profile()


def native_producer_profile():
    # Metadata traversal remains available. Artifact file contents/directory
    # listings are denied except the two exact leaves and this own control.
    artifacts = str(ROOT / 'artifacts')
    support = str(ROOT / '.pytest_cache')
    leaves = ''.join(' (require-not (literal "' + str(SOURCE_DIRECTORY / name) + '"))'
        for name in SOURCE_PINS)
    return ('(version 1)(allow default)(deny network*)'
        '(deny file-read* file-write* (subpath "/Users/sheltonchen/Library/Keychains"))'
        '(deny file-read* file-write* (subpath "/Library/Keychains"))'
        '(deny process-exec (literal "/usr/bin/security"))'
        '(deny file-read-data (require-all (subpath "' + artifacts + '")'
        ' (require-not (subpath "' + str(CONTROL) + '"))' + leaves + '))'
        '(deny file-write* (require-all'
        ' (require-not (subpath "' + str(CONTROL) + '"))'
        ' (require-not (subpath "' + support + '"))'
        ' (require-not (literal "' + str(CONTROL.parent) + '"))'
        ' (require-not (literal "/dev/null"))))'
        '(deny file-write-data file-write-unlink file-write-xattr file-write-mode'
        ' file-write-owner file-write-flags file-write-times'
        ' (literal "' + str(CONTROL.parent) + '"))')


def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'offline_only': True, 'old_controls_spent': True})
        state = {'stage': 'source', 'source': None, 'receipt': None}
        try:
            environment.require_safe_environment()
            directory.write('source-start.json', {**binding(args), 'source_stage': 1})
            with SourceGuard() as sources:
                buffers = sources.read_once(deadline)
                source_receipt = sources.receipt()
                state['source'] = source_receipt
                state['stage'] = 'analysis'
                receipt = syntax.inspect_captures(buffers)
                syntax.validate_receipt(receipt)
                sources.verify()
                state['receipt'] = receipt
                state['stage'] = 'postflight'
                preflight(args, deadline)
                environment.require_safe_environment()
                sources.verify()
                directory.verify()
                result = {'schema': SCHEMA, 'receipt': receipt, 'source': source_receipt,
                    'post_checks_complete': True, 'result_cell': 0, **FALSE_FLAGS}
                validate_result(result)
                state['stage'] = 'report'
                pin = directory.write('report.json', {**binding(args), 'result': result})
                sources.verify()
                directory.verify()
                result_packet = {'result': result, 'report': pin}
            # SourceGuard normal exit verifies once more before release.
            return result_packet
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state, 'claim_consumed': True, **FALSE_FLAGS}
            try:
                directory.write('failure.json', {**binding(args), **failed})
            except BaseException:
                pass
            return {'failure': failed}


def validate_source(value):
    require(type(value) is dict and set(value) == {'files', 'fresh_current_security_authenticated',
        'frozen_T_bytes_authenticated', 'historical_metadata_preservation_proven',
        'continuous_security_proven'} and value['fresh_current_security_authenticated'] is True
        and value['frozen_T_bytes_authenticated'] is True
        and value['historical_metadata_preservation_proven'] is False
        and value['continuous_security_proven'] is False, 'output')
    require(type(value['files']) is dict and set(value['files']) == set(SOURCE_PINS), 'output')
    for name, fields in value['files'].items():
        require(type(fields) is dict and set(fields) == {'byte_count', 'sha256',
            'current_metadata_sha256', 'current_security_sha256'}
            and {'byte_count': fields['byte_count'], 'sha256': fields['sha256']} == SOURCE_PINS[name]
            and type(fields['byte_count']) is int
            and all(type(fields[key]) is str and re.fullmatch('[0-9a-f]{64}', fields[key])
                for key in ('sha256', 'current_metadata_sha256', 'current_security_sha256')), 'output')
    return value


def validate_result(value):
    require(type(value) is dict and set(value) == {'schema', 'receipt', 'source',
        'post_checks_complete', 'result_cell', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['post_checks_complete'] is True
        and type(value['result_cell']) is int and value['result_cell'] == 0
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    validate_source(value['source'])
    syntax.validate_receipt(value['receipt'])


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
        require(actual_exit == 2 and type(failed) is dict
            and set(failed) == {'failure_code', 'state', 'claim_consumed', *FALSE_FLAGS}
            and _finite_code(failed['failure_code']) and failed['claim_consumed'] is True
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        state = failed['state']
        require(type(state) is dict and set(state) == {'stage', 'source', 'receipt'}
            and state['stage'] in ('source', 'analysis', 'postflight', 'report'), 'output')
        if state['source'] is not None:
            validate_source(state['source'])
        if state['receipt'] is not None:
            require(state['source'] is not None, 'output')
            syntax.validate_receipt(state['receipt'])
        if state['stage'] == 'source':
            require(state['source'] is None and state['receipt'] is None, 'output')
        if state['stage'] == 'analysis':
            require(state['source'] is not None and state['receipt'] is None, 'output')
        if state['stage'] in ('postflight', 'report'):
            require(state['source'] is not None and state['receipt'] is not None, 'output')
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        validate_result(outcome['result'])
        report = canonical({**binding(args), 'result': outcome['result']})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def observe(args):
    outer = {'schema': SCHEMA + '-observer', 'parent': None, 'validator': None,
        'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        runtime = Path(tempfile.mkdtemp(prefix='r323-u-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        raw, errors, actual = capture(['/usr/bin/sandbox-exec', '-p', native_producer_profile(),
            str(PYTHON), '-B', str(SOURCE), 'run', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256], safe, 120, stdout_limit=MAX_OUTPUT)
        outer['parent'] = actual
        require(type(actual['actual_exit']) is int and actual['actual_exit'] in (0, 2)
            and actual['bound'] is None and not errors, 'parent_failed')
        validated, errors, checked = capture(['/usr/bin/sandbox-exec', '-p', native_validator_profile(),
            str(PYTHON), '-B', str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(actual['actual_exit'])],
            safe, 20, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = checked
        require(type(checked['actual_exit']) is int and checked['actual_exit'] == 0
            and checked['bound'] is None and not errors, 'validator_failed')
        outer['output'] = parse(validated)
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
        result, code = observe(args)
        sys.stdout.buffer.write(canonical(result))
        return code
    deadline = time.monotonic() + (20 if args.operation == 'validate' else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline)
            environment._bootstrap_cli_logging()
            if args.operation == 'validate':
                result = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args)
                code = 0
            else:
                outcome = run(args, deadline)
                result = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome else 0
            raw = canonical(result)
            require(len(raw) <= MAX_OUTPUT, 'output_bound')
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
