"""Bounded private QC-only operations for the frozen six-universe experiment.

No import performs I/O. Receipts precede credentials, source reads and launches.
The fixed local custody is cooperative; it is not canonical antirollback trust.
Only fresh projects registered here can receive source or launches. No data,
optimization, broker, live, sharing or subscription endpoint is reachable.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

LANE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
BASELINE = '530e95a554a9d06e954cf86df44d3a591d6d4996'
PACKAGE = LANE / 'research/target_price_revisions_qc'
PRIVATE = LANE / 'artifacts/target_price_qc6/TPR-QC6-20261008-v1'
SOURCE = LANE / 'artifacts/target_price_raw_revision/TPR-DEV-RAWREV-v1/structure.json'
SOURCE_HASH = '509047244d47ec489e5a8e1dfbf74e0d0104b51c7dfff19ae7283abba1e9ccd5'
FREEZE_HASH = '3cf40af7325265b15f7de5e03f0667a1554c889fdd2db02de228a01b2fa97ccf'
ALLOWED = frozenset({'authenticate', 'projects/create', 'projects/read', 'files/create',
    'files/update', 'files/read', 'compile/create', 'compile/read', 'backtests/create',
    'backtests/read', 'backtests/orders/read', 'backtests/read/log'})


class Refusal(ValueError):
    """Sanitized boundary or operational failure."""


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                       allow_nan=False) + '\n').encode('ascii')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def guard():
    if Path.cwd().resolve() != LANE or Path.cwd() != LANE:
        raise Refusal('wrong physical lane')
    def git(*args):
        return subprocess.run(['git', *args], cwd=LANE, check=True,
            capture_output=True, text=True).stdout.strip()
    if git('rev-parse', '--show-toplevel') != str(LANE) or git('branch', '--show-current') != BRANCH:
        raise Refusal('wrong Git lane')
    head = git('rev-parse', 'HEAD')
    if head != BASELINE:
        raise Refusal('unexpected implementation baseline')
    # Status is inspected at every operational boundary; other agents' scoped
    # implementation files are allowed, never staged or overwritten here.
    return {'head': head, 'status': git('status', '--short')}


def _custody_info(info, directory=False):
    if (info.st_uid != os.getuid() or stat.S_ISLNK(info.st_mode)
            or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not directory and info.st_nlink != 1)):
        raise Refusal('private custody refused')


def _custody(path, directory=False):
    _custody_info(path.lstat(), directory)


def _read_custodied(directory, name, maximum):
    """Anchor a no-follow file read to a checked directory descriptor."""
    directory_fd = file_fd = None
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        _custody_info(os.fstat(directory_fd), True)
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        before = os.fstat(file_fd)
        _custody_info(before)
        with os.fdopen(file_fd, 'rb') as stream:
            file_fd = None
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            _custody_info(after)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise Refusal('private input changed during read')
        if len(raw) > maximum:
            raise Refusal('private input exceeds bound')
        return raw
    except OSError:
        raise Refusal('private custody read refused') from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _root():
    # Never relax an existing path or follow an existing symlink.
    for path in (PRIVATE.parent, PRIVATE):
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _custody(path, True)
    return PRIVATE


def exclusive(name, value):
    if re.fullmatch(r'[A-Za-z0-9_.-]{1,150}', name) is None:
        raise Refusal('invalid receipt name')
    root = _root()
    raw = value if type(value) is bytes else canonical(value)
    try:
        fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise Refusal('operation already reserved; no implicit retry') from None
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(raw)


def read_private(name, maximum=32 * 1024 * 1024):
    if re.fullmatch(r'[A-Za-z0-9_.-]{1,150}', name) is None:
        raise Refusal('invalid private name')
    return _read_custodied(PRIVATE, name, maximum)


def freeze_body():
    raw = (PACKAGE / 'six_universe_freeze.json').read_bytes()
    body = json.loads(raw)
    if len(body['universes']) != 6 or body['review_baseline'] != BASELINE:
        raise Refusal('invalid six-case freeze')
    if digest(raw) != FREEZE_HASH:
        raise Refusal('freeze changed from the six-case preregistration')
    return body, digest(raw)


def prepare_access():
    context = guard()
    body, frozen = freeze_body()
    receipt = {'schema': 'tpr-qc6-access-v1', 'operation_id': body['operations']['fresh_operation_id'],
        'created_utc': utc(), 'freeze_sha256': frozen, 'git_head': context['head'],
        'operations_source_sha256': digest(Path(__file__).read_bytes()),
        'source_path': str(SOURCE.relative_to(LANE)), 'source_sha256': SOURCE_HASH,
        'source_max_bytes': 32 * 1024 * 1024, 'source_reads': 1,
        'source_refreshes': 0, 'old_outcome_reads': 0, 'd0_reads': 0,
        'qc_credentials': ['QC_USER_ID', 'QC_API_TOKEN'],
        'allowed_endpoints': sorted(ALLOWED), 'max_requests': 1000,
        'specialized_endpoints': ['object/set:one-frozen-plaintext-packet'],
        'max_response_bytes': 16 * 1024 * 1024, 'request_timeout_seconds': 30,
        'max_projects': 6, 'max_attempts_each': 3, 'prior_local_looks': 2,
        'confirmatory_alpha': '0', 'canonical_admission': False, 'trading': False}
    return exclusive('access.json', receipt)


def access():
    body = json.loads(read_private('access.json'))
    if body['freeze_sha256'] != freeze_body()[1]:
        raise Refusal('freeze changed after access reservation')
    if body['operations_source_sha256'] != digest(Path(__file__).read_bytes()):
        raise Refusal('operations source changed after access reservation')
    created = datetime.fromisoformat(body['created_utc'])
    if not 0 <= (datetime.now(timezone.utc) - created).total_seconds() <= 172800:
        raise Refusal('access scope expired')
    return body


def read_structure():
    guard()
    authority = access()
    exclusive('source-read.spent.json', {'at': utc(), 'source_sha256': SOURCE_HASH,
        'freeze_sha256': authority['freeze_sha256'], 'outcomes': False})
    raw = _read_custodied(SOURCE.parent, SOURCE.name, 32 * 1024 * 1024)
    if digest(raw) != SOURCE_HASH:
        raise Refusal('frozen source input mismatch')
    exclusive('source-read.completed.json', {'at': utc(), 'sha256': digest(raw), 'bytes': len(raw)})
    return raw


def _project_receipt(case):
    body, _ = freeze_body()
    matches = [u for u in body['universes'] if u['case'] == case]
    if len(matches) != 1:
        raise Refusal('unknown frozen universe')
    return matches[0]


def registered_project(case):
    _project_receipt(case)
    return json.loads(read_private(case + '.project.json'))['project_id']


def post(endpoint, payload=None, *, _stage_context=None, _project_context=None):
    guard()
    authority = access()
    if endpoint not in ALLOWED:
        raise Refusal('QC endpoint outside scoped research authority')
    payload = {} if payload is None else payload
    if endpoint == 'projects/create':
        if type(_project_context) is not str:
            raise Refusal('typed frozen project creation required')
        identity = _project_receipt(_project_context)
        spent = json.loads(read_private(_project_context + '.project-create.spent.json'))
        expected = {'name': identity['id'] + '-private', 'language': 'Py'}
        if payload != expected or spent.get('name') != expected['name']:
            raise Refusal('project creation binding mismatch')
        exclusive(_project_context + '.project-create.transport-spent.json',
                  {'at': utc(), 'payload_sha256': digest(canonical(payload))})
    if endpoint not in {'authenticate', 'projects/create'}:
        project_id = payload.get('projectId', payload.get('id'))
        known = []
        for case in freeze_body()[0]['universes']:
            name = case['case'] + '.project.json'
            if (PRIVATE / name).exists():
                known.append(json.loads(read_private(name))['project_id'])
        if type(project_id) is not int or project_id not in known:
            raise Refusal('unregistered cloud project')
    if endpoint in {'compile/create', 'backtests/create'}:
        _consume_launch_context(endpoint, payload, _stage_context)
    return _request(endpoint, canonical(payload), 'application/json')


def _request(endpoint, wire_body, content_type):
    """Private transport shared by admitted JSON and specialized upload calls."""
    guard()
    authority = access()
    if endpoint not in ALLOWED and endpoint != 'object/set':
        raise Refusal('QC transport endpoint outside scoped research authority')
    # An immutable request slot is written before credential resolution or I/O.
    slots = [int(p.name.split('.')[1]) for p in PRIVATE.glob('request.*.json')]
    seq = max(slots, default=0) + 1
    if seq > authority['max_requests']:
        raise Refusal('QC request budget exhausted')
    exclusive(f'request.{seq:04d}.json', {'at': utc(), 'endpoint': endpoint,
        'payload_sha256': digest(wire_body), 'payload_bytes': len(wire_body)})
    uid = os.environ.get('QC_USER_ID', '').strip()
    token = os.environ.get('QC_API_TOKEN', '').strip()
    if not uid or not token:
        exclusive(f'request.{seq:04d}.terminal.json', {'status': 'credentials_missing', 'at': utc()})
        raise Refusal('QC_USER_ID / QC_API_TOKEN unavailable in process environment')
    stamp = str(int(time.time()))
    signed = digest((token + ':' + stamp).encode())
    auth = base64.b64encode((uid + ':' + signed).encode()).decode()
    conn = None
    status = 0
    try:
        conn = http.client.HTTPSConnection('www.quantconnect.com', timeout=30, context=ssl.create_default_context())
        conn.request('POST', '/api/v2/' + endpoint, body=wire_body,
            headers={'Authorization': 'Basic ' + auth, 'Timestamp': stamp, 'Content-Type': content_type})
        response = conn.getresponse()
        status = response.status
        raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise Refusal('QC response exceeds bound')
        if token.encode() in raw:
            raise Refusal('credential echo refused')
        value = json.loads(raw)
        if type(value) is not dict or status != 200 or value.get('success') is not True:
            # Retain bounded sanitized errors privately, not raw response rows.
            errors = value.get('errors', []) if type(value) is dict else []
            errors = [str(e).replace(token, '[redacted]')[:400] for e in errors[:5]] if type(errors) is list else []
            exclusive(f'request.{seq:04d}.terminal.json', {'status': 'failed', 'http': status,
                'at': utc(), 'errors': errors})
            raise Refusal(f'QC request failed; HTTP {status}; private terminal slot {seq}')
        exclusive(f'request.{seq:04d}.terminal.json', {'status': 'succeeded', 'http': status,
            'at': utc(), 'response_bytes': len(raw)})
        return value
    except Refusal:
        if not (PRIVATE / f'request.{seq:04d}.terminal.json').exists():
            exclusive(f'request.{seq:04d}.terminal.json', {'status': 'response_refused',
                'http': status, 'at': utc()})
        raise
    except Exception:
        if not (PRIVATE / f'request.{seq:04d}.terminal.json').exists():
            exclusive(f'request.{seq:04d}.terminal.json', {'status': 'transport_or_decode_failure',
                'http': status, 'at': utc()})
        raise Refusal('QC transport or JSON failure; no automatic retry') from None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                # The request terminal already records the outcome; a close
                # error must not expose arbitrary transport exception text.
                pass


def authenticate():
    result = post('authenticate')
    return {'success': result.get('success') is True}


def create_project(case):
    guard()
    identity = _project_receipt(case)
    access()
    name = identity['id'] + '-private'
    exclusive(case + '.project-create.spent.json', {'at': utc(), 'name': name})
    try:
        result = post('projects/create', {'name': name, 'language': 'Py'}, _project_context=case)
    except Exception:
        exclusive(case + '.project-create.terminal.json', {'at': utc(), 'status': 'failed_or_uncertain'})
        raise Refusal('project creation failed or uncertain; no implicit retry') from None
    rows = result.get('projects', [])
    if len(rows) != 1 or rows[0].get('name') != name or type(rows[0].get('projectId')) is not int:
        exclusive(case + '.project-create.terminal.json', {'at': utc(), 'status': 'ambiguous_creation'})
        raise Refusal('ambiguous fresh project creation; do not repeat create')
    project = rows[0]
    # The project must be ours; no sharing endpoint is ever called. Refuse
    # explicit public status or any collaborator not identified as its owner.
    if (project.get('owner') is not True or project.get('isPublic') is True
            or any(row.get('owner') is not True for row in project.get('collaborators', []))):
        exclusive(case + '.project-create.terminal.json', {'at': utc(), 'status': 'ownership_privacy_refused'})
        raise Refusal('fresh project ownership/privacy not established')
    record = {'project_id': project['projectId'], 'name': name, 'at': utc(),
        'owner': True, 'shared_by_this_operation': False, 'max_file_size': project.get('maxFileSize'),
        'lean_version_id': project.get('leanVersionId'), 'organization_id': project.get('organizationId')}
    exclusive(case + '.project.json', record)
    exclusive(case + '.project-create.terminal.json', {'at': utc(), 'status': 'registered',
                                                     'project_id': project['projectId']})
    return record


def reserve_attempt(case, source_hashes, packet_hash):
    guard()
    access()
    identity = _project_receipt(case)
    project = registered_project(case)
    if (type(source_hashes) is not dict or not source_hashes
            or any(type(name) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name) is None
                   or type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None
                   for name, value in source_hashes.items())
            or type(packet_hash) is not str or re.fullmatch(r'[0-9a-f]{64}', packet_hash) is None):
        raise Refusal('invalid attempt source hashes')
    attempts = [int(p.name.split('.')[2]) for p in PRIVATE.glob(case + '.attempt.*.reserved.json')]
    seq = max(attempts, default=0) + 1
    if seq > 3:
        raise Refusal('three attempts consumed; Mia or owner recovery required')
    receipt = {'at': utc(), 'candidate_id': identity['id'], 'case': case, 'attempt': seq,
        'project_id': project, 'freeze_sha256': freeze_body()[1], 'source_hashes': source_hashes,
        'packet_sha256': packet_hash, 'compile_counts_as_attempt': True,
        'look_reserved_before_backtest': True, 'status': 'reserved'}
    exclusive(f'{case}.attempt.{seq}.reserved.json', receipt)
    return receipt


def _attempt(case, number, source_hashes=None):
    identity = _project_receipt(case)
    if type(number) is not int or not 1 <= number <= 3:
        raise Refusal('invalid reserved attempt')
    prefix = f'{case}.attempt.{number}'
    receipt = json.loads(read_private(prefix + '.reserved.json'))
    if (receipt.get('case') != case or receipt.get('attempt') != number
            or receipt.get('candidate_id') != identity['id']
            or receipt.get('project_id') != registered_project(case)
            or receipt.get('freeze_sha256') != freeze_body()[1]
            or (source_hashes is not None and receipt.get('source_hashes') != source_hashes)):
        raise Refusal('reserved attempt binding mismatch')
    return prefix, receipt


def _consume_launch_context(endpoint, payload, context):
    if type(context) is not tuple or len(context) != 3:
        raise Refusal('typed reserved launch required')
    case, number, stage = context
    expected = 'compile' if endpoint == 'compile/create' else 'backtest'
    if stage != expected:
        raise Refusal('launch stage mismatch')
    prefix, receipt = _attempt(case, number)
    spent = json.loads(read_private(prefix + '.' + stage + '.spent.json'))
    if (payload.get('projectId') != receipt['project_id']
            or spent.get('payload_sha256') != digest(canonical(payload))):
        raise Refusal('launch payload binding mismatch')
    exclusive(prefix + '.' + stage + '.transport-spent.json', {'at': utc(), 'endpoint': endpoint})


def compile_candidate(case, attempt, source_hashes):
    """One compile launch, irreversibly consumed even on uncertain failure."""
    guard()
    access()
    prefix, receipt = _attempt(case, attempt, source_hashes)
    payload = {'projectId': receipt['project_id']}
    exclusive(prefix + '.compile.spent.json', {'at': utc(),
        'payload_sha256': digest(canonical(payload)), 'source_hashes': source_hashes})
    try:
        result = post('compile/create', payload, _stage_context=(case, attempt, 'compile'))
        compile_id = result.get('compileId')
        if type(compile_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,200}', compile_id) is None:
            raise Refusal('compile launch returned no usable compile ID')
        exclusive(prefix + '.compile.terminal.json', {'at': utc(), 'status': 'launched',
            'compile_id': compile_id, 'project_id': receipt['project_id'],
            'state': result.get('state')})
        return result
    except Exception:
        if not (PRIVATE / (prefix + '.compile.terminal.json')).exists():
            exclusive(prefix + '.compile.terminal.json', {'at': utc(), 'status': 'failed_or_uncertain'})
        raise Refusal('compile launch failed or uncertain; attempt remains consumed') from None


def launch_backtest(case, attempt, compile_id, name, source_hashes):
    """One backtest launch bound to this attempt's previously returned compile."""
    guard()
    access()
    prefix, receipt = _attempt(case, attempt, source_hashes)
    compiled = json.loads(read_private(prefix + '.compile.terminal.json'))
    if (compiled.get('status') != 'launched' or compiled.get('compile_id') != compile_id
            or compiled.get('project_id') != receipt['project_id']
            or type(name) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name) is None):
        raise Refusal('backtest compile/name binding mismatch')
    payload = {'projectId': receipt['project_id'], 'compileId': compile_id, 'backtestName': name}
    exclusive(prefix + '.backtest.spent.json', {'at': utc(), 'compile_id': compile_id,
        'payload_sha256': digest(canonical(payload)), 'source_hashes': source_hashes,
        'development_look_consumed': True})
    try:
        result = post('backtests/create', payload, _stage_context=(case, attempt, 'backtest'))
        backtest = result.get('backtest', {})
        backtest_id = backtest.get('backtestId') if type(backtest) is dict else None
        if type(backtest_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,200}', backtest_id) is None:
            raise Refusal('backtest launch returned no usable backtest ID')
        exclusive(prefix + '.backtest.terminal.json', {'at': utc(), 'status': 'launched',
            'backtest_id': backtest_id, 'compile_id': compile_id,
            'project_id': receipt['project_id'], 'completed': False})
        return result
    except Exception:
        if not (PRIVATE / (prefix + '.backtest.terminal.json')).exists():
            exclusive(prefix + '.backtest.terminal.json', {'at': utc(), 'status': 'failed_or_uncertain'})
        raise Refusal('backtest launch failed or uncertain; attempt and look remain consumed') from None


def upload_packet(case, raw):
    """One plaintext, content-addressed own-input Object Store upload only."""
    guard()
    authority = access()
    _project_receipt(case)
    project = json.loads(read_private(case + '.project.json'))
    organization = project.get('organization_id')
    if (project.get('owner') is not True or type(organization) is not str
            or re.fullmatch(r'[A-Za-z0-9_-]{1,100}', organization) is None):
        raise Refusal('fresh own-project organization binding required')
    if type(raw) is not bytes or not 0 < len(raw) <= 16 * 1024 * 1024:
        raise Refusal('bounded plaintext packet bytes required')
    from research.target_price_revisions_qc.packet import validate_packet
    try:
        value = json.loads(raw)
        validate_packet(value)
        if (canonical(value) != raw or value['freeze_sha256'] != authority['freeze_sha256']
                or value['source_hashes']['structure.json'] != SOURCE_HASH):
            raise ValueError('packet bindings')
    except (ValueError, KeyError, TypeError, RecursionError):
        raise Refusal('frozen plaintext packet refused') from None
    packet_hash = digest(raw)
    key = 'tpr-qc6/TPR-QC6-20261008-v1/' + packet_hash + '.json'
    boundary = 'tpr-qc6-' + packet_hash
    if boundary.encode() in raw:
        raise Refusal('multipart boundary collision')
    fields = [('organizationId', organization), ('key', key)]
    wire = b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n'
                    f'{value}\r\n').encode('ascii') for field, value in fields)
    wire += (f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; '
             f'filename="{packet_hash}.json"\r\nContent-Type: application/json\r\n\r\n').encode('ascii')
    wire += raw + f'\r\n--{boundary}--\r\n'.encode('ascii')
    exclusive('packet-upload.spent.json', {'at': utc(), 'case': case,
        'project_id': project['project_id'], 'organization_id': organization,
        'packet_sha256': packet_hash, 'key': key, 'bytes': len(raw), 'plaintext': True})
    try:
        _request('object/set', wire, 'multipart/form-data; boundary=' + boundary)
        result = {'at': utc(), 'status': 'uploaded', 'key': key, 'packet_sha256': packet_hash}
        exclusive('packet-upload.terminal.json', result)
        return result
    except Exception:
        if not (PRIVATE / 'packet-upload.terminal.json').exists():
            exclusive('packet-upload.terminal.json', {'at': utc(), 'status': 'failed_or_uncertain', 'key': key})
        raise Refusal('packet upload failed or uncertain; no implicit retry') from None
