"""Once-only READ-only current-state reconciliation before the owner's A4.

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
SOURCE = ROOT / 'scripts/observe_arv2_r347_plain_recovery.py'
PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/legacy_six_recovery_state/R347-20261107-A'
SUPPORT = ROOT / '.pytest_cache/r347-recovery-state'
SECURITY = ROOT / 'scripts/arv2_relocation_security.py'
SECURITY_SHA256 = '3435bc07573697d682f25ea15fd2bfd10c5baf8220c184f73ae877016bae4a30'
HOST, PORT = 'www.quantconnect.com', 443
CA_PATH = Path('/Users/sheltonchen/.venvs/trading_agent-py313/lib/python3.13/site-packages/certifi/cacert.pem')
CA_SIZE, CA_SHA256 = 240216, '9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f'
SCHEMA = 'arv2-r347-QC-readonly-plain-recovery-state-v1'
PROJECT = 39054561
PROJECT_NAME = 'ARV2 LEGACY SIX R343-AR100 OCT2026'
CODE_SOURCE_ID = 'Codex R345 R343-AR100 A2'
MIA_NAME = 'Mia'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
OWNER_ROW_SHA256 = '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
SECONDS, HTTP_SECONDS, DNS_SECONDS = 90, 15, 5
MAX_BODY, MAX_OUTPUT = 1024 * 1024, 32768
CREDENTIALS = ('QC_USER_ID', 'QC_API_TOKEN')
ENDPOINTS = ('authenticate', 'projects/read', 'projects/collaboration/read', 'backtests/list', 'files/read')
FINITE = frozenset(('arguments', 'host', 'environment', 'git_state', 'source_pin',
    'source_changed', 'security', 'claim_spent', 'control', 'output', 'bound', 'deadline',
    'credentials', 'CA', 'dns', 'transport', 'http_status', 'response', 'endpoint',
    'authentication', 'project', 'organization', 'collaborators', 'history', 'files', 'close', 'unknown'))
FALSE_FLAGS = {key: False for key in ('privacy_proven', 'processing_rights_proven',
    'exclusive_resource_lease', 'strategy_launch_performed', 'source_uploaded', 'access_acceptance_granted',
    'lock_acquire_performed', 'lock_release_performed', 'permission_change_performed',
    'backtest_completed', 'point_in_time_proven', 'formal_forward_ready', 'paper_or_live_ready',
    'candidate_write_gates_passed', 'source_context_approved', 'attempt_budget_reset')}
SAFE_OBSERVATION = None

# Exact public R343-B AR100 summary, not a new current cloud observation.
# Public provenance: arv2_r345_legacy_six_plan_v3.json source_summary.cells[1].
B_SOURCE_PINS = {
    'accepted_risk_matched_diagnostics.py': {'byte_count':16928,'sha256':'6ee6b8eb67c431efd2e07448bb854c3cbf2789eb0b90071359f1aba75ab8e8f8'},
    'accepted_risk_order_level_core.py': {'byte_count':30558,'sha256':'07108cbc0aa60c1e2cf8d3cf53cdd5ce25591dccc2d1cb05b5f1d2d96bb24d1f'},
    'accepted_risk_order_level_forced_exit.py': {'byte_count':16313,'sha256':'e421721bb0f3cd29dbca0f2c9fdff87c52a3c298fc94b50f57213d7e22889649'},
    'accepted_risk_order_level_input_runtime.py': {'byte_count':22747,'sha256':'ebd509b8a8fab8534da0703fb2430d1e894c04f4e64e6e5c555a220202b78d56'},
    'accepted_risk_preliminary_qc_figi.py': {'byte_count':25920,'sha256':'5958786ddd787a45a90d636a36d07136841ee79cf1ce904c8d749d47045ff81d'},
    'accepted_risk_preliminary_rating_evaluator.py': {'byte_count':53466,'sha256':'d706a19324f59ac36e910b715c3ee17312a7126444287d9eba18c8fc8d06c21a'},
    'accepted_risk_preliminary_rating_policy.py': {'byte_count':4649,'sha256':'be082935781e8d406e5c6126fe33bb08866bc765b1d1ac162a96df4c0c988fd7'},
    'accepted_risk_sequential_r055_score.py': {'byte_count':5858,'sha256':'2799c47e350dcb18fbe7b1bcb2b4c4a7bd3eb5a6ba3bf5913adff3da1d3e56dc'},
    'accepted_risk_simulated_moo_executor.py': {'byte_count':30938,'sha256':'3bca2edacb1db5f4ce3d6eb5b7facc2178319f90b459545fe40be3651bac0cc5'},
    'accepted_risk_six_universe_gate.py': {'byte_count':27014,'sha256':'f40b840c28de013f1a35f43102d09bf9f0225a43ae42f4b13efc9e51d4d5a2b6'},
    'accepted_risk_six_universe_gate_evaluator.py': {'byte_count':40535,'sha256':'a5c634817535f6234e6cdfe5f2785bd0ef3f14fa2647bceb50d8b98ffe99d2ba'},
    'accepted_risk_six_universe_order_bridge_qc_runtime.py': {'byte_count':18128,'sha256':'ecbb56f81fcb0de3164594dbdd9dd31ed3ed907de1a0ea31613de45d0d10ac45'},
    'accepted_risk_six_universe_order_qc_runtime.py': {'byte_count':61527,'sha256':'6469cc3195317cf8e0dddf28134d56d0ac533adb738eeffb89cb7367db63d3e8'},
    'accepted_risk_six_universe_order_targets.py': {'byte_count':18443,'sha256':'af92ab6a1cda0618b90f45db57fb801984857228bc125840635a860947d973f0'},
    'accepted_risk_six_universe_order_tilt_qc_runtime.py': {'byte_count':8066,'sha256':'1a60ae66f05bc79f0a05004488922abbd21c5d501f07ef67df4180dac8782ded'},
    'accepted_risk_six_universe_order_tilt_targets.py': {'byte_count':16450,'sha256':'5976329e6339fea44142398cc7833d23c633f4ebf2893bb7c06a8f0a4a3535f5'},
    'legacy_six_october_reporting.py': {'byte_count':18635,'sha256':'0a61059da3539ba30a8ca7d917484d47a7305676e873f7c85bb27f82ff5a615c'},
    'main.py': {'byte_count':8133,'sha256':'8d9d8230534bd4ff2fe9d35b26852191239687499dea7bc3f5ba7f8fd7755b21'},
}
UPLOADED_NAMES = tuple(sorted(B_SOURCE_PINS)[:3])
INPUT_NAME = 'accepted_risk_order_level_input_runtime.py'
DEFAULT_MAIN = '''# region imports
from AlgorithmImports import *
# endregion

class BasicTemplateAlgorithm(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2021, 1, 1)
        self.set_cash(100000)

        self.add_equity("SPY", Resolution.DAILY)

    def on_data(self, data: Slice):
        if not self.portfolio.invested:
            self.set_holdings("SPY", 1)
'''


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
        'expected_code_source_sha256': sha(CODE_SOURCE_ID.encode('ascii')),
        'owner_row_sha256': OWNER_ROW_SHA256, 'security_source_sha256': SECURITY_SHA256,
        'native_policy_sha256': sha(native_profile().encode()), 'endpoints': list(ENDPOINTS),
        'maximum_requests': 5, 'seconds': SECONDS, 'request_seconds': HTTP_SECONDS,
        'maximum_response_bytes': MAX_BODY, 'maximum_output_bytes': MAX_OUTPUT,
        'CA': {'byte_count': CA_SIZE, 'sha256': CA_SHA256},
        'purpose': 'fresh_current_own_project_access_history_and_code_hashes_before_separate_A4_freeze',
        'credentials': 'existing_environment_only_after_exclusive_fsynced_claim_no_Keychain_reader',
        'claim_consumption': 'exclusive_leaf_allocation_consumes_use_even_without_provider_contact',
        'terminal_policy': 'any_failure_or_ambiguity_spends_use_no_retry_cleanup_or_alternate_leaf',
        'general_rows': 'bounded_types_keys_fullrow_hash_and_exact_known_A2_match_booleans_no_remote_values',
        'history_policy': 'exact_project_empty_current_history_no_statistics_results_logs_source_or_data',
        'file_policy': 'current_source_bytes_hash_only_no_code_retention_no_codeSourceId_no_mutation',
        'file_encoding': 'exact_UTF8_of_returned_API_text_not_at_rest_byte_attestation',
        'B_source_pins': B_SOURCE_PINS, 'expected_prior_uploaded_names': list(UPLOADED_NAMES),
        'default_main_pin': pin(DEFAULT_MAIN.encode('ascii')), 'input_stub_pin': pin(b'#'),
        'known_Mia_name_sha256': sha(MIA_NAME.encode('ascii')),
        'unrecognized_files': 'hash_names_and_contents_then_refuse_never_write_or_overwrite_remote_files',
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
            re.fullmatch('(intent|dispatch)-[0-4][.]json', name), 'output')
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
        require(self.intents < 5, 'bound')
        self.write(f'intent-{self.intents}.json', {'endpoint': endpoint, 'project_id': project_id,
            'ordinal': self.intents, 'utc': utc()})
        self.intents += 1
    def attempt(self, endpoint, project_id):
        require(self.application_dispatch_count < self.intents, 'bound')
        self.write(f'dispatch-{self.application_dispatch_count}.json', {'endpoint': endpoint,
            'project_id': project_id, 'ordinal': self.application_dispatch_count, 'utc': utc()})
        self.application_dispatch_count += 1
    def close(self):
        failed = False
        for _, fd, _, _, _ in self.leaves:
            try: os.close(fd)
            except OSError: failed = True
        self.leaves.clear()
        for fd, _, _, _, _ in reversed(self.chain):
            try: os.close(fd)
            except OSError: failed = True
        self.chain.clear(); self.fd = None
        require(not failed, 'close')
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
            or (endpoint in ('projects/read', 'projects/collaboration/read', 'files/read') and set(payload) == {'projectId'}
                and type(payload['projectId']) is int and payload['projectId'] == PROJECT)
            or (endpoint == 'backtests/list' and set(payload) == {'projectId', 'includeStatistics'}
                and type(payload['projectId']) is int and payload['projectId'] == PROJECT
                and payload['includeStatistics'] is False)), 'endpoint')
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


KNOWN_FIELDS = ('uid', 'owner', 'name', 'publicId', 'codeSourceId', 'permission',
    'liveControl', 'profileImage', 'email', 'bio')
STATUS_NAMES = ('Completed.', 'Runtime Error', 'BuildError', 'In Queue...', 'In Progress...')


def field_type(row, key):
    if key not in row:
        return 'absent'
    return {type(None): 'null', bool: 'bool', int: 'int', float: 'float',
        str: 'string', list: 'list', dict: 'object'}.get(type(row[key]), 'other')


def flag_class(row, key):
    return 'absent' if key not in row else 'true' if row[key] is True else 'false' if row[key] is False else 'other'


def general_row(row, user_id):
    require(type(row) is dict and len(row) <= 128, 'collaborators')
    raw = canonical(row)
    require(0 < len(raw) <= 65536, 'bound')
    permission = row.get('permission')
    return {'canonical_row_pin': pin(raw),
        'known_keys_present': [key for key in KNOWN_FIELDS if key in row],
        'unknown_key_count': sum(key not in KNOWN_FIELDS for key in row),
        'known_field_types': {key: field_type(row, key) for key in KNOWN_FIELDS},
        'uid_equals_authenticated_owner': type(row.get('uid')) is int and row['uid'] == int(user_id),
        'uid_equals_known_A2_code_source': type(row.get('uid')) is str and row['uid'] == CODE_SOURCE_ID,
        'owner_class': flag_class(row, 'owner'), 'liveControl_class': flag_class(row, 'liveControl'),
        'permission_class': 'absent' if 'permission' not in row else permission
            if type(permission) is str and permission in ('read', 'write') else 'other',
        'known_A2_code_source_matches': {key: type(row.get(key)) is str and row[key] == CODE_SOURCE_ID
            for key in ('name', 'publicId', 'codeSourceId')},
        'known_Mia_matches': {key: type(row.get(key)) is str and row[key] == MIA_NAME
            for key in ('name', 'publicId', 'codeSourceId')}}


def project_summary(project_packet, dedicated_packet, user_id):
    rows = scoped(project_packet).get('projects')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project')
    row = rows[0]
    require(type(row.get('projectId')) is int and row['projectId'] == PROJECT
        and row.get('name') == PROJECT_NAME and row.get('language') == 'Py'
        and row.get('owner') is True and type(row.get('ownerId')) is int
        and row['ownerId'] == int(user_id), 'project')
    organization(row.get('organizationId'))
    require('public' not in row or type(row['public']) is bool, 'project')
    require(type(row.get('codeRunning')) is bool, 'project')
    general = row.get('collaborators')
    require(type(general) is list and len(general) <= 8, 'collaborators')
    general_observations = [general_row(value, user_id) for value in general]
    dedicated = scoped(dedicated_packet)
    dedicated_rows = dedicated.get('collaborators')
    require(type(dedicated_rows) is list and 1 <= len(dedicated_rows) <= 8
        and all(type(value) is dict and type(value.get('owner')) is bool for value in dedicated_rows), 'collaborators')
    owners = [value for value in dedicated_rows if value['owner'] is True]
    require(len(owners) == 1, 'collaborators')
    owner = owners[0]
    require(owner.get('owner') is True and type(owner.get('uid')) is int
        and owner['uid'] == row['ownerId'] and type(owner.get('permission')) is str
        and owner['permission'] in ('read', 'write')
        and type(dedicated.get('userPermissions')) is str
        and dedicated['userPermissions'] in ('read', 'write'), 'collaborators')
    general_owners = [value for value in general if value.get('owner') is True]
    owner_agreement = len(general_owners) == 1 and type(general_owners[0].get('uid')) is int \
        and general_owners[0]['uid'] == row['ownerId']
    return {'exact_owned_python_project_matches': True, 'organization_matches': True,
        'project_id': PROJECT, 'dedicated_owner_only': len(dedicated_rows) == 1,
        'dedicated_owner_row_pin': pin(canonical(owner) + b'\n'),
        'dedicated_owner_pin_matches': sha(canonical(owner) + b'\n') == OWNER_ROW_SHA256,
        'semantic_owner_agreement': owner_agreement,
        'whole_owner_row_agreement': len(general_owners) == 1 and canonical(general_owners[0]) == canonical(owner),
        'current_editor_idle': row['codeRunning'] is False,
        'private_field_present_and_false': 'public' in row and row['public'] is False,
        'project_field_types': {key: field_type(row,key) for key in ('public','codeRunning','owner','ownerId',
            'libraries','isLibrary','leanEnvironment','lastLiveDeployment')},
        'project_flags': {key: flag_class(row,key) for key in ('public','codeRunning','owner','isLibrary')},
        'requester_permission_class': dedicated['userPermissions'],
        'requester_liveControl_class': flag_class(dedicated,'userLiveControl'),
        'general_collaborators_authoritative': False,
        'general_row_count': len(general), 'dedicated_row_count': len(dedicated_rows),
        'general_rows_pin': pin(canonical(general)), 'dedicated_rows_pin': pin(canonical(dedicated_rows)),
        'general_rows': general_observations,
        'dedicated_rows': [general_row(value,user_id) for value in dedicated_rows],
        'unreviewed_observation': True}


def history_summary(packet):
    packet = scoped(packet)
    rows = packet.get('backtests')
    require(type(rows) is list and len(rows) <= 64
        and all(type(row) is dict for row in rows)
        and ('count' not in packet or type(packet['count']) is int and packet['count'] == len(rows)), 'history')
    counts = {name: sum(row.get('status') == name for row in rows) for name in STATUS_NAMES}
    counts['other'] = sum(row.get('status') not in STATUS_NAMES for row in rows)
    require(not rows, 'history')
    return {'current_job_count': 0, 'current_job_status_counts': counts,
        'include_statistics_requested': False, 'empty_current_history': True}


def files_summary(packet):
    packet = scoped(packet)
    rows = packet.get('files')
    require(type(rows) is list and len(rows) <= 24
        and ('count' not in packet or type(packet['count']) is int and packet['count'] == len(rows)), 'files')
    observed, unknown, names = [], [], set()
    for row in rows:
        require(type(row) is dict and type(row.get('name')) is str
            and 0 < len(row['name']) <= 256
            and row['name'] not in names and type(row.get('content')) is str
            and len(row['content']) <= 128*1024
            and ('projectId' not in row or type(row['projectId']) is int and row['projectId'] == PROJECT), 'files')
        try:
            name, raw = row['name'], row['content'].encode('utf-8')
            name_raw = name.encode('utf-8')
        except UnicodeError: raise Refused('files') from None
        require(len(name_raw) <= 1024 and len(raw) <= 128*1024, 'files')
        names.add(name)
        content_pin = pin(raw)
        if name not in B_SOURCE_PINS:
            unknown.append({'name_sha256':sha(name_raw), **content_pin})
            continue
        matches_B = content_pin == B_SOURCE_PINS[name]
        classification = 'B_source_exact' if matches_B else 'other_source'
        if name == 'main.py' and raw == DEFAULT_MAIN.encode('ascii'):
            classification = 'known_default_main'
        elif name == INPUT_NAME and raw == b'#':
            classification = 'known_one_byte_stub'
        observed.append({'project_path':name, **content_pin, 'matches_B_source':matches_B,
            'classification':classification})
    observed.sort(key=lambda value:value['project_path'])
    vector = [{key:value[key] for key in ('project_path','byte_count','sha256')} for value in observed]
    by_name = {value['project_path']:value for value in observed}
    return {'source_file_count':len(rows), 'known_source_file_count':len(observed),
        'unrecognized_file_count':len(unknown),'unrecognized_files':unknown,
        'files':observed,'source_inventory':vector,'source_inventory_pin':pin(canonical(vector)),
        'three_prior_B_sources_match':all(name in by_name and by_name[name]['matches_B_source'] for name in UPLOADED_NAMES),
        'main_classification':by_name['main.py']['classification'] if 'main.py' in by_name else 'absent',
        'input_runtime_classification':by_name[INPUT_NAME]['classification'] if INPUT_NAME in by_name else 'absent',
        'raw_code_retained':False,'codeSourceId_supplied':False}


def observe(api, user_id):
    global SAFE_OBSERVATION
    authentication = api.request('authenticate', {})
    require(type(authentication) is dict and authentication.get('success') is True
        and ('authenticated' not in authentication or authentication['authenticated'] is True), 'authentication')
    project = api.request('projects/read', {'projectId': PROJECT})
    dedicated = api.request('projects/collaboration/read', {'projectId': PROJECT})
    summary = project_summary(project, dedicated, user_id)
    history = history_summary(api.request('backtests/list', {'projectId': PROJECT, 'includeStatistics': False}))
    files = files_summary(api.request('files/read', {'projectId': PROJECT}))
    SAFE_OBSERVATION = {'authentication_observed':True, **summary, **history, **files}
    require(files['unrecognized_file_count'] == 0, 'files')
    return SAFE_OBSERVATION


def run(args):
    global SAFE_OBSERVATION
    SAFE_OBSERVATION = None
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
                    'response_pins': [] if api is None else api.responses,
                    'observation':SAFE_OBSERVATION, **FALSE_FLAGS}
                failure_pin = store.write('failure.json', result)
                return {'result': result, 'failure': failure_pin}, 2
            finally:
                if api is not None: api.close()


RESULT_KEYS = frozenset(('schema','expected_head','caller_sha256','profile_sha256','complete',
    'attempt_consumed','request_intent_count','application_dispatch_count','physical_request_count_measured',
    'http_statuses','response_pins','authentication_observed','exact_owned_python_project_matches',
    'organization_matches','project_id','dedicated_owner_only','dedicated_owner_row_pin',
    'dedicated_owner_pin_matches','semantic_owner_agreement','whole_owner_row_agreement',
    'current_editor_idle','private_field_present_and_false','project_field_types','project_flags',
    'requester_permission_class','requester_liveControl_class','general_collaborators_authoritative',
    'general_row_count','dedicated_row_count','general_rows_pin','dedicated_rows_pin','general_rows',
    'dedicated_rows','unreviewed_observation','current_job_count','current_job_status_counts',
    'include_statistics_requested','empty_current_history','source_file_count','known_source_file_count',
    'unrecognized_file_count','unrecognized_files','files','source_inventory','source_inventory_pin',
    'three_prior_B_sources_match','main_classification','input_runtime_classification','raw_code_retained',
    'codeSourceId_supplied',*FALSE_FLAGS))


def validate_output(raw, actual_exit, args):
    """Validate ORIGINAL observed stdout plus ACTUAL exit, never reread a leaf.

    This is self-consistency of the original output envelope, not independent
    process attestation or authentication of a rehashed edited envelope.
    """
    require(type(actual_exit) is int and actual_exit == 0, 'output')
    require(type(raw) is bytes and 2 < len(raw) <= MAX_OUTPUT and raw.endswith(b'\n\n'), 'output')
    envelope = parse(raw[:-2], MAX_OUTPUT)
    require(type(envelope) is dict and set(envelope) == {'result','report'}
        and canonical(envelope) + b'\n\n' == raw, 'output')
    result = envelope['result']; expected = binding(args)
    require(type(result) is dict and set(result) == RESULT_KEYS
        and all(result.get(key) == value for key,value in expected.items())
        and result['complete'] is True and result['attempt_consumed'] is True
        and all(result[key] is False for key in FALSE_FLAGS)
        and result['unreviewed_observation'] is True
        and result['physical_request_count_measured'] is False
        and result['raw_code_retained'] is False and result['codeSourceId_supplied'] is False
        and type(result['request_intent_count']) is int and result['request_intent_count'] == 5
        and type(result['application_dispatch_count']) is int and result['application_dispatch_count'] == 5
        and type(result['current_job_count']) is int and result['current_job_count'] == 0
        and type(result['unrecognized_file_count']) is int and result['unrecognized_file_count'] == 0
        and result['source_inventory_pin'] == pin(canonical(result['source_inventory']))
        and envelope['report'] == pin(canonical(result)), 'output')
    require(result['http_statuses'] == [{'endpoint':name,'http_status':200} for name in ENDPOINTS], 'output')
    return {'schema':SCHEMA+'-output','output_envelope_validated':True,'actual_exit':actual_exit,
        'report_pin':envelope['report'],'observation':result,
        'qualification':'original_stdout_self_consistency_not_independent_disk_or_process_attestation'}


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
