"""Once-only, metadata-only QC availability observation after the owner hold release.

Import/profile perform no operation. A committed exact caller and profile must
precede the one-use run. No project/file/lock/permission/job mutation, credential
reader, old control access, private data read or backtest launch is implemented.
"""
import argparse
import base64
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import http.client
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
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
SOURCE = ROOT / 'scripts/observe_arv2_r345_qc_availability.py'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_availability/R345-20261107-A'
SUPPORT = ROOT / '.pytest_cache/r345-availability'
SECURITY = ROOT / 'scripts/arv2_relocation_security.py'
SECURITY_SHA256 = '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30'
HOST, PORT = 'www.quantconnect.com', 443
CA_PATH = Path('/Users/sheltonchen/.venvs/trading_agent-py313/lib/python3.13/site-packages/certifi/cacert.pem')
CA_SIZE, CA_SHA256 = 240216, '9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f'
SCHEMA = 'arv2-r345-QC-readonly-availability-v1'
PROJECT = 37165262
PROJECT_NAME = 'ARV2 EIGHT EXECUTION STRESS R281 2021 2025'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
OWNER_ROW_SHA256 = '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
SECONDS, HTTP_SECONDS, DNS_SECONDS = 90, 15, 5
MAX_BODY, MAX_OUTPUT = 1024 * 1024, 32768
CREDENTIALS = ('QC_USER_ID', 'QC_API_TOKEN')
ENDPOINTS = ('authenticate', 'projects/read', 'projects/collaboration/read', 'projects/nodes/read')
FINITE = frozenset(('arguments', 'host', 'environment', 'git_state', 'source_pin',
    'source_changed', 'security', 'claim_spent', 'control', 'output', 'bound', 'deadline',
    'credentials', 'CA', 'dns', 'transport', 'http_status', 'response', 'endpoint',
    'authentication', 'project', 'organization', 'collaborators', 'capacity', 'unknown'))
FALSE_FLAGS = {key: False for key in ('privacy_proven', 'processing_rights_proven',
    'exclusive_resource_lease', 'strategy_launch_performed', 'source_uploaded',
    'backtest_completed', 'point_in_time_proven', 'formal_forward_ready', 'paper_or_live_ready')}


class Refused(ValueError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def parse(raw, maximum=MAX_BODY):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'bound')
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'response')
            result[key] = value
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('response')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('response') from None


def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def metadata(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'))


def remaining(deadline):
    value = deadline - time.monotonic()
    require(type(deadline) in (int, float) and math.isfinite(value) and 0 < value <= SECONDS, 'deadline')
    return value


@contextmanager
def alarm(seconds):
    def expired(*_):
        raise Refused('deadline')
    old = signal.signal(signal.SIGALRM, expired)
    started = time.monotonic()
    previous = signal.getitimer(signal.ITIMER_REAL)
    effective = min(seconds, previous[0]) if previous[0] > 0 else seconds
    signal.setitimer(signal.ITIMER_REAL, effective)
    try:
        yield
    finally:
        left = max(.000001, previous[0] - (time.monotonic() - started)) if previous[0] > 0 else 0
        signal.setitimer(signal.ITIMER_REAL, left, previous[1])
        signal.signal(signal.SIGALRM, old)


def safe_env():
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
        'TMPDIR': str(SUPPORT), 'PYTHONPYCACHEPREFIX': str(SUPPORT / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'GIT_OPTIONAL_LOCKS': '0'}


def environment():
    safe = safe_env()
    require(set(os.environ) <= set(safe) | set(CREDENTIALS) | {'__CF_USER_TEXT_ENCODING'}
        and all(os.environ.get(key) == value for key, value in safe.items()), 'environment')
    if '__CF_USER_TEXT_ENCODING' in os.environ:
        require(os.environ['__CF_USER_TEXT_ENCODING'] == f'0x{os.getuid():X}:0x0:0x0', 'environment')
    require(SUPPORT.resolve() == SUPPORT and SUPPORT.is_dir()
        and http.client.HTTPConnection.debuglevel == http.client.HTTPSConnection.debuglevel == 0, 'environment')
    # Credential values are deliberately not inspected until the durable claim.
    return safe


def native_profile():
    value = '(version 1)(allow default)(deny network-bind)(deny network-inbound)'
    value += '(deny network-outbound (require-all (require-not (remote tcp "*:443"))(require-not (remote tcp "*:53"))(require-not (remote udp "*:53"))(require-not (literal "/private/var/run/mDNSResponder"))))'
    for path in ('/Volumes', '/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        value += '(deny file-read* file-write* (subpath "' + path + '"))'
    value += '(deny process-exec (literal "/usr/bin/security"))(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath "' + str(CONTROL) + '"))'
    value += '(require-not (literal "' + str(CONTROL.parent) + '"))(require-not (subpath "' + str(SUPPORT) + '"))(require-not (literal "/dev/null"))))'
    ancestors = [path for path in CONTROL.parents if ROOT / 'artifacts' == path or ROOT / 'artifacts' in path.parents]
    value += '(deny file-read* (require-all (subpath "' + str(ROOT / 'artifacts') + '")(require-not (subpath "' + str(CONTROL) + '"))'
    value += ''.join('(require-not (literal "' + str(path) + '"))' for path in ancestors) + '))'
    return value


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': PYTHON,
        'control': str(CONTROL.relative_to(ROOT)), 'project_id': PROJECT,
        'project_name': PROJECT_NAME, 'organization_sha256': ORGANIZATION_SHA256,
        'owner_row_sha256': OWNER_ROW_SHA256, 'security_source_sha256': SECURITY_SHA256,
        'native_policy_sha256': sha(native_profile().encode()), 'endpoints': list(ENDPOINTS),
        'maximum_requests': 4, 'seconds': SECONDS, 'request_seconds': HTTP_SECONDS,
        'maximum_response_bytes': MAX_BODY, 'maximum_output_bytes': MAX_OUTPUT,
        'CA': {'byte_count': CA_SIZE, 'sha256': CA_SHA256},
        'purpose': 'fresh_metadata_and_capacity_observation_not_resource_lease_or_launch_authority',
        'credentials': 'existing_environment_only_after_exclusive_fsynced_claim_no_Keychain_reader',
        'claim_consumption': 'exclusive_leaf_allocation_consumes_use_even_without_provider_contact',
        'terminal_policy': 'any_failure_or_ambiguity_spends_use_no_retry_cleanup_or_alternate_leaf',
        'capacity_policy': 'exact_booleans_not_busy_and_autoSelect_or_active_no_other_lane_identifiers',
        'deadline_qualification': 'cannot_bound_uninterruptible_IO_or_host_suspension', **FALSE_FLAGS}


def binding(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{64}', getattr(args, key))
            for key in ('caller_sha256', 'profile_sha256')), 'arguments')
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': args.profile_sha256}


class HeldPublic:
    def __init__(self, path, expected):
        self.path, self.expected, self.fd = path, expected, None
    def __enter__(self):
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            self.info = metadata(os.fstat(self.fd))
            require(stat.S_ISREG(self.info[2]) and self.info[3] == os.getuid()
                and self.info[5] == 1 and 0 < self.info[6] <= 131072, 'source_pin')
            self.raw = os.pread(self.fd, 131073, 0)
            self.verify()
            return self
        except BaseException:
            if self.fd is not None: os.close(self.fd)
            self.fd = None
            raise
    def verify(self):
        require(self.fd is not None and metadata(os.fstat(self.fd)) == self.info
            == metadata(self.path.stat(follow_symlinks=False)) and len(self.raw) == self.info[6]
            and sha(self.raw) == self.expected
            and os.pread(self.fd, 131073, 0) == self.raw, 'source_changed')
    def __exit__(self, *_):
        try: self.verify()
        finally: os.close(self.fd); self.fd = None


def preflight(args, deadline):
    bindings = binding(args)
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin'
        and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and sys.executable == PYTHON and Path(__file__).absolute() == SOURCE
        and sys.flags.isolated == 1 and sys.dont_write_bytecode, 'host')
    safe = environment()
    require(sha(canonical(profile_record())) == args.profile_sha256, 'source_pin')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT).encode()),
            (['branch', '--show-current'], BRANCH.encode()), (['rev-parse', 'HEAD'], args.expected_head.encode()),
            (['status', '--porcelain'], b'')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=safe,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=min(15, remaining(deadline)), check=False)
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 262144
            and result.stdout.strip() == expected, 'git_state')
    for path, expected in ((SOURCE, args.caller_sha256), (SECURITY, SECURITY_SHA256)):
        result = subprocess.run(['/usr/bin/git', 'cat-file', 'blob', args.expected_head + ':' + path.relative_to(ROOT).as_posix()],
            cwd=ROOT, env=safe, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=min(15, remaining(deadline)), check=False)
        require(result.returncode == 0 and not result.stderr and 0 < len(result.stdout) <= 131072
            and sha(result.stdout) == expected, 'source_pin')
    return bindings


class Store:
    """Original held descriptors, full metadata and native security until close."""
    def __init__(self, security):
        self.security, self.chain, self.leaves, self.fd = security, [], [], None
        self.intents = self.application_dispatch_count = 0
    def __enter__(self):
        try:
            parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.chain.append((parent, parent, '.', metadata(os.fstat(parent)), None))
            current = Path('/')
            for part in CONTROL.parts[1:]:
                current /= part
                if current in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                        os.fsync(parent)
                        old = self.chain[-1]; after = metadata(os.fstat(parent))
                        require(all(after[i] == old[3][i] for i in (0, 1, 2, 3, 4, 9))
                            and (old[4] is None or security_snapshot(self.security, parent) == old[4]), 'control')
                        self.chain[-1] = (*old[:3], after, old[4])
                    except FileExistsError:
                        require(current != CONTROL, 'claim_spent')
                before = metadata(os.stat(part, dir_fd=parent, follow_symlinks=False))
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                checked = current == ROOT or ROOT in current.parents
                self.chain.append((fd, parent, part, before, None))
                require(metadata(os.fstat(fd)) == before and stat.S_ISDIR(before[2])
                    and (not checked or (before[3] == os.getuid()
                        and stat.S_IMODE(before[2]) == (0o755 if current == ROOT else 0o700))), 'control')
                self.chain[-1] = (fd, parent, part, before,
                    security_snapshot(self.security, fd) if checked else None)
                parent = fd
            self.fd = parent
            self.verify()
            return self
        except BaseException:
            self.close(); raise
    def verify(self):
        require(self.fd is not None and set(os.listdir(self.fd)) == {r[0] for r in self.leaves}, 'control')
        for fd, parent, name, info, secure in self.chain:
            require(metadata(os.fstat(fd)) == info == metadata(os.stat(name, dir_fd=parent, follow_symlinks=False))
                and (secure is None or security_snapshot(self.security, fd) == secure), 'control')
        for name, fd, info, secure, expected in self.leaves:
            require(metadata(os.fstat(fd)) == info == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False))
                and stat.S_ISREG(info[2]) and stat.S_IMODE(info[2]) == 0o600
                and info[3] == os.getuid() and info[5] == 1
                and security_snapshot(self.security, fd) == secure
                and pin(os.pread(fd, expected['byte_count'] + 1, 0)) == expected, 'control')
    def write(self, name, value):
        require(name in ('claim.json', 'report.json', 'failure.json') or
            re.fullmatch('(intent|dispatch)-[0-3][.]json', name), 'output')
        raw = canonical(value)
        require(0 < len(raw) <= MAX_OUTPUT, 'bound')
        self.verify()
        before = self.chain[-1][3]
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            offset = 0
            while offset < len(raw):
                count = os.write(fd, raw[offset:]); require(count > 0, 'output'); offset += count
            os.fsync(fd)
            info = metadata(os.fstat(fd)); secure = security_snapshot(self.security, fd)
            require(os.pread(fd, len(raw) + 1, 0) == raw, 'output')
            after = metadata(os.fstat(self.fd))
            require(all(after[i] == before[i] for i in (0, 1, 2, 3, 4, 9))
                and security_snapshot(self.security, self.fd) == self.chain[-1][4], 'control')
            self.leaves.append((name, fd, info, secure, pin(raw))); fd = None
            old = self.chain[-1]; self.chain[-1] = (*old[:3], after, old[4])
            os.fsync(self.fd); self.verify()
            return pin(raw)
        finally:
            if fd is not None: os.close(fd)
    def intent(self, endpoint, project_id):
        require(self.intents < 4, 'bound')
        self.write(f'intent-{self.intents}.json', {'endpoint': endpoint, 'project_id': project_id,
            'ordinal': self.intents, 'utc': utc()})
        self.intents += 1
    def attempt(self, endpoint, project_id):
        require(self.application_dispatch_count < self.intents, 'bound')
        self.write(f'dispatch-{self.application_dispatch_count}.json', {'endpoint': endpoint,
            'project_id': project_id, 'ordinal': self.application_dispatch_count, 'utc': utc()})
        self.application_dispatch_count += 1
    def close(self):
        for _, fd, _, _, _ in self.leaves: os.close(fd)
        self.leaves.clear()
        for fd, _, _, _, _ in reversed(self.chain): os.close(fd)
        self.chain.clear(); self.fd = None
    def __exit__(self, *_):
        try: self.verify()
        finally: self.close()


def security_snapshot(security, fd):
    try: return security.snapshot(fd)
    except security.Refusal: raise Refused('security') from None


def credentials(values):
    require(type(values) is dict and set(values) == set(CREDENTIALS), 'credentials')
    user, token = (values[name] for name in CREDENTIALS)
    require(type(user) is str and 1 <= len(user) <= 19 and user.isascii() and user.isdecimal() and 0 < int(user) < 2**63
        and type(token) is str and 8 <= len(token) <= 1024 and all(33 <= ord(c) <= 126 for c in token), 'credentials')
    return values


class API:
    def __init__(self, secret, store, deadline):
        self.secret, self.store, self.deadline = credentials(secret), store, deadline
        self.last_http_status = None
        self.statuses, self.responses, self.used = [], [], set()
        self.ca_fd = None
        try:
            self.ca_fd = os.open(CA_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            self.ca_stat = metadata(os.fstat(self.ca_fd))
            raw = os.pread(self.ca_fd, CA_SIZE + 1, 0)
            require(stat.S_ISREG(self.ca_stat[2]) and self.ca_stat[5] == 1
                and len(raw) == self.ca_stat[6] == CA_SIZE and sha(raw) == CA_SHA256
                and metadata(CA_PATH.stat(follow_symlinks=False)) == self.ca_stat, 'CA')
            self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.context.check_hostname = True; self.context.verify_mode = ssl.CERT_REQUIRED
            self.context.minimum_version = ssl.TLSVersion.TLSv1_2
            self.context.load_verify_locations(cadata=raw.decode('ascii'))
            with alarm(min(DNS_SECONDS, remaining(deadline))):
                answers = socket.getaddrinfo(HOST, PORT, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            require(type(answers) is list and 0 < len(answers) <= 64, 'dns')
            first = answers[0]
            require(first[0] in (socket.AF_INET, socket.AF_INET6) and first[1] == socket.SOCK_STREAM
                and first[2] == socket.IPPROTO_TCP and ipaddress.ip_address(first[4][0]).is_global
                and first[4][1] == PORT, 'dns')
            self.family, self.address = first[0], first[4]
        except BaseException:
            self.close(); raise
    def request(self, endpoint, payload):
        require(endpoint in ENDPOINTS and endpoint not in self.used
            and type(payload) is dict and ((endpoint == 'authenticate' and payload == {})
            or (endpoint != 'authenticate' and set(payload) == {'projectId'}
                and type(payload['projectId']) is int and payload['projectId'] == PROJECT)), 'endpoint')
        self.used.add(endpoint)
        return self._exchange(endpoint, payload)
    def _exchange(self, endpoint, payload):
        """Fixed-host bounded transport; public request owns action authorization."""
        self.last_http_status = None
        self.store.intent(endpoint, payload.get('projectId'))
        self._ca_verify()
        timestamp = str(int(time.time()))
        digest = sha((self.secret['QC_API_TOKEN'] + ':' + timestamp).encode('ascii'))
        auth = base64.b64encode((self.secret['QC_USER_ID'] + ':' + digest).encode('ascii')).decode('ascii')
        body = canonical(payload)
        headers = {'Host': HOST, 'Authorization': 'Basic ' + auth, 'Timestamp': timestamp,
            'Content-Type': 'application/json', 'Content-Length': str(len(body)),
            'Accept-Encoding': 'identity', 'Connection': 'close'}
        tcp = secured = connection = None
        try:
            with alarm(min(HTTP_SECONDS, remaining(self.deadline))):
                tcp = socket.socket(self.family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
                tcp.settimeout(min(HTTP_SECONDS, remaining(self.deadline))); tcp.connect(self.address)
                secured = self.context.wrap_socket(tcp, server_hostname=HOST)
                require(secured.version() in ('TLSv1.2', 'TLSv1.3'), 'transport')
                connection = http.client.HTTPConnection(HOST, PORT, timeout=min(HTTP_SECONDS, remaining(self.deadline)))
                connection.auto_open = 0; connection.sock = secured
                require(connection.debuglevel == http.client.HTTPConnection.debuglevel == 0, 'transport')
                self.store.attempt(endpoint, payload.get('projectId'))
                connection.request('POST', '/api/v2/' + endpoint, body=body, headers=headers)
                response = connection.getresponse()
                require(type(response.status) is int and 100 <= response.status <= 599, 'http_status')
                self.last_http_status = response.status
                self.statuses.append({'endpoint': endpoint, 'http_status': response.status})
                require(response.status == 200, 'http_status')
                require(response.getheader('Content-Encoding', 'identity').lower() == 'identity', 'response')
                length = response.getheader('Content-Length')
                require(length is None or length.isdecimal() and 0 < int(length) <= MAX_BODY, 'bound')
                raw = response.read(MAX_BODY + 1)
                require(0 < len(raw) <= MAX_BODY and (length is None or len(raw) == int(length)), 'bound')
                self.responses.append({'endpoint': endpoint, **pin(raw)})
                value = parse(raw)
                require(type(value) is dict and value.get('success') is True
                    and ('errors' not in value or (type(value['errors']) is list and value['errors'] == [])), 'response')
                self._ca_verify()
                return value
        except Refused: raise
        except BaseException: raise Refused('transport') from None
        finally:
            if connection is not None: connection.close()
            else:
                for stream in (secured, tcp):
                    if stream is not None: stream.close()
    def _ca_verify(self):
        require(self.ca_fd is not None and metadata(os.fstat(self.ca_fd)) == self.ca_stat
            == metadata(CA_PATH.stat(follow_symlinks=False)), 'CA')
    def close(self):
        if self.ca_fd is not None: os.close(self.ca_fd); self.ca_fd = None


def scoped(packet):
    require(type(packet) is dict and packet.get('success') is True
        and ('errors' not in packet or type(packet['errors']) is list and packet['errors'] == []), 'response')
    require('projectId' not in packet or (type(packet['projectId']) is int and packet['projectId'] == PROJECT), 'project')
    if 'organizationId' in packet:
        organization(packet['organizationId'])
    return packet


def organization(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{32}', value)
        and sha(value.encode('ascii')) == ORGANIZATION_SHA256, 'organization')


def project_summary(project_packet, dedicated_packet, user_id):
    rows = scoped(project_packet).get('projects')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project')
    row = rows[0]
    require(type(row.get('projectId')) is int and row['projectId'] == PROJECT
        and row.get('name') == PROJECT_NAME and row.get('language') == 'Py'
        and row.get('owner') is True and type(row.get('ownerId')) is int
        and row['ownerId'] == int(user_id), 'project')
    organization(row.get('organizationId'))
    require('public' not in row or type(row['public']) is bool and row['public'] is False, 'project')
    require(type(row.get('codeRunning')) is bool, 'project')
    dedicated = scoped(dedicated_packet)
    owners = dedicated.get('collaborators')
    require(type(owners) is list and len(owners) == 1 and type(owners[0]) is dict, 'collaborators')
    owner = owners[0]
    require(owner.get('owner') is True and type(owner.get('uid')) is int
        and owner['uid'] == row['ownerId'] and owner.get('permission') == 'write'
        and owner.get('liveControl') is True
        and dedicated.get('userPermissions') == 'write' and dedicated.get('userLiveControl') is True
        and sha(canonical(owner) + b'\n') == OWNER_ROW_SHA256, 'collaborators')
    return {'reference_owned_python_project_matches': True, 'organization_matches': True,
        'dedicated_owner_only': True, 'reference_editor_idle': row['codeRunning'] is False,
        'private_field_present_and_false': 'public' in row and row['public'] is False,
        'general_collaborators_authoritative': False}


def capacity_summary(packet):
    packet = scoped(packet)
    nodes, auto = packet.get('nodes'), packet.get('autoSelectNode')
    require(type(nodes) is dict and type(auto) is bool, 'capacity')
    rows = nodes.get('backtest')
    require(type(rows) is list and len(rows) <= 64
        and all(type(row) is dict and type(row.get('busy')) is bool
            and type(row.get('active')) is bool for row in rows), 'capacity')
    available = sum(not row['busy'] and (auto or row['active']) for row in rows)
    return {'backtest_node_count': len(rows), 'busy_node_count': sum(row['busy'] for row in rows),
        'available_backtest_count': available, 'auto_select': auto,
        'state': 'available_observed' if available else 'wait_occupied_or_unavailable'}


def observe(api, user_id):
    authentication = api.request('authenticate', {})
    require(type(authentication) is dict and authentication.get('success') is True
        and ('authenticated' not in authentication or authentication['authenticated'] is True), 'authentication')
    project = api.request('projects/read', {'projectId': PROJECT})
    dedicated = api.request('projects/collaboration/read', {'projectId': PROJECT})
    summary = project_summary(project, dedicated, user_id)
    capacity = capacity_summary(api.request('projects/nodes/read', {'projectId': PROJECT}))
    return {'authentication_observed': True, **summary, **capacity}


def run(args):
    deadline = time.monotonic() + SECONDS
    api, claim = None, False
    with alarm(SECONDS), ExitStack() as stack:
        bound = preflight(args, deadline)
        held_self = stack.enter_context(HeldPublic(SOURCE, args.caller_sha256))
        held_security = stack.enter_context(HeldPublic(SECURITY, SECURITY_SHA256))
        security = type(sys)('r345_exact_security')
        exec(compile(held_security.raw, str(SECURITY), 'exec'), security.__dict__)
        with Store(security) as store:
            store.write('claim.json', {**bound, 'attempt_consumed': True, 'claimed_utc': utc()})
            claim = True
            try:
                secret = credentials({key: os.environ.get(key) for key in CREDENTIALS})
                api = API(secret, store, deadline)
                summary = observe(api, secret['QC_USER_ID'])
                held_self.verify(); held_security.verify(); remaining(deadline)
                result = {**bound, 'complete': True, 'attempt_consumed': True,
                    'request_intent_count': store.intents,
                    'application_dispatch_count': store.application_dispatch_count,
                    'physical_request_count_measured': False, 'http_statuses': api.statuses,
                    'response_pins': api.responses, **summary, **FALSE_FLAGS}
                report_pin = store.write('report.json', result)
                return {'result': result, 'report': report_pin}, 0
            except BaseException as error:
                result = {**bound, 'complete': False, 'attempt_consumed': claim,
                    'failure_code': finite(error), 'request_intent_count': store.intents,
                    'application_dispatch_count': store.application_dispatch_count,
                    'physical_request_count_measured': False,
                    'http_statuses': [] if api is None else api.statuses,
                    'response_pins': [] if api is None else api.responses, **FALSE_FLAGS}
                failure_pin = store.write('failure.json', result)
                return {'result': result, 'failure': failure_pin}, 2
            finally:
                if api is not None: api.close()


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise Refused('arguments')


def main():
    try:
        parser = Parser(add_help=False)
        parser.add_argument('mode', choices=('profile', 'run'))
        parser.add_argument('--expected-head')
        parser.add_argument('--caller-sha256')
        parser.add_argument('--profile-sha256')
        args = parser.parse_args()
        if args.mode == 'profile':
            value, exit_code = profile_record(), 0
        else:
            value, exit_code = run(args)
    except BaseException as error:
        value, exit_code = {'schema': SCHEMA, 'complete': False, 'failure_code': finite(error),
            'attempt_consumption': 'unknown_if_control_allocation_started', **FALSE_FLAGS}, 2
    raw = canonical(value)
    require(len(raw) <= MAX_OUTPUT, 'output')
    sys.stdout.buffer.write(raw + b'\n\n')
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
