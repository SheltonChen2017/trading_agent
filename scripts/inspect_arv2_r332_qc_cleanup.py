"""One bounded metadata-only QC inventory for the owner's R332 cleanup.

No deletion, file/result/statistic read, project editing or strategy launch is
implemented. Parent credentials cross only its own child's stdin; output is a
selected Analyst-only metadata report. An actual child exit zero and matching
report pin are required, not merely a parent exit or an existing control leaf.
"""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import ipaddress
import json
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
SOURCE = ROOT / 'scripts/inspect_arv2_r332_qc_cleanup.py'
POLICY = ROOT / 'scripts/arv2_r332_qc_cleanup_policy.py'
RECORD = ROOT / 'docs/Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/qc_cleanup/R332-20261028-A'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
BRANCH = 'codex/strategy-analyst-revisions-v2'
HOST = 'www.quantconnect.com'
CA_PATH = Path('/Users/sheltonchen/.venvs/trading_agent-py313/lib/python3.13/site-packages/certifi/cacert.pem')
CA_SIZE = 240216
CA_SHA256 = '9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f'
SCHEMA = 'arv2-r332-Analyst-only-cleanup-inventory-v1'
MAX_BODY, MAX_OUTPUT, MAX_PROJECTS = 8 * 1024 * 1024, 512 * 1024, 1024
PARENT_SECONDS, WORKER_SECONDS, HTTP_SECONDS = 900, 600, 15
ENTRY = time.monotonic()
FINITE = frozenset(('arguments', 'host', 'git_state', 'source_pin', 'credentials', 'claim_spent',
    'control', 'deadline', 'CA', 'dns', 'transport', 'http_status', 'response', 'bound',
    'projects', 'history', 'policy', 'output', 'child_failure', 'unknown'))


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


def parse(raw, maximum):
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


def safe_env():
    support = ROOT / '.pytest_cache/r332-inventory-runtime'
    support.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(support.resolve() == support and support.is_dir(), 'host')
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'LANG': 'C',
        'TMPDIR': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'GIT_OPTIONAL_LOCKS': '0'}


def native_profile():
    value = '(version 1)(allow default)(deny network-bind)(deny network-inbound)'
    value += '(deny network-outbound (require-all (require-not (remote tcp "*:443"))(require-not (remote tcp "*:53"))(require-not (remote udp "*:53"))(require-not (literal "/private/var/run/mDNSResponder"))))'
    for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        value += '(deny file-read* file-write* (subpath "' + path + '"))'
    value += '(deny process-exec (literal "/usr/bin/security"))'
    value += '(deny file-read-data (regex "[.]pyc$"))'
    value += '(deny file-write* (require-all (require-not (subpath "' + str(CONTROL) + '"))'
    value += '(require-not (literal "' + str(CONTROL.parent) + '"))(require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))(require-not (literal "/dev/null"))))'
    ancestors = [path for path in CONTROL.parents if ROOT / 'artifacts' == path or ROOT / 'artifacts' in path.parents]
    value += '(deny file-read* (require-all (subpath "' + str(ROOT / 'artifacts') + '")(require-not (subpath "' + str(CONTROL) + '"))'
    value += ''.join('(require-not (literal "' + str(path) + '"))' for path in ancestors) + '))'
    return value


def read_public(path, expected, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.getuid()
            and 0 < before.st_size <= maximum, 'source_pin')
        raw = os.pread(fd, maximum + 1, 0)
        require(len(raw) == before.st_size and sha(raw) == expected
            and metadata(os.fstat(fd)) == metadata(before)
            and metadata(path.stat(follow_symlinks=False)) == metadata(before), 'source_pin')
        return raw
    finally:
        os.close(fd)


def metadata(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'))


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'policy_sha256': args.policy_sha256,
        'record_sha256': args.record_sha256}


def preflight(args):
    require(Path.cwd() == ROOT and ROOT.resolve() == ROOT and sys.platform == 'darwin'
        and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and sys.executable == PYTHON and Path(__file__).absolute() == SOURCE
        and sys.flags.isolated == 1, 'host')
    for key, length in (('expected_head', 40), ('caller_sha256', 64), ('policy_sha256', 64), ('record_sha256', 64)):
        require(re.fullmatch('[0-9a-f]{' + str(length) + '}', getattr(args, key)) is not None, 'arguments')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
            (['branch', '--show-current'], BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
            (['status', '--porcelain'], '')):
        result = subprocess.run(['/usr/bin/git', *command], cwd=ROOT, env=safe_env(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        require(result.returncode == 0 and not result.stderr and result.stdout.decode('utf-8').strip() == expected, 'git_state')
    read_public(SOURCE, args.caller_sha256, 128 * 1024)
    policy_raw = read_public(POLICY, args.policy_sha256, 128 * 1024)
    record_raw = read_public(RECORD, args.record_sha256, 16 * 1024 * 1024)
    return policy_raw, record_raw


def credentials(value):
    require(type(value) is dict and set(value) == {'QC_USER_ID', 'QC_API_TOKEN'}, 'credentials')
    user, token = value['QC_USER_ID'], value['QC_API_TOKEN']
    require(type(user) is str and user.isascii() and user.isdecimal() and 0 < int(user) < 2**63
        and type(token) is str and 8 <= len(token) <= 1024 and all(33 <= ord(c) <= 126 for c in token), 'credentials')
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
        remaining = max(0.000001, previous[0] - (time.monotonic() - started)) if previous[0] > 0 else 0
        signal.setitimer(signal.ITIMER_REAL, remaining, previous[1])
        signal.signal(signal.SIGALRM, old)


class Store:
    """One exclusive control, fd-relative writes; never follows old controls."""
    def __init__(self):
        self.parents = []
        self.intents = self.dispatches = 0
        fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.parents.append(fd)
        try:
            for part in CONTROL.relative_to(ROOT).parts[:-1]:
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    os.fsync(fd)
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                require(os.fstat(child).st_uid == os.getuid(), 'control')
                self.parents.append(child); fd = child
            try:
                os.mkdir(CONTROL.name, 0o700, dir_fd=fd)
            except FileExistsError:
                raise Refused('claim_spent') from None
            os.fsync(fd)
            self.fd = os.open(CONTROL.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            self.parents.append(self.fd)
            self.journal = os.open('dispatch.jsonl', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        except BaseException:
            self.close()
            raise

    def write(self, name, value):
        require(name in ('claim.json', 'report.json', 'failure.json'), 'output')
        raw = canonical(value)
        require(len(raw) <= MAX_OUTPUT, 'bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            require(os.write(fd, raw) == len(raw), 'output')
            os.fsync(fd); os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == len(raw)
                and os.pread(fd, len(raw) + 1, 0) == raw
                and metadata(os.fstat(fd)) == metadata(info)
                == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), 'output')
        finally:
            os.close(fd)
        return pin(raw)

    def intent(self, endpoint, project_id):
        raw = canonical({'kind': 'request_intent', 'ordinal': self.intents,
            'endpoint': endpoint, 'project_id': project_id, 'utc': utc()}) + b'\n'
        require(os.write(self.journal, raw) == len(raw), 'output')
        os.fsync(self.journal); self.intents += 1

    def attempt(self, endpoint, project_id):
        raw = canonical({'kind': 'application_dispatch_attempt', 'ordinal': self.dispatches,
            'endpoint': endpoint, 'project_id': project_id, 'utc': utc()}) + b'\n'
        require(os.write(self.journal, raw) == len(raw), 'output')
        os.fsync(self.journal); self.dispatches += 1

    def close(self):
        if hasattr(self, 'journal'):
            os.close(self.journal); del self.journal
        for fd in reversed(self.parents):
            os.close(fd)
        self.parents = []


class API:
    def __init__(self, secret, store):
        self.secret, self.store = secret, store
        self.last_http_status = None
        self.ca_fd = os.open(CA_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        self.ca_stat = os.fstat(self.ca_fd)
        raw = os.pread(self.ca_fd, CA_SIZE + 1, 0)
        require(stat.S_ISREG(self.ca_stat.st_mode) and self.ca_stat.st_nlink == 1
            and len(raw) == self.ca_stat.st_size == CA_SIZE and sha(raw) == CA_SHA256
            and metadata(CA_PATH.stat(follow_symlinks=False)) == metadata(self.ca_stat), 'CA')
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.check_hostname = True; self.context.verify_mode = ssl.CERT_REQUIRED
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=raw.decode('ascii'))
        with alarm(5):
            answers = socket.getaddrinfo(HOST, 443, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        require(type(answers) is list and 0 < len(answers) <= 64, 'dns')
        first = answers[0]
        require(first[0] in (socket.AF_INET, socket.AF_INET6) and first[1] == socket.SOCK_STREAM
            and first[2] == socket.IPPROTO_TCP and ipaddress.ip_address(first[4][0]).is_global
            and first[4][1] == 443, 'dns')
        self.family, self.address = first[0], first[4]

    def request(self, endpoint, payload):
        require((endpoint == 'projects/read' and payload == {}) or
            (endpoint == 'backtests/list' and type(payload) is dict and set(payload) == {'projectId', 'includeStatistics'}
             and type(payload['projectId']) is int and 0 < payload['projectId'] < 2**31
             and payload['includeStatistics'] is False), 'arguments')
        return self._exchange(endpoint, payload)

    def _exchange(self, endpoint, payload):
        """Fixed-host transport primitive; public request enforces inventory scope."""
        self.last_http_status = None
        self.store.intent(endpoint, payload.get('projectId'))
        require(metadata(os.fstat(self.ca_fd)) == metadata(self.ca_stat)
            == metadata(CA_PATH.stat(follow_symlinks=False)), 'CA')
        timestamp = str(int(time.time()))
        digest = sha((self.secret['QC_API_TOKEN'] + ':' + timestamp).encode('ascii'))
        auth = base64.b64encode((self.secret['QC_USER_ID'] + ':' + digest).encode('ascii')).decode('ascii')
        body = canonical(payload)
        headers = {'Host': HOST, 'Authorization': 'Basic ' + auth, 'Timestamp': timestamp,
            'Content-Type': 'application/json', 'Content-Length': str(len(body)),
            'Accept-Encoding': 'identity', 'Connection': 'close'}
        tcp = secured = connection = None
        try:
            with alarm(HTTP_SECONDS):
                tcp = socket.socket(self.family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
                tcp.settimeout(HTTP_SECONDS); tcp.connect(self.address)
                secured = self.context.wrap_socket(tcp, server_hostname=HOST)
                require(secured.version() in ('TLSv1.2', 'TLSv1.3'), 'transport')
                connection = http.client.HTTPConnection(HOST, 443, timeout=HTTP_SECONDS)
                connection.auto_open = 0; connection.sock = secured
                require(connection.debuglevel == http.client.HTTPConnection.debuglevel == 0, 'transport')
                self.store.attempt(endpoint, payload.get('projectId'))
                connection.request('POST', '/api/v2/' + endpoint, body=body, headers=headers)
                response = connection.getresponse()
                require(type(response.status) is int and 100 <= response.status <= 599, 'http_status')
                self.last_http_status = response.status
                require(response.status == 200, 'http_status')
                require(response.getheader('Content-Encoding', 'identity').lower() == 'identity', 'response')
                length = response.getheader('Content-Length')
                require(length is None or length.isdecimal() and 0 < int(length) <= MAX_BODY, 'bound')
                raw = response.read(MAX_BODY + 1)
                require(0 < len(raw) <= MAX_BODY and (length is None or len(raw) == int(length)), 'bound')
                value = parse(raw, MAX_BODY)
                require(type(value) is dict and value.get('success') is True
                    and ('errors' not in value or value['errors'] == []), 'response')
                require(metadata(os.fstat(self.ca_fd)) == metadata(self.ca_stat)
                    == metadata(CA_PATH.stat(follow_symlinks=False)), 'CA')
                return value
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

    def close(self):
        os.close(self.ca_fd)


def inventory(api, policy, record_raw, user_id):
    packet = api.request('projects/read', {})
    projects = packet.get('projects')
    require(type(projects) is list and len(projects) <= MAX_PROJECTS
        and all(type(item) is dict for item in projects), 'projects')
    ids = [item.get('projectId') for item in projects]
    require(all(type(value) is int and 0 < value < 2**31 for value in ids)
        and len(set(ids)) == len(ids), 'projects')
    references = policy.referenced_project_ids(projects)
    selected = [item for item in projects if policy.ownership(item, record_raw)]
    rows = []
    for project in sorted(selected, key=lambda item: item['projectId']):
        row = {'project_id': project['projectId'], 'name': project['name'], 'eligible': False}
        try:
            summary = policy.project_summary(project, user_id)
            history = api.request('backtests/list', {'projectId': project['projectId'], 'includeStatistics': False})
            # Validate every selected row even for a protected project whose
            # decision deliberately returns before inspecting its history.
            policy.history_summary(history)
            decision = policy.decision(project, history, user_id=user_id,
                record_bytes=record_raw, referenced_ids=references)
            row.update(summary); row.update(decision)
            backtests = history.get('backtests')
            require(type(backtests) is list and len(backtests) <= 4096, 'history')
            row['backtests'] = [{'backtest_id': item['backtestId'],
                'status': item['status'] if item['status'] in policy.TERMINAL else 'Unrecognized'} for item in backtests]
        except policy.Refused:
            row.update(eligible=False, reason='policy_metadata_refusal')
        except Refused as error:
            row.update(eligible=False, reason=finite(error))
            if type(api.last_http_status) is int:
                row['http_status'] = api.last_http_status
        rows.append(row)
    return {'schema': SCHEMA, 'complete': True, 'all_project_count': len(projects),
        'Analyst_project_count': len(selected), 'out_of_scope_or_unconfirmed_count': len(projects) - len(selected),
        'projects': rows, 'eligible_count': sum(row.get('eligible') is True for row in rows),
        'request_intent_count': api.store.intents,
        'application_dispatch_count': api.store.dispatches, 'physical_request_count_measured': False,
        'statistics_requested': False, 'deletion_performed': False, 'strategy_launch_performed': False,
        'Safari_access': False, 'new_research_looks': 0}


def worker(args):
    policy_raw, record_raw = preflight(args)
    # Execute only the exact already verified public policy bytes; no pycache.
    policy = type(sys)('arv2_r332_qc_cleanup_policy')
    exec(compile(policy_raw, str(POLICY), 'exec'), policy.__dict__)
    store = Store()
    api = None
    try:
        store.write('claim.json', {**binding(args), 'claimed_utc': utc(), 'attempt_consumed': True})
        secret_raw = sys.stdin.buffer.read(4097)
        secret = credentials(parse(secret_raw, 4096))
        api = API(secret, store)
        result = inventory(api, policy, record_raw, int(secret['QC_USER_ID']))
        preflight(args)
        report = {**binding(args), 'finished_utc': utc(), 'result': result}
        report_pin = store.write('report.json', report)
        output = {**binding(args), 'result': result, 'finished_utc': report['finished_utc'],
            'report_pin': report_pin, 'attempt_consumed': True}
        raw = canonical(output) + b'\n'; require(len(raw) <= MAX_OUTPUT, 'bound')
        sys.stdout.buffer.write(raw)
        return 0
    except BaseException as error:
        value = {**binding(args), 'failure_code': finite(error), 'attempt_consumed': True,
            'request_intent_count': store.intents, 'application_dispatch_count': store.dispatches,
            'http_status': api.last_http_status if api is not None else None, 'deletion_performed': False}
        try:
            value['failure_pin'] = store.write('failure.json', value)
        except BaseException:
            pass
        sys.stdout.buffer.write(canonical(value) + b'\n')
        return 2
    finally:
        if api is not None:
            api.close()
        store.close()


def launch(args):
    preflight(args)
    secret = credentials({key: os.environ.get(key) for key in ('QC_USER_ID', 'QC_API_TOKEN')})
    command = ['/usr/bin/sandbox-exec', '-p', native_profile(), PYTHON, '-I', '-B', str(SOURCE), 'worker',
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--policy-sha256', args.policy_sha256, '--record-sha256', args.record_sha256]
    child = subprocess.Popen(command, cwd=ROOT, env=safe_env(), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        raw, err = child.communicate(canonical(secret), timeout=max(1, PARENT_SECONDS - (time.monotonic() - ENTRY)))
    except BaseException:
        child.kill()
        child.wait(timeout=5)
        raise Refused('child_failure') from None
    require(not err and len(raw) <= MAX_OUTPUT and raw.endswith(b'\n') and raw.count(b'\n') == 1, 'output')
    envelope = parse(raw[:-1], MAX_OUTPUT)
    require(type(envelope) is dict and all(envelope.get(key) == value for key, value in binding(args).items()), 'output')
    accepted = child.returncode == 0 and envelope.get('result', {}).get('complete') is True
    if accepted:
        require(type(envelope.get('finished_utc')) is str and len(envelope['finished_utc']) <= 64, 'output')
        require(envelope.get('report_pin') == pin(canonical({**binding(args),
            'finished_utc': envelope['finished_utc'], 'result': envelope['result']})), 'output')
        preflight(args)
    output = {'schema': SCHEMA + '-parent', 'actual_child_exit': child.returncode,
        'output_accepted': accepted, 'child_output_pin': pin(raw), 'child_envelope': envelope}
    final = canonical(output) + b'\n'; require(len(final) <= MAX_OUTPUT + 4096, 'bound')
    sys.stdout.buffer.write(final)
    return 0 if accepted else 2


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('launch', 'worker'))
    for name in ('expected-head', 'caller-sha256', 'policy-sha256', 'record-sha256'):
        parser.add_argument('--' + name, required=True)
    return parser.parse_args()


if __name__ == '__main__':
    try:
        args = cli()
        with alarm(PARENT_SECONDS if args.mode == 'launch' else WORKER_SECONDS):
            code = launch(args) if args.mode == 'launch' else worker(args)
        raise SystemExit(code)
    except SystemExit:
        raise
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'schema': SCHEMA, 'failure_code': finite(error),
            'attempt_reusable': False, 'deletion_performed': False}) + b'\n')
        raise SystemExit(2)
