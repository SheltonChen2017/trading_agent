"""One bounded current-vintage Sharadar identity/exact-reference existence look.

No QC or strategy action exists. Original source/input authentication occurs in
separate credential-free native workers, before and after the two permitted
provider requests. Private routes/CSV stay private; observers receive only
closed evidence. A claim or ambiguous/nonzero exit is always spent.
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
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import observe_arv2_r298_reference_ticker as previous
from scripts import run_arv2_r298_reference_feed as feed
from scripts import arv2_keychain_connections as keychain
from scripts import arv2_relocation_security as security
from scripts import arv2_r298_sharadar_reference_binding as source_binding
from scripts import arv2_r298_sharadar_reference_observation as observation

admitted, environment, capture_support = previous.admitted, previous.environment, previous.capture_support
SOURCE = ROOT / 'scripts/run_arv2_r298_sharadar_reference.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_sharadar_reference/R323-20261025-O'
SCHEMA = 'arv2-r298-sharadar-reference-o-v1'
PYTHON = previous.PYTHON
DEADLINE_SECONDS, MAX_OUTPUT, MAX_PRIVATE_PACKET = 600, 128 * 1024, 16 * 1024
MAX_OBSERVER_OUTPUT, MAX_FILES = MAX_OUTPUT + 4096, 24
CAPTURE_NAMES = ('metadata.csv', 'price.csv')
CAPTURE_BOUNDS = (64 * 1024, 8 * 1024)
NEW_PINS = {
    'scripts/observe_arv2_r298_reference_ticker.py': '81ba47db277a5c20979490f9c0e901d4b5199a378fbb53b1be68a930463d6efc',
    'scripts/run_arv2_r298_reference_feed.py': '884bbd08d8e20b192e6fd694cf9a0b458e09b60ef400accb8664cfcae7cd0987',
    'scripts/arv2_keychain_connections.py': 'bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227',
    'scripts/arv2_r298_sharadar_reference_binding.py': '1e5b13c8a5338e286e2adc11046e2bfde0b066e55d6585549f718da4cfe8041e',
    'scripts/arv2_r298_sharadar_reference_observation.py': '72329cc48ce39eb2ccc3d61bca8fc79624a685704f1fa7fd96c5198dd882950f',
}
FALSE_FLAGS = {**previous.previous.FALSE_FLAGS, 'qc_contact': False,
    'source_repair_performed': False, 'provider_route_admitted': False,
    'strategy_result_accepted': False, 'family_comparable': False,
    'price_used': False, 'paper_or_live_ready': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin', 'claim_spent',
    'control_changed', 'control_name', 'control_bound', 'control_write', 'worker_scope',
    'worker_credentials', 'worker_failed', 'worker_packet', 'source_changed', 'capture_changed',
    'capture_scope', 'capture_security', 'journal', 'credentials_unavailable', 'output', 'output_bound',
    'parent_failed', 'validator_failed', 'refused', 'unknown_exception', 'os_error'))
canonical, parse, sha, capture = previous.canonical, previous.parse, previous.sha, previous.capture


class Refused(ValueError): pass


class WorkerRefused(ValueError):
    """A strict own-binding native child finite refusal, never child text."""


def _foreign():
    return ((source_binding.source_guard, 'native_security_'),
        (source_binding.evidence, 'native_evidence_'),
        (source_binding.admission, 'native_admission_'),
        (source_binding.identity_join, 'native_join_'), (previous, 'native_original_'))


def require(value, code):
    if not value: raise Refused(code)


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= DEADLINE_SECONDS, 'deadline')
    return deadline - time.monotonic()


def finite(error):
    if type(error) is WorkerRefused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and _finite_code(args[0]) else 'worker_failed'
    for module, prefix in _foreign():
        if type(error) is module.Refused:
            method = vars(module).get('finite')
            if callable(method): code = method(error)
            else:
                values = BaseException.args.__get__(error)
                code = values[0] if len(values) == 1 and type(values[0]) is str and values[0] in module.FINITE else 'unknown'
            return prefix + code if type(code) is str and code in module.FINITE | {'unknown'} else 'refused'
    for module, prefix in ((source_binding, 'source_'), (observation, 'provider_')):
        if type(error) is module.Refused:
            code = module.finite(error)
            return prefix + code if type(code) is str and code in module.FINITE | {'unknown'} else 'refused'
    if type(error) is keychain.KeychainUnavailable: return 'credentials_unavailable'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, OSError): return 'os_error'
    return 'unknown_exception'


def _finite_code(value):
    inventory = FINITE | {'source_' + code for code in source_binding.FINITE | {'unknown'}} \
        | {'provider_' + code for code in observation.FINITE | {'unknown'}}
    for module, prefix in _foreign(): inventory |= {prefix + code for code in module.FINITE | {'unknown'}}
    return type(value) is str and value in inventory


def pins():
    values = {}
    for selected in (previous.pins(), feed.pins(), NEW_PINS):
        for name, pin in selected.items():
            require(name not in values or values[name] == pin, 'source_pin')
            values[name] = pin
    return values


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'deadline_seconds': DEADLINE_SECONDS, 'max_output': MAX_OUTPUT,
        'private_packet_bound': MAX_PRIVATE_PACKET, 'maximum_provider_attempts': 2,
        'capture_names': list(CAPTURE_NAMES), 'capture_bounds': list(CAPTURE_BOUNDS),
        'keychain_provider': 'sharadar', 'keychain_service': 'trading-agent-sharadar',
        'keychain_account': 'sharadar', 'keychain_path': keychain.KEYCHAIN,
        'keychain_lookups': 1, 'keychain_timeout_seconds': 20,
        'credential_fallback': False, 'qc_jobs': 0, 'new_strategy_looks': 0, 'result_cell': 0,
        'source_guard_across_provider_contact': False, 'separate_initial_final_native_guards': True,
        'source_binding_profile_sha256': sha(canonical(source_binding.profile_record())),
        'provider_profile_sha256': sha(canonical(observation.profile_record())),
        'm_control_read': False, 'n_control_read': False, 'old_controls_spent': True,
        'raw_private_payloads_in_external_output': False, 'historical_cause_authenticated': False,
        'continuous_security_proven': False, **FALSE_FLAGS}


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
    raw = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline, 128 * 1024)
    require(sha(raw) == args.caller_sha256, 'source_pin')
    remaining(deadline)


def metadata(info):
    return tuple(getattr(info, key, None) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'))


def security_snapshot(fd):
    try: return security.snapshot(fd)
    except security.Refusal: raise Refused('capture_security') from None


class Store:
    """Exclusive O output, with private CSV descriptors retained until return."""
    def __init__(self):
        self.fd, self.chain, self.files, self.private = None, [], {}, {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try: os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    except FileExistsError: require(here != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt
                self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd; self.verify()
        except BaseException: os.close(fd); raise

    def __enter__(self): return self
    def __exit__(self, *_):
        for fd, _ in self.private.values(): os.close(fd)
        os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(self.fd)) == metadata(os.fstat(other))
                and os.fstat(other).st_uid == os.getuid() and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES, 'control_changed')
            for name, baseline in self.files.items():
                require(metadata(os.stat(name, dir_fd=other, follow_symlinks=False)) == baseline, 'control_changed')
            for name, (fd, snapshot) in self.private.items():
                require(metadata(os.fstat(fd)) == self.files[name]
                    and security_snapshot(fd) == snapshot, 'capture_changed')
        finally: os.close(other)

    def adopt_started(self, index, args):
        name = 'worker-' + str(index) + '-started.json'
        try:
            value = _read_json(self.fd, name, MAX_OUTPUT)
        except FileNotFoundError:
            return
        require(type(value) is dict and set(value) == {'binding', 'worker_index'}
            and value['binding'] == binding(args) and type(value['worker_index']) is int
            and value['worker_index'] == index, 'worker_scope')
        require(name not in self.files, 'worker_scope')
        self.files[name] = metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
        self.verify()

    def write(self, name, value): return self.write_bytes(name, canonical(value), private=False)

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
            before_security = None
            if private:
                empty = os.fstat(fd)
                require(stat.S_ISREG(empty.st_mode) and stat.S_IMODE(empty.st_mode) == 0o600
                    and empty.st_uid == os.getuid() and empty.st_nlink == 1 and empty.st_size == 0, 'control_write')
                # Authenticate inherited ACL/xattrs BEFORE any licensed byte.
                before_security = security_snapshot(fd)
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); require(count > 0, 'control_write'); view = view[count:]
            os.fsync(fd); os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            os.lseek(fd, 0, os.SEEK_SET)
            reread = os.read(fd, len(raw) + 1)
            require(reread == raw and metadata(info) == metadata(os.fstat(fd)), 'control_changed')
            self.files[name] = metadata(info)
            if private:
                require(security_snapshot(fd) == before_security, 'capture_changed')
                self.private[name] = (fd, before_security); kept = True
        finally:
            if not kept: os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}


def native_profile(*, artifacts=False):
    value = feed.native_profile(artifacts=artifacts)
    if not artifacts:
        old = (f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
            ' (require-not (literal "/dev/null"))))')
        new = (f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
            f' (require-not (literal "/dev/null")) (require-not (subpath "{CONTROL}"))))')
        require(value.count(old) == 1, 'worker_scope')
        value = value.replace(old, new)
    return value + ''.join(f'(deny file-read* file-write* (subpath "{path}"))'
        for path in (previous.CONTROL, feed.CONTROL))


def _credential_free():
    require(not any(key in os.environ for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY',
        'MASSIVE_API_KEY', 'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY')), 'worker_credentials')


def _read_json(fd, name, maximum):
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        info = os.fstat(source)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_nlink == 1 and 0 < info.st_size <= maximum, 'worker_scope')
        raw = os.read(source, info.st_size + 1)
        require(len(raw) == info.st_size and metadata(info) == metadata(os.fstat(source))
            == metadata(os.stat(name, dir_fd=fd, follow_symlinks=False)), 'worker_scope')
        return parse(raw)
    finally: os.close(source)


def worker(args, deadline):
    _credential_free()
    require(type(args.control_fd) is int and args.control_fd > 2
        and type(args.worker_index) is int and args.worker_index in (0, 1), 'worker_scope')
    named, _ = admitted._storage_module()._walk(CONTROL)
    try:
        require(metadata(os.fstat(named)) == metadata(os.fstat(args.control_fd)), 'worker_scope')
        claim = _read_json(named, 'claim.json', MAX_OUTPUT)
        expected_claim = {**binding(args), 'old_controls_spent': True}
        require(type(claim) is dict and set(claim) == set(expected_claim)
            and all(type(claim[key]) is type(item) and claim[key] == item for key, item in expected_claim.items()), 'worker_scope')
        intent = _read_json(named, 'worker-' + str(args.worker_index) + '-intent.json', MAX_OUTPUT)
        require(type(intent) is dict and intent.get('binding') == binding(args)
            and type(intent.get('worker_index')) is int and intent['worker_index'] == args.worker_index
            and set(intent) == {'binding', 'worker_index', 'expected'}, 'worker_scope')
        started = os.open('worker-' + str(args.worker_index) + '-started.json',
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=named)
        try:
            view = memoryview(canonical({'binding': binding(args), 'worker_index': args.worker_index}))
            while view:
                count = os.write(started, view); require(count > 0, 'control_write'); view = view[count:]
            os.fsync(started); os.fsync(named)
        finally: os.close(started)
        # The parent made this exclusive intent before dispatch. Its inherited
        # descriptor is the only control capability passed to a native worker.
        def consume(receipt, packet):
            source_binding.validate_pair(receipt, packet)
            if args.worker_index == 1:
                expected = intent['expected']
                require(type(expected) is dict and set(expected) == {'source', 'private_packet_sha256',
                    'receipt', 'captures'} and receipt == expected['source']
                    and source_binding.packet_digest(packet) == expected['private_packet_sha256'], 'source_changed')
                fds, raws, snapshots, baselines = [], [], [], []
                try:
                    for name, limit in zip(CAPTURE_NAMES, CAPTURE_BOUNDS, strict=True):
                        pin = expected['captures'].get(name)
                        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'}
                            and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= limit, 'capture_scope')
                        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=named); fds.append(fd)
                        before = security_snapshot(fd); snapshots.append(before)
                        info = os.fstat(fd)
                        baselines.append(metadata(info))
                        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == pin['byte_count'], 'capture_changed')
                        raw = os.read(fd, limit + 1)
                        require(len(raw) == pin['byte_count'] and sha(raw) == pin['sha256'], 'capture_changed')
                        raws.append(raw)
                    observation.validate_capture(packet, expected['receipt'], *raws)
                    preflight(args, deadline); environment.require_safe_environment()
                    for name, fd, snapshot, baseline in zip(CAPTURE_NAMES, fds, snapshots, baselines, strict=True):
                        require(security_snapshot(fd) == snapshot
                            and baseline == metadata(os.fstat(fd))
                            == metadata(os.stat(name, dir_fd=named, follow_symlinks=False)), 'capture_changed')
                finally:
                    for fd in fds: os.close(fd)
            else:
                require(intent['expected'] is None, 'worker_scope')
                preflight(args, deadline); environment.require_safe_environment()
            result = {'source': receipt, 'private_packet': source_binding.private_record(packet)}
            require(len(canonical(result)) <= MAX_PRIVATE_PACKET, 'worker_packet')
            return result
        return source_binding.prepare(deadline, phase='initial' if args.worker_index == 0 else 'final', consumer=consume)
    finally: os.close(named)


def run_worker(args, directory, deadline, index, expected=None):
    require(type(index) is int and index in (0, 1), 'worker_scope')
    directory.write('worker-' + str(index) + '-intent.json',
        {'binding': binding(args), 'worker_index': index, 'expected': expected})
    runtime = Path(tempfile.mkdtemp(prefix='r323-o-worker-', dir=ROOT / '.pytest_cache'))
    safe = capture_support._environment(runtime)
    raw, errors, observed = capture(['/usr/bin/sandbox-exec', '-p', native_profile(), str(PYTHON), '-B',
        str(SOURCE), 'worker', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(directory.fd), '--worker-index', str(index)], safe,
        min(150, remaining(deadline)), stdout_limit=MAX_PRIVATE_PACKET, pass_fds=(directory.fd,))
    directory.adopt_started(index, args)
    directory.write('worker-' + str(index) + '-observed.json', observed)
    if type(observed.get('actual_exit')) is int and observed['actual_exit'] == 2 and observed['bound'] is None and not errors:
        try: failed = parse(raw)
        except BaseException: failed = None
        if type(failed) is dict and set(failed) == {'binding', 'preflight_failure'} \
                and failed['binding'] == binding(args) and _finite_code(failed['preflight_failure']):
            raise WorkerRefused(failed['preflight_failure'])
    require(type(observed.get('actual_exit')) is int and observed['actual_exit'] == 0
        and observed['bound'] is None and not errors, 'worker_failed')
    require('worker-' + str(index) + '-started.json' in directory.files, 'worker_scope')
    value = parse(raw)
    require(type(value) is dict and set(value) == {'binding', 'packet'}
        and value['binding'] == binding(args), 'worker_packet')
    result = value['packet']
    require(type(result) is dict and set(result) == {'source', 'private_packet'}, 'worker_packet')
    source_binding.validate_pair(result['source'], result['private_packet'])
    return result


def _events(values):
    require(type(values) is list and len(values) <= 4, 'journal')
    checked = [observation.validate_event(value) for value in values]
    order = [(role, event) for role in ('metadata', 'price') for event in ('intent', 'status')]
    require(all((value['role'], value['event']) == order[index] for index, value in enumerate(checked)), 'journal')
    require(len(checked) <= 2 or checked[1]['http_status'] == 200, 'journal')
    return checked


def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'old_controls_spent': True})
        state = {'stage': 'initial_source', 'http_events': [], 'receipt': None, 'source': None}
        key, private_packet, payloads = None, None, None
        try:
            initial = run_worker(args, directory, deadline, 0)
            state['source'] = source_binding.validate_receipt(initial['source'])
            private_packet = source_binding.validate_packet(initial['private_packet'])
            state['stage'] = 'credentials'
            key = keychain.load_key('sharadar', timeout_seconds=min(20, remaining(deadline)))
            state['stage'] = 'provider'
            import requests
            def journal(marker, event):
                remaining(deadline)
                checked = observation.validate_event(event)
                require(marker == checked['role'] + '-' + checked['event'], 'journal')
                values = _events([*state['http_events'], checked])
                state['http_events'] = values
                directory.write(marker + '.json', {**binding(args), 'observation': checked})
            with requests.Session() as session:
                observation.configure_owned_session(session)
                receipt, payloads = observation.observe(private_packet, session=session,
                    api_key=key, journal=journal, deadline=deadline)
            state['receipt'] = observation.validate_receipt(receipt)
            observation.validate_events(state['receipt'], state['http_events'])
            require(state['receipt']['private_packet_sha256'] == state['source']['private_packet_sha256'], 'source_changed')
            state['stage'] = 'publication'
            raw_pair = payloads.bytes_pair()
            require(type(raw_pair) is tuple and len(raw_pair) == 2, 'capture_scope')
            captures = {name: directory.write_bytes(name, raw, private=True)
                for name, raw in zip(CAPTURE_NAMES, raw_pair, strict=True)}
            require(captures == observation.capture_pins(state['receipt']), 'capture_changed')
            state['stage'] = 'final_source'
            expected = {'source': initial['source'], 'private_packet_sha256': source_binding.packet_digest(private_packet),
                'receipt': state['receipt'], 'captures': captures}
            final = run_worker(args, directory, deadline, 1, expected)
            require(final == initial, 'source_changed')
            preflight(args, deadline); directory.verify()
            result = {'schema': SCHEMA, 'source': initial['source'], 'receipt': state['receipt'],
                'http_events': _events(state['http_events']), 'captures': captures,
                'final_source_authenticated': True, 'result_cell': 0, **FALSE_FLAGS}
            pin = directory.write('report.json', {**binding(args), 'result': result})
            return {'result': result, 'report': pin}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state, 'claim_consumed': True, **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}
        finally:
            key = private_packet = payloads = None


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    require(type(value) is dict and value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and _finite_code(value['preflight_failure']), 'output'); return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failed = outcome['failure']
        require(actual_exit == 2 and type(failed) is dict and set(failed) == {'failure_code', 'state', 'claim_consumed', *FALSE_FLAGS}
            and _finite_code(failed['failure_code']) and failed['claim_consumed'] is True
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        state = failed['state']
        require(type(state) is dict and set(state) == {'stage', 'http_events', 'receipt', 'source'}
            and state['stage'] in ('initial_source', 'credentials', 'provider', 'publication', 'final_source'), 'output')
        _events(state['http_events'])
        if state['source'] is not None: source_binding.validate_receipt(state['source'])
        require(not state['http_events'] or state['source'] is not None, 'output')
        require((state['stage'] != 'initial_source' or (state['source'] is None and not state['http_events'] and state['receipt'] is None))
            and (state['stage'] != 'credentials' or (state['source'] is not None and not state['http_events'] and state['receipt'] is None)), 'output')
        if state['receipt'] is not None:
            observation.validate_receipt(state['receipt'])
            observation.validate_events(state['receipt'], state['http_events'])
            require(state['source'] is not None
                and state['receipt']['private_packet_sha256'] == state['source']['private_packet_sha256'], 'output')
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        result = outcome['result']
        require(type(result) is dict and set(result) == {'schema', 'source', 'receipt', 'http_events',
            'captures', 'final_source_authenticated', 'result_cell', *FALSE_FLAGS}
            and result['schema'] == SCHEMA and result['final_source_authenticated'] is True
            and type(result['result_cell']) is int and result['result_cell'] == 0
            and all(result[key] is False for key in FALSE_FLAGS), 'output')
        source_binding.validate_receipt(result['source']); observation.validate_receipt(result['receipt'])
        require(len(_events(result['http_events'])) == 4
            and result['source']['private_packet_sha256'] == result['receipt']['private_packet_sha256'], 'output')
        observation.validate_events(result['receipt'], result['http_events'])
        require(type(result['captures']) is dict and set(result['captures']) == set(CAPTURE_NAMES), 'output')
        for name, limit in zip(CAPTURE_NAMES, CAPTURE_BOUNDS, strict=True):
            pin = result['captures'][name]
            require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'}
                and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= limit
                and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'output')
        require(result['captures'] == observation.capture_pins(result['receipt']), 'output')
        report = canonical({**binding(args), 'result': result})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def observe(args):
    outer = {'schema': SCHEMA + '-observer', 'parent': None, 'validator': None,
        'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        runtime = Path(tempfile.mkdtemp(prefix='r323-o-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        raw, errors, actual = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            safe, DEADLINE_SECONDS + 30, stdout_limit=MAX_OUTPUT)
        outer['parent'] = actual
        require(type(actual['actual_exit']) is int and actual['actual_exit'] in (0, 2)
            and actual['bound'] is None and not errors, 'parent_failed')
        validated, errors, check = capture(['/usr/bin/sandbox-exec', '-p', native_profile(artifacts=True),
            str(PYTHON), '-B', str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(actual['actual_exit'])],
            safe, 30, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = check
        require(check['actual_exit'] == 0 and check['bound'] is None and not errors, 'validator_failed')
        outer['output'] = parse(validated); outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OBSERVER_OUTPUT, 'output_bound')
        return outer, actual['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error); return outer, 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'worker', 'validate'))
    parser.add_argument('--expected-head', required=True); parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--actual-exit', type=int); parser.add_argument('--control-fd', type=int)
    parser.add_argument('--worker-index', type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        result, code = observe(args); sys.stdout.buffer.write(canonical(result)); return code
    deadline = time.monotonic() + (150 if args.operation == 'worker' else 30 if args.operation == 'validate' else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline); environment._bootstrap_cli_logging()
            if args.operation == 'worker': result, code = {'binding': binding(args), 'packet': worker(args, deadline)}, 0
            elif args.operation == 'validate':
                result, code = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args), 0
            else:
                outcome = run(args, deadline)
                result, code = {'binding': binding(args), 'outcome': outcome}, 2 if 'failure' in outcome else 0
            raw = canonical(result)
            require(len(raw) <= (MAX_PRIVATE_PACKET if args.operation == 'worker' else MAX_OUTPUT), 'output_bound')
            sys.stdout.buffer.write(raw); return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)})); return 2


if __name__ == '__main__': raise SystemExit(main())
