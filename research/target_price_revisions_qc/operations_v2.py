"""Prospective, source-bound QC operations for the standalone matched study.

This successor never renews the executed six-universe controller or receipts.
It offers cooperative POSIX custody, not hostile-process or canonical custody.
Imports do no I/O. Every empirical operation requires a fresh closed manifest,
the designated checkout, hash-matching dirty source bytes and private receipts.
"""
from __future__ import annotations

import base64
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import threading
import time

LANE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
STUDY = 'TPR-MATCHED-20261008-v1'
BASELINE = '32016848bc9ce4dfab3f52ddb5bb34e105e445dc'
FREEZE_PATH = 'research/target_price_revisions_qc/matched_freeze.json'
FREEZE_HASH = 'a0645dce96d1153de4a6709b4d39c1d8cc0c583950a76421220e00539a9521d0'
PRIVATE_PARENT = LANE / 'artifacts/target_price_matched'
PACKET_PATH = 'artifacts/target_price_qc6/TPR-QC6-20261008-v1/signal-packet.json'
PACKET_HASH = '4dd3a9d800b7c1cb8114272c829ee18239972cc0a15c71e47a3e86ed6491a316'
CANDIDATES = frozenset(f'TPR-MATCHED-{arm}-{cost}-v1'
                      for arm in ('ON', 'OFF', 'ETF') for cost in ('BASE', 'ADVERSE'))
SOURCE_FILES = frozenset({'main.py', 'proxy_core.py', 'signal_packet.py', 'matched_config.py'})
MODULE_PATH = 'research/target_price_revisions_qc/operations_v2.py'
ENDPOINTS = frozenset({'authenticate', 'projects/create', 'files/create', 'files/update',
    'files/read', 'compile/create', 'compile/read', 'backtests/create', 'backtests/read',
    'backtests/read/log', 'backtests/orders/read', 'object/set'})
_MANIFEST_KEYS = frozenset({'schema', 'study_id', 'operation_id', 'created_utc', 'expires_utc',
    'baseline_git_head', 'freeze_sha256', 'repository_source_hashes', 'input_hashes',
    'packet_path', 'packet_sha256', 'candidates', 'max_requests', 'max_response_bytes',
    'request_timeout_seconds', 'max_attempts_per_candidate', 'log_prefix'})


class Refusal(ValueError):
    """Bounded refusal; never includes a credential or source row."""


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                       allow_nan=False) + '\n').encode('ascii')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def _hash(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _name(value, maximum=120):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_.-]{1,' + str(maximum) + '}', value) is not None


def _clock(value):
    try:
        result = datetime.fromisoformat(value)
        if type(value) is not str or result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise Refusal('aware manifest clock required') from None


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal('duplicate JSON key')
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refusal('nonfinite JSON')))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refusal('bounded JSON refused') from None


def validate_manifest(manifest, expected_hash):
    if (type(manifest) is not dict or set(manifest) != _MANIFEST_KEYS
            or not _hash(expected_hash) or digest(canonical(manifest)) != expected_hash
            or manifest['schema'] != 'tpr-qc-operations-manifest-v2'
            or manifest['study_id'] != STUDY or not _name(manifest['operation_id'], 80)
            or type(manifest['baseline_git_head']) is not str
            or re.fullmatch(r'[0-9a-f]{40}', manifest['baseline_git_head']) is None
            or manifest['baseline_git_head'] == '0' * 40
            or manifest['freeze_sha256'] != FREEZE_HASH
            or manifest['packet_path'] != PACKET_PATH or manifest['packet_sha256'] != PACKET_HASH):
        raise Refusal('closed matched operations manifest refused')
    created, expires = _clock(manifest['created_utc']), _clock(manifest['expires_utc'])
    if not 0 < (expires - created).total_seconds() <= 172800:
        raise Refusal('bounded access lifetime required')
    for field, maximum in (('max_requests', 1000), ('max_response_bytes', 16 * 1024 * 1024),
                           ('request_timeout_seconds', 30)):
        if type(manifest[field]) is not int or not 1 <= manifest[field] <= maximum:
            raise Refusal('manifest operational bound refused')
    if (type(manifest['max_attempts_per_candidate']) is not int
            or manifest['max_attempts_per_candidate'] != 3
            or type(manifest['log_prefix']) is not str
            or manifest['log_prefix'] != 'MATCHED_'):
        raise Refusal('attempt/log contract refused')
    sources = manifest['repository_source_hashes']
    if (type(sources) is not dict or not 2 <= len(sources) <= 32 or MODULE_PATH not in sources
            or sources.get(FREEZE_PATH) != FREEZE_HASH):
        raise Refusal('operations source binding required')
    for path, value in sources.items():
        if (type(path) is not str or (re.fullmatch(
                r'research/target_price_revisions_qc/[A-Za-z0-9_.-]+[.](?:py|json)', path) is None
                and path not in {'research/target_price_revisions_development/raw_candidate.py',
                                 'research/target_price_revisions_development/raw_revision.py'})
                or not _hash(value)):
            raise Refusal('repository source allowlist refused')
    inputs = manifest['input_hashes']
    if (type(inputs) is not dict or not 1 <= len(inputs) <= 16
            or inputs.get('signal-packet.json') != PACKET_HASH
            or any(not _name(key, 80) or not _hash(value) for key, value in inputs.items())):
        raise Refusal('input identity inventory refused')
    rows = manifest['candidates']
    if type(rows) is not list or len(rows) != 6:
        raise Refusal('all six matched portfolio candidates required')
    candidates = {}
    names = set()
    for row in rows:
        if (type(row) is not dict or set(row) != {
                'candidate_id', 'project_name', 'config_sha256', 'source_hashes'}
                or type(row['candidate_id']) is not str
                or row['candidate_id'] not in CANDIDATES or row['candidate_id'] in candidates
                or not _name(row['project_name']) or row['project_name'] in names
                or not _hash(row['config_sha256'])
                or type(row['source_hashes']) is not dict
                or set(row['source_hashes']) != SOURCE_FILES
                or any(not _hash(value) for value in row['source_hashes'].values())):
            raise Refusal('matched candidate source contract refused')
        candidates[row['candidate_id']] = row
        names.add(row['project_name'])
    copied = _json(canonical(manifest))
    return copied, {row['candidate_id']: row for row in copied['candidates']}


def _custody(info, directory=False):
    if (info.st_uid != os.getuid() or stat.S_ISLNK(info.st_mode)
            or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not directory and info.st_nlink != 1)):
        raise Refusal('owner-only private custody refused')


def _read(directory, name, maximum):
    directory_fd = file_fd = None
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        _custody(os.fstat(directory_fd), True)
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        before = os.fstat(file_fd)
        _custody(before)
        with os.fdopen(file_fd, 'rb') as stream:
            file_fd = None
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        _custody(after)
        if (len(raw) > maximum or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise Refusal('private input bound/change refused')
        return raw
    except OSError:
        raise Refusal('private read refused') from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def redact(value, user_id='', token=''):
    """Redact both credentials in nested retained metadata and error messages."""
    if type(value) is str:
        for secret in (token, user_id):
            if secret:
                value = value.replace(secret, '[redacted]')
        return value
    if type(value) is list:
        return [redact(item, user_id, token) for item in value]
    if type(value) is dict:
        return {key: ('[redacted]' if key.lower() in {'userid', 'user_id', 'apitoken', 'api_token'}
                      else redact(item, user_id, token)) for key, item in value.items()}
    return value


@contextmanager
def _wall_deadline(seconds):
    """POSIX main-thread request deadline, including headers and body reads.

    Refuse an existing alarm rather than replacing another component's timer.
    This controller is for this owner's pinned macOS research checkout.
    """
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, 'setitimer'):
        raise Refusal('request wall deadline unavailable on this caller')
    prior = signal.getitimer(signal.ITIMER_REAL)
    if prior != (0.0, 0.0):
        raise Refusal('request would replace an existing wall timer')
    handler = signal.getsignal(signal.SIGALRM)
    def expired(_signal, _frame):
        raise Refusal('request wall deadline exceeded; outcome may be unknown')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, handler)


class Operations:
    """Real scoped orchestration; every receipt is immutable and private.

    The explicit private fixture seam never resolves credentials or constructs
    a network connection. Fixture receipts carry zero empirical authority.
    """
    def __init__(self, manifest, *, manifest_sha256, _fixture_root=None, _fixture_transport=None):
        self.manifest, self.candidates = validate_manifest(manifest, manifest_sha256)
        self.manifest_sha256 = manifest_sha256
        if (_fixture_root is None) != (_fixture_transport is None):
            raise Refusal('complete fixture transport/root seam required')
        self.fixture = _fixture_root is not None
        self.root = Path(_fixture_root) if self.fixture else PRIVATE_PARENT / STUDY
        self.transport = _fixture_transport
        self.operation = self.manifest['operation_id']

    def guard(self):
        if not _clock(self.manifest['created_utc']) <= datetime.now(timezone.utc) <= _clock(self.manifest['expires_utc']):
            raise Refusal('fresh access scope not active')
        if self.fixture:
            return {'git_head': self.manifest['baseline_git_head'], 'fixture': True,
                    'dirty_status_sha256': digest(b'fixture')}
        if Path.cwd() != LANE or Path.cwd().resolve() != LANE:
            raise Refusal('wrong physical lane')
        def git(*args):
            output = subprocess.run(['git', *args], cwd=LANE, check=True,
                capture_output=True, text=True).stdout
            return output.rstrip('\n') if args == ('status', '--short') else output.strip()
        if git('rev-parse', '--show-toplevel') != str(LANE) or git('branch', '--show-current') != BRANCH:
            raise Refusal('wrong Git lane')
        head, status = git('rev-parse', 'HEAD'), git('status', '--short')
        if head != self.manifest['baseline_git_head']:
            raise Refusal('implementation baseline moved')
        ancestry = subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE, head],
            cwd=LANE, capture_output=True, text=True)
        if ancestry.returncode != 0:
            raise Refusal('implementation baseline diverges from completed review')
        for relative, expected in self.manifest['repository_source_hashes'].items():
            path = LANE / relative
            if path.resolve() != path or path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                raise Refusal('repository source shape refused')
            if digest(path.read_bytes()) != expected:
                raise Refusal('declared dirty implementation source changed')
        return {'git_head': head, 'fixture': False, 'dirty_status_sha256': digest(status.encode()),
                'repository_source_hashes': self.manifest['repository_source_hashes']}

    def _root(self):
        parents = (self.root,) if self.fixture else (PRIVATE_PARENT, self.root)
        for path in parents:
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
            _custody(path.lstat(), True)
        return self.root

    def exclusive(self, name, value):
        if not _name(name, 220):
            raise Refusal('invalid receipt name')
        raw = value if type(value) is bytes else canonical(value)
        try:
            fd = os.open(self._root() / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            raise Refusal('receipt already exists; no implicit retry') from None
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return digest(raw)

    def read_private(self, name, maximum=16 * 1024 * 1024):
        if not _name(name, 220):
            raise Refusal('invalid receipt name')
        return _read(self.root, name, maximum)

    def _value(self, name):
        return _json(self.read_private(name))

    def prepare_access(self):
        context = self.guard()
        receipt = {'schema': 'tpr-qc-access-v2', 'manifest': self.manifest,
                   'manifest_sha256': self.manifest_sha256, 'at': utc(), **context}
        return self.exclusive('access.' + self.operation + '.json', receipt)

    def _access(self):
        context = self.guard()
        body = self._value('access.' + self.operation + '.json')
        if body.get('manifest_sha256') != self.manifest_sha256 or body.get('manifest') != self.manifest:
            raise Refusal('access manifest binding changed')
        return context

    def _candidate(self, candidate):
        if type(candidate) is not str or candidate not in self.candidates:
            raise Refusal('candidate outside frozen six-arm study')
        return self.candidates[candidate]

    def _seq(self, prefix, suffix):
        numbers = []
        for path in self.root.glob(prefix + '*' + suffix):
            middle = path.name[len(prefix):-len(suffix)]
            if prefix == 'request.' and middle.endswith('.terminal'):
                continue
            if not middle.isdigit():
                raise Refusal('malformed immutable receipt sequence')
            numbers.append(int(middle))
        return max(numbers, default=0) + 1

    def _project(self, candidate):
        specification = self._candidate(candidate)
        result = self._value(candidate + '.project.json')
        if (result.get('candidate_id') != candidate or result.get('name') != specification['project_name']
                or type(result.get('project_id')) is not int or result.get('owner') is not True):
            raise Refusal('own fresh project binding refused')
        return result

    def _request(self, endpoint, payload, *, content_type='application/json', project=None, stage=None):
        context = self._access()
        if endpoint not in ENDPOINTS:
            raise Refusal('endpoint outside matched research scope')
        if endpoint not in {'authenticate', 'projects/create', 'object/set'}:
            if (type(project) is not dict or type(payload) is not dict
                    or type(project.get('candidate_id')) is not str
                    or project.get('candidate_id') not in self.candidates
                    or project != self._project(project['candidate_id'])
                    or payload.get('projectId') != project['project_id']):
                raise Refusal('request not bound to own fresh project')
        raw = payload if type(payload) is bytes else canonical(payload)
        if endpoint in {'projects/create', 'files/create', 'files/update', 'compile/create',
                        'backtests/create', 'object/set'}:
            self._admit_mutation(endpoint, payload, raw, project, stage)
        seq = self._seq('request.', '.json')
        # Terminal filenames are intentionally outside the numeric request glob.
        if seq > self.manifest['max_requests']:
            raise Refusal('matched request budget exhausted')
        prefix = f'request.{seq:04d}'
        self.exclusive(prefix + '.json', {'at': utc(), 'endpoint': endpoint,
            'manifest_sha256': self.manifest_sha256, 'payload_sha256': digest(raw),
            'payload_bytes': len(raw), **context})
        conn, status, user_id, token = None, None, '', ''
        try:
            if self.fixture:
                value = self.transport(endpoint, raw, content_type)
            else:
                with _wall_deadline(self.manifest['request_timeout_seconds']):
                    user_id = os.environ.get('QC_USER_ID', '').strip()
                    token = os.environ.get('QC_API_TOKEN', '').strip()
                    if not user_id or not token:
                        raise Refusal('QC credentials unavailable')
                    stamp = str(int(time.time()))
                    signed = digest((token + ':' + stamp).encode())
                    auth = base64.b64encode((user_id + ':' + signed).encode()).decode()
                    conn = http.client.HTTPSConnection('www.quantconnect.com',
                        timeout=self.manifest['request_timeout_seconds'], context=ssl.create_default_context())
                    conn.request('POST', '/api/v2/' + endpoint, body=raw, headers={
                        'Authorization': 'Basic ' + auth, 'Timestamp': stamp, 'Content-Type': content_type})
                    response = conn.getresponse()
                    status = response.status
                    response_raw = response.read(self.manifest['max_response_bytes'] + 1)
                    if len(response_raw) > self.manifest['max_response_bytes']:
                        raise Refusal('QC response exceeds bound')
                    if token.encode() in response_raw:
                        raise Refusal('QC token echo refused')
                    value = _json(response_raw)
            if type(value) is not dict or value.get('success') is not True or (status is not None and status != 200):
                errors = value.get('errors', []) if type(value) is dict else []
                errors = [str(item)[:400] for item in errors[:5]] if type(errors) is list else []
                self.exclusive(prefix + '.terminal.json', {'at': utc(), 'status': 'api_refused',
                    'http': status, 'errors': redact(errors, user_id, token)})
                raise Refusal('QC API refused; no automatic retry')
            safe = redact(value, user_id, token)
            self.exclusive(prefix + '.terminal.json', {'at': utc(), 'status': 'succeeded',
                'http': status if status is not None else 'fixture', 'response_sha256': digest(canonical(safe))})
            return safe
        except Exception:
            if not (self.root / (prefix + '.terminal.json')).exists():
                self.exclusive(prefix + '.terminal.json', {'at': utc(), 'status': 'failed_or_unknown',
                    'http': status, 'automatic_retry': False})
            raise Refusal('QC request failed or outcome unknown; receipt remains consumed') from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _admit_mutation(self, endpoint, payload, raw, project, stage):
        """All effectful transports require the typed method's spent stage."""
        if endpoint == 'object/set':
            row = self._value('packet-upload.spent.json')
            if (stage != ('packet',) or row.get('wire_sha256') != digest(raw)
                    or row.get('manifest_sha256') != self.manifest_sha256):
                raise Refusal('specialized packet upload stage required')
            self.exclusive('packet-upload.transport-spent.json', {'at': utc()})
            return
        if type(stage) is not tuple or not stage:
            raise Refusal('typed effectful operation stage required')
        candidate = stage[0]
        specification = self._candidate(candidate)
        if endpoint == 'projects/create':
            row = self._value(candidate + '.project-create.spent.json')
            if (len(stage) != 1 or row.get('manifest_sha256') != self.manifest_sha256
                    or payload != {'name': specification['project_name'], 'language': 'Py'}):
                raise Refusal('project creation stage binding refused')
            self.exclusive(candidate + '.project-create.transport-spent.json', {'at': utc()})
        elif endpoint in {'files/create', 'files/update'}:
            row = self._value(candidate + '.source-upload.' + self.operation + '.spent.json')
            if (len(stage) != 1 or project != self._project(candidate)
                    or set(payload) != {'projectId', 'name', 'content'}
                    or payload.get('name') not in SOURCE_FILES or type(payload.get('content')) is not str
                    or digest(payload['content'].encode()) != specification['source_hashes'][payload['name']]
                    or row.get('manifest_sha256') != self.manifest_sha256):
                raise Refusal('project source write binding refused')
            self.exclusive(candidate + '.source-upload.' + self.operation + '.' + payload['name'] + '.transport-spent.json',
                           {'at': utc(), 'source_sha256': digest(payload['content'].encode())})
        else:
            if len(stage) != 2:
                raise Refusal('typed reserved launch stage required')
            prefix, row = self._attempt(candidate, stage[1])
            kind = 'compile' if endpoint == 'compile/create' else 'backtest'
            spent = self._value(prefix + '.' + kind + '.spent.json')
            if (project != self._project(candidate) or payload.get('projectId') != row['project_id']
                    or spent.get('payload_sha256') != digest(raw)):
                raise Refusal('reserved launch payload mismatch')
            self.exclusive(prefix + '.' + kind + '.transport-spent.json', {'at': utc()})

    def authenticate(self):
        return self._request('authenticate', {})

    def prepare_packet(self):
        """Exactly one new explicit read of the original own derived packet."""
        self._access()
        prefix = 'packet-read.' + self.operation
        self.exclusive(prefix + '.spent.json', {'at': utc(), 'path': PACKET_PATH,
            'packet_sha256': PACKET_HASH, 'manifest_sha256': self.manifest_sha256,
            'old_source_or_d0_read': False})
        source = LANE / PACKET_PATH
        if self.fixture:
            source = self.root / 'fixture-packet.json'
        raw = _read(source.parent, source.name, 16 * 1024 * 1024)
        if digest(raw) != PACKET_HASH:
            raise Refusal('original packet hash mismatch')
        self.exclusive('signal-packet.' + self.operation + '.json', raw)
        self.exclusive(prefix + '.completed.json', {'at': utc(), 'sha256': digest(raw), 'bytes': len(raw)})
        return {'sha256': digest(raw), 'bytes': len(raw)}

    def create_project(self, candidate):
        self._access()
        specification = self._candidate(candidate)
        self.exclusive(candidate + '.project-create.spent.json', {'at': utc(),
            'manifest_sha256': self.manifest_sha256, 'name': specification['project_name']})
        try:
            result = self._request('projects/create', {'name': specification['project_name'], 'language': 'Py'},
                                   stage=(candidate,))
            rows = result.get('projects')
            if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
                raise Refusal('ambiguous project create response')
            row = rows[0]
            collaborators = row.get('collaborators', [])
            if (type(row.get('projectId')) is not int or row.get('name') != specification['project_name']
                    or row.get('owner') is not True or row.get('isPublic') is True
                    or type(collaborators) is not list
                    or any(type(item) is not dict or item.get('owner') is not True for item in collaborators)
                    or type(row.get('maxFileSize')) is not int or row['maxFileSize'] < 60000
                    or not _name(row.get('organizationId'), 100)):
                raise Refusal('fresh project ownership/quota refused')
            project = {'candidate_id': candidate, 'project_id': row['projectId'],
                'name': row['name'], 'owner': True, 'organization_id': row['organizationId'],
                'max_file_size': row['maxFileSize'], 'lean_version_id': row.get('leanVersionId'), 'at': utc()}
            existing = list(self.root.glob('*.project.json'))
            if len(existing) >= 6:
                raise Refusal('six fresh projects already registered')
            if any(self._value(path.name)['organization_id'] != project['organization_id'] for path in existing):
                raise Refusal('new projects belong to different organizations')
            self.exclusive(candidate + '.project.json', project)
            self.exclusive(candidate + '.project-create.terminal.json', {'status': 'registered', 'at': utc()})
            return project
        except Exception:
            if not (self.root / (candidate + '.project-create.terminal.json')).exists():
                self.exclusive(candidate + '.project-create.terminal.json', {'at': utc(), 'status': 'failed_or_unknown'})
            raise Refusal('project creation failed or uncertain; do not create again') from None

    def upload_packet(self, candidate):
        self._access()
        project = self._project(candidate)
        raw = self.read_private('signal-packet.' + self.operation + '.json')
        if digest(raw) != PACKET_HASH:
            raise Refusal('prepared packet changed')
        key = f'tpr-matched/{STUDY}/{PACKET_HASH}.json'
        boundary = 'tpr-matched-' + PACKET_HASH
        wire = b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n').encode()
            for field, value in (('organizationId', project['organization_id']), ('key', key)))
        wire += (f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="{PACKET_HASH}.json"\r\n'
                 'Content-Type: application/json\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
        self.exclusive('packet-upload.spent.json', {'at': utc(), 'key': key,
            'packet_sha256': PACKET_HASH, 'manifest_sha256': self.manifest_sha256,
            'organization_id': project['organization_id'], 'bytes': len(raw), 'wire_sha256': digest(wire)})
        self._request('object/set', wire, content_type='multipart/form-data; boundary=' + boundary, stage=('packet',))
        self.exclusive('packet-upload.completed.json', {'at': utc(), 'key': key, 'packet_sha256': PACKET_HASH})
        return {'key': key, 'sha256': PACKET_HASH}

    def _cloud_files(self, candidate):
        project = self._project(candidate)
        result = self._request('files/read', {'projectId': project['project_id']}, project=project)
        rows = result.get('files')
        if type(rows) is not list or len(rows) > 5:
            raise Refusal('cloud source inventory refused')
        files = {}
        for row in rows:
            if (type(row) is not dict or row.get('name') not in SOURCE_FILES | {'research.ipynb'}
                    or row['name'] in files or type(row.get('content')) is not str
                    or len(row['content'].encode()) > project['max_file_size']):
                raise Refusal('unexpected cloud file; do not overwrite')
            files[row['name']] = row['content']
        return files

    def upload_sources(self, candidate, files):
        self._access()
        specification, project = self._candidate(candidate), self._project(candidate)
        if (type(files) is not dict or set(files) != SOURCE_FILES
                or any(type(raw) is not str or len(raw.encode()) > min(60000, project['max_file_size'])
                       or digest(raw.encode()) != specification['source_hashes'][name]
                       for name, raw in files.items())):
            raise Refusal('uploaded file bytes do not match frozen bundle')
        self._config(candidate, files['matched_config.py'])
        self.exclusive(candidate + '.source-upload.' + self.operation + '.spent.json', {
            'at': utc(), 'source_hashes': specification['source_hashes'], 'manifest_sha256': self.manifest_sha256})
        existing = self._cloud_files(candidate)
        if 'research.ipynb' in existing:
            receipt = candidate + '.notebook.json'
            expected = digest(existing['research.ipynb'].encode())
            if (self.root / receipt).exists():
                if self._value(receipt)['sha256'] != expected:
                    raise Refusal('unrelated notebook changed')
            else:
                self.exclusive(receipt, {'sha256': expected})
        for name in sorted(files):
            endpoint = 'files/update' if name in existing else 'files/create'
            self._request(endpoint, {'projectId': project['project_id'], 'name': name,
                'content': files[name]}, project=project, stage=(candidate,))
        return self.verify_cloud_sources(candidate)

    def verify_cloud_sources(self, candidate):
        self._access()
        specification = self._candidate(candidate)
        files = self._cloud_files(candidate)
        if not SOURCE_FILES <= set(files):
            raise Refusal('cloud sources incomplete')
        hashes = {name: digest(files[name].encode()) for name in SOURCE_FILES}
        if hashes != specification['source_hashes']:
            raise Refusal('cloud source content differs from frozen bundle')
        self._config(candidate, files['matched_config.py'])
        notebook = candidate + '.notebook.json'
        if (self.root / notebook).exists() and (
                'research.ipynb' not in files or digest(files['research.ipynb'].encode()) != self._value(notebook)['sha256']):
            raise Refusal('unrelated cloud notebook changed')
        seq = self._seq(candidate + '.source-verification.', '.json')
        receipt = {'at': utc(), 'candidate_id': candidate, 'source_hashes': hashes,
            'config_sha256': specification['config_sha256'], 'input_hashes': self.manifest['input_hashes'],
            'manifest_sha256': self.manifest_sha256, 'equal': True}
        receipt_hash = self.exclusive(f'{candidate}.source-verification.{seq:04d}.json', receipt)
        return {'sha256': receipt_hash, **receipt}

    def _config(self, candidate, module):
        """Read one CONFIG_JSON literal without executing fetched source code."""
        try:
            tree = ast.parse(module)
            statements = [node for node in tree.body if not (
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and type(node.value.value) is str)]
            if len(statements) != 1 or not isinstance(statements[0], ast.Assign):
                raise ValueError
            node = statements[0]
            if (len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)
                    or node.targets[0].id != 'CONFIG_JSON' or not isinstance(node.value, ast.Constant)
                    or type(node.value.value) is not str):
                raise ValueError
            text = node.value.value
            body = _json(text)
            arm = 'tpr_on' if '-ON-' in candidate else 'tpr_off' if '-OFF-' in candidate else 'etf_basket'
            cost = 'adverse' if '-ADVERSE-' in candidate else 'baseline'
            if (digest(text.encode()) != self._candidate(candidate)['config_sha256']
                    or type(body) is not dict or set(body) != {
                        'schema', 'study_id', 'freeze_sha256', 'candidate_id', 'arm', 'cost', 'slippage'}
                    or body.get('schema') != 'tpr-qc-matched-config-v1' or body.get('candidate_id') != candidate
                    or body.get('study_id') != STUDY or body.get('freeze_sha256') != FREEZE_HASH
                    or body.get('arm') != arm or body.get('cost') != cost
                    or body.get('slippage') != ('0.0015' if cost == 'adverse' else '0.001')):
                raise ValueError
            return body
        except (ValueError, TypeError, SyntaxError):
            raise Refusal('matched configuration literal/hash binding refused') from None

    def reserve_attempt(self, candidate):
        self._access()
        specification, project = self._candidate(candidate), self._project(candidate)
        numbers = []
        for path in self.root.glob(candidate + '.attempt.*.reserved.json'):
            middle = path.name[len(candidate + '.attempt.'):-len('.reserved.json')]
            if not middle.isdigit():
                raise Refusal('malformed candidate attempt sequence')
            numbers.append(int(middle))
        attempt = max(numbers, default=0) + 1
        if attempt > 3:
            raise Refusal('three candidate attempts consumed; Mia or owner recovery required')
        verification = self.verify_cloud_sources(candidate)
        receipt = {'at': utc(), 'candidate_id': candidate, 'attempt': attempt,
            'project_id': project['project_id'], 'manifest_sha256': self.manifest_sha256,
            'freeze_sha256': self.manifest['freeze_sha256'], 'source_hashes': specification['source_hashes'],
            'config_sha256': specification['config_sha256'], 'input_hashes': self.manifest['input_hashes'],
            'source_verification_sha256': verification['sha256'], 'compile_counts_as_attempt': True,
            'fixture': self.fixture, 'status': 'reserved'}
        self.exclusive(f'{candidate}.attempt.{attempt}.reserved.json', receipt)
        return receipt

    def _attempt(self, candidate, attempt):
        specification = self._candidate(candidate)
        if type(attempt) is not int or not 1 <= attempt <= 3:
            raise Refusal('reserved attempt required')
        prefix = f'{candidate}.attempt.{attempt}'
        row = self._value(prefix + '.reserved.json')
        expected = {'candidate_id': candidate, 'attempt': attempt,
            'project_id': self._project(candidate)['project_id'], 'manifest_sha256': self.manifest_sha256,
            'freeze_sha256': self.manifest['freeze_sha256'], 'source_hashes': specification['source_hashes'],
            'config_sha256': specification['config_sha256'], 'input_hashes': self.manifest['input_hashes']}
        if any(row.get(key) != value for key, value in expected.items()):
            raise Refusal('attempt/code/input binding changed')
        return prefix, row

    def compile_candidate(self, candidate, attempt):
        self._access()
        prefix, row = self._attempt(candidate, attempt)
        verification = self.verify_cloud_sources(candidate)
        payload = {'projectId': row['project_id']}
        self.exclusive(prefix + '.compile.spent.json', {'at': utc(), 'source_verification_sha256': verification['sha256'],
            'payload_sha256': digest(canonical(payload))})
        try:
            result = self._request('compile/create', payload, project=self._project(candidate), stage=(candidate, attempt))
            compile_id = result.get('compileId')
            if not _name(compile_id, 200):
                raise Refusal('compile identity missing')
            self.exclusive(prefix + '.compile.launched.json', {'at': utc(), 'compile_id': compile_id,
                'project_id': row['project_id'], 'source_hashes': row['source_hashes'], 'state': result.get('state')})
            return {'compile_id': compile_id, 'state': result.get('state')}
        except Exception:
            self.exclusive(prefix + '.compile.failed-or-unknown.json', {'at': utc(), 'status': 'failed_or_unknown'})
            raise Refusal('compile failed or uncertain; attempt stays consumed') from None

    def poll_compile(self, candidate, attempt):
        self._access()
        prefix, row = self._attempt(candidate, attempt)
        launched = self._value(prefix + '.compile.launched.json')
        if (self.root / (prefix + '.compile.verified.json')).exists():
            return {'compile_id': launched['compile_id'], 'state': 'BuildSuccess'}
        if (self.root / (prefix + '.compile.failed.json')).exists():
            return {'compile_id': launched['compile_id'], 'state': self._value(prefix + '.compile.failed.json')['state']}
        result = self._request('compile/read', {'projectId': row['project_id'],
            'compileId': launched['compile_id']}, project=self._project(candidate))
        if (result.get('compileId') != launched['compile_id']
                or result.get('projectId', row['project_id']) != row['project_id']):
            raise Refusal('compile poll identity mismatch')
        seq = self._seq(prefix + '.compile.poll.', '.json')
        response_hash = self.exclusive(f'{prefix}.compile.poll.{seq:04d}.json', result)
        state = result.get('state')
        if state == 'BuildSuccess':
            verification = self.verify_cloud_sources(candidate)
            verified = {'at': utc(), 'state': state, 'compile_id': launched['compile_id'],
                'project_id': row['project_id'], 'source_hashes': row['source_hashes'],
                'manifest_sha256': self.manifest_sha256, 'compile_response_sha256': response_hash,
                'compile_response_file': f'{prefix}.compile.poll.{seq:04d}.json',
                'source_verification_sha256': verification['sha256']}
            self.exclusive(prefix + '.compile.verified.json', verified)
        elif state in {'BuildError', 'Error', 'Failed'}:
            self.exclusive(prefix + '.compile.failed.json', {'at': utc(), 'state': state, 'compile_response_sha256': response_hash})
        return {'compile_id': launched['compile_id'], 'state': state}

    def _verified_compile(self, prefix, row):
        verified = self._value(prefix + '.compile.verified.json')
        launched = self._value(prefix + '.compile.launched.json')
        response_file = verified.get('compile_response_file')
        if (type(response_file) is not str or re.fullmatch(
                re.escape(prefix) + r'[.]compile[.]poll[.][0-9]{4}[.]json', response_file) is None):
            raise Refusal('verified compile response file required')
        response_raw = self.read_private(response_file)
        response = _json(response_raw)
        if (verified.get('state') != 'BuildSuccess' or verified.get('compile_id') != launched['compile_id']
                or verified.get('project_id') != row['project_id']
                or verified.get('source_hashes') != row['source_hashes']
                or verified.get('manifest_sha256') != self.manifest_sha256
                or digest(response_raw) != verified.get('compile_response_sha256')
                or response.get('state') != 'BuildSuccess' or response.get('compileId') != launched['compile_id']
                or response.get('projectId', row['project_id']) != row['project_id']):
            raise Refusal('matching verified BuildSuccess receipt required')
        return verified

    def launch_backtest(self, candidate, attempt):
        self._access()
        prefix, row = self._attempt(candidate, attempt)
        verified = self._verified_compile(prefix, row)
        if '-ON-' in candidate:
            packet = self._value('packet-upload.completed.json')
            if packet.get('packet_sha256') != PACKET_HASH or packet.get('key') != f'tpr-matched/{STUDY}/{PACKET_HASH}.json':
                raise Refusal('TPR-on requires the admitted private packet upload')
        verification = self.verify_cloud_sources(candidate)
        payload = {'projectId': row['project_id'], 'compileId': verified['compile_id'],
                   'backtestName': candidate + '-attempt-' + str(attempt)}
        self.exclusive(prefix + '.backtest.spent.json', {'at': utc(),
            'compile_id': verified['compile_id'], 'source_verification_sha256': verification['sha256'],
            'payload_sha256': digest(canonical(payload)),
            'development_look_consumed': not self.fixture, 'fixture': self.fixture})
        try:
            result = self._request('backtests/create', payload, project=self._project(candidate), stage=(candidate, attempt))
            backtest = result.get('backtest')
            if type(backtest) is not dict or not _name(backtest.get('backtestId'), 200):
                raise Refusal('backtest identity missing')
            identity = {'at': utc(), 'project_id': row['project_id'], 'compile_id': verified['compile_id'],
                'backtest_id': backtest['backtestId'], 'completed': False}
            self.exclusive(prefix + '.backtest.launched.json', identity)
            return identity
        except Exception:
            self.exclusive(prefix + '.backtest.failed-or-unknown.json', {'at': utc(), 'status': 'failed_or_unknown'})
            raise Refusal('backtest failed or uncertain; attempt/look stays consumed') from None

    def poll_backtest(self, candidate, attempt):
        self._access()
        prefix, row = self._attempt(candidate, attempt)
        launched = self._value(prefix + '.backtest.launched.json')
        if (self.root / (prefix + '.backtest.result.json')).exists():
            stored = self._value(prefix + '.backtest.result.json')
            return {'backtest_id': launched['backtest_id'], 'completed': stored.get('completed') is True,
                'terminal': True, 'status': stored.get('status'), 'error': bool(stored.get('error')),
                'result_sha256': digest(canonical(stored))}
        result = self._request('backtests/read', {'projectId': row['project_id'],
            'backtestId': launched['backtest_id']}, project=self._project(candidate))
        backtest = result.get('backtest')
        if (type(backtest) is not dict or backtest.get('backtestId') != launched['backtest_id']
                or backtest.get('projectId', row['project_id']) != row['project_id']):
            raise Refusal('backtest poll identity mismatch')
        # Keep own portfolio/results/order metadata; no benchmark/market chart export.
        safe = {key: value for key, value in backtest.items() if key != 'charts'}
        if type(backtest.get('charts')) is dict:
            safe['charts'] = {key: value for key, value in backtest['charts'].items()
                              if key in {'Strategy Equity', 'Drawdown', 'Portfolio Turnover'}}
        seq = self._seq(prefix + '.backtest.poll.', '.json')
        result_hash = self.exclusive(f'{prefix}.backtest.poll.{seq:04d}.json', safe)
        terminal = backtest.get('completed') is True or bool(backtest.get('error'))
        if terminal:
            self.exclusive(prefix + '.backtest.result.json', safe)
        return {'backtest_id': launched['backtest_id'], 'completed': backtest.get('completed') is True,
            'terminal': terminal, 'status': backtest.get('status'), 'error': bool(backtest.get('error')),
            'result_sha256': result_hash}

    def collect_terminal(self, candidate, attempt):
        """Explicitly collect one bounded read-only round for an existing terminal job.

        Each call reserves an immutable numbered round before its first API read.
        Loading/incomplete evidence remains a diagnostic; a caller can deliberately
        recollect the same job, at most five times, without another attempt or look.
        No automatic retry, source upload, compile or backtest launch occurs here.
        """
        self._access()
        attempt_prefix, row = self._attempt(candidate, attempt)
        launched = self._value(attempt_prefix + '.backtest.launched.json')
        result = self._value(attempt_prefix + '.backtest.result.json')
        if (result.get('backtestId') != launched['backtest_id'] or
                not (result.get('completed') is True or bool(result.get('error')))):
            raise Refusal('verified terminal backtest result required')
        collection_round = self._seq(attempt_prefix + '.collection.', '.spent.json')
        if collection_round > 5:
            raise Refusal('five read-only collection rounds consumed; no automatic retry or cap reset')
        prefix = f'{attempt_prefix}.collection.{collection_round:04d}'
        self.exclusive(prefix + '.spent.json', {'at': utc(), 'candidate_id': candidate, 'attempt': attempt,
            'collection_round': collection_round, 'project_id': row['project_id'],
            'backtest_id': launched['backtest_id'], 'compile_id': launched['compile_id'],
            'manifest_sha256': self.manifest_sha256, 'read_only': True, 'automatic_retry': False,
            'new_compile_attempts': 0, 'new_backtest_launches': 0, 'new_development_looks': 0,
            'fixture': self.fixture})
        payload = {'projectId': row['project_id'], 'backtestId': launched['backtest_id']}
        try:
            compiled = self._verified_compile(attempt_prefix, row)
            if compiled['compile_id'] != launched['compile_id']:
                raise Refusal('terminal evidence compile/source binding refused')
            verification = self.verify_cloud_sources(candidate)
            self.exclusive(prefix + '.source-verification.json', verification)
            config = self._config(candidate, self._cloud_files(candidate)['matched_config.py'])
        except Exception:
            error = {'at': utc(), 'candidate_id': candidate, 'attempt': attempt,
                'collection_round': collection_round, 'project_id': row['project_id'],
                'backtest_id': launched['backtest_id'], 'manifest_sha256': self.manifest_sha256,
                'stage': 'compile_source_binding', 'status': 'failed_or_incomplete',
                'read_only': True, 'automatic_retry': False, 'strategy_accepted': False}
            self.exclusive(prefix + '.error.json', error)
            error_hash = self.exclusive(prefix + '.completion.json', {**error,
                'schema': 'tpr-qc-completion-v2', 'classification': 'diagnostic_or_incomplete',
                'canonical_admission': False, 'fixture': self.fixture})
            self._collection_index(prefix, error_hash)
            raise Refusal('numbered collection compile/source verification refused; no implicit retry') from None
        orders, logs, errors, order_pages = [], [], [], []
        stage = 'orders'
        try:
            start, total = 0, None
            while total is None or start < total:
                response = self._request('backtests/orders/read', {**payload, 'start': start, 'end': start + 99},
                                         project=self._project(candidate))
                page = {**response, 'start': start, 'end': start + 99}
                # Retain Loading and unexpected successful response shapes before
                # validating pagination; their absence is not an empty data set.
                self.exclusive(f'{prefix}.orders.{start:05d}.wire.json', response)
                self.exclusive(f'{prefix}.orders.{start:05d}.json', page)
                values, reported = page.get('orders'), page.get('length')
                if (type(values) is not list or type(reported) is not int or not 0 <= reported <= 10000
                        or (total is not None and total != reported) or len(values) > 99):
                    raise Refusal('order page contract refused')
                total = reported
                order_pages.append(page)
                orders.extend(values)
                if not values and start < total:
                    raise Refusal('missing required order page')
                start += 99
            if len(orders) != total:
                raise Refusal('complete order census mismatch')
            ids = [item.get('id') for item in orders if type(item) is dict]
            if len(ids) != len(orders) or len(set(ids)) != len(ids) or any(type(item) is not int for item in ids):
                raise Refusal('duplicate or missing order identity')
            stage = 'logs'
            start, total = 0, None
            while total is None or start < total:
                page = self._request('backtests/read/log', {**payload, 'start': start, 'end': start + 200,
                    'query': self.manifest['log_prefix']}, project=self._project(candidate))
                self.exclusive(f'{prefix}.logs.{start:05d}.wire.json', page)
                self.exclusive(f'{prefix}.logs.{start:05d}.json', {**page, 'start': start, 'end': start + 200})
                values, reported = page.get('logs'), page.get('length')
                if (type(values) is not list or type(reported) is not int or not 0 <= reported <= 4000
                        or (total is not None and total != reported)
                        or any(type(line) is not str or len(line) > 8192
                               or self.manifest['log_prefix'] not in line for line in values)):
                    raise Refusal('prefixed own aggregate log contract refused')
                total = reported
                logs.extend(values)
                if not values and start < total:
                    raise Refusal('missing required aggregate log page')
                start += 200
            if len(logs) != total:
                raise Refusal('complete aggregate log census mismatch')
        except Exception:
            errors.append('collection_failed_or_incomplete; no implicit retry')
            self.exclusive(prefix + '.error.json', {'at': utc(), 'candidate_id': candidate,
                'attempt': attempt, 'collection_round': collection_round, 'project_id': row['project_id'],
                'backtest_id': launched['backtest_id'], 'stage': stage, 'status': 'failed_or_incomplete',
                'read_only': True, 'automatic_retry': False})
        filled = [order for order in orders if type(order) is dict and order.get('status') == 3]
        audit = {'schema': 'tpr-qc-completion-v2', 'at': utc(), 'candidate_id': candidate, 'attempt': attempt,
            'collection_round': collection_round, 'receipt_prefix': prefix,
            'project_id': row['project_id'], 'compile_id': launched['compile_id'],
            'backtest_id': launched['backtest_id'], 'manifest_sha256': self.manifest_sha256,
            'freeze_sha256': row['freeze_sha256'], 'config_sha256': row['config_sha256'],
            'source_hashes': row['source_hashes'], 'input_hashes': row['input_hashes'],
            'engine_completed': result.get('completed') is True, 'engine_error': bool(result.get('error')),
            'order_count': len(orders), 'filled_order_count': len(filled), 'aggregate_log_count': len(logs),
            'collection_errors': errors, 'has_filled_order_status': bool(filled) and not errors,
            'classification': ('diagnostic_or_incomplete' if errors or not filled or result.get('error')
                               else 'completed_orders_require_strategy_accounting_audit'),
            'strategy_accepted': False, 'canonical_admission': False, 'fixture': self.fixture}
        audit_hash = self.exclusive(prefix + '.completion.json', audit)
        result_response = {'success': True, 'backtest': result}
        logs_response = {'success': True, 'logs': logs, 'length': len(logs)}
        source_receipt = {'candidate_id': candidate, 'project_id': row['project_id'],
            'backtest_id': launched['backtest_id'], 'compile_id': launched['compile_id'],
            'config_sha256': row['config_sha256'], 'packet_sha256': PACKET_HASH if '-ON-' in candidate else None,
            'freeze_sha256': row['freeze_sha256'], 'source_hashes': row['source_hashes'],
            'exact_cloud_readback': True, 'build_success': True,
            'source_verification_sha256': verification['sha256'],
            'evidence_hashes': {'result': digest(canonical(result_response)), 'logs': digest(canonical(logs_response)),
                                'order_pages': [digest(canonical(page)) for page in order_pages]}}
        self.exclusive(prefix + '.source-receipt.json', source_receipt)
        self.exclusive(prefix + '.logs.combined.json', logs_response)
        self._collection_index(prefix, audit_hash)
        return {'collection_round': collection_round, 'receipt_prefix': prefix,
                'completion': audit, 'result_response': result_response, 'logs_response': logs_response,
                'order_pages': order_pages, 'source_receipt': source_receipt, 'candidate_config': config}

    def _collection_index(self, prefix, completion_hash):
        """Private immutable metadata index; no licensed rows or source in Git."""
        files = [{'name': path.name, 'sha256': digest(self.read_private(path.name)), 'bytes': path.stat().st_size}
                 for path in sorted(self.root.iterdir()) if path.is_file()]
        self.exclusive(prefix + '.evidence-index.json', {'schema': 'tpr-qc-evidence-v2', 'at': utc(),
            'manifest_sha256': self.manifest_sha256, 'completion_sha256': completion_hash, 'files': files})
