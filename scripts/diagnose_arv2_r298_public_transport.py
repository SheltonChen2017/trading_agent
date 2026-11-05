"""One credential-free DNS/TCP/TLS/HEAD phase observation, never acquisition.

Only a bounded numeric HTTP status is read. No response headers/body, provider
data endpoint, credentials, source corpus, QC operation, retries or alternate address is
available. A separate committed exact run freeze must precede actual use.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import ssl
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_raw_price_acquisition_v2 as frozen

SOURCE = ROOT / 'scripts/diagnose_arv2_r298_public_transport.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_public_transport/R326-20261027-AN'
PYTHON = frozen.PYTHON
SCHEMA = 'arv2-r298-public-transport-phase-an-v1'
AM_SHA256 = '88a1c9df85f29655d8069826ad3b22453023776299306f6ed192bbf64c427334'
HOST, PORT = 'api.sharadar.com', 443
REQUEST = b'HEAD / HTTP/1.1\r\nHost: api.sharadar.com\r\nConnection: close\r\nAccept-Encoding: identity\r\n\r\n'
CA_PATH = Path('/Users/sheltonchen/.venvs/trading_agent-py313/lib/python3.13/site-packages/certifi/cacert.pem')
CA_BYTES, CA_SHA256 = 240216, '9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f'
SECONDS, STAGE_SECONDS, OUTER_SECONDS, VALIDATOR_SECONDS = 30, 5, 60, 30
MAX_OUTPUT, MAX_JOURNAL, MAX_DNS, MAX_STATUS = 32768, 8192, 64, 512
STAGES = ('dns', 'tcp', 'tls', 'http')
EGRESS = ('(deny network-bind)(deny network-inbound)'
    '(deny network-outbound (require-all (require-not (remote tcp "*:443"))'
    ' (require-not (remote tcp "*:53")) (require-not (remote udp "*:53"))))')
FALSE_FLAGS = {'credential_access': False, 'provider_data_endpoint_called': False,
    'response_headers_read': False, 'response_body_read': False, 'price_capture': False,
    'QC_operation': False, 'old_controls_read': False, 'physical_packets_measured': False,
    'historical_failure_cause_proven': False, 'price_admission': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('host', 'arguments', 'environment', 'source_pin', 'git_state', 'deadline',
    'claim_spent', 'control', 'control_write', 'journal', 'inherited', 'dns_inventory',
    'dns_empty', 'ca_pin', 'tls_configuration', 'tls_protocol', 'peer_certificate',
    'http_status_line', 'transport', 'child_failed', 'output', 'unknown'))
security, metadata = frozen.security, frozen.metadata
capture = frozen.previous.capture


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii') + b'\n'


def sha(raw): return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        value = {}
        for key, child in items:
            require(key not in value, 'output'); value[key] = child
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('output')))
        require(type(value) is dict and canonical(value) == raw, 'output')
        return value
    except (ValueError, UnicodeError, RecursionError): raise Refused('output') from None


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    return 'unknown'


_ERROR_TYPES = {OSError: 'os_error', PermissionError: 'permission', TimeoutError: 'timeout',
    ConnectionRefusedError: 'connection_refused', ConnectionResetError: 'connection_reset',
    ConnectionAbortedError: 'connection_aborted', BrokenPipeError: 'broken_pipe',
    socket.gaierror: 'dns_gaierror', socket.herror: 'dns_herror', ssl.SSLError: 'ssl_error',
    ssl.SSLCertVerificationError: 'ssl_certificate', ssl.SSLZeroReturnError: 'ssl_closed',
    ssl.SSLWantReadError: 'ssl_want_read', ssl.SSLWantWriteError: 'ssl_want_write',
    ssl.SSLEOFError: 'ssl_eof',
    ValueError: 'value_error', RuntimeError: 'runtime_error'}


def error_record(error):
    """No args, str/repr, dynamic class names, messages, endpoints or addresses."""
    pending, seen, rows = [(error, 0, 'root', frozenset())], set(), []
    cycle = truncated = False
    while pending and len(rows) < 8:
        item, depth, relation, ancestors = pending.pop(0)
        if id(item) in ancestors: cycle = True; continue
        if id(item) in seen: continue
        seen.add(id(item))
        known = type(item) in _ERROR_TYPES
        number = verify = None
        if known and isinstance(item, OSError):
            value = OSError.errno.__get__(item)
            if type(value) is int and -65535 <= value <= 65535: number = value
        if type(item) is ssl.SSLCertVerificationError:
            try: value = BaseException.__getattribute__(item, 'verify_code')
            except AttributeError: value = None
            if type(value) is int and 0 <= value <= 65535: verify = value
        rows.append({'label': _ERROR_TYPES.get(type(item), 'unknown'), 'errno': number,
            'verify_code': verify, 'relation': relation, 'depth': depth})
        if not isinstance(item, BaseException): continue
        for name, descriptor in (('cause', BaseException.__cause__), ('context', BaseException.__context__)):
            value = descriptor.__get__(item)
            if value is not None:
                if depth >= 7: truncated = True
                else: pending.append((value, depth + 1, name, ancestors | {id(item)}))
    return {'nodes': rows, 'cycle_observed': cycle, 'truncated': truncated or bool(pending),
        'interpretation': 'bounded_exception_metadata_not_authenticated_historical_cause'}


@contextmanager
def alarm(deadline):
    old = signal.getsignal(signal.SIGALRM); prior = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    target = min(deadline, started + prior[0]) if prior[0] > 0 else deadline
    def expired(*_): raise Refused('deadline')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, max(.000001, target - time.monotonic()))
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)
        if prior[0] > 0:
            left = prior[0] - (time.monotonic() - started)
            if left <= 0: raise Refused('deadline')
            signal.setitimer(signal.ITIMER_REAL, left, prior[1])


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= OUTER_SECONDS, 'deadline')
    return deadline - time.monotonic()


def source_pins():
    value = frozen.pins()
    name = 'scripts/run_arv2_r298_raw_price_acquisition_v2.py'
    require(name not in value or value[name] == AM_SHA256, 'source_pin')
    value[name] = AM_SHA256
    return value


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': frozen.admitted.frozen.BRANCH,
        'source': str(SOURCE), 'control': str(CONTROL), 'python': str(PYTHON), 'source_pins': source_pins(),
        'purpose': 'one_credential_free_public_transport_phase_identification_not_auth_retry_or_price_capture',
        'host': HOST, 'port': PORT, 'fixed_HEAD_sha256': sha(REQUEST), 'stages': list(STAGES),
        'CA': {'path': str(CA_PATH), 'byte_count': CA_BYTES, 'sha256': CA_SHA256},
        'CA_loading': 'same_hash_authenticated_public_bytes_cadata_no_default_or_client_cert',
        'egress_exact_AM': EGRESS, 'egress_is_not_domain_fence': True,
        'DNS': 'one_getaddrinfo_AF_UNSPEC_SOCK_STREAM_IPPROTO_TCP_first_supported_no_fallback',
        'TLS': 'PROTOCOL_TLS_CLIENT_CERT_REQUIRED_check_hostname_minTLS1.2_ALPNhttp1.1',
        'HTTP': 'one_fixed_HEAD_read_one_byte_at_a_time_status_line_only_no_headers_or_body',
        'status_line_byte_count': 'validated_completed_line_only_not_partial_or_wire_bytes',
        'no_body_qualification': 'application_read_parse_retention_only_TLS_or_OS_can_buffer_more_bytes',
        'maximum_DNS_rows': MAX_DNS, 'maximum_status_line_bytes': MAX_STATUS,
        'seconds': SECONDS, 'per_stage_seconds': STAGE_SECONDS, 'outer_seconds': OUTER_SECONDS,
        'validator_seconds': VALIDATOR_SECONDS, 'claim_and_stage_intents_fsynced_before_operations': True,
        'one_original_mutable_journal_FD_held_through_child_and_parent_validation': True,
        'deadline_native_IO_host_suspension_qualification': True,
        'one_attempt_partial_unknown_consumed_no_retry_cleanup_or_alternate_address': True,
        'environment': 'explicit_PATH_usrbin_LANG_C_root_cache_only_no_credentials',
        'automatic_locale': 'LC_CTYPE_absent_or_C.UTF-8_only_designated_Darwin_Python3.13_PEP538_qualification',
        'selected_library_and_CA_pins_not_whole_interpreter_integrity': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': sha(canonical(profile_record()))}


def environment():
    allowed = {'PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME',
        'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE', '__CF_USER_TEXT_ENCODING'}
    require(set(os.environ) <= allowed and os.environ.get('PATH') == '/usr/bin:/bin:/usr/sbin:/sbin'
        and os.environ.get('LANG') == 'C' and os.environ.get('LC_ALL') in (None, 'C')
        and os.environ.get('LC_CTYPE') in (None, 'C.UTF-8')
        and os.environ.get('PYTHONDONTWRITEBYTECODE') in (None, '1'), 'environment')
    if '__CF_USER_TEXT_ENCODING' in os.environ:
        require(re.fullmatch(r'(?:0x[0-9a-fA-F]{1,8}|[0-9]{1,10}):0x[0-9a-fA-F]{1,8}:0x[0-9a-fA-F]{1,8}',
            os.environ['__CF_USER_TEXT_ENCODING']) is not None, 'environment')
    for key in ('TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX'):
        value = os.environ.get(key)
        require(type(value) is str and Path(value).is_relative_to(ROOT / '.pytest_cache')
            and Path(value).resolve() == Path(value), 'environment')


def preflight(args, deadline):
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE and not frozen.admitted.v5._under_test(), 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    environment()
    for cmd, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], frozen.admitted.frozen.BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(frozen.admitted.v5._git(cmd, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in source_pins().items(): require(sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256
        and sha(frozen.admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline, 131072))
            == args.caller_sha256, 'source_pin')
    remaining(deadline)


def _walk(path):
    fd, held = os.open('/', os.O_RDONLY | os.O_DIRECTORY), []
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = nxt; held.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
        return fd, tuple(held)
    except BaseException: os.close(fd); raise


def _read(fd, maximum):
    os.lseek(fd, 0, os.SEEK_SET); raw = bytearray()
    while len(raw) <= maximum:
        part = os.read(fd, min(65536, maximum + 1 - len(raw)))
        if not part: break
        raw.extend(part)
    require(len(raw) <= maximum, 'control'); return bytes(raw)


class Store:
    def __init__(self):
        parent, _ = _walk(CONTROL.parent.parent)
        try:
            try: os.mkdir(CONTROL.parent.name, 0o700, dir_fd=parent); os.fsync(parent)
            except FileExistsError: pass
        finally: os.close(parent)
        parent, _ = _walk(CONTROL.parent)
        try:
            info = os.fstat(parent)
            require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'control')
            try: os.mkdir(CONTROL.name, 0o700, dir_fd=parent); os.fsync(parent)
            except FileExistsError: raise Refused('claim_spent') from None
        finally: os.close(parent)
        self.fd, self.chain = _walk(CONTROL)
        self.snapshot, self.files = security.snapshot(self.fd), {}

    def __enter__(self): return self
    def __exit__(self, *_):
        for fd, _, _ in self.files.values(): os.close(fd)
        os.close(self.fd)

    def verify(self):
        other, chain = _walk(CONTROL)
        try:
            info = os.fstat(self.fd)
            require(chain == self.chain and metadata(info) == metadata(os.fstat(other))
                and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid()
                and security.snapshot(self.fd) == self.snapshot
                and set(os.listdir(other)) == set(self.files), 'control')
            for name, (fd, baseline, snapshot) in self.files.items():
                held = os.fstat(fd)
                require(metadata(held) == metadata(os.stat(name, dir_fd=other, follow_symlinks=False))
                    and (name == 'stages.jsonl' or metadata(held) == baseline)
                    and stat.S_ISREG(held.st_mode) and held.st_uid == os.getuid() and held.st_nlink == 1
                    and stat.S_IMODE(held.st_mode) == 0o600 and held.st_size <= MAX_OUTPUT
                    and security.snapshot(fd) == snapshot, 'control')
        finally: os.close(other)

    def write(self, name, raw):
        require(name in ('claim.json', 'intent.json', 'stages.jsonl', 'report.json')
            and name not in self.files and type(raw) is bytes and len(raw) <= MAX_OUTPUT, 'control_write')
        self.verify()
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            snapshot = security.snapshot(fd)
            view = memoryview(raw)
            while view:
                n = os.write(fd, view); require(n > 0, 'control_write'); view = view[n:]
            os.fsync(fd); os.fsync(self.fd)
            info = os.fstat(fd)
            require(_read(fd, MAX_OUTPUT) == raw and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600, 'control_write')
            self.files[name] = fd, metadata(info), snapshot
        except BaseException: os.close(fd); raise
        self.verify(); return {'byte_count': len(raw), 'sha256': sha(raw)}


def native_profile(mode):
    require(mode in ('child', 'validator'), 'arguments')
    profile = '(version 1)(allow default)' + (EGRESS if mode == 'child' else '(deny network*)')
    profile += ''.join('(deny file-read* file-write* (subpath "' + p + '"))' for p in
        ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    profile += '(deny process-exec (literal "/usr/bin/security"))'
    exceptions = '(require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))(require-not (literal "/dev/null"))'
    if mode == 'child': exceptions += '(require-not (literal "' + str(CONTROL / 'stages.jsonl') + '"))'
    profile += '(deny file-write* (require-all ' + exceptions + '))'
    if mode == 'validator': return profile + '(deny file-read* (subpath "' + str(ROOT / 'artifacts') + '"))'
    paths = {CONTROL, CONTROL / 'claim.json', CONTROL / 'intent.json', CONTROL / 'stages.jsonl'}
    paths.update(p for p in CONTROL.parents if p == ROOT / 'artifacts' or ROOT / 'artifacts' in p.parents)
    return profile + '(deny file-read* (require-all (subpath "' + str(ROOT / 'artifacts') + '") ' + ''.join(
        '(require-not (literal "' + str(p) + '"))' for p in sorted(paths)) + '))'


def _inherited(args):
    fds = (args.control_fd, args.claim_fd, args.intent_fd, args.journal_fd)
    require(all(type(fd) is int and fd > 2 for fd in fds) and len(set(fds)) == 4, 'inherited')
    directory = os.fstat(args.control_fd)
    require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == os.getuid()
        and stat.S_IMODE(directory.st_mode) == 0o700
        and metadata(directory) == metadata(os.stat(CONTROL, follow_symlinks=False)), 'inherited')
    for fd, name in ((args.claim_fd, 'claim.json'), (args.intent_fd, 'intent.json'), (args.journal_fd, 'stages.jsonl')):
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o600
            and metadata(info) == metadata(os.stat(name, dir_fd=args.control_fd, follow_symlinks=False)), 'inherited')
        security.snapshot(fd)
    require(_read(args.claim_fd, MAX_OUTPUT) == canonical({**binding(args), 'attempt_consumed': True})
        and _read(args.intent_fd, MAX_OUTPUT) == canonical({**binding(args), 'one_child': True})
        and os.fstat(args.journal_fd).st_size == 0, 'inherited')


def _stage(args, state, stage):
    require(len(state['stage_intents']) < len(STAGES) and stage == STAGES[len(state['stage_intents'])], 'journal')
    raw = canonical({'binding': binding(args), 'ordinal': len(state['stage_intents']), 'stage': stage})
    fd = args.journal_fd
    info, snapshot = os.fstat(fd), security.snapshot(fd)
    require(metadata(info) == metadata(os.stat('stages.jsonl', dir_fd=args.control_fd, follow_symlinks=False))
        and info.st_size + len(raw) <= MAX_JOURNAL, 'journal')
    os.lseek(fd, 0, os.SEEK_END); view = memoryview(raw)
    while view:
        n = os.write(fd, view); require(n > 0, 'journal'); view = view[n:]
    os.fsync(fd); os.fsync(args.control_fd)
    require(metadata(os.fstat(fd)) == metadata(os.stat('stages.jsonl', dir_fd=args.control_fd, follow_symlinks=False))
        and security.snapshot(fd) == snapshot, 'journal')
    state['stage_intents'].append(stage)


def _ca_bytes():
    fd = os.open(CA_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size == CA_BYTES, 'ca_pin')
        raw = _read(fd, CA_BYTES)
        require(metadata(before) == metadata(os.fstat(fd)) and len(raw) == CA_BYTES and sha(raw) == CA_SHA256,
            'ca_pin')
        return raw
    finally: os.close(fd)


def _context(ca_raw):
    require(len(ca_raw) == CA_BYTES and sha(ca_raw) == CA_SHA256, 'ca_pin')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True; context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(['http/1.1'])
    context.load_verify_locations(cadata=ca_raw.decode('ascii'))
    require(context.protocol == ssl.PROTOCOL_TLS_CLIENT and context.check_hostname is True
        and context.verify_mode == ssl.CERT_REQUIRED and context.minimum_version >= ssl.TLSVersion.TLSv1_2,
        'tls_configuration')
    return context


def _inventory(rows):
    require(type(rows) is list and 0 < len(rows) <= MAX_DNS, 'dns_inventory')
    encoded, families, chosen = [], {'AF_INET': 0, 'AF_INET6': 0, 'unsupported': 0}, None
    for index, row in enumerate(rows):
        require(type(row) is tuple and len(row) == 5, 'dns_inventory')
        family, kind, protocol, name, address = row
        require(type(family) in (int, socket.AddressFamily) and type(kind) in (int, socket.SocketKind)
            and type(protocol) is int and type(name) is str and len(name) <= 1024
            and type(address) in (str, tuple), 'dns_inventory')
        label = 'AF_INET' if family == socket.AF_INET else 'AF_INET6' if family == socket.AF_INET6 else 'unsupported'
        families[label] += 1
        require(len(canonical(address)) <= 2048, 'dns_inventory')
        encoded.append([index, int(family), int(kind), protocol, name, address])
        if chosen is None and label != 'unsupported' and kind == socket.SOCK_STREAM and protocol == socket.IPPROTO_TCP:
            require(type(address) is tuple and len(address) == (2 if family == socket.AF_INET else 4)
                and type(address[0]) is str and type(address[1]) is int and address[1] == PORT
                and ipaddress.ip_address(address[0]).version == (4 if family == socket.AF_INET else 6), 'dns_inventory')
            chosen = index, family, address, label
    require(chosen is not None, 'dns_empty')
    return {'count': len(rows), 'families': families, 'ordered_inventory_sha256': sha(canonical(encoded)),
        'selected_ordinal': chosen[0], 'selected_family': chosen[3]}, chosen[1], chosen[2]


def _status(stream, deadline):
    line = bytearray()
    while len(line) < MAX_STATUS:
        remaining(deadline)
        part = stream.recv(1)
        require(type(part) is bytes and len(part) == 1, 'http_status_line')
        line.extend(part)
        if line.endswith(b'\r\n'): break
    match = re.fullmatch(rb'HTTP/1\.[01] ([1-5][0-9]{2})(?: [\x20-\x7e]*)?\r\n', bytes(line))
    require(match is not None, 'http_status_line')
    return int(match.group(1)), len(line)


def initial_state():
    return {'stage_intents': [], 'DNS': None, 'TCP_connected': False, 'TLS': None,
        'HEAD_send_attempts': 0, 'http_status': None, 'status_line_byte_count': 0,
        'failure_code': None, 'error': None, 'diagnostic_complete': False,
        'physical_packets': None, **FALSE_FLAGS}


def protocol(args, deadline):
    state, tcp, stream = initial_state(), None, None
    try:
        ca_raw = _ca_bytes()
        _stage(args, state, 'dns')
        with alarm(min(deadline, time.monotonic() + STAGE_SECONDS)):
            rows = socket.getaddrinfo(HOST, PORT, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        state['DNS'], family, address = _inventory(rows)
        _stage(args, state, 'tcp')
        with alarm(min(deadline, time.monotonic() + STAGE_SECONDS)):
            tcp = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            tcp.settimeout(min(STAGE_SECONDS, remaining(deadline))); tcp.connect(address)
        state['TCP_connected'] = True
        _stage(args, state, 'tls')
        with alarm(min(deadline, time.monotonic() + STAGE_SECONDS)):
            context = _context(ca_raw)
            stream = context.wrap_socket(tcp, server_hostname=HOST)
            version = stream.version()
            require(version in ('TLSv1.2', 'TLSv1.3')
                and stream.selected_alpn_protocol() in (None, 'http/1.1'), 'tls_protocol')
            peer = stream.getpeercert(binary_form=True)
            require(type(peer) is bytes and 0 < len(peer) <= 65536, 'peer_certificate')
            state['TLS'] = {'version': version, 'peer_DER_sha256': sha(peer)}
        _stage(args, state, 'http')
        with alarm(min(deadline, time.monotonic() + STAGE_SECONDS)):
            stream.settimeout(min(STAGE_SECONDS, remaining(deadline)))
            state['HEAD_send_attempts'] = 1; stream.sendall(REQUEST)
            state['http_status'], state['status_line_byte_count'] = _status(stream, deadline)
        state['diagnostic_complete'] = True
    except BaseException as error:
        state['failure_code'] = finite(error) if type(error) is Refused else 'transport'
        state['error'] = error_record(error)
    finally:
        for value in (stream, tcp):
            if value is not None:
                try: value.close()
                except BaseException as error:
                    if state['failure_code'] is None:
                        state.update(failure_code='transport', error=error_record(error), diagnostic_complete=False)
    return state


def validate_state(value):
    require(type(value) is dict and set(value) == set(initial_state())
        and type(value['stage_intents']) is list and value['stage_intents'] == list(STAGES[:len(value['stage_intents'])])
        and len(value['stage_intents']) <= 4 and type(value['TCP_connected']) is bool
        and type(value['HEAD_send_attempts']) is int and value['HEAD_send_attempts'] in (0, 1)
        and type(value['diagnostic_complete']) is bool and value['physical_packets'] is None
        and all(value[key] is False for key in FALSE_FLAGS), 'output')
    if value['DNS'] is not None:
        dns = value['DNS']
        require(type(dns) is dict and set(dns) == {'count', 'families', 'ordered_inventory_sha256', 'selected_ordinal', 'selected_family'}
            and type(dns['count']) is int and 0 < dns['count'] <= MAX_DNS
            and type(dns['families']) is dict and set(dns['families']) == {'AF_INET', 'AF_INET6', 'unsupported'}
            and all(type(n) is int and 0 <= n <= MAX_DNS for n in dns['families'].values())
            and sum(dns['families'].values()) == dns['count']
            and re.fullmatch('[0-9a-f]{64}', dns['ordered_inventory_sha256'])
            and type(dns['selected_ordinal']) is int and 0 <= dns['selected_ordinal'] < dns['count']
            and dns['selected_family'] in ('AF_INET', 'AF_INET6') and 'dns' in value['stage_intents'], 'output')
    if value['TCP_connected']: require(value['DNS'] is not None and 'tcp' in value['stage_intents'], 'output')
    if len(value['stage_intents']) >= 2: require(value['DNS'] is not None, 'output')
    if len(value['stage_intents']) >= 3: require(value['TCP_connected'] is True, 'output')
    if value['TLS'] is not None:
        tls = value['TLS']
        require(type(tls) is dict and set(tls) == {'version', 'peer_DER_sha256'}
            and tls['version'] in ('TLSv1.2', 'TLSv1.3') and re.fullmatch('[0-9a-f]{64}', tls['peer_DER_sha256'])
            and value['TCP_connected'] and 'tls' in value['stage_intents'], 'output')
    require((value['http_status'] is None or type(value['http_status']) is int and 100 <= value['http_status'] <= 599)
        and type(value['status_line_byte_count']) is int and 0 <= value['status_line_byte_count'] <= MAX_STATUS, 'output')
    if value['HEAD_send_attempts']: require(value['TLS'] is not None and 'http' in value['stage_intents'], 'output')
    if len(value['stage_intents']) == 4: require(value['TLS'] is not None, 'output')
    if value['http_status'] is None: require(value['status_line_byte_count'] == 0, 'output')
    else: require(value['HEAD_send_attempts'] == 1 and value['status_line_byte_count'] >= 14, 'output')
    if value['error'] is not None:
        error = value['error']
        require(type(error) is dict and set(error) == {'nodes', 'cycle_observed', 'truncated', 'interpretation'}
            and type(error['nodes']) is list and 0 < len(error['nodes']) <= 8
            and type(error['cycle_observed']) is bool and type(error['truncated']) is bool
            and error['interpretation'] == 'bounded_exception_metadata_not_authenticated_historical_cause', 'output')
        for row in error['nodes']:
            require(type(row) is dict and set(row) == {'label', 'errno', 'verify_code', 'relation', 'depth'}
                and row['label'] in set(_ERROR_TYPES.values()) | {'unknown'}
                and row['relation'] in ('root', 'cause', 'context') and type(row['depth']) is int and 0 <= row['depth'] <= 7
                and (row['errno'] is None or type(row['errno']) is int and -65535 <= row['errno'] <= 65535)
                and (row['verify_code'] is None or type(row['verify_code']) is int and 0 <= row['verify_code'] <= 65535), 'output')
            require((row['label'] == 'ssl_certificate' or row['verify_code'] is None)
                and (row['label'] not in ('unknown', 'runtime_error', 'value_error') or row['errno'] is None), 'output')
        require(error['nodes'][0]['relation'] == 'root' and error['nodes'][0]['depth'] == 0
            and all(row['relation'] != 'root' and row['depth'] > 0 for row in error['nodes'][1:]), 'output')
    if value['diagnostic_complete']:
        require(value['stage_intents'] == list(STAGES) and value['HEAD_send_attempts'] == 1
            and value['http_status'] is not None and value['status_line_byte_count'] >= 14
            and value['failure_code'] is value['error'] is None, 'output')
    else: require(value['failure_code'] in FINITE and value['error'] is not None, 'output')
    return value


def _actual_metadata(actual):
    keys = {'actual_exit', 'bound', 'spawn_observed', 'dispatched_at', 'completion_observed_at',
        'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256'}
    require(type(actual) is dict and set(actual) == keys
        and (actual['actual_exit'] is None or type(actual['actual_exit']) is int and -255 <= actual['actual_exit'] <= 255)
        and actual['bound'] in (None, 'deadline', 'channel_bound', 'capture_failed', 'reap_unknown')
        and type(actual['spawn_observed']) is bool
        and all(type(actual[key]) is int and 0 <= actual[key] <= 2 ** 31 for key in ('stdout_bytes', 'stderr_bytes'))
        and all(type(actual[key]) is str and re.fullmatch('[0-9a-f]{64}', actual[key])
            for key in ('stdout_sha256', 'stderr_sha256'))
        and all(type(actual[key]) is str and 20 <= len(actual[key]) <= 40
            and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)', actual[key])
            for key in ('dispatched_at', 'completion_observed_at')), 'output')
    for role in ('stdout', 'stderr'):
        require((actual[role + '_bytes'] == 0) == (actual[role + '_sha256'] == sha(b'')), 'output')
    try:
        times = [datetime.fromisoformat(actual[key].replace('Z', '+00:00'))
            for key in ('dispatched_at', 'completion_observed_at')]
        require(all(value.utcoffset() == timedelta(0) for value in times) and times[0] <= times[1], 'output')
    except (ValueError, TypeError): raise Refused('output') from None


def _actual(actual, raw, exits):
    _actual_metadata(actual)
    require(type(actual.get('actual_exit')) is int and actual['actual_exit'] in exits
        and actual.get('bound') is None and actual.get('spawn_observed') is True
        and actual.get('stdout_bytes') == len(raw) and actual.get('stdout_sha256') == sha(raw)
        and actual.get('stderr_bytes') == 0 and actual.get('stderr_sha256') == sha(b''), 'child_failed')


def run(args, deadline):
    with Store() as directory:
        directory.write('claim.json', canonical({**binding(args), 'attempt_consumed': True}))
        directory.write('intent.json', canonical({**binding(args), 'one_child': True}))
        directory.write('stages.jsonl', b'')
        runtime = Path(tempfile.mkdtemp(prefix='r326-an-', dir=ROOT / '.pytest_cache'))
        safe = {key: str(runtime) for key in ('TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX')}
        safe.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin', LANG='C', PYTHONDONTWRITEBYTECODE='1')
        command = ['/usr/bin/sandbox-exec', '-p', native_profile('child'), str(PYTHON), '-B', str(SOURCE), 'child',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
            '--control-fd', str(directory.fd), '--claim-fd', str(directory.files['claim.json'][0]),
            '--intent-fd', str(directory.files['intent.json'][0]), '--journal-fd', str(directory.files['stages.jsonl'][0])]
        raw, errors, actual = capture(command, safe, min(OUTER_SECONDS, remaining(deadline)),
            stdout_limit=MAX_OUTPUT, pass_fds=(directory.fd, *(directory.files[name][0]
                for name in ('claim.json', 'intent.json', 'stages.jsonl'))))
        result = {'binding': binding(args), 'claim_consumed': True, 'child_actual': actual,
            'child': None, 'journal_pin': None, 'parent_failure': None, **FALSE_FLAGS}
        try:
            require(not errors, 'child_failed'); _actual(actual, raw, (0, 2))
            child = parse(raw); require(set(child) == {'binding', 'state'} and child['binding'] == binding(args), 'output')
            validate_state(child['state'])
            require(actual['actual_exit'] == (0 if child['state']['diagnostic_complete'] else 2), 'child_failed')
            directory.verify(); journal = _read(directory.files['stages.jsonl'][0], MAX_JOURNAL)
            expected = b''.join(canonical({'binding': binding(args), 'ordinal': index, 'stage': stage})
                for index, stage in enumerate(child['state']['stage_intents']))
            require(journal == expected, 'journal')
            result['child'], result['journal_pin'] = child, {'byte_count': len(journal), 'sha256': sha(journal)}
            preflight(args, deadline); directory.verify()
        except BaseException as error:
            result['parent_failure'] = finite(error)
        code = 0 if result['parent_failure'] is None and result['child']['state']['diagnostic_complete'] else 2
        report = directory.write('report.json', canonical(result)); directory.verify()
        return {'result': result, 'report': report}, code


def validate_output(raw, actual_exit, args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT and type(actual_exit) is int and actual_exit in (0, 2), 'output')
    value = parse(raw)
    require(value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'failure'}:
        require(actual_exit == 2 and value['failure'] in FINITE, 'output'); return value
    require(set(value) == {'binding', 'outcome'} and set(value['outcome']) == {'result', 'report'}, 'output')
    outcome, result = value['outcome'], value['outcome']['result']
    require(type(result) is dict and set(result) == {'binding', 'claim_consumed', 'child_actual', 'child',
        'journal_pin', 'parent_failure', *FALSE_FLAGS} and result['binding'] == binding(args)
        and result['claim_consumed'] is True and all(result[key] is False for key in FALSE_FLAGS), 'output')
    _actual_metadata(result['child_actual'])
    if result['child'] is not None:
        child = result['child']; require(type(child) is dict and set(child) == {'binding', 'state'}
            and child['binding'] == binding(args), 'output'); validate_state(child['state'])
        _actual(result['child_actual'], canonical(child), (0 if child['state']['diagnostic_complete'] else 2,))
        journal = b''.join(canonical({'binding': binding(args), 'ordinal': i, 'stage': stage})
            for i, stage in enumerate(child['state']['stage_intents']))
        require(result['journal_pin'] == {'byte_count': len(journal), 'sha256': sha(journal)}, 'output')
    else: require(result['journal_pin'] is None, 'output')
    if result['parent_failure'] is None:
        require(result['child'] is not None and actual_exit == (0 if result['child']['state']['diagnostic_complete'] else 2), 'output')
    else: require(actual_exit == 2 and result['parent_failure'] in FINITE, 'output')
    report = canonical(result)
    require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'child', 'validate'))
    parser.add_argument('--expected-head', required=True); parser.add_argument('--caller-sha256', required=True)
    for name in ('control-fd', 'claim-fd', 'intent-fd', 'journal-fd', 'actual-exit'): parser.add_argument('--' + name, type=int)
    args = parser.parse_args(argv)
    deadline = time.monotonic() + (VALIDATOR_SECONDS if args.operation == 'validate' else SECONDS if args.operation == 'child' else OUTER_SECONDS)
    try:
        with alarm(deadline):
            preflight(args, deadline)
            if args.operation == 'validate':
                raw = sys.stdin.buffer.read(MAX_OUTPUT + 1); validate_output(raw, args.actual_exit, args)
                sys.stdout.buffer.write(raw); return 0
            if args.operation == 'child':
                _inherited(args); state = protocol(args, deadline)
                validate_state(state); value, code = {'binding': binding(args), 'state': state}, 0 if state['diagnostic_complete'] else 2
            else:
                outcome, code = run(args, deadline); value = {'binding': binding(args), 'outcome': outcome}
            raw = canonical(value); require(len(raw) <= MAX_OUTPUT, 'output'); sys.stdout.buffer.write(raw); return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'failure': finite(error)})); return 2


if __name__ == '__main__': raise SystemExit(main())
