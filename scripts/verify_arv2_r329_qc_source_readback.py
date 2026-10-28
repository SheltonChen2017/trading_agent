"""One separately frozen, named-file QC public-source readback, never a launch.

The stdlib supervisor precedes repository imports. Its one child has no credential
environment, consumes inherited intent/credential pipes, and owns one exclusive
claim. HTTP content is compared in memory and never retained or emitted.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import http.client
from importlib.machinery import PathFinder
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'scripts/verify_arv2_r329_qc_source_readback.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_available_history_native_coverage_source/R329-20261028-D'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r329-named-QC-public-source-readback-v1'
STAGE_SHA256 = '652a46b6b0db83f50cf042e1b374b9beed3192d897e5886557e48cf25a75193e'
AUTH_SOURCE_SHA256 = '7a12fdb68194ee10f6e8c3d7c0fc49c08b34166d056bd5ea2a72937dd03be373'
HOST, PORT, ENDPOINT, PROJECT = 'www.quantconnect.com', 443, '/api/v2/files/read', 38522505
CA_PATH = Path('/Users/sheltonchen/.venvs/trading_agent-py313/lib/python3.13/site-packages/certifi/cacert.pem')
CA_SIZE, CA_SHA256 = 240216, '9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f'
SECONDS, DNS_SECONDS, HTTP_SECONDS = 210, 5, 15
MAX_OUTPUT, MAX_BODY, MAX_SECRET = 40000, 1024 * 1024, 4096
ENTRY_DEADLINE = time.monotonic() + SECONDS
CREDENTIALS = ('QC_USER_ID', 'QC_API_TOKEN')


class Refused(ValueError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def parse(raw, maximum=MAX_OUTPUT):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'bound')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'response')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('response')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('response') from None


def remaining(deadline):
    value = deadline - time.monotonic()
    require(type(deadline) in (int, float) and math.isfinite(value) and 0 < value <= SECONDS, 'deadline')
    return value


def arguments(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{64}', getattr(args, key))
            for key in ('caller_sha256', 'profile_sha256')), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}


def credentials(values):
    require(type(values) is dict and set(values) == set(CREDENTIALS), 'credentials')
    user, token = (values[name] for name in CREDENTIALS)
    require(type(user) is str and user.isascii() and user.isdecimal() and 0 < int(user) < 2**63
        and type(token) is str and 8 <= len(token) <= 1024 and all(33 <= ord(c) <= 126 for c in token), 'credentials')
    return values


def environment(*, secret=False):
    allowed = {'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD', '__CF_USER_TEXT_ENCODING'} | (set(CREDENTIALS) if secret else set())
    require(set(os.environ) <= allowed and os.environ.get('PATH') == '/usr/bin:/bin:/usr/sbin:/sbin'
        and os.environ.get('LC_ALL') == 'C' and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'
        and os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') == '1', 'environment')
    for key in ('TMPDIR', 'PYTHONPYCACHEPREFIX'):
        path = Path(os.environ.get(key, ''))
        require(path.is_absolute() and ROOT / '.pytest_cache' in path.parents and path.resolve() == path, 'environment')
    require(http.client.HTTPConnection.debuglevel == 0 and http.client.HTTPSConnection.debuglevel == 0, 'environment')
    return {key: value for key, value in os.environ.items() if key not in CREDENTIALS}


def native_profile():
    value = '(version 1)(allow default)(deny network-bind)(deny network-inbound)'
    value += '(deny network-outbound (require-all (require-not (remote tcp "*:443"))(require-not (remote tcp "*:53"))(require-not (remote udp "*:53"))(require-not (literal "/private/var/run/mDNSResponder"))))'
    value += ''.join('(deny file-read* file-write* (subpath "' + path + '"))'
        for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath "' + str(CONTROL) + '"))'
    value += '(require-not (literal "' + str(CONTROL.parent) + '"))(require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))(require-not (literal "/dev/null"))))'
    ancestors = [path for path in CONTROL.parents if path == ROOT / 'artifacts' or ROOT / 'artifacts' in path.parents]
    value += '(deny file-read* (require-all (subpath "' + str(ROOT / 'artifacts') + '")(require-not (subpath "' + str(CONTROL) + '"))'
    value += ''.join('(require-not (literal "' + str(path) + '"))' for path in ancestors) + '))'
    return value


def public_preflight(args, deadline):
    arguments(args)
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and sys.executable == PYTHON and Path(__file__).absolute() == SOURCE
        and sys.flags.isolated == 1, 'host')
    safe = environment(secret=args.mode == 'run')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT,
            env={**safe, 'GIT_OPTIONAL_LOCKS': '0'}, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=min(15, remaining(deadline)), check=False)
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144
            and result.stdout.decode('ascii').strip() == expected, 'git_state')
    fd = os.open(SOURCE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= 131072, 'source_pin')
        raw = os.pread(fd, 131073, 0)
        require(len(raw) == before.st_size and sha(raw) == args.caller_sha256 and os.fstat(fd) == before
            and SOURCE.stat(follow_symlinks=False) == before, 'source_pin')
    finally:
        os.close(fd)
    result = subprocess.run(['/usr/bin/git', 'cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
        cwd=ROOT, env={**safe, 'GIT_OPTIONAL_LOCKS': '0'}, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=min(15, remaining(deadline)), check=False)
    require(result.returncode == 0 and not result.stderr and 0 < len(result.stdout) <= 131072
        and sha(result.stdout) == args.caller_sha256, 'source_pin')
    return safe


def capture(command, safe, inherited, deadline):
    child, raw, status, exit_code = None, bytearray(), 'unknown', None
    try:
        child = subprocess.Popen(command, cwd=ROOT, env=safe, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True, pass_fds=inherited)
        with selectors.DefaultSelector() as selected:
            for pipe, label in ((child.stdout, 'stdout'), (child.stderr, 'stderr')):
                os.set_blocking(pipe.fileno(), False)
                selected.register(pipe, selectors.EVENT_READ, label)
            while selected.get_map() or child.poll() is None:
                for key, _ in selected.select(min(.1, remaining(deadline))):
                    data = os.read(key.fileobj.fileno(), 8192)
                    if not data:
                        selected.unregister(key.fileobj)
                    else:
                        require(key.data == 'stdout', 'child_stderr')
                        require(len(raw) + len(data) <= MAX_OUTPUT, 'bound')
                        raw.extend(data)
            exit_code = child.wait(timeout=min(1, remaining(deadline)))
            status = 'returned'
    except BaseException as error:
        status = finite(error)
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            try:
                exit_code = child.wait(timeout=5)
            except BaseException:
                status, exit_code = 'reap_ambiguous', None
            for pipe in (child.stdout, child.stderr):
                if pipe:
                    pipe.close()
    return bytes(raw), {'status': status, 'actual_exit': exit_code, 'stdout': pin(bytes(raw))}


def _pipe(raw):
    reader, writer = os.pipe()
    try:
        require(0 < len(raw) <= os.fpathconf(writer, 'PC_PIPE_BUF'), 'inherited')
        require(os.write(writer, raw) == len(raw), 'inherited')
    except BaseException:
        os.close(reader)
        raise
    finally:
        os.close(writer)
    return reader


def supervise(args, deadline):
    safe = public_preflight(args, deadline)
    secret = canonical(credentials({key: os.environ.get(key) for key in CREDENTIALS}))
    intent = canonical({'binding': arguments(args), 'purpose': 'one_named_source_readback_worker'})
    readers = []
    try:
        readers.append(_pipe(intent)); readers.append(_pipe(secret)); secret = None
        command = ['/usr/bin/sandbox-exec', '-p', native_profile(), PYTHON, '-I', '-B', str(SOURCE), 'worker',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
            '--profile-sha256', args.profile_sha256, '--intent-fd', str(readers[0]), '--credential-fd', str(readers[1]),
            '--outer-deadline', repr(deadline)]
        raw, actual = capture(command, safe, tuple(readers), deadline)
        envelope = None
        if actual['status'] == 'returned' and type(actual['actual_exit']) is int and actual['actual_exit'] in (0, 2):
            require(raw.endswith(b'\n') and raw.count(b'\n') == 1, 'output')
            envelope = parse(raw[:-1]); require(canonical(envelope) + b'\n' == raw, 'output')
            require(type(envelope) is dict and envelope.get('binding') == arguments(args)
                and set(envelope) in ({'binding', 'result', 'report_pin'}, {'binding', 'failure_code', 'claim_consumed', 'allocation_unknown'}), 'output')
        return {'binding': arguments(args), 'child_actual': actual, 'child_envelope': envelope,
            'child_output_accepted': False, 'attempt_reusable': False}
    finally:
        for fd in readers:
            os.close(fd)


FINITE = frozenset(('arguments', 'host', 'environment', 'git_state', 'source_pin', 'source_changed', 'source_bound',
    'security', 'projection', 'deadline', 'bound', 'credentials', 'inherited', 'dns', 'CA', 'transport', 'http_status',
    'response', 'source_mismatch', 'claim_spent', 'output_changed', 'output_write', 'output', 'child_stderr', 'unknown'))


def finite(error):
    if type(error) is Refused:
        values = BaseException.args.__get__(error)
        if len(values) == 1 and type(values[0]) is str and values[0] in FINITE:
            return values[0]
    if isinstance(error, TimeoutError):
        return 'deadline'
    return 'unknown'


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('arguments')


def cli():
    parser = Parser(add_help=False)
    parser.add_argument('mode', choices=('launch', 'run', 'worker', 'validate'))
    for name in ('expected-head', 'caller-sha256', 'profile-sha256'):
        parser.add_argument('--' + name, required=True)
    for name in ('intent-fd', 'credential-fd'):
        parser.add_argument('--' + name, type=int)
    parser.add_argument('--outer-deadline', type=float)
    parser.add_argument('--actual-parent-exit', type=int)
    return parser.parse_args()


def launch(args):
    arguments(args)
    require(args.mode == 'launch' and args.intent_fd is args.credential_fd is args.outer_deadline is args.actual_parent_exit is None, 'arguments')
    require(Path.cwd() == ROOT and sys.platform == 'darwin' and sys.version_info[:2] == (3, 13)
        and sys.executable == PYTHON and Path(__file__).absolute() == SOURCE and sys.flags.isolated == 1
        and sys.dont_write_bytecode is True, 'host')
    fd = os.open(SOURCE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
            and 0 < info.st_size <= 131072, 'source_pin')
        raw = os.pread(fd, 131073, 0)
        require(sha(raw) == args.caller_sha256 and len(raw) == info.st_size
            and os.fstat(fd) == info and SOURCE.stat(follow_symlinks=False) == info, 'source_pin')
    finally:
        os.close(fd)
    secret = credentials({name: os.environ.get(name) for name in CREDENTIALS})
    support = Path(tempfile.mkdtemp(prefix='r329-d-', dir=ROOT / '.pytest_cache'))
    safe = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', **secret}
    remaining(ENTRY_DEADLINE)
    os.execve(PYTHON, [PYTHON, '-I', '-B', str(SOURCE), 'run', '--expected-head', args.expected_head,
        '--caller-sha256', args.caller_sha256, '--profile-sha256', args.profile_sha256,
        '--outer-deadline', repr(ENTRY_DEADLINE)], safe)


# The actual parent takes this branch before any repository module import.
if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] in ('launch', 'run'):
    try:
        parent_args = cli()
        if parent_args.mode == 'launch':
            launch(parent_args)
        require(parent_args.outer_deadline is not None, 'arguments')
        parent_deadline = min(ENTRY_DEADLINE, parent_args.outer_deadline)
        remaining(parent_deadline)
        require(parent_args.intent_fd is parent_args.credential_fd is parent_args.actual_parent_exit is None, 'arguments')
        value = supervise(parent_args, parent_deadline)
        raw_output = canonical(value) + b'\n'; require(len(raw_output) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(raw_output)
        raise SystemExit(0 if value['child_actual']['status'] == 'returned' else 2)
    except SystemExit:
        raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'failure_code': finite(error), 'attempt_reusable': False}) + b'\n')
        raise SystemExit(2)


# Offline validation has no producer/secret/control path; bound its import and stdin phase.
if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'validate':
    ENTRY_DEADLINE = time.monotonic() + 30
    def _validation_expired(*_):
        raise Refused('deadline')
    signal.signal(signal.SIGALRM, _validation_expired)
    signal.setitimer(signal.ITIMER_REAL, 30)


def _bootstrap_stage():
    """Bind this one import before execution; its own bootstrap binds closure."""
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags')
    def record(info):
        return tuple(getattr(info, key, None) for key in fields)
    path = ROOT / 'scripts/prepare_arv2_r329_native_coverage_source.py'
    opened, rows = [], []
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened.append(fd)
        for part in path.parts[1:-1]:
            before = record(os.stat(part, dir_fd=fd, follow_symlinks=False))
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            opened.append(child)
            if record(os.fstat(child)) != before or not stat.S_ISDIR(before[2]):
                raise RuntimeError('public_bootstrap')
            rows.append((fd, part, child, before))
            fd = child
        before = record(os.stat(path.name, dir_fd=fd, follow_symlinks=False))
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        opened.append(leaf)
        if not stat.S_ISREG(before[2]) or before[3] != os.getuid() or before[5] != 1 \
                or not 0 < before[6] <= 131072 or record(os.fstat(leaf)) != before:
            raise RuntimeError('public_bootstrap')
        raw = os.pread(leaf, 131073, 0)
        if len(raw) != before[6] or hashlib.sha256(raw).hexdigest() != STAGE_SHA256 \
                or record(os.fstat(leaf)) != before \
                or record(os.stat(path.name, dir_fd=fd, follow_symlinks=False)) != before:
            raise RuntimeError('public_bootstrap')
        for parent, name, child, before in rows:
            if record(os.fstat(child)) != before or record(os.stat(name, dir_fd=parent, follow_symlinks=False)) != before:
                raise RuntimeError('public_bootstrap')
        leaf_metadata = record(os.fstat(leaf))
    finally:
        for fd in reversed(opened):
            os.close(fd)
    sys.path[:] = [str(ROOT), *(item for item in sys.path if item and Path(item).is_absolute()
        and Path(item) != ROOT and ROOT not in Path(item).parents)]
    spec = PathFinder.find_spec('scripts', sys.path)
    if spec is None or spec.origin is not None or tuple(spec.submodule_search_locations) != (str(ROOT / 'scripts'),):
        raise RuntimeError('public_bootstrap')
    if 'scripts' in sys.modules and tuple(sys.modules['scripts'].__path__) != (str(ROOT / 'scripts'),):
        raise RuntimeError('public_bootstrap')
    name = 'scripts.prepare_arv2_r329_native_coverage_source'
    spec = PathFinder.find_spec(name, [str(ROOT / 'scripts')])
    if spec is None or spec.origin != str(path) or time.monotonic() >= ENTRY_DEADLINE:
        raise RuntimeError('public_bootstrap')
    if name in sys.modules and (__name__ == '__main__' or getattr(sys.modules[name], '__file__', None) != str(path)):
        raise RuntimeError('public_bootstrap')
    return leaf_metadata


try:
    BOOTSTRAP_STAGE_METADATA = _bootstrap_stage()
except BaseException:
    if __name__ == '__main__':
        sys.stdout.buffer.write(b'{"failure_code":"public_bootstrap"}\n')
        raise SystemExit(2)
    raise RuntimeError('public_bootstrap') from None

from scripts import prepare_arv2_r329_native_coverage_source as stage


projection, security = stage.projection, stage.security
FALSE_FLAGS = {'source_absence_of_extras_proven': False, 'atomic_cloud_snapshot_proven': False,
    'current_owner_idle_proven': False, 'QC_write': False, 'compile_created': False, 'backtest_created': False,
    'licensed_data_read': False, 'private_source_DATA_read': False, 'source_content_retained': False,
    'credential_retained': False, 'physical_request_count_measured': False, 'new_launch_attempt_granted': False,
    'price_coverage_admitted': False, 'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False}
FILES = ('claim.json', 'worker-started.json', 'request-intents.jsonl', 'worker-result.json', 'report.json', 'failure.json')


def selected_plan():
    return {**stage.public_plan(), 'scripts/prepare_arv2_r329_native_coverage_source.py': STAGE_SHA256,
        'research/quantconnect.py': AUTH_SOURCE_SHA256}


def profile_record():
    return {'schema': SCHEMA, 'project_id': PROJECT, 'endpoint': ENDPOINT, 'names': list(projection.CLOUD_NAMES),
        'source_plan': selected_plan(), 'projection_pin': stage.EXPECTED_PROJECTION_PIN,
        'projection_profile_pin': stage.EXPECTED_PROFILE_PIN, 'maximum_application_dispatches': 11,
        'maximum_seconds': SECONDS, 'operation_seconds': 180, 'offline_validator_seconds': 30, 'DNS_seconds': DNS_SECONDS, 'HTTP_seconds': HTTP_SECONDS,
        'maximum_body_bytes': MAX_BODY, 'maximum_output_bytes': MAX_OUTPUT,
        'CA': {'path': str(CA_PATH), 'byte_count': CA_SIZE, 'sha256': CA_SHA256},
        'native_policy_sha256': sha(native_profile().encode('ascii')),
        'DNS': 'one_public_preclaim_lookup_first_global_supported_address_no_fallback',
        'credential_handoff': 'parent_shape_before_dispatch_owned_pipes_child_no_env_credentials',
        'auth_recipe': 'sha256(token:integer_timestamp)_basic(user_id:hex_digest)_Timestamp_header',
        'control': CONTROL.relative_to(ROOT).as_posix(), 'normal_control_files': list(FILES[:-1]),
        'metadata_only': True, 'ordinary_isolated_parent_independent_native_worker_no_nested_sandbox': True, 'preclaim_spent_leaf_metadata_check': True, 'port_policy_is_domain_fence': False, **FALSE_FLAGS}


def binding(args):
    value = arguments(args)
    require(value['profile_sha256'] == sha(canonical(profile_record())), 'source_pin')
    return value


@contextmanager
def alarm(seconds):
    require(type(seconds) in (int, float) and 0 < seconds <= SECONDS, 'deadline')
    def expired(*_):
        raise Refused('deadline')
    old = signal.getsignal(signal.SIGALRM)
    timer = signal.getitimer(signal.ITIMER_REAL)
    require(timer == (0.0, 0.0), 'deadline')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def address_row(family, address):
    require(type(family) is int and family in (int(socket.AF_INET), int(socket.AF_INET6))
        and type(address) in (tuple, list) and len(address) == (2 if family == socket.AF_INET else 4), 'dns')
    require(type(address[0]) is str and type(address[1]) is int and address[1] == PORT, 'dns')
    try:
        ip = ipaddress.ip_address(address[0])
    except ValueError:
        raise Refused('dns') from None
    require(ip.is_global and ip.version == (4 if family == socket.AF_INET else 6), 'dns')
    if family == socket.AF_INET6:
        require(all(type(value) is int and value == 0 for value in address[2:]), 'dns')
    return {'family': family, 'address': list(address)}


def resolver(deadline):
    try:
        with alarm(min(DNS_SECONDS, remaining(deadline))):
            rows = socket.getaddrinfo(HOST, PORT, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    except Refused:
        raise
    except BaseException:
        raise Refused('dns') from None
    require(type(rows) is list and 0 < len(rows) <= 64, 'dns')
    normalized, chosen = [], None
    for row in rows:
        require(type(row) is tuple and len(row) == 5 and row[1] == socket.SOCK_STREAM
            and row[2] == socket.IPPROTO_TCP and type(row[3]) is str and len(row[3]) <= 253, 'dns')
        require(row[0] in (socket.AF_INET, socket.AF_INET6), 'dns')
        item = address_row(int(row[0]), row[4])
        normalized.append(item)
        if chosen is None:
            chosen = item
    return chosen, {'answer_count': len(normalized), 'ordered_answers_sha256': sha(canonical(normalized)),
        'selected_address_sha256': sha(canonical(chosen)), 'family': chosen['family']}


def read_pipe(fd, maximum):
    require(type(fd) is int and fd > 2, 'inherited')
    info = os.fstat(fd)
    require(stat.S_ISFIFO(info.st_mode) and info.st_uid == os.getuid(), 'inherited')
    os.set_blocking(fd, False)
    try:
        raw = os.read(fd, maximum + 1)
        require(0 < len(raw) <= maximum and os.read(fd, 1) == b'', 'inherited')
    except (BlockingIOError, OSError):
        raise Refused('inherited') from None
    finally:
        os.close(fd)
    value = parse(raw, maximum)
    require(canonical(value) == raw, 'inherited')
    return value


class CA:
    """Fixed external public CA exception; original ancestor/leaf descriptors.

    All ancestor metadata is held/named; native ACL/xattr checks cover only
    the CA leaf and its immediate parent. No arbitrary external path exists.
    """
    def __init__(self):
        self.rows, self.fd = [], None
        try:
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.rows.append({'fd': fd, 'parent': fd, 'name': '.', 'metadata': stage.metadata(fd)})
            for part in CA_PATH.parts[1:-1]:
                before = stage.named(fd, part)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                self.rows.append({'fd': child, 'parent': fd, 'name': part, 'metadata': before})
                require(stat.S_ISDIR(before[2]) and stage.metadata(child) == before, 'CA')
                fd = child
            self.parent = fd
            self.parent_security = stage._security(fd)
            before = stage.named(fd, CA_PATH.name)
            self.fd = os.open(CA_PATH.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            require(stage._regular(before, private=False) and before[6] == CA_SIZE
                and stage.metadata(self.fd) == before, 'CA')
            self.metadata, self.security = before, stage._security(self.fd)
            self.raw = os.pread(self.fd, CA_SIZE + 1, 0)
            require(len(self.raw) == CA_SIZE and sha(self.raw) == CA_SHA256, 'CA')
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        for row in self.rows:
            require(stage.metadata(row['fd']) == row['metadata'] == stage.named(row['parent'], row['name']), 'CA')
        require(stage._security(self.parent) == self.parent_security
            and stage.metadata(self.fd) == self.metadata == stage.named(self.parent, CA_PATH.name)
            and stage._security(self.fd) == self.security, 'CA')

    def close(self):
        if self.fd is not None:
            os.close(self.fd); self.fd = None
        for row in reversed(self.rows):
            os.close(row['fd'])
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.verify()
        finally:
            self.close()


class Store:
    def __init__(self):
        self.guard = stage.DirectoryGuard(CONTROL, create=True, control=CONTROL)
        self.fd, self.files, self.failed = self.guard.fd, {}, False

    def verify(self):
        self.guard.verify()
        require(set(os.listdir(self.fd)) == set(self.files), 'output_changed')
        for name, row in self.files.items():
            require(stage.metadata(row['fd']) == row['metadata'] == stage.named(self.fd, name)
                and stage._regular(row['metadata'], private=True) and stage._security(row['fd']) == row['security'], 'output_changed')

    def create(self, name, raw):
        require(name in FILES and name not in self.files and type(raw) is bytes and len(raw) <= MAX_OUTPUT, 'output')
        self.verify()
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        initial = stage.metadata(fd)
        row = {'fd': fd, 'metadata': initial, 'security': stage._security(fd), 'parent': self.fd, 'name': name}
        try:
            require(initial[6] == 0 and initial == stage.named(self.fd, name), 'output_changed')
            self.guard.own_created(self.guard.rows[-1], row, directory=False)
            self.files[name] = row
            os.fsync(self.fd)
            if raw:
                self.append(name, raw)
            self.verify()
            return pin(raw)
        except BaseException:
            if name not in self.files:
                os.close(fd)
            raise

    def append(self, name, raw):
        self.verify()
        require(name in self.files and type(raw) is bytes and raw, 'output')
        row, old = self.files[name], self.files[name]['metadata']
        require(old[6] + len(raw) <= MAX_OUTPUT and (old[6] == 0 or name == 'request-intents.jsonl'), 'output')
        os.lseek(row['fd'], 0, os.SEEK_END)
        view = memoryview(raw)
        while view:
            count = os.write(row['fd'], view[:65536])
            require(type(count) is int and count > 0, 'output_write')
            view = view[count:]
        os.fsync(row['fd'])
        current = stage.metadata(row['fd'])
        require(current[:6] == old[:6] and current[9] == old[9] and current[6] == old[6] + len(raw)
            and stage._security(row['fd']) == row['security'], 'output_changed')
        row['metadata'] = current
        require(os.pread(row['fd'], len(raw), old[6]) == raw, 'output_write')
        self.verify()

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        try:
            if kind is None and not self.failed:
                self.verify()
        finally:
            for row in self.files.values():
                os.close(row['fd'])
            self.files = {}
            self.guard.close()


def auth_headers(secret, timestamp):
    credentials(secret)
    require(type(timestamp) is int and timestamp > 0, 'credentials')
    digest = sha((secret['QC_API_TOKEN'] + ':' + str(timestamp)).encode('ascii'))
    encoded = base64.b64encode((secret['QC_USER_ID'] + ':' + digest).encode('ascii')).decode('ascii')
    return {'Authorization': 'Basic ' + encoded, 'Timestamp': str(timestamp)}


def request_parts(name, secret, timestamp):
    require(type(name) is str and name in projection.CLOUD_NAMES, 'response')
    body = canonical({'projectId': PROJECT, 'name': name})
    headers = {'Host': HOST, 'Content-Type': 'application/json', 'Content-Length': str(len(body)),
        'Accept-Encoding': 'identity', 'Connection': 'close', **auth_headers(secret, timestamp)}
    return body, headers


def exact_file(packet, name, expected):
    require(type(packet) is dict and set(packet) <= {'success', 'files', 'errors', 'messages'}
        and packet.get('success') is True and ('errors' not in packet or packet['errors'] == []), 'response')
    if 'messages' in packet:
        require(type(packet['messages']) is list and len(packet['messages']) <= 16
            and all(type(item) is str and len(item) <= 1024 for item in packet['messages']), 'response')
    rows = packet.get('files')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'response')
    row = rows[0]
    require(set(row) <= {'id', 'projectId', 'name', 'content', 'modified', 'open', 'isLibrary'}
        and type(row.get('projectId')) is int and row['projectId'] == PROJECT and row.get('name') == name
        and type(row.get('content')) is str and len(row['content']) <= len(expected), 'response')
    if 'isLibrary' in row:
        require(row['isLibrary'] is False, 'response')
    if 'id' in row:
        require(row['id'] is None or type(row['id']) is int and row['id'] >= 0, 'response')
    if 'open' in row:
        require(type(row['open']) is bool, 'response')
    if 'modified' in row:
        require(type(row['modified']) is str and 0 < len(row['modified']) <= 64 and row['modified'].isascii(), 'response')
    try:
        raw = row['content'].encode('utf-8')
    except UnicodeError:
        raise Refused('response') from None
    require(raw == expected, 'source_mismatch')
    return {'name': name, **pin(raw)}


def fetch(name, expected, secret, selected, ca, entry, deadline):
    require(address_row(selected['family'], selected['address']) == selected, 'dns')
    body, headers = request_parts(name, secret, int(time.time()))
    require(entry['request_sha256'] == sha(body) and entry['name'] == name, 'response')
    tcp, secured, connection = None, None, None
    try:
        with alarm(min(HTTP_SECONDS, remaining(deadline))):
            ca.verify()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = True; context.verify_mode = ssl.CERT_REQUIRED
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_verify_locations(cadata=ca.raw.decode('ascii'))
            tcp = socket.socket(selected['family'], socket.SOCK_STREAM, socket.IPPROTO_TCP)
            tcp.settimeout(min(HTTP_SECONDS, remaining(deadline)))
            tcp.connect(tuple(selected['address']))
            secured = context.wrap_socket(tcp, server_hostname=HOST)
            require(secured.version() in ('TLSv1.2', 'TLSv1.3'), 'transport')
            connection = http.client.HTTPConnection(HOST, PORT, timeout=min(HTTP_SECONDS, remaining(deadline)))
            connection.auto_open = 0; connection.sock = secured
            require(http.client.HTTPConnection.debuglevel == connection.debuglevel == 0, 'environment')
            entry['application_dispatch_attempted'] = True
            connection.request('POST', ENDPOINT, body=body, headers=headers)
            response = connection.getresponse()
            require(type(response.status) is int and 100 <= response.status <= 599, 'http_status')
            entry['http_status'] = response.status
            require(response.status == 200, 'http_status')
            require(response.getheader('Set-Cookie') is None and response.getheader('Content-Encoding', 'identity').lower() == 'identity', 'response')
            length = response.getheader('Content-Length')
            require(length is None or length.isdecimal() and len(length) <= 10 and 0 < int(length) <= MAX_BODY, 'bound')
            raw = bytearray()
            while True:
                part = response.read(min(65536, MAX_BODY - len(raw) + 1))
                if not part:
                    break
                require(type(part) is bytes and len(raw) + len(part) <= MAX_BODY, 'bound')
                raw.extend(part)
                remaining(deadline)
            require(raw and (length is None or len(raw) == int(length)), 'response')
            result = exact_file(parse(bytes(raw), MAX_BODY), name, expected)
            ca.verify()
            return result
    except Refused:
        raise
    except BaseException:
        raise Refused('transport') from None
    finally:
        if connection is not None:
            connection.close()
        else:
            for stream in (secured, tcp):
                if stream is not None:
                    stream.close()


def initial_state():
    return {'complete': False, 'failure_code': None, 'intent_count': 0, 'application_dispatch_count': 0,
        'entries': [], 'source_files': [], **FALSE_FLAGS}


def sequence(store, expected, secret, selected, ca, deadline):
    state = initial_state()
    for ordinal, name in enumerate(projection.CLOUD_NAMES):
        entry = {'ordinal': ordinal, 'name': name,
            'request_sha256': sha(canonical({'projectId': PROJECT, 'name': name})),
            'application_dispatch_attempted': False, 'http_status': None}
        state['entries'].append(entry)
        try:
            store.append('request-intents.jsonl', canonical({key: entry[key]
                for key in ('ordinal', 'name', 'request_sha256')}) + b'\n')
            state['intent_count'] += 1
            state['source_files'].append(fetch(name, expected[name], secret, selected, ca, entry, deadline))
        except BaseException as error:
            state['failure_code'] = finite(error)
            break
        finally:
            state['application_dispatch_count'] = sum(row['application_dispatch_attempted'] for row in state['entries'])
    state['complete'] = len(state['source_files']) == 11 and state['failure_code'] is None
    return state


def validate_state(value):
    require(type(value) is dict and set(value) == {'complete', 'failure_code', 'intent_count',
        'application_dispatch_count', 'entries', 'source_files', *FALSE_FLAGS}
        and type(value['complete']) is bool and all(value[key] is False for key in FALSE_FLAGS), 'output')
    rows, sources = value['entries'], value['source_files']
    require(type(rows) is list and type(sources) is list and 0 <= len(sources) <= len(rows) <= 11
        and type(value['intent_count']) is int and 0 <= value['intent_count'] <= len(rows)
        and type(value['application_dispatch_count']) is int and all(type(row) is dict for row in rows)
        and value['application_dispatch_count'] == sum(row.get('application_dispatch_attempted') is True for row in rows), 'output')
    for ordinal, row in enumerate(rows):
        require(type(row) is dict and set(row) == {'ordinal', 'name', 'request_sha256', 'application_dispatch_attempted', 'http_status'}
            and type(row['ordinal']) is int and row['ordinal'] == ordinal and row['name'] == projection.CLOUD_NAMES[ordinal]
            and row['request_sha256'] == sha(canonical({'projectId': PROJECT, 'name': row['name']}))
            and type(row['application_dispatch_attempted']) is bool
            and (row['http_status'] is None or type(row['http_status']) is int and 100 <= row['http_status'] <= 599), 'output')
        if row['http_status'] is not None:
            require(row['application_dispatch_attempted'], 'output')
    expected = {**projection.CLOUD_DEPENDENCY_PINS,
        'main.py': '6f59864e930fba4c2ebc3ca16622b50fe859bb3ae1d793e0bc96b44a4794e298'}
    for ordinal, row in enumerate(sources):
        require(type(row) is dict and set(row) == {'name', 'byte_count', 'sha256'}
            and row['name'] == projection.CLOUD_NAMES[ordinal] and row['sha256'] == expected[row['name']]
            and type(row['byte_count']) is int and 0 < row['byte_count'] <= projection.MAX_CLOUD_FILE_BYTES
            and rows[ordinal]['http_status'] == 200, 'output')
    if value['complete']:
        require(value['failure_code'] is None and len(sources) == value['intent_count'] == value['application_dispatch_count'] == 11
            and sum(row['byte_count'] for row in sources) == 239149, 'output')
    else:
        require(value['failure_code'] in FINITE, 'output')
    return value


def require_unclaimed():
    # No census/content read: refuse an existing/partial own leaf before DNS.
    with stage.DirectoryGuard(CONTROL.parent, control=CONTROL) as held:
        try:
            os.stat(CONTROL.name, dir_fd=held.fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise Refused('claim_spent')


def operation_deadline(outer):
    remaining(outer)
    return min(outer, time.monotonic() + 180)


def produce(args, deadline):
    deadline = operation_deadline(deadline)
    binding(args); public_preflight(args, deadline)
    require(type(args.intent_fd) is int and type(args.credential_fd) is int and args.intent_fd != args.credential_fd, 'inherited')
    intent = read_pipe(args.intent_fd, MAX_SECRET)
    require(intent == {'binding': binding(args), 'purpose': 'one_named_source_readback_worker'}, 'inherited')
    plan = {**selected_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}
    with stage.PublicSources(plan, deadline) as sources:
        require(sources.files[stage.SOURCE.relative_to(ROOT).as_posix()]['metadata'] == BOOTSTRAP_STAGE_METADATA, 'source_changed')
        require(all(sources.files[name]['metadata'] == original
            for name, original in stage.BOOTSTRAP_METADATA.items()), 'source_changed')
        by_name = {Path(name).name: raw for name, raw in sources.raw.items()}
        generated = projection.generate(project_id=PROJECT, sources={name: by_name[name] for name in projection.SOURCE_PINS},
            generator_source_bytes=by_name[projection.PATCHER_NAME], expected_generator_sha256=stage.GENERATOR_SHA256)
        require(pin(generated.record_bytes) == stage.EXPECTED_PROJECTION_PIN
            and pin(generated.profile_bytes) == stage.EXPECTED_PROFILE_PIN, 'projection')
        require_unclaimed()
        selected, dns = resolver(deadline)
        secret = credentials(read_pipe(args.credential_fd, MAX_SECRET))
        sources.verify()
        with CA() as ca:
            with Store() as store:
                store.create('claim.json', canonical({'binding': binding(args), 'dns': dns,
                    'projection_pin': stage.EXPECTED_PROJECTION_PIN}))
                try:
                    store.create('worker-started.json', canonical(binding(args)))
                    store.create('request-intents.jsonl', b'')
                    state = validate_state(sequence(store, dict(generated.source_pairs), secret, selected, ca, deadline))
                    secret.clear(); secret = None
                    store.create('worker-result.json', canonical(state))
                    public_preflight(args, deadline); ca.verify(); sources.verify(); store.verify()
                    result = {'schema': SCHEMA, 'project_id': PROJECT, 'dns': dns, 'state': state,
                        'projection_pin': stage.EXPECTED_PROJECTION_PIN, 'profile_pin': stage.EXPECTED_PROFILE_PIN,
                        'projection_record': generated.to_record(),
                        'selected_source_plan_sha256': sha(canonical(plan)),
                        'claim_consumed': True, 'all_original_source_descriptors_postchecked': True}
                    report = canonical({'binding': binding(args), 'result': result})
                    report_pin = store.create('report.json', report)
                    ca.verify(); sources.verify(); store.verify()
                    require(not state['complete'] or state['source_files'] == generated.to_record()['source_files'], 'output')
                    return {'binding': binding(args), 'result': result, 'report_pin': report_pin}
                except BaseException as error:
                    store.failed = True
                    value = {'binding': binding(args), 'failure_code': finite(error), 'claim_consumed': True, 'allocation_unknown': False}
                    try:
                        store.create('failure.json', canonical(value))
                    except BaseException:
                        pass
                    return value


def validate_output(raw, actual_exit, args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT and raw.endswith(b'\n') and raw.count(b'\n') == 1
        and type(actual_exit) is int and actual_exit == 0, 'output')
    value = parse(raw[:-1]); require(canonical(value) + b'\n' == raw, 'output')
    require(type(value) is dict and set(value) == {'binding', 'child_actual', 'child_envelope', 'child_output_accepted', 'attempt_reusable'}
        and value['binding'] == binding(args) and value['child_output_accepted'] is value['attempt_reusable'] is False, 'output')
    child, evidence = value['child_envelope'], value['child_actual']
    require(type(evidence) is dict and set(evidence) == {'status', 'actual_exit', 'stdout'} and evidence['status'] == 'returned'
        and type(evidence['actual_exit']) is int and evidence['actual_exit'] == 0
        and type(child) is dict and set(child) == {'binding', 'result', 'report_pin'} and child['binding'] == binding(args)
        and evidence['stdout'] == pin(canonical(child) + b'\n'), 'output')
    result = child['result']
    require(type(result) is dict and set(result) == {'schema', 'project_id', 'dns', 'state', 'projection_pin', 'profile_pin',
        'selected_source_plan_sha256', 'claim_consumed', 'all_original_source_descriptors_postchecked', 'projection_record'}
        and result['schema'] == SCHEMA and type(result['project_id']) is int and result['project_id'] == PROJECT
        and result['projection_pin'] == stage.EXPECTED_PROJECTION_PIN and result['profile_pin'] == stage.EXPECTED_PROFILE_PIN
        and result['claim_consumed'] is result['all_original_source_descriptors_postchecked'] is True
        and result['selected_source_plan_sha256'] == sha(canonical({**selected_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256})), 'output')
    validate_dns(result['dns'])
    require(pin(canonical(result['projection_record'])) == stage.EXPECTED_PROJECTION_PIN, 'output')
    validate_state(result['state']); require(result['state']['complete'] is True
        and result['state']['source_files'] == result['projection_record'].get('source_files'), 'output')
    require(child['report_pin'] == pin(canonical({'binding': binding(args), 'result': result})), 'output')
    return value


def validate_dns(value):
    require(type(value) is dict and set(value) == {'answer_count', 'ordered_answers_sha256', 'selected_address_sha256', 'family'}
        and type(value['answer_count']) is int and 0 < value['answer_count'] <= 64
        and type(value['family']) is int and value['family'] in (int(socket.AF_INET), int(socket.AF_INET6))
        and all(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key])
            for key in ('ordered_answers_sha256', 'selected_address_sha256')), 'output')
    return value


def validate_mode(args, raw, deadline):
    require(args.mode == 'validate' and args.intent_fd is args.credential_fd is args.outer_deadline is None
        and type(args.actual_parent_exit) is int, 'arguments')
    public_preflight(args, deadline)
    plan = {**selected_plan(), SOURCE.relative_to(ROOT).as_posix(): args.caller_sha256}
    with stage.PublicSources(plan, deadline) as sources:
        require(sources.files[stage.SOURCE.relative_to(ROOT).as_posix()]['metadata'] == BOOTSTRAP_STAGE_METADATA
            and all(sources.files[name]['metadata'] == original for name, original in stage.BOOTSTRAP_METADATA.items()), 'source_changed')
        value = validate_output(raw, args.actual_parent_exit, args)
        sources.verify()
        result = value['child_envelope']['result']
        return {'binding': binding(args), 'output_authenticated': True, 'accepted': True, 'project_id': PROJECT,
            'file_count': len(result['state']['source_files']), 'application_dispatch_count': result['state']['application_dispatch_count'],
            'report_pin': value['child_envelope']['report_pin'], 'parent_actual_exit': args.actual_parent_exit,
            'child_actual_exit': value['child_actual']['actual_exit'], 'attempt_reusable': False, **FALSE_FLAGS}


def worker_main():
    consumed = False
    args = None
    try:
        args = cli()
        if args.mode == 'validate':
            raw = sys.stdin.buffer.read(MAX_OUTPUT + 1)
            value = validate_mode(args, raw, ENTRY_DEADLINE)
            sys.stdout.buffer.write(canonical(value) + b'\n')
            return 0
        require(args.mode == 'worker' and args.actual_parent_exit is None, 'arguments')
        require(args.outer_deadline is not None, 'arguments')
        value = produce(args, min(ENTRY_DEADLINE, args.outer_deadline))
        output = canonical(value) + b'\n'; require(len(output) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(output)
        return 0 if 'result' in value and value['result']['state']['complete'] else 2
    except BaseException as error:
        try:
            failed_binding = arguments(args) if args is not None else None
        except BaseException:
            failed_binding = None
        value = {'binding': failed_binding, 'failure_code': finite(error),
            'claim_consumed': consumed, 'allocation_unknown': True}
        sys.stdout.buffer.write(canonical(value) + b'\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(worker_main())
