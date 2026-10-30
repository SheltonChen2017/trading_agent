"""One prospective local-only V eligibility observation with complete CUSIP parsing.

This is not a price/NAV admission, QC transfer, strategy run or rights grant.
The exclusive claim precedes the one fixed Keychain lookup and every request.
Only bounded private response files and closed redacted evidence are retained;
all historical controls and operational entry points remain unused.
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
from scripts import run_arv2_r298_sharadar_reference as previous
from scripts import arv2_keychain_connections as keychain
from scripts import arv2_relocation_security as security
from scripts import arv2_r298_sharadar_eligibility_v2_observation as observation

admitted, environment, capture_support = previous.admitted, previous.environment, previous.capture_support
canonical, parse, sha, capture = previous.canonical, previous.parse, previous.sha, previous.capture
SOURCE = ROOT / 'scripts/run_arv2_r298_sharadar_eligibility_v2.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_sharadar_eligibility/R323-20261025-V'
SCHEMA = 'arv2-r298-sharadar-eligibility-v-v2'
PYTHON = previous.PYTHON
DEADLINE_SECONDS, MAX_OUTPUT, MAX_FILES = 600, 128 * 1024, 24
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
ROLES = ('stocks_metadata', 'funds_metadata', 'stocks_status', 'funds_status', 'stock_early', 'funds_early')
CAPTURE_NAMES = ('stocks-metadata.csv', 'funds-metadata.csv', 'stocks-status.json',
    'funds-status.json', 'stocks-prior.csv', 'funds-prior.csv')
CAPTURE_BOUNDS = (16 * 1024 * 1024, 16 * 1024 * 1024, 8 * 1024, 8 * 1024, 64 * 1024, 64 * 1024)
NEW_PINS = {
    'scripts/run_arv2_r298_sharadar_reference.py': '68a0272a7e78c3ec1490715b0dacc12c4e4c9532e7b4a9653a90bb20dee3023e',
    'scripts/capture_arv2_sharadar_identities.py': 'b307d102588c33002868e9d29d87a028046336442f314c7d6ef4041c65dba9e4',
    'research/analyst_revisions_v2_qc/newrule_comparison_targets.py': '30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d',
    'scripts/arv2_r298_sharadar_eligibility_observation.py': 'c2c669b7e58bbb9ce118328225ddc8b8e7d96df1c1d7727309e42544279a197e',
    'scripts/run_arv2_r298_sharadar_eligibility.py': 'b24c1538b13dfc44aa4890695043fb1d270023319b2e07039211b88c4c1b0ad6',
    'scripts/arv2_r298_sharadar_cusip_syntax.py': 'cab79cb04bbc0788b37138b74526fdd518b7d0e90ee7ceeca546227f91a7b72b',
    'scripts/arv2_r298_sharadar_probe_metadata.py': '3122b8f2be402d1d74de7b0f0259835d5c317d6d30b00274a069607024b881ae',
    'scripts/arv2_r298_sharadar_current_routes.py': '514e1f895c7e088de25e80b958ca4f2f9190e69bdadb18343f7dde40172e7955',
    'scripts/arv2_r298_sharadar_eligibility_v2_observation.py': 'a5dd7356316351af6ede75eb07db79464a546b661a9fba74a9c92786072c3b13',
}
FALSE_FLAGS = {'qc_contact': False, 'qc_transfer_authorized': False,
    'original_private_input_read': False, 'old_controls_read': False, 'new_paid_rights': False,
    'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'licensed_rows_disclosed': False, 'credential_persisted': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin',
    'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'capture_changed', 'capture_scope', 'capture_security', 'journal',
    'credentials_unavailable', 'output', 'output_bound', 'parent_failed',
    'validator_failed', 'refused', 'unknown_exception', 'os_error'))


class Refused(ValueError):
    """Closed caller predicate, never an exception or response rendering."""


def require(value, code):
    if not value:
        raise Refused(code)


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= DEADLINE_SECONDS, 'deadline')
    return value


def finite(error):
    if type(error) is observation.Refused:
        code = observation.finite(error)
        return 'provider_' + code if type(code) is str and code in observation.FINITE | {'unknown'} else 'refused'
    if type(error) is keychain.KeychainUnavailable:
        return 'credentials_unavailable'
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    return type(value) is str and value in FINITE | {'execution_environment_refused'} \
        | {'provider_' + code for code in observation.FINITE | {'unknown'}}


def pins():
    values = dict(previous.pins())
    for name, pin in NEW_PINS.items():
        require(name not in values or values[name] == pin, 'source_pin')
        values[name] = pin
    return values


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'prospective_complete_CUSIP_vocabulary_current_routes_status_and_early_window_eligibility_only',
        'deadline_seconds': DEADLINE_SECONDS, 'outer_seconds': 630, 'validator_seconds': 20,
        'maximum_application_dispatches': 6, 'provider_request_count': None,
        'capture_names': list(CAPTURE_NAMES), 'capture_bounds': list(CAPTURE_BOUNDS),
        'max_output': MAX_OUTPUT, 'max_control_files': MAX_FILES,
        'provider_profile_sha256': sha(canonical(observation.profile_record())),
        'closed_catalog_before_used_route_validation': True,
        'closed_catalog_retained_on_later_failure': True,
        'catalog_marker_is_not_an_HTTP_dispatch': True,
        'keychain_provider': 'sharadar', 'keychain_service': 'trading-agent-sharadar',
        'keychain_account': 'sharadar', 'keychain_path': keychain.KEYCHAIN,
        'keychain_lookups': 1, 'keychain_timeout_seconds': 20, 'credential_fallback': False,
        'claim_fsync_before_keychain_and_contact': True,
        'retained_fds_through_publication_and_return': True,
        'security_policy': 'empty_extended_ACL;only_opaque_stable_com.apple.provenance_xattr',
        'full_metadata_fields': ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid',
            'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'],
        'actual_exit_and_supplied_output_validator_required': True,
        'old_operational_entrypoints_invoked': False, 'automatic_retry': False,
        'cleanup_or_marker_repair': False, 'complete_coverage_proven': False,
        'cloud_processing_rights_proven': False, 'continuous_security_proven': False,
        'selected_pins_are_whole_interpreter_integrity': False,
        'uninterruptible_io_or_host_suspension_bounded': False,
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


metadata = previous.metadata


def security_snapshot(fd):
    try:
        return security.snapshot(fd)
    except security.Refusal:
        raise Refused('capture_security') from None


class Store:
    """Own V directory and all original response/control descriptors only."""
    def __init__(self):
        self.fd, self.chain, self.files, self.held = None, [], {}, {}
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
        return self.write_bytes(name, canonical(value), private=False)

    def write_bytes(self, name, raw, *, private):
        self.verify()
        require(type(name) is str and name not in self.files and len(self.files) < MAX_FILES
            and ((private is True and name in CAPTURE_NAMES)
                or (private is False and re.fullmatch(r'[a-z0-9-]{1,100}\.json', name))), 'control_name')
        limit = CAPTURE_BOUNDS[CAPTURE_NAMES.index(name)] if private else MAX_OUTPUT
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

    def capture_bytes(self):
        self.verify()
        require(all(name in self.files for name in CAPTURE_NAMES), 'capture_scope')
        result = {name: self._read(self.held[name][0], self.files[name][6]) for name in CAPTURE_NAMES}
        self.verify()
        return result


def native_profile():
    # The old function only constructs a policy string. No old operation or
    # control is invoked/read; artifacts, network, Keychains and security CLI
    # are denied for this supplied-public-output validator.
    return previous.native_profile(artifacts=True)


def _events(values):
    require(type(values) is list and len(values) <= 12, 'journal')
    checked = [observation.validate_event(value) for value in values]
    order = [(role, event) for role in ROLES for event in ('intent', 'status')]
    require(all((value['role'], value['event']) == order[index]
        for index, value in enumerate(checked)), 'journal')
    require(all(checked[index]['http_status'] == 200 for index in range(1, len(checked) - 1, 2)), 'journal')
    return checked


def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'local_only': True, 'old_controls_spent': True})
        state = {'stage': 'credentials', 'http_events': [], 'current_route_catalog': None,
            'receipt': None, 'captures': {}}
        key, payloads, buffers = None, None, None
        try:
            environment.require_safe_environment()
            key = keychain.load_key('sharadar', timeout_seconds=min(20, remaining(deadline)))
            state['stage'] = 'provider'
            import requests
            def journal(marker, event):
                remaining(deadline)
                environment.require_safe_environment()
                checked = observation.validate_event(event)
                require(marker == checked['role'].replace('_', '-') + '-' + checked['event'], 'journal')
                require(ROLES.index(checked['role']) < 2 or state['current_route_catalog'] is not None, 'journal')
                values = _events([*state['http_events'], checked])
                directory.write(marker + '.json', {**binding(args), 'observation': checked})
                state['http_events'] = values
            def catalog_observer(value):
                remaining(deadline)
                environment.require_safe_environment()
                require(state['current_route_catalog'] is None and len(state['http_events']) == 4
                    and all(state['http_events'][index]['http_status'] == 200 for index in (1, 3)), 'journal')
                try:
                    catalog = observation.current_routes.validate_receipt(value)
                except observation.current_routes.Refused:
                    raise Refused('journal') from None
                directory.write('metadata-catalog.json', {**binding(args), 'catalog': catalog})
                state['current_route_catalog'] = catalog
            with requests.Session() as session:
                observation.configure_owned_session(session)
                receipt, payloads = observation.observe(session=session, api_key=key,
                    journal=journal, catalog_observer=catalog_observer, deadline=deadline)
            checked = observation.validate_receipt(receipt)
            require(state['current_route_catalog'] is not None
                and canonical(state['current_route_catalog']) == canonical(checked['current_route_catalog']), 'capture_changed')
            observation.validate_events(checked, state['http_events'])
            require(type(payloads) is observation.PrivateCapture, 'capture_scope')
            buffers = payloads.bytes_by_name()
            require(type(buffers) is dict and set(buffers) == set(CAPTURE_NAMES)
                and all(type(value) is bytes for value in buffers.values()), 'capture_scope')
            observation.validate_capture(checked, buffers)
            state['receipt'] = checked
            state['stage'] = 'publication'
            for name in CAPTURE_NAMES:
                state['captures'][name] = directory.write_bytes(name, buffers[name], private=True)
            require(state['captures'] == observation.capture_pins(checked), 'capture_changed')
            # Consume retained own descriptors, not a new source/control reader.
            observation.validate_capture(checked, directory.capture_bytes())
            state['stage'] = 'postflight'
            preflight(args, deadline)
            environment.require_safe_environment()
            directory.verify()
            result = {'schema': SCHEMA, 'receipt': checked, 'http_events': _events(state['http_events']),
                'captures': dict(state['captures']), 'private_capture_authenticated': True,
                'post_checks_complete': True, 'result_cell': 0, **FALSE_FLAGS}
            validate_result(result)
            state['stage'] = 'report'
            pin = directory.write('report.json', {**binding(args), 'result': result})
            directory.verify()
            return {'result': result, 'report': pin}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state, 'claim_consumed': True, **FALSE_FLAGS}
            try:
                directory.write('failure.json', {**binding(args), **failed})
            except BaseException:
                pass
            return {'failure': failed}
        finally:
            key = payloads = buffers = None


def _capture_pins(value, *, partial=False):
    require(type(value) is dict and all(type(name) is str for name in value)
        and (set(value) <= set(CAPTURE_NAMES) if partial else set(value) == set(CAPTURE_NAMES)), 'output')
    require(set(value) == set(CAPTURE_NAMES[:len(value)]) if partial else True, 'output')
    for name, pin in value.items():
        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'}
            and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= CAPTURE_BOUNDS[CAPTURE_NAMES.index(name)]
            and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'output')
    return value


def validate_result(result):
    require(type(result) is dict and set(result) == {'schema', 'receipt', 'http_events',
        'captures', 'private_capture_authenticated', 'post_checks_complete', 'result_cell', *FALSE_FLAGS}
        and result['schema'] == SCHEMA and result['private_capture_authenticated'] is True
        and result['post_checks_complete'] is True and type(result['result_cell']) is int
        and result['result_cell'] == 0 and all(result[key] is False for key in FALSE_FLAGS), 'output')
    observation.validate_receipt(result['receipt'])
    require(len(_events(result['http_events'])) == 12, 'output')
    observation.validate_events(result['receipt'], result['http_events'])
    _capture_pins(result['captures'])
    require(result['captures'] == observation.capture_pins(result['receipt']), 'output')


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
        require(type(state) is dict and set(state) == {'stage', 'http_events', 'current_route_catalog', 'receipt', 'captures'}
            and state['stage'] in ('credentials', 'provider', 'publication', 'postflight', 'report'), 'output')
        _events(state['http_events'])
        _capture_pins(state['captures'], partial=True)
        if state['current_route_catalog'] is not None:
            try:
                observation.current_routes.validate_receipt(state['current_route_catalog'])
            except observation.current_routes.Refused:
                raise Refused('output') from None
            require(len(state['http_events']) >= 4
                and all(state['http_events'][index]['http_status'] == 200 for index in (1, 3)), 'output')
        require(len(state['http_events']) <= 4 or state['current_route_catalog'] is not None, 'output')
        if state['stage'] == 'credentials':
            require(state['http_events'] == [] and state['current_route_catalog'] is None
                and state['receipt'] is None and state['captures'] == {}, 'output')
        if state['stage'] == 'provider':
            require(state['receipt'] is None and state['captures'] == {}, 'output')
        if state['receipt'] is not None:
            observation.validate_receipt(state['receipt'])
            require(state['current_route_catalog'] is not None and canonical(state['current_route_catalog'])
                == canonical(state['receipt']['current_route_catalog']), 'output')
            observation.validate_events(state['receipt'], state['http_events'])
            expected = observation.capture_pins(state['receipt'])
            require(all(expected[name] == pin for name, pin in state['captures'].items()), 'output')
        else:
            require(state['captures'] == {} and state['stage'] in ('credentials', 'provider'), 'output')
        if state['stage'] in ('postflight', 'report'):
            require(set(state['captures']) == set(CAPTURE_NAMES), 'output')
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
        runtime = Path(tempfile.mkdtemp(prefix='r323-v-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        raw, errors, actual = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            safe, 630, stdout_limit=MAX_OUTPUT)
        outer['parent'] = actual
        require(type(actual['actual_exit']) is int and actual['actual_exit'] in (0, 2)
            and actual['bound'] is None and not errors, 'parent_failed')
        validated, errors, checked = capture(['/usr/bin/sandbox-exec', '-p', native_profile(),
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
