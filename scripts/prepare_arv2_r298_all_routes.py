"""One separately frozen full-original-catalog current-route preparation.

Four fixed current metadata/status requests precede a native network-denied
all-binding join. This does not acquire or admit prices, transfer data to QC,
or launch a strategy. Every successful secret-checked response is retained
before semantic interpretation. One claim, one worker, no retry or fallback.
"""
from __future__ import annotations
import argparse
import base64
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
from scripts import run_arv2_r298_sharadar_eligibility_v2 as previous
from scripts import arv2_r298_post_merge_source_pins as pin_contract
from scripts import arv2_r298_sharadar_bulk_status_v2 as status_v2
from scripts import arv2_r298_all_route_worker as worker
from scripts import arv2_keychain_connections as keychain
from scripts import arv2_relocation_security as security
from scripts import arv2_r298_sharadar_eligibility_v2_observation as observation

admitted, environment, capture_support = previous.admitted, previous.environment, previous.capture_support
canonical, parse, sha, capture, metadata = previous.canonical, previous.parse, previous.sha, previous.capture, previous.metadata
PYTHON = previous.PYTHON
SOURCE = ROOT / 'scripts/prepare_arv2_r298_all_routes.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z'
SCHEMA = 'arv2-r298-all-route-preparation-z-v1'
DEADLINE_SECONDS, MAX_OUTPUT, MAX_FILES = 900, 128 * 1024, 24
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
MAX_PRIVATE = 129 * 1024 * 1024
MAX_WORKER_INPUT = 46 * 1024 * 1024
ROLES = observation.ROLES[:4]
BODY_NAMES = observation.CAPTURE_NAMES[:4]
BODY_BOUNDS = observation.CAPTURE_BOUNDS[:4]
CAPTURE_NAMES = (*BODY_NAMES, 'routes-private.json')
CAPTURE_BOUNDS = (*BODY_BOUNDS, MAX_PRIVATE)
NEW_PINS = {
    'scripts/arv2_r298_post_merge_source_pins.py': '45212ec4ad2585a29c8105f2c66862ae2b625def159ac2706479974f3faa3f5b',
    'scripts/arv2_r298_sharadar_bulk_status_v2.py': '0394c5d1dd1a9d11077dacb5ae3f480ce6152ab2bab4dc1cc61f3401f488f691',
    'scripts/arv2_r298_sharadar_all_routes.py': 'd3a7ab5fd486d548ec90d27532741cd8e0194863bd548baa53c0fd8c765bdd83',
    'scripts/arv2_r298_original_ticker_catalog.py': 'e88d6197445880a832c55fa60a3bcce98213aa3baef02fae11a7a33c131d9d29',
    'scripts/arv2_r298_all_route_worker.py': '52a9ad6abf2f7385adbf844743ea2e5c06aaf707a872a4e2c17bf6a0bb6d0a81',
}
FALSE_FLAGS = {'qc_contact': False, 'qc_transfer_authorized': False,
    'old_operational_controls_read': False, 'new_paid_rights': False,
    'price_acquired': False, 'strategy_price_admitted': False,
    'strategy_nav_admitted': False, 'strategy_result_accepted': False,
    'family_comparable': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'licensed_rows_disclosed': False,
    'credential_persisted': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin',
    'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'capture_changed', 'capture_scope', 'capture_security', 'journal',
    'credentials_unavailable', 'output', 'output_bound', 'parent_failed',
    'validator_failed', 'refused', 'unknown_exception', 'os_error', 'worker_failed',
    'worker_input', 'worker_binding', 'private_binding', 'summary'))

class Refused(ValueError): pass

def require(value, code):
    if not value: raise Refused(code)

def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= DEADLINE_SECONDS, 'deadline')
    return value

def finite(error):
    for module, prefix in ((observation, 'provider_'), (status_v2, 'status_'), (worker, 'worker_')):
        if type(error) is module.Refused:
            code = module.finite(error)
            return prefix + code if code in module.FINITE else 'refused'
    if type(error) is keychain.KeychainUnavailable: return 'credentials_unavailable'
    if type(error) is environment.EnvironmentRefused: return 'execution_environment_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'refused'
    if isinstance(error, OSError): return 'os_error'
    return 'unknown_exception'

def _finite_code(value):
    return type(value) is str and value in FINITE | {'execution_environment_refused'} | {
        prefix + code for module, prefix in ((observation, 'provider_'),
        (status_v2, 'status_'), (worker, 'worker_')) for code in module.FINITE}

def pins():
    result = pin_contract.pins()
    for name, pin in NEW_PINS.items():
        require(name not in result or result[name] == pin, 'source_pin')
        require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64, 'source_pin')
        result[name] = pin
    return result

def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'first_full_original_6151_binding_and_eight_ETF_current_route_preparation',
        'source_contract': pin_contract.profile_record(),
        'worker_profile': worker.profile_record(), 'bulk_status_profile': status_v2.profile_record(),
        'roles': list(ROLES), 'body_names': list(BODY_NAMES), 'body_bounds': list(BODY_BOUNDS),
        'queries': [{'role': role, 'endpoint': observation.BASE + observation._query(role)[0],
            'parameters': observation._query(role)[1]} for role in ROLES],
        'maximum_application_dispatch_attempts': 4, 'provider_request_count': None,
        'deadline_seconds': DEADLINE_SECONDS, 'outer_seconds': 930, 'worker_seconds': 450,
        'validator_seconds': 20, 'maximum_worker_input_bytes': MAX_WORKER_INPUT,
        'maximum_private_worker_output_bytes': MAX_PRIVATE, 'maximum_public_bytes': MAX_OUTPUT,
        'claim_consumes_even_without_contact': True, 'partial_claim_is_ambiguous_spent': True,
        'success_body_retained_before_semantic_checks': True,
        'private_pipe_never_printed': True, 'one_worker_only_after_persistent_marker': True,
        'old_A11_D2_controls_not_used_for_new_local_input_purpose': True,
        'current_metadata_not_vendor_atomic_snapshot': True,
        'endpoint_checks_not_continuous_integrity_or_cause': True,
        'selected_pins_not_whole_interpreter_integrity': True,
        'only_own_child_killed_and_reaped': True, 'deadline_host_suspension_IO_qualification': True,
        'actual_exit_and_external_output_validation_required': True,
        'raw_capture_retention': 'private_personal_research_no_QC_transfer',
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

def native_profile(*, worker_mode=False):
    value = '(version 1)(allow default)(deny network*)'
    value += ''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
        ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))'
    value += (f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
        ' (require-not (literal "/dev/null"))))')
    if not worker_mode:
        return value + f'(deny file-read* (subpath "{ROOT / "artifacts"}"))'
    from scripts import run_arv2_newrule_comparison as inputs
    from scripts import arv2_r298_reference_ticker_source_guard as original_guard
    leaves = [inputs.LINEAGE, *(original_guard.CAPTURE / name for name in original_guard.LEAVES),
        CONTROL / 'claim.json', CONTROL / 'join-start.json']
    directories = {ROOT / 'artifacts', CONTROL, inputs.PACKAGE}
    for path in [*leaves, inputs.PACKAGE]:
        directories.update(parent for parent in path.parents if ROOT / 'artifacts' == parent
            or ROOT / 'artifacts' in parent.parents)
    exceptions = ''.join(f'(require-not (literal "{path}"))' for path in sorted(directories | set(leaves)))
    return value + (f'(deny file-read* (require-all (subpath "{ROOT / "artifacts"}")'
        f' (require-not (subpath "{inputs.PACKAGE}")) {exceptions}))')

def _events(values):
    require(type(values) is list and len(values) <= 8, 'journal')
    checked = [observation.validate_event(value) for value in values]
    order = [(role, event) for role in ROLES for event in ('intent', 'status')]
    require(all((value['role'], value['event']) == order[index]
        for index, value in enumerate(checked)), 'journal')
    require(all(checked[index]['http_status'] == 200 for index in range(1, len(checked) - 1, 2)), 'journal')
    return checked

def _json_private(raw, maximum):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'worker_input')
            result[key] = value
        return result
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'worker_input')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('worker_input')))
        require(type(value) is dict and canonical(value) == raw, 'worker_input')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('worker_input') from None

def worker_packet(raw, expected_capture_pins):
    value = _json_private(raw, MAX_PRIVATE)
    require(set(value) == {'summary', 'private', 'capture_pins'}, 'worker_binding')
    require(value['capture_pins'] == expected_capture_pins, 'worker_binding')
    worker.validate_summary(value['summary'])
    require(value['summary']['current_metadata'] == {
        table: expected_capture_pins[name] for table, name in
        zip(('stocks', 'funds'), BODY_NAMES[:2], strict=True)}, 'worker_binding')
    private_raw = worker.canonical(value['private'])
    require(value['summary']['private_frame_byte_count'] == len(private_raw)
        and value['summary']['private_frame_sha256'] == sha(private_raw), 'private_binding')
    return value, private_raw

def _inherited(args, deadline):
    """An accidental direct worker invocation cannot substitute stdin for a claim."""
    require(all(type(value) is int and value > 2 for value in
        (args.claim_fd, args.marker_fd, args.directory_fd))
        and len({args.claim_fd, args.marker_fd, args.directory_fd}) == 3, 'worker_binding')
    named, chain = admitted._storage_module()._walk(CONTROL)
    try:
        require(metadata(os.fstat(named)) == metadata(os.fstat(args.directory_fd)), 'worker_binding')
        for fd, name, expected in ((args.claim_fd, 'claim.json',
            {**binding(args), 'local_only': True, 'old_controls_spent': True}),
            (args.marker_fd, 'join-start.json', {**binding(args), 'stage': 'native-all-binding-join'})):
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and metadata(info) == metadata(os.stat(name, dir_fd=named, follow_symlinks=False))
                and info.st_size == len(canonical(expected)), 'worker_binding')
            raw = Store._read(fd, info.st_size)
            require(raw == canonical(expected) and metadata(info) == metadata(os.fstat(fd)), 'worker_binding')
        remaining(deadline)
    finally: os.close(named)

def run_worker(args, deadline):
    _inherited(args, deadline)
    packet = _json_private(sys.stdin.buffer.read(MAX_WORKER_INPUT + 1), MAX_WORKER_INPUT)
    require(set(packet) == {'stocks', 'funds', 'capture_pins'}, 'worker_input')
    buffers = []
    for key, name, bound in zip(('stocks', 'funds'), BODY_NAMES[:2], BODY_BOUNDS[:2], strict=True):
        require(type(packet[key]) is str and len(packet[key]) <= (bound + 2) // 3 * 4, 'worker_input')
        try: raw = base64.b64decode(packet[key], validate=True)
        except ValueError: raise Refused('worker_input') from None
        require(0 < len(raw) <= bound and base64.b64encode(raw).decode('ascii') == packet[key], 'worker_input')
        buffers.append(raw)
    expected = {name: {'byte_count': len(raw), 'sha256': sha(raw)}
        for name, raw in zip(BODY_NAMES[:2], buffers, strict=True)}
    require(packet['capture_pins'] == expected, 'worker_binding')
    summary, private = worker.prepare(*buffers, deadline=deadline)
    worker.validate_summary(summary)
    _inherited(args, deadline)
    return {'summary': summary, 'private': private, 'capture_pins': expected}

def _actual(value):
    require(type(value) is dict and set(value) == {'actual_exit', 'bound', 'spawn_observed',
        'dispatched_at', 'completion_observed_at', 'stdout_bytes', 'stdout_sha256',
        'stderr_bytes', 'stderr_sha256'} and type(value['spawn_observed']) is bool
        and value['bound'] in (None, 'deadline', 'channel_bound', 'capture_failed', 'reap_unknown')
        and (value['actual_exit'] is None or (type(value['actual_exit']) is int
            and -128 <= value['actual_exit'] <= 255))
        and all(type(value[key]) is str and re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z', value[key]) for key in
            ('dispatched_at', 'completion_observed_at'))
        and type(value['stdout_bytes']) is int and 0 <= value['stdout_bytes'] <= MAX_PRIVATE + 16384
        and type(value['stderr_bytes']) is int and 0 <= value['stderr_bytes'] <= 4096 + 16384
        and all(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]) for key in
            ('stdout_sha256', 'stderr_sha256')), 'output')
    return dict(value)

def invoke_worker(directory, buffers, args, deadline, state):
    require(set(buffers) == set(BODY_NAMES), 'capture_scope')
    directory.write('join-start.json', {**binding(args), 'stage': 'native-all-binding-join'})
    claim_fd = directory.held['claim.json'][0]
    marker_fd = directory.held['join-start.json'][0]
    packet = {key: base64.b64encode(buffers[name]).decode('ascii')
        for key, name in zip(('stocks', 'funds'), BODY_NAMES[:2], strict=True)}
    expected = {name: {'byte_count': len(buffers[name]), 'sha256': sha(buffers[name])}
        for name in BODY_NAMES[:2]}
    packet['capture_pins'] = expected
    raw = canonical(packet)
    require(len(raw) <= MAX_WORKER_INPUT, 'worker_input')
    runtime = Path(tempfile.mkdtemp(prefix='r326-z-worker-', dir=ROOT / '.pytest_cache'))
    safe = capture_support._environment(runtime)
    # This bounded capture owns exactly one child. The inherited protocol
    # descriptors have fixed identities and are never changed by that child.
    output, errors, actual = capture(['/usr/bin/sandbox-exec', '-p', native_profile(worker_mode=True),
        str(PYTHON), '-B', str(SOURCE), 'worker', '--expected-head', args.expected_head,
        '--caller-sha256', args.caller_sha256, '--claim-fd', str(claim_fd),
        '--marker-fd', str(marker_fd), '--directory-fd', str(directory.fd)], safe,
        min(450, remaining(deadline)), input_bytes=raw, stdout_limit=MAX_PRIVATE,
        pass_fds=(claim_fd, marker_fd, directory.fd))
    state['worker_actual'] = _actual(actual)
    directory.write('join-observed.json', {**binding(args), 'observed': state['worker_actual']})
    if actual['actual_exit'] == 2 and len(output) <= MAX_OUTPUT:
        failed = parse(output)
        if (set(failed) == {'binding', 'preflight_failure'} and failed['binding'] == binding(args)
                and _finite_code(failed['preflight_failure'])):
            state['worker_failure_code'] = failed['preflight_failure']
    require(type(actual['actual_exit']) is int and actual['actual_exit'] == 0
        and actual['bound'] is None and actual['spawn_observed'] is True and not errors
        and actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == sha(b''), 'worker_failed')
    require(actual['stdout_bytes'] == len(output) and actual['stdout_sha256'] == sha(output), 'worker_binding')
    checked, private_raw = worker_packet(output, expected)
    directory.verify()
    return checked['summary'], private_raw, actual

def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'local_only': True, 'old_controls_spent': True})
        state = {'stage': 'credentials', 'http_events': [], 'captures': {}, 'status_receipts': {},
            'summary': None, 'worker_actual': None, 'worker_failure_code': None}
        key, buffers = None, {}
        try:
            environment.require_safe_environment()
            key = keychain.load_key('sharadar', timeout_seconds=min(20, remaining(deadline)))
            import requests
            state['stage'] = 'provider'
            def journal(marker, event):
                remaining(deadline); environment.require_safe_environment()
                checked = observation.validate_event(event)
                require(checked['role'] in ROLES and marker == checked['role'].replace('_', '-')
                    + '-' + checked['event'], 'journal')
                values = _events([*state['http_events'], checked])
                directory.write(marker + '.json', {**binding(args), 'observation': checked})
                state['http_events'] = values
            with requests.Session() as session:
                observation.configure_owned_session(session)
                for role, name in zip(ROLES, BODY_NAMES, strict=True):
                    raw = observation._fetch(session, key, role, journal, deadline)
                    # CSV decoded escaping and JSON escaping are checked before
                    # persistence, while semantic compatibility comes afterwards.
                    observation._decoded_secret_guard(raw, key, role)
                    if role.endswith('_status'): status_v2.safe_body(raw, api_key=key)
                    state['captures'][name] = directory.write_bytes(name, raw, private=True)
                    buffers[name] = raw
            # All four secret-checked bounded responses survive a later
            # semantic refusal; this is diagnostic acquisition, not fallback.
            for role, name in zip(ROLES, BODY_NAMES, strict=True):
                raw = buffers[name]
                if role.endswith('_metadata'):
                    observation._metadata(raw, role.split('_')[0], BODY_BOUNDS[BODY_NAMES.index(name)])
                else:
                    state['status_receipts'][role] = status_v2.inspect_body(raw, api_key=key,
                        table=role.split('_')[0])
            state['stage'] = 'worker'
            summary, private_raw, actual = invoke_worker(directory, buffers, args, deadline, state)
            state['worker_actual'] = actual
            state['summary'] = summary
            state['stage'] = 'publication'
            state['captures']['routes-private.json'] = directory.write_bytes(
                'routes-private.json', private_raw, private=True)
            require(state['captures']['routes-private.json'] == {
                'byte_count': summary['private_frame_byte_count'],
                'sha256': summary['private_frame_sha256']}, 'private_binding')
            state['stage'] = 'postflight'
            preflight(args, deadline); environment.require_safe_environment(); directory.verify()
            result = {'schema': SCHEMA, **state, 'post_checks_complete': True,
                'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
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
        finally: key = buffers = None

def _capture_pins(value, *, partial=False):
    require(type(value) is dict and all(type(name) is str for name in value)
        and (set(value) <= set(CAPTURE_NAMES) if partial else set(value) == set(CAPTURE_NAMES)), 'output')
    require(set(value) == set(CAPTURE_NAMES[:len(value)]) if partial else True, 'output')
    for name, pin in value.items():
        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'}
            and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= CAPTURE_BOUNDS[CAPTURE_NAMES.index(name)]
            and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'output')

def validate_result(result):
    require(type(result) is dict and set(result) == {'schema', 'stage', 'http_events', 'captures',
        'status_receipts', 'summary', 'worker_actual', 'worker_failure_code', 'post_checks_complete', 'diagnostic_only',
        'result_cell', *FALSE_FLAGS} and result['schema'] == SCHEMA and result['stage'] == 'postflight'
        and result['post_checks_complete'] is True and result['diagnostic_only'] is True
        and type(result['result_cell']) is int and result['result_cell'] == 0
        and all(result[key] is False for key in FALSE_FLAGS), 'output')
    require(len(_events(result['http_events'])) == 8
        and all(row['http_status'] == 200 for row in result['http_events'][1::2]), 'output')
    _capture_pins(result['captures'])
    require(type(result['status_receipts']) is dict
        and set(result['status_receipts']) == {'stocks_status', 'funds_status'}, 'output')
    for role, receipt in result['status_receipts'].items():
        status_v2.validate_receipt(receipt)
        require(receipt['table'] == role.split('_')[0] and result['captures'][role.replace('_', '-') + '.json']
            == {'byte_count': receipt['body_byte_count'], 'sha256': receipt['body_sha256']}, 'output')
    worker.validate_summary(result['summary'])
    require(result['summary']['current_metadata'] == {table: result['captures'][name]
        for table, name in zip(('stocks', 'funds'), BODY_NAMES[:2], strict=True)}, 'output')
    require(result['captures']['routes-private.json'] == {
        'byte_count': result['summary']['private_frame_byte_count'],
        'sha256': result['summary']['private_frame_sha256']}, 'private_binding')
    _actual(result['worker_actual'])
    require(type(result['worker_actual']['actual_exit']) is int
        and result['worker_actual']['actual_exit'] == 0 and result['worker_actual']['bound'] is None
        and result['worker_actual']['spawn_observed'] is True
        and result['worker_actual']['stderr_bytes'] == 0
        and result['worker_actual']['stderr_sha256'] == sha(b'')
        and result['summary']['private_frame_byte_count'] < result['worker_actual']['stdout_bytes'] <= MAX_PRIVATE
        and result['worker_failure_code'] is None, 'output')

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
        require(type(state) is dict and set(state) == {'stage', 'http_events', 'captures',
            'status_receipts', 'summary', 'worker_actual', 'worker_failure_code'}
            and state['stage'] in ('credentials', 'provider', 'worker', 'publication', 'postflight', 'report'), 'output')
        _events(state['http_events']); _capture_pins(state['captures'], partial=True)
        require(type(state['status_receipts']) is dict
            and set(state['status_receipts']) <= {'stocks_status', 'funds_status'}, 'output')
        for role, receipt in state['status_receipts'].items():
            status_v2.validate_receipt(receipt)
            name = role.replace('_', '-') + '.json'
            require(receipt['table'] == role.split('_')[0] and state['captures'].get(name)
                == {'byte_count': receipt['body_byte_count'], 'sha256': receipt['body_sha256']}, 'output')
        for index, name in enumerate(BODY_NAMES):
            if name in state['captures']:
                require(len(state['http_events']) >= 2 * (index + 1)
                    and all(event['http_status'] == 200 for event in
                        state['http_events'][1:2 * (index + 1):2]), 'output')
        if state['stage'] == 'credentials':
            require(not state['http_events'] and not state['captures'] and not state['status_receipts']
                and state['summary'] is None and state['worker_actual'] is None
                and state['worker_failure_code'] is None, 'output')
        if state['stage'] == 'provider':
            require(state['summary'] is None and state['worker_actual'] is None
                and state['worker_failure_code'] is None and 'routes-private.json' not in state['captures'], 'output')
        if state['stage'] in ('worker', 'publication', 'postflight', 'report'):
            require(len(state['http_events']) == 8 and all(event['http_status'] == 200
                for event in state['http_events'][1::2]) and set(BODY_NAMES) <= set(state['captures']), 'output')
        if state['summary'] is not None:
            worker.validate_summary(state['summary'])
            require(state['summary']['current_metadata'] == {table: state['captures'].get(name)
                for table, name in zip(('stocks', 'funds'), BODY_NAMES[:2], strict=True)}, 'output')
            if 'routes-private.json' in state['captures']:
                require(state['captures']['routes-private.json'] == {
                    'byte_count': state['summary']['private_frame_byte_count'],
                    'sha256': state['summary']['private_frame_sha256']}, 'private_binding')
        if state['worker_actual'] is not None: _actual(state['worker_actual'])
        require(state['worker_failure_code'] is None or _finite_code(state['worker_failure_code']), 'output')
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
        runtime = Path(tempfile.mkdtemp(prefix='r326-z-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        raw, errors, actual = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            safe, 930, stdout_limit=MAX_OUTPUT)
        outer['parent'] = actual
        require(type(actual['actual_exit']) is int and actual['actual_exit'] in (0, 2)
            and actual['bound'] is None and not errors, 'parent_failed')
        valid, errors, checked = capture(['/usr/bin/sandbox-exec', '-p', native_profile(),
            str(PYTHON), '-B', str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(actual['actual_exit'])],
            safe, 20, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = checked
        require(type(checked['actual_exit']) is int and checked['actual_exit'] == 0
            and checked['bound'] is None and not errors, 'validator_failed')
        outer['output'] = parse(valid)
        outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OBSERVER_OUTPUT, 'output_bound')
        return outer, actual['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error)
        return outer, 2

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'validate', 'worker'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--actual-exit', type=int)
    for name in ('claim-fd', 'marker-fd', 'directory-fd'): parser.add_argument('--' + name, type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        result, code = observe(args)
        sys.stdout.buffer.write(canonical(result))
        return code
    deadline = time.monotonic() + (20 if args.operation == 'validate' else
        450 if args.operation == 'worker' else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline); environment._bootstrap_cli_logging()
            if args.operation == 'worker':
                result = run_worker(args, deadline)
                raw = canonical(result)
                require(len(raw) <= MAX_PRIVATE, 'output_bound')
                sys.stdout.buffer.write(raw)
                return 0
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
        # A worker failure emits only a finite code. No private frame survives
        # as stdout on a nonzero/ambiguous terminal path.
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2

if __name__ == '__main__': raise SystemExit(main())
