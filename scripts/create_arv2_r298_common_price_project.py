"""One bounded private-default QC project creation; no source/data/job action.

This uninvoked caller needs a separate committed run freeze and genuine source,
rights and resource gates. It never treats creation as price/backtest readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import requests
from research.quantconnect import QuantConnectCredentials, build_auth_headers, API_BASE
from scripts import prepare_arv2_r298_common_price_sidecar_v2 as sidecar
from scripts import arv2_r298_ar_source_binding as anchor
from scripts import diagnose_arv2_r298_public_transport_v2 as public_transport
from scripts import observe_arv2_r298_native_qc_rights as technical
from scripts import arv2_r298_collaborator_access as owner_policy

admitted, environment, security = sidecar.admitted, sidecar.environment, sidecar.ap.security
capture, capture_support = sidecar.ap.previous.capture, sidecar.ap.previous.capture_support
canonical, sha, parse, metadata = sidecar.canonical, sidecar.sha, sidecar.parse, sidecar.metadata
SOURCE = ROOT / 'scripts/create_arv2_r298_common_price_project.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_common_price_project/R326-20261027-AT'
SCHEMA = 'arv2-r326-common-price-project-at-v1'
PROJECT_NAME = 'ARV2 R326 COMMON RAW 20261027'
REFERENCE_ID, REFERENCE_NAME = 38522505, 'ARV2 R326 FIVE SOURCE RAW 20261027'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
ANCHOR_SHA256 = '52ae31ddb440e1ecaf693d54fb6cf6d48ee377813d8614e7ce3cee5a02d68d76'
FACT_SHA256 = '19194ca0fc562b4b0fed8331d7c6e725c3dd7cc31fada7fa519a08acc10d28b3'
SIDECAR_OUTPUT_SHA256 = '70e6def0fe2621965904e31fe8121c7713c5201b9b151397766f78091e7ab843'
AR_OUTPUT_PIN = {'byte_count': 28655, 'sha256': '5c0a070c1d2f03e4a78adb9400db8a94c4d11b334e1a777a7f0fb65a281bc52b'}
SECONDS, WORKER_SECONDS, VALIDATOR_SECONDS = 120, 90, 20
MAX_OUTPUT, MAX_BODY, MAX_CREDENTIAL = 32768, 1024 * 1024, 4096
PYTHON, CA_PATH = sidecar.PYTHON, public_transport.CA_PATH
CA_BYTES, CA_SHA256 = 240216, '9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f'
STAGES = ('authenticate', 'reference', 'reference-collaboration', 'create', 'created', 'created-collaboration')
ENDPOINTS = ('authenticate', 'projects/read', 'projects/collaboration/read', 'projects/create', 'projects/read', 'projects/collaboration/read')
FALSE_FLAGS = {'data_uploaded': False, 'source_installed': False, 'compile_created': False,
    'capacity_read': False, 'backtest_created': False, 'permissions_changed': False,
    'organization_paid_or_manager_status_proven': False, 'licensed_transfer_granted': False,
    'price_coverage_ready': False, 'strategy_ready': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'physical_request_count_measured': False}
FINITE = frozenset(('host', 'arguments', 'source', 'git', 'deadline', 'environment', 'claim_spent',
    'control', 'credential_handoff', 'inherited', 'CA', 'request', 'http_status', 'http_refused',
    'response', 'bound', 'organization', 'owner', 'project', 'collaboration', 'public_project',
    'libraries', 'created_ambiguous', 'child', 'output', 'os_error', 'unknown'))
NEW_PINS = {'scripts/prepare_arv2_r298_common_price_sidecar_v2.py': '25eec980ccc9dcf9b6e15c7618597bfe050954bd160be6b32f07452e7ed96edc',
    'scripts/arv2_r298_ar_source_binding.py': ANCHOR_SHA256,
    'scripts/observe_arv2_r298_native_qc_rights.py': 'b3a9d74363018e0a2064ae3dd5ab1bbfb4914d0f772363d07eb3be86221e8443'}


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    if type(error) is admitted.helpers.Deadline: return 'deadline'
    if type(error) is environment.EnvironmentRefused: return 'environment'
    if type(error) is Refused:
        values = BaseException.args.__get__(error)
        return values[0] if len(values) == 1 and type(values[0]) is str and values[0] in FINITE else 'unknown'
    return 'os_error' if isinstance(error, OSError) else 'unknown'


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline) and 0 < deadline - time.monotonic() <= SECONDS, 'deadline')
    return deadline - time.monotonic()


def source_binding():
    fact, output = anchor.observed_fact(), anchor.sidecar_output()
    require(sha(canonical(fact)) == FACT_SHA256 and sha(canonical(output)) == SIDECAR_OUTPUT_SHA256, 'source')
    raw = canonical(output) + b'\n'
    require({'byte_count': len(raw), 'sha256': sha(raw)} == AR_OUTPUT_PIN, 'source')
    for role in ('AR_producer', 'AR_native_validator', 'AS_actual'):
        try: public_transport._actual_metadata(fact[role])
        except Exception: raise Refused('source') from None
        actual = fact[role]
        require(type(actual['actual_exit']) is int and actual['actual_exit'] == 0 and actual['bound'] is None
            and actual['spawn_observed'] is True and actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == sha(b'')
            and actual['stdout_bytes'] == AR_OUTPUT_PIN['byte_count'] and actual['stdout_sha256'] == AR_OUTPUT_PIN['sha256'], 'source')
    require(fact['AR_producer']['completion_observed_at'] <= fact['AR_native_validator']['dispatched_at']
        and fact['AR_native_validator']['completion_observed_at'] <= fact['AS_actual']['dispatched_at']
        and fact['complete_original_payload_recovered'] is fact['source_guards_normal_return'] is True, 'source')
    args = SimpleNamespace(**{key: fact['AR_binding'][key] for key in ('expected_head', 'caller_sha256', 'profile_sha256')})
    try: sidecar.validate_output(raw, 0, args)
    except Exception: raise Refused('source') from None
    require(all(fact[key] is False for key in ('QC_transfer_granted', 'QC_processing_rights_granted',
        'new_operation_or_read_granted', 'price_input_admitted', 'formal_forward_ready', 'paper_or_live_ready')), 'source')
    return {'AR_fact_sha256': FACT_SHA256, 'AR_output_pin': dict(AR_OUTPUT_PIN),
        'AR_binding': fact['AR_binding'], 'AS_binding': fact['AS_binding'],
        'AR_manifest_pin': fact['manifest_pin'], 'AR_catalog_pin': fact['catalog_pin'],
        'source_prices_are_not_admitted': True}


def pins():
    values = sidecar.pins()
    for name, value in NEW_PINS.items():
        require(name not in values or values[name] == value, 'source'); values[name] = value
    return values


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH, 'control': str(CONTROL),
        'source_pins': pins(), 'source_binding': source_binding(), 'project_name': PROJECT_NAME,
        'reference_project_id': REFERENCE_ID, 'organization_sha256': ORGANIZATION_SHA256,
        'stages': list(zip(STAGES, ENDPOINTS)), 'maximum_dispatches': 6, 'one_create': True,
        'create_fields': ['name', 'language', 'organizationId'], 'privacy': 'documented_private_default_missing_API_field_is_UNKNOWN_not_false',
        'before_licensed_transfer': 'separate_current_explicit_private_observation_and_frozen_transfer_required',
        'CA': {'path': str(CA_PATH), 'byte_count': CA_BYTES, 'sha256': CA_SHA256},
        'CA_trust': 'held_pinned_bytes_in_SSLContext_cadata_no_default_CA_or_client_certificate',
        'parent_seconds': SECONDS, 'worker_seconds': WORKER_SECONDS, 'validator_seconds': VALIDATOR_SECONDS,
        'credentials': 'trusted_env_only_once_after_claim_and_AR_AS_source_binding_owned_pipe_not_output',
        'no_retry_or_replacement_project': True, 'uninterruptible_IO_or_host_suspension_qualification': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': args.profile_sha256}


def preflight(args, deadline):
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE and not admitted.v5._under_test(), 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and all(type(getattr(args, key)) is str and re.fullmatch('[0-9a-f]{64}', getattr(args, key))
            for key in ('caller_sha256', 'profile_sha256')), 'arguments')
    environment._require_environment()
    for cmd, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)), (['branch', '--show-current'], admitted.frozen.BRANCH),
            (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(admitted.v5._git(cmd, deadline).decode('ascii').strip() == expected, 'git')
    for name, value in pins().items(): require(sha((ROOT / name).read_bytes()) == value, 'source')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256
        and sha(admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline, 128 * 1024)) == args.caller_sha256
        and sha(canonical(profile_record())) == args.profile_sha256, 'source')
    remaining(deadline)


def _read(fd, maximum):
    info = os.fstat(fd); require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= maximum, 'bound')
    raw = os.pread(fd, maximum + 1, 0); require(len(raw) == info.st_size and metadata(os.fstat(fd)) == metadata(info), 'control')
    return raw


def _write(fd, raw):
    view = memoryview(raw)
    while view:
        count = os.write(fd, view); require(count > 0, 'control'); view = view[count:]
    os.fsync(fd)


class Store:
    def __init__(self):
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY); self.files, self.chain = {}, []
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                path = Path(*CONTROL.parts[:index + 1])
                if path in (CONTROL.parent, CONTROL):
                    try: os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    except FileExistsError: require(path != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt; self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd; self.security = security.snapshot(fd); self.verify()
        except BaseException: os.close(fd); raise
    def __enter__(self): return self
    def __exit__(self, *_):
        for row in self.files.values(): os.close(row[0])
        os.close(self.fd)
    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(self.fd)) == metadata(os.fstat(other))
                and stat.S_IMODE(os.fstat(other).st_mode) == 0o700 and os.fstat(other).st_uid == os.getuid()
                and security.snapshot(self.fd) == self.security and set(os.listdir(other)) == set(self.files), 'control')
            for name, (fd, old, snap) in self.files.items():
                require(metadata(os.fstat(fd)) == old == metadata(os.stat(name, dir_fd=other, follow_symlinks=False))
                    and security.snapshot(fd) == snap, 'control')
        finally: os.close(other)
    def create(self, name, raw=b''):
        self.verify(); require(name in ('claim.json', 'worker-intent.json', 'worker-started.json', 'stages.jsonl', 'worker-result.json', 'report.json')
            and name not in self.files and type(raw) is bytes and len(raw) <= MAX_OUTPUT, 'control')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            require(os.fstat(fd).st_uid == os.getuid() and os.fstat(fd).st_nlink == 1 and stat.S_IMODE(os.fstat(fd).st_mode) == 0o600, 'control')
            snap = security.snapshot(fd); _write(fd, raw); os.fsync(self.fd)
            require(_read(fd, MAX_OUTPUT) == raw and security.snapshot(fd) == snap, 'control')
            self.files[name] = (fd, metadata(os.fstat(fd)), snap)
        except BaseException: os.close(fd); raise
        self.verify(); return {'byte_count': len(raw), 'sha256': sha(raw)}
    def refresh_worker(self):
        for name in ('worker-started.json', 'stages.jsonl', 'worker-result.json'):
            fd, old, snap = self.files[name]; current = metadata(os.fstat(fd))
            require(current[:6] == old[:6] and current[9] == old[9] and old[6] <= current[6] <= MAX_OUTPUT
                and security.snapshot(fd) == snap, 'control')
            self.files[name] = (fd, current, snap)
        self.verify()


def native_profile(mode):
    require(mode in ('worker', 'validate'), 'arguments')
    base = '(version 1)(allow default)'
    base += ('(deny network-bind)(deny network-inbound)(deny network-outbound (require-all '
        '(require-not (remote tcp "*:443"))(require-not (remote tcp "*:53"))(require-not (remote udp "*:53"))'
        '(require-not (literal "/private/var/run/mDNSResponder"))))') if mode == 'worker' else '(deny network*)'
    for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'):
        base += '(deny file-read* file-write* (subpath "' + path + '"))'
    base += '(deny process-exec (literal "/usr/bin/security"))'
    exceptions = '(require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))(require-not (literal "/dev/null"))'
    if mode == 'worker':
        exceptions += ''.join('(require-not (literal "' + str(CONTROL / name) + '"))' for name in ('worker-started.json', 'stages.jsonl', 'worker-result.json'))
    base += '(deny file-write* (require-all ' + exceptions + '))'
    leaves = [] if mode == 'validate' else [CONTROL, *(CONTROL / name for name in ('claim.json', 'worker-intent.json', 'worker-started.json', 'stages.jsonl', 'worker-result.json'))]
    return base + technical._artifact_policy(leaves)


def _ca(fd):
    info = os.fstat(fd); require(stat.S_ISREG(info.st_mode) and info.st_size == CA_BYTES
        and metadata(info) == metadata(os.stat(CA_PATH, follow_symlinks=False)), 'CA')
    snap = security.snapshot(fd); raw = _read(fd, CA_BYTES)
    require(len(raw) == CA_BYTES and sha(raw) == CA_SHA256 and security.snapshot(fd) == snap, 'CA')
    return raw, metadata(info), snap


def _credential_value(values):
    require(type(values) is dict and set(values) == {'QC_USER_ID', 'QC_API_TOKEN'}, 'credential_handoff')
    try: credentials = QuantConnectCredentials.from_env(values)
    except Exception: raise Refused('credential_handoff') from None
    require(credentials.user_id.isascii() and credentials.user_id.isdecimal() and 0 < int(credentials.user_id) < 2 ** 63
        and 8 <= len(credentials.api_token) <= 1024 and all(33 <= ord(char) <= 126 for char in credentials.api_token), 'credential_handoff')
    return credentials


def _credential_packet(environ):
    try: values = capture_support._credential_handoff(environ)
    except Exception: raise Refused('credential_handoff') from None
    credentials = _credential_value(values)
    raw = canonical({'QC_USER_ID': credentials.user_id, 'QC_API_TOKEN': credentials.api_token})
    require(0 < len(raw) <= MAX_CREDENTIAL, 'credential_handoff'); values.clear(); return raw


def _inherited(args):
    fds = (args.control_fd, args.claim_fd, args.intent_fd, args.started_fd, args.stages_fd, args.result_fd, args.ca_fd, args.credential_fd)
    require(all(type(fd) is int and fd > 2 for fd in fds) and len(set(fds)) == len(fds), 'inherited')
    require(not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'environment')
    info = os.fstat(args.control_fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
        and metadata(info) == metadata(os.stat(CONTROL, follow_symlinks=False)), 'inherited')
    for fd, name in ((args.claim_fd, 'claim.json'), (args.intent_fd, 'worker-intent.json'), (args.started_fd, 'worker-started.json'),
            (args.stages_fd, 'stages.jsonl'), (args.result_fd, 'worker-result.json')):
        row = os.fstat(fd); require(stat.S_ISREG(row.st_mode) and row.st_uid == os.getuid() and row.st_nlink == 1
            and stat.S_IMODE(row.st_mode) == 0o600 and metadata(row) == metadata(os.stat(name, dir_fd=args.control_fd, follow_symlinks=False)), 'inherited')
        security.snapshot(fd)
    require(_read(args.claim_fd, MAX_OUTPUT) == canonical(binding(args))
        and _read(args.intent_fd, MAX_OUTPUT) == canonical({'binding': binding(args), 'source_binding_sha256': sha(canonical(source_binding())), 'stages': list(STAGES)})
        and all(os.fstat(fd).st_size == 0 for fd in (args.started_fd, args.stages_fd, args.result_fd)), 'inherited')
    pipe = os.fstat(args.credential_fd); require(stat.S_ISFIFO(pipe.st_mode) and pipe.st_uid == os.getuid(), 'inherited')
    _ca(args.ca_fd); _write(args.started_fd, canonical(binding(args))); os.fsync(args.control_fd)


class OwnedAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, ca_raw):
        require(type(ca_raw) is bytes and len(ca_raw) == CA_BYTES and sha(ca_raw) == CA_SHA256, 'CA')
        self.ca_ascii = ca_raw.decode('ascii'); self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.check_hostname = True; self.context.verify_mode = ssl.CERT_REQUIRED
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=self.ca_ascii)
        super().__init__(max_retries=0, pool_connections=1, pool_maxsize=1)
    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        kwargs['ssl_context'] = self.context
        return super().init_poolmanager(connections, maxsize, block, **kwargs)
    def cert_verify(self, conn, url, verify, cert):
        require(url.startswith(API_BASE + '/') and verify is True and cert is None, 'request')
        conn.cert_reqs, conn.ca_certs, conn.ca_cert_dir, conn.ca_cert_data = 'CERT_REQUIRED', None, None, self.ca_ascii
    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        require(verify is True and cert is None and request.url.startswith(API_BASE + '/'), 'request')
        host, kwargs = super().build_connection_pool_key_attributes(request, verify, cert)
        kwargs.update(ssl_context=self.context, cert_reqs='CERT_REQUIRED', ca_certs=None,
            ca_cert_dir=None, ca_cert_data=self.ca_ascii)
        return host, kwargs
    def proxy_manager_for(self, *args, **kwargs): raise Refused('request')


class OwnedSession(requests.Session):
    def resolve_redirects(self, *args, **kwargs): return iter(())


def _session(ca_raw):
    value = OwnedSession(); value.trust_env, value.auth, value.verify, value.cert, value.max_redirects = False, None, True, None, 0
    value.headers.clear(); value.cookies.clear(); value.proxies.clear(); value.params.clear(); value.adapters.clear()
    value.hooks = {'response': []}; value.mount('https://', OwnedAdapter(ca_raw)); return value


def _session_check(value, url):
    adapter = value.get_adapter(url)
    require(type(value) is OwnedSession and value.trust_env is False and value.auth is None and value.verify is True
        and value.cert is None and value.max_redirects == 0 and not value.headers and not value.cookies
        and not value.proxies and not value.params and value.hooks == {'response': []}
        and type(adapter) is OwnedAdapter and adapter.max_retries.total == 0
        and adapter.context.check_hostname is True and adapter.context.verify_mode == ssl.CERT_REQUIRED
        and adapter.context.minimum_version >= ssl.TLSVersion.TLSv1_2 and sha(adapter.ca_ascii.encode('ascii')) == CA_SHA256, 'request')


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items: require(key not in result, 'response'); result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('response')))
        require(type(value) is dict, 'response')
        return value
    except (ValueError, UnicodeError, RecursionError): raise Refused('response') from None


def _fetch(credentials, stage, payload, entry, ca_raw, deadline):
    require(stage in STAGES and type(payload) is dict, 'request'); environment.require_safe_environment()
    url = API_BASE + '/' + ENDPOINTS[STAGES.index(stage)]; raw = canonical(payload)
    require(entry['request_sha256'] == sha(raw), 'request')
    headers = build_auth_headers(credentials, int(time.time())); headers.update({'Content-Type': 'application/json', 'Accept-Encoding': 'identity'})
    with _session(ca_raw) as session:
        _session_check(session, url)
        prepared = session.prepare_request(requests.Request('POST', url, data=raw, headers=headers))
        expected = {key.casefold(): value for key, value in headers.items()}; expected['content-length'] = str(len(raw))
        require(prepared.method == 'POST' and prepared.url == url and prepared.body == raw
            and prepared.hooks == {'response': []} and {key.casefold(): value for key, value in prepared.headers.items()} == expected, 'request')
        try:
            with session.send(prepared, stream=True, allow_redirects=False, timeout=min(15, remaining(deadline)), verify=True, proxies={}) as response:
                status = response.status_code; require(type(status) is int and 100 <= status <= 599, 'http_status'); entry['http_status'] = status
                if status != 200: raise Refused('http_refused')
                environment.require_safe_environment(); _session_check(session, url)
                require(response.request is prepared and response.url == url and not response.history
                    and not response.headers.get('Set-Cookie') and response.headers.get('Content-Encoding', 'identity').casefold() == 'identity', 'response')
                declared = response.headers.get('Content-Length')
                require(declared is None or type(declared) is str and declared.isdecimal() and len(declared) <= 10
                    and 0 < int(declared) <= MAX_BODY, 'bound')
                body = bytearray()
                for part in response.iter_content(65536, decode_unicode=False):
                    remaining(deadline); require(type(part) is bytes and len(body) + len(part) <= MAX_BODY, 'bound'); body.extend(part)
                require(body and (declared is None or len(body) == int(declared)), 'response')
                raw_response = bytes(body); entry['body_pin'] = {'byte_count': len(raw_response), 'sha256': sha(raw_response)}
                return _decode(raw_response)
        except (Refused, admitted.helpers.Deadline): raise
        except BaseException as error:
            entry['transport_failure'] = technical.transport_failure(error); raise Refused('request') from None


def _organization(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{32}', value) and sha(value.encode('ascii')) == ORGANIZATION_SHA256, 'organization'); return value


def _project(packet, project_id, name, user_id, *, created):
    rows = packet.get('projects'); require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project'); row = rows[0]
    require(type(row.get('projectId')) is int and row['projectId'] == project_id and row.get('name') == name
        and row.get('language') == 'Py' and row.get('owner') is True and type(row.get('ownerId')) is int
        and str(row['ownerId']) == user_id, 'project')
    organization = _organization(row.get('organizationId')); require('public' not in row or type(row['public']) is bool, 'project')
    require(row.get('public') is not True, 'public_project')
    require(type(row.get('libraries')) is list and row['libraries'] == [], 'libraries')
    general = row.get('collaborators'); require(type(general) is list and 1 <= len(general) <= 16
        and all(type(item) is dict for item in general), 'collaboration')
    own = [item for item in general if type(item.get('uid')) is int and str(item['uid']) == user_id]
    require(len(own) == 1 and own[0].get('owner') is True
        and all(item is own[0] or item.get('uid') is None and item.get('owner') is False for item in general), 'owner')
    return {'project_id': project_id, 'expected_name_matched': True, 'organization_sha256': ORGANIZATION_SHA256,
        'owner_id_sha256': sha(user_id.encode('ascii')), 'general_owner_row_sha256': sha(owner_policy._canonical(own[0])),
        'general_count': len(general), 'unidentified_general_rows': len(general) - 1, 'libraries_count': 0,
        'private_verified': row.get('public') is False, 'privacy_field_shape': 'boolean' if 'public' in row else 'missing',
        'privacy_observation': 'explicit_private' if row.get('public') is False else 'UNKNOWN',
        'documented_private_default_inference': 'public' not in row,
        'current_private_observation_required_before_licensed_transfer': True}, organization


def _collaboration(packet, project, user_id, *, reference):
    require('projectId' not in packet or type(packet['projectId']) is int and packet['projectId'] == project['project_id'], 'collaboration')
    require('organizationId' not in packet or _organization(packet['organizationId']), 'organization')
    rows = packet.get('collaborators'); require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'collaboration')
    row = rows[0]
    require(type(row.get('uid')) is int and str(row['uid']) == user_id and row.get('owner') is True
        and row.get('permission') == 'write' and row.get('liveControl') is True
        and packet.get('userPermissions') == 'write' and packet.get('userLiveControl') is True, 'collaboration')
    row_pin = sha(owner_policy._canonical(row)); require(row_pin == project['general_owner_row_sha256'], 'owner')
    if reference: require(row_pin == owner_policy.OWNER_ROW_SHA256, 'owner')
    return {'project_id': project['project_id'], 'dedicated_owner_count': 1, 'owner_row_sha256': row_pin,
        'owner_id_sha256': project['owner_id_sha256'], 'project_owner_write_liveControl_observed': True,
        'organization_manager_or_paid_status_proven': False}


def initial_state():
    return {'dispatches': [], 'reference': None, 'reference_collaboration': None, 'created': None,
        'created_collaboration': None, 'create_intent': False, 'observed_created_project_ids': [],
        'created_project_id': None, 'complete': False, 'failure_code': None, 'physical_request_count': None, **FALSE_FLAGS}


def creation_observation(args, state):
    return {'binding': binding(args), 'create_intent': True,
        'observed_created_project_ids': list(state['observed_created_project_ids']),
        'created_project_id': state['created_project_id']}


def _retain_creation(args, state):
    require(os.fstat(args.result_fd).st_size == 0, 'control')
    _write(args.result_fd, canonical(creation_observation(args, state)) + b'\n')
    os.fsync(args.control_fd)


def validate_creation_observation(value, args):
    require(type(value) is dict and set(value) == {'binding','create_intent','observed_created_project_ids','created_project_id'}
        and value['binding'] == binding(args) and value['create_intent'] is True, 'output')
    ids = value['observed_created_project_ids']
    require(type(ids) is list and len(ids) <= 8 and ids == sorted(set(ids))
        and all(type(item) is int and 0 < item <= 2147483647 for item in ids)
        and (value['created_project_id'] is None or type(value['created_project_id']) is int
            and value['created_project_id'] in ids), 'output')
    return value


def _sequence(args, credentials, ca_raw, deadline):
    state = initial_state(); organization = None
    try:
        for index, stage in enumerate(STAGES):
            environment.require_safe_environment(); remaining(deadline)
            if stage == 'authenticate': payload = {}
            elif stage.startswith('reference'): payload = {'projectId': REFERENCE_ID}
            elif stage == 'create': payload = {'name': PROJECT_NAME, 'language': 'Py', 'organizationId': organization}
            else: payload = {'projectId': state['created_project_id']}
            require(stage != 'create' or state['reference'] is not None and state['reference_collaboration'] is not None, 'owner')
            entry = {'ordinal': index, 'stage': stage, 'endpoint': ENDPOINTS[index], 'http_status': None,
                'body_pin': None, 'transport_failure': None, 'request_sha256': sha(canonical(payload))}
            intent = canonical({'binding': binding(args), 'ordinal': index, 'stage': stage, 'request_sha256': sha(canonical(payload))}) + b'\n'
            require(os.lseek(args.stages_fd, 0, os.SEEK_END) + len(intent) <= MAX_OUTPUT, 'bound')
            _write(args.stages_fd, intent); os.fsync(args.control_fd); state['dispatches'].append(entry)
            if stage == 'create': state['create_intent'] = True
            packet = _fetch(credentials, stage, payload, entry, ca_raw, deadline)
            if stage == 'create':
                rows = packet.get('projects')
                if type(rows) is list and len(rows) <= 8:
                    state['observed_created_project_ids'] = sorted({row['projectId'] for row in rows
                        if type(row) is dict and type(row.get('projectId')) is int and 0 < row['projectId'] <= 2147483647})
                if type(rows) is list and len(rows) == 1 and len(state['observed_created_project_ids']) == 1:
                    state['created_project_id'] = state['observed_created_project_ids'][0]
                _retain_creation(args, state)
                require(state['created_project_id'] is not None, 'created_ambiguous')
                require(state['created_project_id'] not in (REFERENCE_ID, 38364439), 'created_ambiguous')
            require(packet.get('success') is True and packet.get('errors', []) == [], 'response')
            if stage == 'reference': state['reference'], organization = _project(packet, REFERENCE_ID, REFERENCE_NAME, credentials.user_id, created=False)
            elif stage == 'reference-collaboration': state['reference_collaboration'] = _collaboration(packet, state['reference'], credentials.user_id, reference=True)
            elif stage == 'create':
                _project(packet, state['created_project_id'], PROJECT_NAME, credentials.user_id, created=True)
            elif stage == 'created': state['created'], _ = _project(packet, state['created_project_id'], PROJECT_NAME, credentials.user_id, created=True)
            elif stage == 'created-collaboration': state['created_collaboration'] = _collaboration(packet, state['created'], credentials.user_id, reference=False)
        state['complete'] = True
    except BaseException as error: state['failure_code'] = finite(error)
    return state


def validate_state(value):
    require(type(value) is dict and set(value) == set(initial_state()) and type(value['dispatches']) is list
        and len(value['dispatches']) <= 6 and type(value['create_intent']) is bool and type(value['complete']) is bool
        and value['physical_request_count'] is None and all(value[key] is False for key in FALSE_FLAGS), 'output')
    for index, row in enumerate(value['dispatches']):
        require(type(row) is dict and set(row) == {'ordinal', 'stage', 'endpoint', 'http_status', 'body_pin', 'transport_failure', 'request_sha256'}
            and type(row['ordinal']) is int and row['ordinal'] == index and row['stage'] == STAGES[index] and row['endpoint'] == ENDPOINTS[index]
            and (row['http_status'] is None or type(row['http_status']) is int and 100 <= row['http_status'] <= 599)
            and (row['transport_failure'] is None or row['transport_failure'] in {
                'transport_connect_timeout','transport_read_timeout','transport_tls','transport_proxy','transport_redirect',
                'transport_connection','transport_timeout','transport_request','transport_os','transport_unknown'})
            and sidecar._hash(row['request_sha256']), 'output')
        if row['body_pin'] is not None:
            sidecar.ap._pin(row['body_pin'], MAX_BODY); require(row['http_status'] == 200, 'output')
    ids = value['observed_created_project_ids']
    require(type(ids) is list and len(ids) <= 8 and ids == sorted(set(ids))
        and all(type(item) is int and 0 < item <= 2147483647 for item in ids), 'output')
    require(value['create_intent'] == (len(value['dispatches']) >= 4)
        and (value['created_project_id'] is None or type(value['created_project_id']) is int
            and value['created_project_id'] in ids and value['create_intent']), 'output')
    for name in ('reference', 'created'):
        row = value[name]
        if row is not None:
            keys = {'project_id','expected_name_matched','organization_sha256','owner_id_sha256','general_owner_row_sha256',
                'general_count','unidentified_general_rows','libraries_count','private_verified','privacy_field_shape',
                'privacy_observation','documented_private_default_inference','current_private_observation_required_before_licensed_transfer'}
            require(type(row) is dict and set(row) == keys and row['project_id'] == (REFERENCE_ID if name == 'reference' else value['created_project_id'])
                and row['expected_name_matched'] is True and row['organization_sha256'] == ORGANIZATION_SHA256
                and sidecar._hash(row['owner_id_sha256']) and sidecar._hash(row['general_owner_row_sha256'])
                and type(row['general_count']) is int and 1 <= row['general_count'] <= 16
                and row['unidentified_general_rows'] == row['general_count'] - 1 and row['libraries_count'] == 0
                and type(row['private_verified']) is bool and row['privacy_field_shape'] in ('missing','boolean')
                and row['privacy_observation'] == ('explicit_private' if row['private_verified'] else 'UNKNOWN')
                and row['documented_private_default_inference'] == (row['privacy_field_shape'] == 'missing')
                and row['private_verified'] == (row['privacy_field_shape'] == 'boolean')
                and row['current_private_observation_required_before_licensed_transfer'] is True, 'output')
    for name, project in (('reference_collaboration', value['reference']), ('created_collaboration', value['created'])):
        row = value[name]
        if row is not None:
            require(project is not None and type(row) is dict and set(row) == {'project_id','dedicated_owner_count',
                'owner_row_sha256','owner_id_sha256','project_owner_write_liveControl_observed','organization_manager_or_paid_status_proven'}
                and row['project_id'] == project['project_id'] and row['dedicated_owner_count'] == 1
                and row['owner_row_sha256'] == project['general_owner_row_sha256'] and row['owner_id_sha256'] == project['owner_id_sha256']
                and row['project_owner_write_liveControl_observed'] is True and row['organization_manager_or_paid_status_proven'] is False, 'output')
    if value['complete']:
        require(len(value['dispatches']) == 6 and value['created_project_id'] is not None and value['created_collaboration'] is not None
            and value['failure_code'] is None and all(row['http_status'] == 200 and row['body_pin'] is not None
                and row['transport_failure'] is None for row in value['dispatches']), 'output')
    else: require(value['failure_code'] in FINITE, 'output')
    return value


def run(args, deadline):
    with Store() as store:
        store.create('claim.json', canonical(binding(args))); source = source_binding()
        ca_fd = os.open(CA_PATH, os.O_RDONLY | os.O_NOFOLLOW); credential_read = credential_write = None
        try:
            _, ca_meta, ca_security = _ca(ca_fd)
            store.create('worker-intent.json', canonical({'binding': binding(args), 'source_binding_sha256': sha(canonical(source)), 'stages': list(STAGES)}))
            for name in ('worker-started.json','stages.jsonl','worker-result.json'): store.create(name)
            secret = _credential_packet(os.environ); credential_read, credential_write = os.pipe()
            require(len(secret) <= os.fpathconf(credential_write, 'PC_PIPE_BUF'), 'credential_handoff')
            _write_count = os.write(credential_write, secret); require(_write_count == len(secret), 'credential_handoff')
            os.close(credential_write); credential_write = None; secret = None
            runtime = Path(tempfile.mkdtemp(prefix='r326-at-', dir=ROOT / '.pytest_cache'))
            safe = capture_support._environment(runtime)
            command = ['/usr/bin/sandbox-exec','-p',native_profile('worker'),str(PYTHON),'-B',str(SOURCE),'worker',
                '--expected-head',args.expected_head,'--caller-sha256',args.caller_sha256,'--profile-sha256',args.profile_sha256]
            named = [('control',store.fd),('claim',store.files['claim.json'][0]),('intent',store.files['worker-intent.json'][0]),
                ('started',store.files['worker-started.json'][0]),('stages',store.files['stages.jsonl'][0]),
                ('result',store.files['worker-result.json'][0]),('ca',ca_fd),('credential',credential_read)]
            for name, fd in named: command += ['--'+name+'-fd',str(fd)]
            raw, errors, actual = capture(command,safe,min(WORKER_SECONDS,remaining(deadline)),stdout_limit=MAX_OUTPUT,pass_fds=tuple(fd for _,fd in named))
            state = None; failure = None; observed_creation = None
            try:
                require(not errors,'child'); public_transport._actual(actual,raw,(0,2))
                packet = parse(raw[:-1]) if raw.endswith(b'\n') else None
                require(type(packet) is dict and set(packet)=={'binding','state'} and packet['binding']==binding(args),'child')
                state = validate_state(packet['state']); require(actual['actual_exit']==(0 if state['complete'] else 2),'child')
                store.refresh_worker()
                observation_raw = _read(store.files['worker-result.json'][0],MAX_OUTPUT)
                if observation_raw:
                    require(observation_raw.endswith(b'\n'),'child')
                    observed_creation = validate_creation_observation(parse(observation_raw[:-1]),args)
                    require(observed_creation == creation_observation(args,state),'child')
                else: require(not state['observed_created_project_ids'],'child')
                journal = _read(store.files['stages.jsonl'][0],MAX_OUTPUT)
                lines = journal.splitlines(); require(len(lines)==len(state['dispatches']),'child')
                for index,line in enumerate(lines):
                    entry = parse(line); require(set(entry)=={'binding','ordinal','stage','request_sha256'}
                        and entry['binding']==binding(args) and entry['ordinal']==index and entry['stage']==STAGES[index]
                        and entry['request_sha256'] == state['dispatches'][index]['request_sha256'],'child')
                require(_ca(ca_fd)[1:] == (ca_meta,ca_security),'CA'); preflight(args,deadline); store.verify()
            except BaseException as error:
                failure = finite(error)
                # A bounded captured-channel failure cannot erase the already
                # fsynced created-ID checkpoint. It remains failure evidence.
                try:
                    store.refresh_worker(); observation_raw = _read(store.files['worker-result.json'][0],MAX_OUTPUT)
                    if observation_raw and observation_raw.endswith(b'\n'):
                        observed_creation = validate_creation_observation(parse(observation_raw[:-1]),args)
                except BaseException: pass
            result = {'schema':SCHEMA,'source_binding':source,'credential_handoff_complete':True,'worker_actual':actual,
                'state':state,'creation_observation':observed_creation,'parent_failure':failure,'attempt_consumed':True,**FALSE_FLAGS}
            code = 0 if failure is None and state is not None and state['complete'] else 2
            try:
                report = store.create('report.json',canonical({'binding':binding(args),'result':result})); store.verify()
            except BaseException as error:
                result['parent_failure'] = finite(error); report = None; code = 2
            return {'result':result,'report':report},code
        finally:
            for fd in (credential_read,credential_write,ca_fd):
                if fd is not None: os.close(fd)


def validate_output(raw, actual_exit, args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT and raw.endswith(b'\n')
        and type(actual_exit) is int and actual_exit in (0,2),'output')
    packet = parse(raw[:-1]); require(packet.get('binding')==binding(args),'output')
    if set(packet)=={'binding','failure_code'}:
        require(actual_exit==2 and packet['failure_code'] in FINITE,'output'); return packet
    require(set(packet)=={'binding','outcome'} and type(packet['outcome']) is dict
        and set(packet['outcome'])=={'result','report'},'output')
    result = packet['outcome']['result']
    require(type(result) is dict and set(result)=={'schema','source_binding','credential_handoff_complete','worker_actual',
        'state','creation_observation','parent_failure','attempt_consumed',*FALSE_FLAGS} and result['schema']==SCHEMA
        and result['source_binding']==source_binding() and result['credential_handoff_complete'] is True
        and result['attempt_consumed'] is True and all(result[key] is False for key in FALSE_FLAGS),'output')
    public_transport._actual_metadata(result['worker_actual'])
    state=result['state']
    if state is not None:
        validate_state(state); child_raw=canonical({'binding':binding(args),'state':state})+b'\n'
        public_transport._actual(result['worker_actual'],child_raw,(0 if state['complete'] else 2,))
    observation = result['creation_observation']
    if observation is not None:
        validate_creation_observation(observation,args)
        if state is not None: require(observation == creation_observation(args,state),'output')
    if state is not None and state['observed_created_project_ids']: require(observation is not None,'output')
    if result['parent_failure'] is None:
        require(state is not None and actual_exit==(0 if state['complete'] else 2),'output')
    else: require(actual_exit==2 and result['parent_failure'] in FINITE,'output')
    if packet['outcome']['report'] is None:
        require(actual_exit == 2 and result['parent_failure'] in FINITE, 'output')
    else:
        require(packet['outcome']['report']=={'byte_count':len(canonical({'binding':binding(args),'result':result})),
            'sha256':sha(canonical({'binding':binding(args),'result':result}))},'output')
    return packet


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('create','worker','validate'))
    for key in ('expected-head','caller-sha256','profile-sha256'): parser.add_argument('--'+key,required=True)
    for key in ('control','claim','intent','started','stages','result','ca','credential'): parser.add_argument('--'+key+'-fd',type=int)
    parser.add_argument('--actual-exit',type=int);args=parser.parse_args(argv)
    deadline=time.monotonic()+({'create':SECONDS,'worker':WORKER_SECONDS,'validate':VALIDATOR_SECONDS}[args.operation])
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline)
            if args.operation=='validate':
                raw=sys.stdin.buffer.read(MAX_OUTPUT+1);validate_output(raw,args.actual_exit,args);sys.stdout.buffer.write(raw);return 0
            if args.operation=='create':
                technical._bootstrap_broker_logging();outcome,code=run(args,deadline);packet={'binding':binding(args),'outcome':outcome}
            else:
                environment._bootstrap_cli_logging();_inherited(args);environment.require_safe_environment()
                ca_raw,ca_meta,ca_security=_ca(args.ca_fd)
                secret=os.read(args.credential_fd,MAX_CREDENTIAL+1);require(0<len(secret)<=MAX_CREDENTIAL and os.read(args.credential_fd,1)==b'','credential_handoff')
                values=parse(secret);require(set(values)=={'QC_USER_ID','QC_API_TOKEN'},'credential_handoff')
                credentials=_credential_value(values);values.clear();secret=None
                state=_sequence(args,credentials,ca_raw,deadline);credentials=None
                try:
                    validate_state(state);require(_ca(args.ca_fd)[1:]==(ca_meta,ca_security),'CA');preflight(args,deadline)
                except BaseException as error:
                    state['complete']=False;state['failure_code']=finite(error);validate_state(state)
                packet={'binding':binding(args),'state':state};code=0 if state['complete'] else 2
            raw=canonical(packet)+b'\n';require(len(raw)<=MAX_OUTPUT,'bound');sys.stdout.buffer.write(raw);return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding':binding(args),'failure_code':finite(error)})+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
