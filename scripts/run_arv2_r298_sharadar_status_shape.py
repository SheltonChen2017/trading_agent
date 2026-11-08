"""One separately frozen, local-only stocks-status shape diagnostic.

Exactly one request; no raw body persistence, price request or QC capability.
A diagnostic observation never admits a bulk source, subscription or strategy.
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
from scripts import run_arv2_r298_sharadar_eligibility_v2 as frozen
from scripts import arv2_r298_sharadar_status_shape as observation

protocol = frozen.observation

admitted, environment, capture_support = previous.admitted, previous.environment, previous.capture_support
canonical, parse, sha, capture = previous.canonical, previous.parse, previous.sha, previous.capture
SOURCE = ROOT / 'scripts/run_arv2_r298_sharadar_status_shape.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_sharadar_status_shape/R323-20261025-W'
SCHEMA = 'arv2-r298-sharadar-status-shape-w-v1'
PYTHON = previous.PYTHON
DEADLINE_SECONDS, MAX_OUTPUT, MAX_FILES = 90, 64 * 1024, 8
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
ROLES = ('stocks_status',)
EVENT_SCHEMA = SCHEMA + '-event'
CAPTURE_NAMES, CAPTURE_BOUNDS = (), ()
ENDPOINT = protocol.BASE + '/v1.0/data/stocks'
QUERY = {'status': 'True'}
NEW_PINS = {
    'scripts/run_arv2_r298_sharadar_eligibility_v2.py': 'c8fdf22b783e784a4ee4cefeffe346f5d6c4db1158b3e9e5133f9e36095e926b',
    'scripts/arv2_r298_sharadar_status_shape.py': '5ed5da0208aae8b18580b2a1569b5fab9df5fd49c3dee3ccf2bda208c1b5f5cb',
}
FALSE_FLAGS = {'qc_contact': False, 'qc_transfer_authorized': False,
    'original_private_input_read': False, 'old_controls_read': False, 'new_paid_rights': False,
    'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'licensed_rows_disclosed': False, 'credential_persisted': False}
FINITE = protocol.FINITE | frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin',
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
    if type(error) is protocol.Refused:
        code = protocol.finite(error)
        return code if code in FINITE else 'refused'
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
    values = dict(frozen.pins())
    for name, pin in NEW_PINS.items():
        require(name not in values or values[name] == pin, 'source_pin')
        values[name] = pin
    return values


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'first_retained_stocks_status_structure_not_V_eligibility_retry_or_source_admission',
        'endpoint': ENDPOINT, 'query': dict(QUERY), 'maximum_body_bytes': 8192,
        'deadline_seconds': 90, 'outer_seconds': 120, 'validator_seconds': 20,
        'maximum_application_dispatches': 1, 'provider_request_count': None,
        'max_output': MAX_OUTPUT, 'max_control_files': MAX_FILES,
        'provider_profile_sha256': sha(canonical(observation.profile_record())),
        'keychain_provider': 'sharadar', 'keychain_service': 'trading-agent-sharadar',
        'keychain_account': 'sharadar', 'keychain_path': keychain.KEYCHAIN,
        'keychain_lookups': 1, 'keychain_timeout_seconds': 20, 'credential_fallback': False,
        'claim_fsync_before_keychain_and_contact': True,
        'raw_body_persisted': False, 'raw_body_returned': False,
        'status_shape_not_bulk_or_price_admission': True,
        'retained_control_fds_through_publication_and_return_checks': True,
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
    """Own W control descriptors only; raw response bodies are never stored."""
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


def native_profile():
    # The old function only constructs a policy string. No old operation or
    # control is invoked/read; artifacts, network, Keychains and security CLI
    # are denied for this supplied-public-output validator.
    return previous.native_profile(artifacts=True)


def validate_event(value):
    require(type(value) is dict and set(value) == {'schema', 'event', 'role',
        'application_attempt', 'http_status', 'http_status_state'}
        and value['schema'] == EVENT_SCHEMA and value['role'] == 'stocks_status'
        and type(value['application_attempt']) is int and value['application_attempt'] == 1
        and value['event'] in ('intent', 'status'), 'journal')
    status, state = value['http_status'], value['http_status_state']
    require((value['event'] == 'intent' and status is None and state == 'not_observed')
        or (value['event'] == 'status' and ((type(status) is int and 100 <= status <= 599 and state == 'validated')
            or (status is None and state == 'unavailable'))), 'journal')
    return dict(value)


def _events(values):
    require(type(values) is list and len(values) <= 2, 'journal')
    checked = [validate_event(value) for value in values]
    require(all(row['event'] == ('intent', 'status')[index] for index, row in enumerate(checked)), 'journal')
    return checked


def _fetch(session, key, journal, deadline):
    import requests
    params = {**QUERY, 'api_key': key}
    protocol._session(session); protocol._budget(deadline)
    try:
        intent = session.prepare_request(requests.Request('GET', ENDPOINT, params=params,
            headers={'Accept-Encoding': 'identity'}))
        protocol._identity(intent, ENDPOINT, params)
    except protocol.Refused:
        raise
    except Exception:
        raise Refused('prepared_identity') from None
    journal('intent', None)
    response, complete = None, False
    try:
        try:
            response = session.get(ENDPOINT, params=params, timeout=protocol._budget(deadline),
                allow_redirects=False, stream=True, verify=True, headers={'Accept-Encoding': 'identity'})
        except Exception:
            journal('status', None)
            raise Refused('request_failed') from None
        try: numeric = response.status_code
        except Exception: numeric = None
        status = numeric if type(numeric) is int and 100 <= numeric <= 599 else None
        journal('status', status)
        require(status is not None, 'http_status_unavailable')
        require(status == 200, 'http_status')
        try:
            require(type(response) is requests.Response and response.history == [], 'response_identity')
            protocol._identity(response.request, ENDPOINT, params)
            from urllib.parse import urlencode
            parts, pairs = protocol.source._parse_url(response.url, provider=True)
            expected, expected_pairs = protocol.source._parse_url(ENDPOINT + '?' + urlencode(params), provider=True)
            require(parts.scheme == expected.scheme and parts.netloc == expected.netloc
                and parts.path == expected.path and pairs == expected_pairs, 'response_identity')
            headers = response.headers
            require(len(headers) <= 64, 'response_headers')
            for name, value in headers.items():
                require(type(name) is str and type(value) is str and len(name) <= 128 and len(value) <= 8192,
                    'response_headers')
                require(not any(secret in (name + ':' + value).encode('utf-8')
                    for secret in protocol._encodings(key)), 'credential_echo')
            encoding = headers.get('Content-Encoding')
            require(encoding is None or (type(encoding) is str and encoding.casefold() == 'identity'), 'response_encoding')
            length = headers.get('Content-Length')
            require(length is None or (type(length) is str and length.isascii() and length.isdecimal()
                and 0 < len(length) <= 10 and 0 < int(length) <= 8192), 'response_bound')
            chunks, count = [], 0
            for chunk in response.iter_content(chunk_size=8192):
                remaining(deadline)
                require(type(chunk) is bytes, 'response_stream')
                count += len(chunk); require(count <= 8192, 'response_bound')
                chunks.append(chunk)
            raw = b''.join(chunks)
            require(raw and (length is None or len(raw) == int(length)), 'response_bound')
            require(not any(secret in raw for secret in protocol._encodings(key)), 'credential_echo')
        except Refused:
            raise
        except protocol.Refused:
            raise
        except Exception:
            raise Refused('response_identity') from None
        protocol._session(session); remaining(deadline)
        complete = True
        return raw
    finally:
        if response is not None:
            try: response.close()
            except Exception:
                if complete: raise Refused('response_close') from None


def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'local_only': True, 'old_controls_spent': True})
        state = {'stage': 'credentials', 'http_events': [], 'receipt': None}
        key, raw = None, None
        try:
            environment.require_safe_environment()
            key = keychain.load_key('sharadar', timeout_seconds=min(20, remaining(deadline)))
            try: key = protocol.source._validated_api_key(key, synthetic=False)
            except Exception: raise Refused('credential') from None
            state['stage'] = 'provider'
            def journal(kind, status):
                remaining(deadline); environment.require_safe_environment()
                row = validate_event({'schema': EVENT_SCHEMA, 'event': kind, 'role': 'stocks_status',
                    'application_attempt': 1, 'http_status': status,
                    'http_status_state': 'not_observed' if kind == 'intent'
                        else 'unavailable' if status is None else 'validated'})
                checked = _events([*state['http_events'], row])
                directory.write('stocks-status-' + kind + '.json', {**binding(args), 'observation': row})
                state['http_events'] = checked
            import requests
            with requests.Session() as session:
                protocol.configure_owned_session(session)
                raw = _fetch(session, key, journal, deadline)
            receipt = observation.inspect_body(raw, api_key=key)
            state['receipt'] = observation.validate_capture(receipt, raw, api_key=key)
            state['stage'] = 'postflight'
            preflight(args, deadline)
            environment.require_safe_environment(); directory.verify()
            result = {'schema': SCHEMA, 'receipt': state['receipt'],
                'http_events': _events(state['http_events']), 'post_checks_complete': True,
                'result_cell': 0, **FALSE_FLAGS}
            validate_result(result)
            state['stage'] = 'report'
            pin = directory.write('report.json', {**binding(args), 'result': result})
            directory.verify()
            return {'result': result, 'report': pin}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state, 'claim_consumed': True, **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}
        finally:
            key = raw = None


def validate_result(value):
    require(type(value) is dict and set(value) == {'schema', 'receipt', 'http_events',
        'post_checks_complete', 'result_cell', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['post_checks_complete'] is True
        and type(value['result_cell']) is int and value['result_cell'] == 0
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    observation.validate_receipt(value['receipt'])
    events = _events(value['http_events'])
    require(len(events) == 2 and events[1]['http_status'] == 200, 'output')


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
        require(type(state) is dict and set(state) == {'stage', 'http_events', 'receipt'}
            and state['stage'] in ('credentials', 'provider', 'postflight', 'report'), 'output')
        events = _events(state['http_events'])
        if state['stage'] == 'credentials':
            require(not events and state['receipt'] is None, 'output')
        if state['receipt'] is not None:
            observation.validate_receipt(state['receipt'])
            require(len(events) == 2 and events[1]['http_status'] == 200, 'output')
        else:
            require(state['stage'] in ('credentials', 'provider'), 'output')
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
        runtime = Path(tempfile.mkdtemp(prefix='r323-w-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        raw, errors, actual = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            safe, 120, stdout_limit=MAX_OUTPUT)
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
