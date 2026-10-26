"""One new plain-data storage publication; never source upload or backtest.

A credential-free native-network-denied worker authenticates private inputs,
owns the genuine process-local capability and fresh source rechecks. Its sole
inherited-pipe broker can contact only two fixed projects/read identities and
the six authenticated new object keys. The broker never parses licensed rows.
No old operational entrypoint or old control is invoked, repaired or renewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import prepare_arv2_newrule_plain_transport as prep

SOURCE = ROOT / 'scripts/run_arv2_plain_storage_publication.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_plain_storage/R322-20261025-B'
SCHEMA = 'arv2-newrule-plain-storage-operation-v1'
PREPARATION_HEAD = 'd95198e014926ba1a578db61a5c21c4887293a26'
PREPARATION_SHA256 = '11ee089e4f16247a87bfd4afed58b1f86f353f9e45eafe7b462a23126263ad7c'
PREPARATION_BYTES = 13873
PREPARATION_ACTUAL_EXIT = 0  # Observed externally for the sole committed D1 run.
PREPARATION_CALLER = '858d631f3aecd4107581ee768fbb606eb5f48addacbf0c1c43ecabf5b615158a'
EXPECTED = {
    'package_sha256': '1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2',
    'projection_sha256': '9dde39783bcb401d1f36aeb5beb1b1983882250b0472c2afd22dca1408c2a5f5',
    'profile_sha256': '89d6ac9bb0f1be8bd8f307f0b00d5725620e33b402fecb7ee2ff06daecc2106e',
    'activation_sha256': 'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b',
    'parent_proof_sha256': '95405d1b569d4bfeeb6c6d87fdb430f2fd27b8b7a31d6dcde7f82276d9903cd1',
    'object_count': 6, 'total_byte_count': 19164859,
}
HELPER_SHA256 = 'b7be26c1bee3d9ff07b2daeb2c61d7731d85d0f54f7e1dd25978d81cce9de022'
RPC_SHA256 = 'f79a83fc15fe8b45ddd32103d76ca72d3149e9cd51da0fe37f4fc8772f70ce1a'
PINNED = {
    'scripts/prepare_arv2_newrule_plain_transport.py': PREPARATION_CALLER,
    'scripts/arv2_newrule_execution_environment.py': 'bacf030e82b309111d8e7788991880860620f6d876bbd750246345c95d7c3194',
    'scripts/arv2_newrule_storage_recovery_v4.py': 'c77e1e8ba3634f6edd03ec9e825da56eeca3ecac13b48face9b3c25ce9e46c8f',
    'scripts/arv2_r298_collaborator_access.py': '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93',
}
DEADLINE_SECONDS, STORAGE_SECONDS = 600, 300
MAX_FILE, MAX_OUTPUT = 256 * 1024, 64 * 1024
REFERENCE, PROJECT = 37165262, 38364439
FALSE_FLAGS = {'backtest_created': False, 'capacity_access': False, 'project_source_modified': False,
    'qc_source_policy_acceptance_proven': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'provider_contact': False}
READY_FIELDS = frozenset(('kind', 'binding_sha256', 'preparation_sha256', 'summary', 'inventory', 'inventory_sha256', 'projection_binding'))
ORG_FIELDS = frozenset(('kind', 'binding_sha256', 'organization_id'))
REQUEST_FIELDS = frozenset(('kind', 'ordinal', 'phase', 'index', 'endpoint', 'key', 'request_sha256'))
RESPONSE_FIELDS = frozenset(('kind', 'ordinal', 'phase', 'index', 'request_sha256', 'packet'))
DONE_FIELDS = frozenset(('kind', 'binding_sha256', 'result_sha256'))
FLOW_FIELDS = REQUEST_FIELDS | DONE_FIELDS
PROJECTION_FIELDS = frozenset(('project_source_manifest_sha256', 'activation_manifest_key', 'activation_manifest_byte_count'))
OBJECT_FIELDS = frozenset(('schema', 'role', 'ordinal', 'object_store_key', 'relative_path',
    'byte_count', 'content_sha256', 'record_count', 'compression', 'activation_manifest'))
ROLES = ('evaluator_manifest', 'session_axis', 'memberships', 'contributions',
         'runtime_symbol_bindings', 'activation_manifest')
CODES = frozenset(('host', 'source', 'git', 'arguments', 'credentials', 'control', 'claim',
    'control_changed', 'bound', 'json', 'deadline', 'preparation', 'handshake', 'inventory',
    'organization', 'request', 'sequence', 'payload', 'child', 'child_output', 'count',
    'result', 'actual_exit', 'source_recheck', 'unknown_exception'))


class Refused(ValueError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    return prep.canonical(value)


def sha(raw):
    require(type(raw) is bytes, 'bound')
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'source')
    return value


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_FILE, 'bound')
    try:
        value = json.loads(raw.decode('ascii'))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None
    require(type(value) is dict and canonical(value) == raw, 'json')
    return value


def remaining(deadline):
    require(type(deadline) in (float, int) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= DEADLINE_SECONDS, 'deadline')
    return value


def modules():
    from scripts import arv2_newrule_plain_storage as helper
    from scripts import arv2_plain_storage_rpc as rpc
    from scripts import arv2_newrule_execution_environment as environment
    return helper, rpc, environment


def selected_pins():
    from scripts import arv2_newrule_storage_recovery_v4 as wire
    return {**prep.selected_pins(), **wire.ADDITIONS, **PINNED,
        'scripts/arv2_newrule_plain_storage.py': HELPER_SHA256,
        'scripts/arv2_plain_storage_rpc.py': RPC_SHA256}


def sandbox():
    return ('(version 1)(allow default)(deny network*)'
        '(deny process-exec (literal "/usr/bin/security"))'
        '(deny file-read* file-write* (subpath "/Users/sheltonchen/Library/Keychains"))'
        '(deny file-read* file-write* (subpath "/Library/Keychains"))'
        '(deny file-write* (require-all '
        f'(require-not (subpath "{CONTROL}"))'
        f'(require-not (subpath "{ROOT / ".pytest_cache"}"))'
        '(require-not (literal "/dev/null"))))')


def profile():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': prep.frozen.BRANCH,
        'python': str(prep.frozen.PYTHON), 'control': str(CONTROL), 'source_pins': selected_pins(),
        'preparation_head': PREPARATION_HEAD, 'preparation_sha256': PREPARATION_SHA256,
        'preparation_bytes': PREPARATION_BYTES, 'actual_preparation_exit': PREPARATION_ACTUAL_EXIT,
        'expected': EXPECTED, 'deadline_seconds': DEADLINE_SECONDS, 'storage_seconds': STORAGE_SECONDS,
        'native_worker_sandbox': sandbox(), 'worker_credentials': False,
        'storage_dispatch_limit': 24, 'organization_dispatch_limit': 2,
        'organization_projects': [REFERENCE, PROJECT], 'storage_endpoints': ['object/properties', 'object/set'],
        'parent_private_row_parsing': False, 'native_worker_inventory_attestation': True,
        'actual_parent_exit_required': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': sha(canonical(profile()))}


def preflight(args, deadline):
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == prep.frozen.PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE, 'host')
    require('pytest' not in sys.modules and 'PYTEST_CURRENT_TEST' not in os.environ, 'host')
    require(args.operation in ('publish', 'worker') and type(args.expected_head) is str
        and re.fullmatch('[0-9a-f]{40}', args.expected_head), 'arguments')
    digest(args.caller_sha256)
    worker = args.operation == 'worker'
    require(all((type(getattr(args, name)) is int and getattr(args, name) > 2) if worker
        else getattr(args, name) is None for name in ('control_fd', 'request_fd', 'reply_fd')), 'arguments')
    if worker:
        require(len({args.control_fd, args.request_fd, args.reply_fd}) == 3
            and not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'arguments')
        require(type(args.deadline) is float and args.deadline == deadline, 'arguments')
    else:
        require(args.deadline is None, 'arguments')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], prep.frozen.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        out = subprocess.run(['git', *command], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, remaining(deadline)))
        require(out.returncode == 0 and not out.stderr and out.stdout.decode('ascii').strip() == expected, 'git')
    for name, pin in selected_pins().items():
        require(prep.frozen.helpers._source_digest(ROOT / name) == digest(pin), 'source')
    require(prep.frozen.helpers._source_digest(SOURCE) == args.caller_sha256, 'source')
    # Bind committed caller bytes as well as the mutable working path.
    object_name = args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()
    size = subprocess.run(['git', 'cat-file', '-s', object_name], cwd=ROOT,
        stdin=subprocess.DEVNULL, capture_output=True, timeout=min(3, remaining(deadline)))
    require(size.returncode == 0 and not size.stderr and re.fullmatch(rb'[1-9][0-9]{0,6}\n', size.stdout)
        and int(size.stdout) <= MAX_FILE, 'source')
    out = subprocess.run(['git', 'show', object_name],
        cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, timeout=min(3, remaining(deadline)))
    require(out.returncode == 0 and not out.stderr and 0 < len(out.stdout) <= MAX_FILE
        and sha(out.stdout) == args.caller_sha256, 'source')
    remaining(deadline)


def _walk(path):
    require(type(path) is type(ROOT) and path.is_absolute() and '..' not in path.parts, 'control')
    fd, chain = os.open('/', os.O_RDONLY | os.O_DIRECTORY), []
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            chain.append((info.st_dev, info.st_ino))
        return fd, tuple(chain)
    except BaseException:
        os.close(fd)
        raise


class Store:
    """Only the new leaf; no old Store/global path is reused."""
    def __init__(self, *, create=False, inherited=None):
        self.files = {}
        if create:
            parent_fd, _ = _walk(CONTROL.parent.parent)
            try:
                try:
                    os.mkdir(CONTROL.parent.name, 0o700, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                except FileExistsError:
                    pass
            finally:
                os.close(parent_fd)
            parent_fd, _ = _walk(CONTROL.parent)
            try:
                os.mkdir(CONTROL.name, 0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        self.fd, self.chain = _walk(CONTROL)
        try:
            if inherited is not None:
                require(type(inherited) is int and inherited > 2
                    and prep.metadata(os.fstat(inherited)) == prep.metadata(os.fstat(self.fd)), 'claim')
            self.verify()
        except BaseException:
            os.close(self.fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def verify(self):
        fd, chain = _walk(CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(fd)
            names = os.listdir(fd)
            require(chain == self.chain and prep.metadata(held) == prep.metadata(named)
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and held.st_nlink == 2 + len(names) and len(names) <= 128
                and all(re.fullmatch('[a-z0-9-]+\\.json', name) for name in names), 'control')
            for name, expected in self.files.items():
                require(prep.metadata(os.stat(name, dir_fd=fd, follow_symlinks=False)) == expected, 'control_changed')
            require(prep.metadata(named) == prep.metadata(os.fstat(fd)), 'control_changed')
        finally:
            os.close(fd)

    def names(self):
        self.verify()
        return tuple(os.listdir(self.fd))

    def read_raw(self, name):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-z0-9-]+\\.json', name), 'control')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
                and 0 < before.st_size <= MAX_FILE, 'control')
            raw = bytearray()
            while len(raw) <= before.st_size:
                chunk = os.read(fd, min(65536, before.st_size + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            require(len(raw) == before.st_size and prep.metadata(before) == prep.metadata(os.fstat(fd))
                == prep.metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), 'control_changed')
            self.files[name] = prep.metadata(before)
        finally:
            os.close(fd)
        self.verify()
        return bytes(raw)

    def read(self, name):
        return parse(self.read_raw(name))

    def write(self, name, value):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-z0-9-]+\\.json', name), 'control')
        raw = canonical(value)
        require(type(value) is dict and 0 < len(raw) <= MAX_FILE, 'bound')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'control')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        require(self.read_raw(name) == raw, 'control_changed')
        return {'sha256': sha(raw), 'byte_count': len(raw)}


def read_preparation():
    """Only the newly pinned preparation report, in the native worker."""
    fd, chain = _walk(prep.CONTROL)
    leaf = None
    try:
        directory = os.fstat(fd)
        require(directory.st_uid == os.getuid() and stat.S_IMODE(directory.st_mode) == 0o700
            and set(os.listdir(fd)) == {'claim.json', 'report.json'}, 'preparation')
        leaf = os.open('report.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        info = os.fstat(leaf)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == PREPARATION_BYTES, 'preparation')
        raw = bytearray()
        while len(raw) <= PREPARATION_BYTES:
            chunk = os.read(leaf, min(65536, PREPARATION_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        require(len(raw) == PREPARATION_BYTES and sha(bytes(raw)) == PREPARATION_SHA256
            and prep.metadata(info) == prep.metadata(os.fstat(leaf))
            == prep.metadata(os.stat('report.json', dir_fd=fd, follow_symlinks=False)), 'preparation')
        other, current_chain = _walk(prep.CONTROL)
        try:
            require(chain == current_chain and prep.metadata(directory) == prep.metadata(os.fstat(other))
                == prep.metadata(os.fstat(fd)), 'preparation')
        finally:
            os.close(other)
        result = bytes(raw)
        record = parse(result)
        require(record.get('expected_head') == PREPARATION_HEAD
            and record.get('caller_sha256') == PREPARATION_CALLER, 'preparation')
        return result
    finally:
        if leaf is not None:
            os.close(leaf)
        os.close(fd)


def ready_header(args, plain, projected):
    summary = prep.summary(plain, projected)
    require(summary == EXPECTED, 'preparation')
    inventory = [item.to_record() for item in plain.upload_objects]
    record = projected.to_record()
    source_manifest = {'project_id': PROJECT, 'projection_sha256': projected.projection_sha256,
        'files': sorted([{'name': item['project_path'], 'byte_count': item['byte_count'],
            'sha256': item['content_sha256']} for item in record['source_files']], key=lambda item: item['name'])}
    derived = {'project_source_manifest_sha256': sha(canonical(source_manifest)),
        'activation_manifest_key': plain.activation_manifest_key,
        'activation_manifest_byte_count': plain.activation_manifest_byte_count}
    return {'kind': 'ready', 'binding_sha256': sha(canonical(binding(args))),
        'preparation_sha256': PREPARATION_SHA256, 'summary': summary, 'inventory': inventory,
        'inventory_sha256': sha(canonical(inventory)), 'projection_binding': derived}


def validate_ready(header, args):
    require(type(header) is dict and set(header) == READY_FIELDS and header['kind'] == 'ready'
        and header['binding_sha256'] == sha(canonical(binding(args)))
        and header['preparation_sha256'] == PREPARATION_SHA256
        and canonical(header['summary']) == canonical(EXPECTED), 'handshake')
    rows = header['inventory']
    require(type(rows) is list and len(rows) == 6 and sha(canonical(rows)) == header['inventory_sha256'], 'inventory')
    prefix = 'arv2/newrule-plain-v1/' + EXPECTED['parent_proof_sha256'][:24] + '/'
    for index, (item, role) in enumerate(zip(rows, ROLES)):
        name = ('evaluator-manifest.json' if index == 0 else 'transport-manifest.json' if index == 5
                else role + '-0000.jsonl')
        require(type(item) is dict and set(item) == OBJECT_FIELDS
            and item['schema'] == 'arv2-newrule-plain-upload-object-v1' and item['role'] == role
            and type(item['ordinal']) is int and item['ordinal'] == 0
            and item['relative_path'] == name and item['object_store_key'] == prefix + name
            and item['compression'] == 'identity' and item['activation_manifest'] is (index == 5)
            and type(item['byte_count']) is int and 0 < item['byte_count'] <= (32 if index in (0, 5) else 16) * 1024 * 1024
            and type(item['record_count']) is int and item['record_count'] > 0
            and (index not in (0, 5) or item['record_count'] == 1), 'inventory')
        digest(item['content_sha256'])
    require(sum(item['byte_count'] for item in rows) == EXPECTED['total_byte_count']
        and rows[-1]['content_sha256'] == EXPECTED['activation_sha256'], 'inventory')
    derived = header['projection_binding']
    require(type(derived) is dict and set(derived) == PROJECTION_FIELDS
        and derived['activation_manifest_key'] == rows[-1]['object_store_key']
        and type(derived['activation_manifest_byte_count']) is int
        and derived['activation_manifest_byte_count'] == rows[-1]['byte_count'], 'inventory')
    digest(derived['project_source_manifest_sha256'])
    return tuple((item['object_store_key'], item['content_sha256'], item['byte_count'], item['activation_manifest'])
                 for item in rows)


def validate_ready_preparation(raw, header):
    """Hash first, then inspect only the pinned metadata-only D1 report bytes.

    The network parent never opens the private report or parses source rows.
    This mechanically anchors every descriptor/source pin in the ready header
    to the externally frozen preparation result, not only worker attestation.
    """
    require(type(raw) is bytes and len(raw) == PREPARATION_BYTES
        and sha(raw) == PREPARATION_SHA256, 'preparation')
    value = parse(raw)
    fields = {'schema', 'expected_head', 'caller_sha256', 'profile_sha256', 'complete', 'failure_code',
        'transport', 'projection', 'attempt_consumed', *prep.FALSE_FLAGS}
    require(set(value) == fields and value['schema'] == prep.SCHEMA
        and value['expected_head'] == PREPARATION_HEAD and value['caller_sha256'] == PREPARATION_CALLER
        and value['complete'] is True and value['failure_code'] is None and value['attempt_consumed'] is True
        and all(value[key] is False for key in prep.FALSE_FLAGS), 'preparation')
    digest(value['profile_sha256'])
    transport, projected = value['transport'], value['projection']
    require(type(transport) is dict and type(projected) is dict
        and transport.get('package_sha256') == EXPECTED['package_sha256']
        and transport.get('parent_proof_sha256') == EXPECTED['parent_proof_sha256']
        and canonical(transport.get('objects')) == canonical(header['inventory'][:-1])
        and sha(canonical(transport)) == EXPECTED['activation_sha256']
        and len(canonical(transport)) == header['inventory'][-1]['byte_count']
        and sha(canonical(projected)[:-1]) == EXPECTED['projection_sha256']
        and projected.get('profile_sha256') == EXPECTED['profile_sha256']
        and projected.get('package_sha256') == EXPECTED['package_sha256']
        and canonical(projected.get('upload_inventory')) == canonical(header['inventory'])
        and projected.get('activation_manifest_key') == header['projection_binding']['activation_manifest_key']
        and type(projected.get('activation_manifest_byte_count')) is int
        and projected['activation_manifest_byte_count'] == header['projection_binding']['activation_manifest_byte_count']
        and projected.get('activation_manifest_sha256') == EXPECTED['activation_sha256']
        and type(projected.get('total_upload_byte_count')) is int
        and projected['total_upload_byte_count'] == EXPECTED['total_byte_count'], 'preparation')
    files = projected.get('source_files')
    require(type(files) is list and len(files) == 11, 'preparation')
    for item in files:
        require(type(item) is dict and set(item) == {'project_path', 'byte_count', 'content_sha256'}
            and type(item['project_path']) is str and re.fullmatch('[a-z_]+\\.py', item['project_path'])
            and type(item['byte_count']) is int and 0 < item['byte_count'] <= 64000, 'preparation')
        digest(item['content_sha256'])
    require(len({item['project_path'] for item in files}) == 11, 'preparation')
    source_manifest = {'project_id': PROJECT, 'projection_sha256': EXPECTED['projection_sha256'],
        'files': sorted([{'name': item['project_path'], 'byte_count': item['byte_count'],
            'sha256': item['content_sha256']} for item in files], key=lambda item: item['name'])}
    require(sha(canonical(source_manifest)) == header['projection_binding']['project_source_manifest_sha256'], 'preparation')


def flow_frame(header):
    require(type(header) is dict and set(header) in (REQUEST_FIELDS, DONE_FIELDS), 'request')
    return {**{key: None for key in FLOW_FIELDS}, **header}


def flow_header(frame):
    require(type(frame) is dict and set(frame) == FLOW_FIELDS, 'request')
    fields = DONE_FIELDS if frame['kind'] == 'done' else REQUEST_FIELDS
    require(frame['kind'] in ('done', 'storage_request')
        and all(frame[key] is None for key in FLOW_FIELDS - fields), 'request')
    return {key: frame[key] for key in fields}


def worker(args, deadline):
    helper, rpc, environment = modules()
    environment.require_safe_environment()
    with Store(inherited=args.control_fd) as store:
        claim = store.read('parent-claim.json')
        require(claim == {**binding(args), 'attempt_consumed': True, 'parent_pid': os.getppid()}, 'claim')
        store.write('worker-start.json', {**binding(args), 'worker_pid': os.getpid()})
        raw_preparation = read_preparation()
        plain, projected = prep.construct(deadline)
        helper._preparation(raw_preparation, PREPARATION_ACTUAL_EXIT, PREPARATION_SHA256, plain)
        hello = ready_header(args, plain, projected)
        rpc.send_frame(args.request_fd, hello, raw_preparation, deadline, header_fields=READY_FIELDS)
        org, payload = rpc.receive_frame(args.reply_fd, deadline, header_fields=ORG_FIELDS)
        require(not payload and org['kind'] == 'organization'
            and org['binding_sha256'] == hello['binding_sha256'], 'handshake')
        helper.access._organization(org['organization_id'])
        ordinal = 0

        def dispatch(phase, index, row, payload, request_sha256, request_deadline):
            nonlocal ordinal
            header = {'kind': 'storage_request', 'ordinal': ordinal, 'phase': phase, 'index': index,
                'endpoint': 'object/set' if phase == 'put' else 'object/properties', 'key': row[0],
                'request_sha256': request_sha256}
            rpc.send_frame(args.request_fd, flow_frame(header), payload, request_deadline, header_fields=FLOW_FIELDS)
            response, returned = rpc.receive_frame(args.reply_fd, request_deadline, header_fields=RESPONSE_FIELDS)
            require(not returned and response['kind'] == 'storage_response'
                and all(response[key] == header[key] for key in ('ordinal', 'phase', 'index', 'request_sha256')), 'request')
            ordinal += 1
            return helper.validate_dispatch_packet(response['packet'], phase, row)

        def recheck(value):
            current, next_projection = prep.construct(deadline)
            require(prep.summary(current, next_projection) == EXPECTED
                and current.record_bytes == value.record_bytes
                and tuple((item.to_record(), item.payload) for item in current.upload_objects)
                    == tuple((item.to_record(), item.payload) for item in value.upload_objects), 'source_recheck')

        result = helper.publish(store, org['organization_id'], plain,
            deadline=min(deadline, time.monotonic() + STORAGE_SECONDS),
            expected_package_sha256=EXPECTED['package_sha256'], expected_activation_sha256=EXPECTED['activation_sha256'],
            expected_preparation_sha256=PREPARATION_SHA256, preparation_record=raw_preparation,
            actual_preparation_exit=PREPARATION_ACTUAL_EXIT, source_recheck=recheck, transport_request=dispatch)
        preflight(args, deadline)
        store.verify()
        require(store.write('worker-result.json', {**binding(args), 'result': result})
            == worker_result_pin(binding(args), result), 'result')
        rpc.send_frame(args.request_fd, flow_frame({'kind': 'done', 'binding_sha256': hello['binding_sha256'],
            'result_sha256': sha(canonical(result))}), b'', deadline, header_fields=FLOW_FIELDS)
        return result


class Broker:
    """Six immutable keys and exactly one properties-first sequence, no retry."""
    def __init__(self, rows, organization, api, store, deadline):
        self.rows, self.organization, self.api, self.store, self.deadline = rows, organization, api, store, deadline
        self.ordinal, self.dispatches = 0, 0
        self.initial, self.missing, self.pending, self.failed = [], [], ('initial', 0), False

    def request(self, header, payload):
        helper, _, _ = modules()
        wire = helper.wire
        require(type(header) is dict and set(header) == REQUEST_FIELDS
            and header['kind'] == 'storage_request' and not self.failed and self.pending is not None
            and type(header['ordinal']) is int and header['ordinal'] == self.ordinal < 24
            and type(header['index']) is int and 0 <= header['index'] < 6
            and (header['phase'], header['index']) == self.pending, 'sequence')
        phase, index = self.pending
        row = self.rows[index]
        require(type(payload) is bytes and len(payload) == row[2] and sha(payload) == row[1]
            and header['key'] == row[0], 'payload')
        endpoint, body, content_type = wire._body(phase, self.organization, row, payload)
        require(header['endpoint'] == endpoint and endpoint in ('object/properties', 'object/set')
            and header['request_sha256'] == sha(body), 'request')
        entry = {'ordinal': self.ordinal, 'phase': phase, 'endpoint': endpoint, 'index': index,
            'request_sha256': sha(body), 'attempted': False, 'http_status': None, 'observation': None,
            'error_shape': None, 'object_state': None, 'absence_template_index': None, 'failure_code': None}
        self.store.write(f'broker-{self.ordinal:02d}-intent.json', {key: entry[key] for key in
            ('ordinal', 'phase', 'endpoint', 'index', 'request_sha256')})
        state = {'attempted_request_count': self.dispatches}
        try:
            response = wire._transport(self.api, endpoint, body, content_type, self.organization,
                row[0], entry, state, self.deadline)
            if phase == 'put':
                require(type(response) is dict and set(response) <= {'success', 'errors'}
                    and response.get('success') is True and response.get('errors', []) == [], 'request')
                entry['object_state'] = 'published'
            else:
                entry['object_state'], entry['absence_template_index'] = wire._properties_state(response, row, payload)
        except BaseException as error:
            entry['failure_code'] = helper.finite_failure(error)
            entry['object_state'] = entry['absence_template_index'] = None
        self.dispatches = state['attempted_request_count']
        packet = {key: entry[key] for key in helper.PACKET_FIELDS}
        packet = helper.validate_dispatch_packet(packet, phase, row)
        self.store.write(f'broker-{self.ordinal:02d}-observed.json', {'ordinal': self.ordinal, 'packet': packet})
        self.ordinal += 1
        self._advance(phase, index, packet)
        return {'kind': 'storage_response', 'ordinal': header['ordinal'], 'phase': phase, 'index': index,
            'request_sha256': header['request_sha256'], 'packet': packet}

    def _advance(self, phase, index, packet):
        if packet['failure_code'] is not None:
            self.failed = True
            return
        outcome = packet['object_state']
        if phase == 'initial':
            self.initial.append(outcome)
            if index < 5:
                self.pending = ('initial', index + 1)
            else:
                self.missing = [i for i, state in enumerate(self.initial) if state == 'absent']
                self.failed = self.initial[-1] == 'present' and bool(self.missing)
                self.pending = ('recheck', self.missing[0]) if self.missing else None
        elif phase == 'recheck':
            self.failed = outcome != 'absent'
            self.pending = ('put', index)
        elif phase == 'put':
            self.pending = ('verify', index)
        else:
            self.failed = outcome != 'present'
            require(self.missing and self.missing.pop(0) == index, 'sequence')
            self.pending = ('recheck', self.missing[0]) if self.missing else None


def organization(api, store, state):
    """Read only fixed reference/current organization scope, not capacity."""
    helper, _, environment = modules()
    value = None
    for index, project in enumerate((REFERENCE, PROJECT)):
        environment.require_safe_environment()
        store.write(f'organization-{index}-intent.json', {'endpoint': 'projects/read', 'project_id': project})
        state['organization_dispatches'] += 1
        packet = api.request('projects/read', {'projectId': project})
        require(type(packet) is dict and packet.get('success') is True
            and packet.get('errors', []) == [], 'organization')
        rows = packet.get('projects')
        require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'organization')
        row = rows[0]
        require(type(row.get('projectId')) is int and row['projectId'] == project
            and row.get('owner') is True and row.get('language') == 'Py'
            and row.get('public', False) is False, 'organization')
        helper.access._organization(row.get('organizationId'))
        if value is not None:
            require(value == row['organizationId'], 'organization')
        value = row['organizationId']
        store.write(f'organization-{index}-observed.json', {'project_id': project,
            'organization_sha256': helper.access.ORGANIZATION_SHA256,
            'response_sha256': sha(canonical(packet)), 'scope_accepted': True})
    return value


def validate_organization_binding(value, expected_binding):
    helper, _, _ = modules()
    require(type(value) is dict and set(value) == set(expected_binding) | {'organization_id', 'organization_sha256'}
        and canonical({key: value[key] for key in expected_binding}) == canonical(expected_binding)
        and value['organization_sha256'] == helper.access.ORGANIZATION_SHA256, 'organization')
    helper.access._organization(value['organization_id'])
    return value['organization_id']


def _channels(process, deadline):
    out, err = bytearray(), bytearray()
    with selectors.DefaultSelector() as selector:
        for channel, target in ((process.stdout, out), (process.stderr, err)):
            os.set_blocking(channel.fileno(), False)
            selector.register(channel, selectors.EVENT_READ, target)
        while selector.get_map():
            for key, _ in selector.select(min(0.25, remaining(deadline))):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    key.data.extend(chunk)
                    require(len(key.data) <= MAX_OUTPUT, 'child_output')
    code = process.wait(timeout=remaining(deadline))
    require(not err and bytes(out).endswith(b'\n\n'), 'child_output')
    return code, parse(bytes(out[:-1]))


def worker_failure(packet, args, actual_exit):
    """Only a completed child's bounded finite fallback, never its raw text."""
    require(type(actual_exit) is int and actual_exit == 2 and type(packet) is dict
        and set(packet) == {'schema', 'operation', 'binding', 'complete', 'failure_code', 'result', *FALSE_FLAGS}
        and packet['schema'] == SCHEMA and packet['operation'] == 'worker'
        and canonical(packet['binding']) == canonical(binding(args))
        and packet['complete'] is False and packet['result'] is None
        and type(packet['failure_code']) is str and packet['failure_code'] in CODES
        and all(packet[key] is False for key in FALSE_FLAGS), 'child_output')
    return packet['failure_code']


def validate_result(result, *, actual_worker_exit, broker):
    helper, _, _ = modules()
    fields = {'complete', 'failure_code', 'report_sha256', 'report_byte_count', 'attempted_request_count',
        'attempted_request_count_lower_bound', 'dispatch_count_known', 'admission_sha256', 'admission_byte_count', *helper.FLAGS}
    require(type(result) is dict and set(result) == fields and type(result.get('complete')) is bool
        and all(result.get(key) is value for key, value in helper.FLAGS.items()), 'result')
    require(type(result['dispatch_count_known']) is bool
        and type(result['attempted_request_count_lower_bound']) is int
        and 0 <= result['attempted_request_count_lower_bound'] <= broker.dispatches <= 24, 'count')
    if result['dispatch_count_known']:
        require(type(result['attempted_request_count']) is int
            and result['attempted_request_count'] == result['attempted_request_count_lower_bound'] == broker.dispatches, 'count')
    else:
        require(result['attempted_request_count'] is None, 'count')
    digest(result['report_sha256'])
    require(type(result['report_byte_count']) is int and 0 < result['report_byte_count'] <= helper.MAX_REPORT_BYTES, 'bound')
    if result['complete']:
        require(type(actual_worker_exit) is int and actual_worker_exit == 0 and not broker.failed
            and broker.pending is None and len(broker.initial) == 6
            and result.get('failure_code') is None and result.get('dispatch_count_known') is True
            and 6 <= broker.dispatches <= 24 and broker.dispatches % 3 == 0
            and type(result.get('attempted_request_count')) is int
            and result['attempted_request_count'] == result.get('attempted_request_count_lower_bound')
            == broker.dispatches == broker.ordinal, 'count')
        for key in ('admission_sha256', 'report_sha256'):
            digest(result.get(key))
        for key in ('admission_byte_count', 'report_byte_count'):
            require(type(result.get(key)) is int and 0 < result[key] <= helper.MAX_REPORT_BYTES, 'bound')
    else:
        require(type(actual_worker_exit) is int and actual_worker_exit == 2
            and type(result['failure_code']) is str and result['failure_code'] in helper.FINITE_CODES
            and result['admission_sha256'] is None and result['admission_byte_count'] is None, 'result')
    return result


def worker_result_pin(expected_binding, result):
    raw = canonical({**expected_binding, 'result': result})
    require(0 < len(raw) <= MAX_FILE, 'bound')
    return {'sha256': sha(raw), 'byte_count': len(raw)}


def complete_names(count, *, final=False):
    require(type(count) is int and 6 <= count <= 24 and count % 3 == 0, 'count')
    helper, _, _ = modules()
    names = {'parent-claim.json', 'worker-start.json', 'worker-result.json', 'organization-binding.json',
        'organization-0-intent.json', 'organization-0-observed.json',
        'organization-1-intent.json', 'organization-1-observed.json', helper.CLAIM, helper.REPORT, helper.ADMISSION}
    names.update(f'broker-{i:02d}-{kind}.json' for i in range(count) for kind in ('intent', 'observed'))
    names.update(helper._stem(i) + '-' + kind + '.json' for i in range(count) for kind in ('intent', 'observed'))
    if final:
        names.add('broker-report.json')
    return names


def complete_census(store, count, *, final=False):
    require(set(store.names()) == complete_names(count, final=final), 'control')


def publish(args, deadline):
    helper, rpc, environment = modules()
    environment.require_safe_environment()
    for name in ('QC_USER_ID', 'QC_API_TOKEN'):
        require(type(os.environ.get(name)) is str and bool(os.environ[name].strip()), 'credentials')
    state = {'organization_dispatches': 0, 'storage_dispatches': 0, 'worker_exit': None}
    with Store(create=True) as store:
        store.write('parent-claim.json', {**binding(args), 'attempt_consumed': True, 'parent_pid': os.getpid()})
        request_read, request_write = os.pipe()
        reply_read, reply_write = os.pipe()
        process = None
        broker = None
        summary = None
        organization_pin = None
        try:
            child_env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
            command = ['/usr/bin/sandbox-exec', '-p', sandbox(), str(prep.frozen.PYTHON), '-B', str(SOURCE), 'worker',
                '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
                '--control-fd', str(store.fd), '--request-fd', str(request_write), '--reply-fd', str(reply_read),
                '--deadline', str(deadline)]
            process = subprocess.Popen(command, cwd=ROOT, env=child_env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(store.fd, request_write, reply_read))
            os.close(request_write); request_write = None
            os.close(reply_read); reply_read = None
            hello, payload = rpc.receive_frame(request_read, deadline, header_fields=READY_FIELDS)
            rows = validate_ready(hello, args)
            validate_ready_preparation(payload, hello)
            summary = {**EXPECTED, **hello['projection_binding']}
            # Credentials are loaded only after successful native input authentication.
            api = helper.wire.old._client()
            org = organization(api, store, state)
            organization_record = {**binding(args), 'organization_id': org,
                'organization_sha256': helper.access.ORGANIZATION_SHA256}
            validate_organization_binding(organization_record, binding(args))
            organization_pin = store.write('organization-binding.json', organization_record)
            rpc.send_frame(reply_write, {'kind': 'organization', 'binding_sha256': hello['binding_sha256'],
                'organization_id': org}, b'', deadline, header_fields=ORG_FIELDS)
            broker = Broker(rows, org, api, store, min(deadline, time.monotonic() + STORAGE_SECONDS))
            done = None
            # The union has one exact finite field list; inactive fields must
            # be null, so the framing layer never accepts arbitrary headers.
            for _ in range(25):
                frame, payload = rpc.receive_frame(request_read, deadline, header_fields=FLOW_FIELDS)
                frame = flow_header(frame)
                if frame.get('kind') == 'done':
                    require(set(frame) == DONE_FIELDS and not payload
                        and frame['binding_sha256'] == hello['binding_sha256'], 'handshake')
                    digest(frame.get('result_sha256'))
                    done = frame
                    break
                response = broker.request(frame, payload)
                state['storage_dispatches'] = broker.dispatches
                rpc.send_frame(reply_write, response, b'', deadline, header_fields=RESPONSE_FIELDS)
            require(done is not None, 'sequence')
            code, packet = _channels(process, deadline)
            state['worker_exit'] = code
            rpc.reject_pending(request_read, deadline)
            require(set(packet) == {'schema', 'operation', 'binding', 'result', *FALSE_FLAGS}
                and packet['schema'] == SCHEMA and packet['operation'] == 'worker'
                and packet['binding'] == binding(args)
                and all(packet[key] is False for key in FALSE_FLAGS)
                and sha(canonical(packet['result'])) == done['result_sha256'], 'child_output')
            result = validate_result(packet['result'], actual_worker_exit=code, broker=broker)
            preflight(args, deadline)
            require(state['organization_dispatches'] == 2, 'count')
            if result['complete']:
                complete_census(store, broker.dispatches)
            report = {**binding(args), 'worker_result': result, 'summary': summary,
                'worker_result_file': worker_result_pin(binding(args), result),
                'worker_failure_code': None,
                'organization_binding': organization_pin, 'attempt_consumed': True, **state, **FALSE_FLAGS}
            pin = store.write('broker-report.json', report)
            store.verify()
            if result['complete']:
                complete_census(store, broker.dispatches, final=True)
            return {'complete': result['complete'], 'failure_code': None if result['complete'] else 'result',
                'report': pin, 'worker_result': result, 'summary': summary,
                'worker_result_file': worker_result_pin(binding(args), result),
                'worker_failure_code': None,
                'organization_binding': organization_pin, 'attempt_consumed': True, **state}
        except BaseException as error:
            # Terminate only our own child before recording a finite failure.
            # A late success report does not override this nonzero parent exit.
            child_failure = None
            if process is not None and process.poll() is None:
                try:
                    process.wait(timeout=min(0.25, remaining(deadline)))
                except BaseException:
                    pass
            if process is not None and process.poll() == 2:
                try:
                    child_exit, child_packet = _channels(process, min(deadline, time.monotonic() + 2))
                    child_failure = worker_failure(child_packet, args, child_exit)
                except BaseException:
                    # Exhausted deadline, noise or malformed output remains
                    # explicitly unknown; never emit or infer its contents.
                    pass
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if process is not None:
                state['worker_exit'] = process.poll()
            if broker is not None:
                state['storage_dispatches'] = broker.dispatches
            result = {'complete': False, 'failure_code': finite(error), 'report': None,
                'worker_result': None, 'summary': summary, 'organization_binding': organization_pin,
                'worker_result_file': None,
                'worker_failure_code': child_failure,
                'attempt_consumed': True, **state}
            try:
                result['report'] = store.write('broker-failure.json', {**binding(args), **result, **FALSE_FLAGS})
            except BaseException:
                # Preserve the original retained leaves; no cleanup or repair.
                pass
            return result
        finally:
            if broker is not None:
                state['storage_dispatches'] = broker.dispatches
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close(); process.stderr.close()
            for fd in (request_read, request_write, reply_read, reply_write):
                if fd is not None:
                    os.close(fd)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in CODES:
            return args[0]
    return 'unknown_exception'


def validate_output(raw, *, actual_exit, expected_binding):
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT and raw.endswith(b'\n\n'), 'actual_exit')
    value = parse(raw[:-1])
    require(set(value) == {'schema', 'operation', 'binding', 'complete', 'failure_code', 'result', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['operation'] == 'publish'
        and value['binding'] == expected_binding and type(value['complete']) is bool
        and all(value[key] is False for key in FALSE_FLAGS), 'result')
    require((value['complete'] and actual_exit == 0 and value['failure_code'] is None)
        or (not value['complete'] and actual_exit == 2 and value['failure_code'] in CODES), 'actual_exit')
    result = value['result']
    if result is not None:
        fields = {'complete', 'failure_code', 'report', 'worker_result', 'summary', 'attempt_consumed',
            'organization_dispatches', 'storage_dispatches', 'worker_exit', 'organization_binding',
            'worker_result_file', 'worker_failure_code'}
        require(type(result) is dict and set(result) == fields and result['complete'] is value['complete']
            and result['failure_code'] == value['failure_code'] and result['attempt_consumed'] is True
            and type(result['storage_dispatches']) is int and 0 <= result['storage_dispatches'] <= 24
            and type(result['organization_dispatches']) is int and 0 <= result['organization_dispatches'] <= 2
            and (result['worker_exit'] is None or type(result['worker_exit']) is int), 'result')
        require(result['worker_failure_code'] is None or type(result['worker_failure_code']) is str
            and result['worker_failure_code'] in CODES and result['worker_exit'] == 2
            and result['worker_result'] is None and not value['complete'], 'result')
        for name in ('report', 'organization_binding'):
            if result[name] is not None:
                require(type(result[name]) is dict and set(result[name]) == {'sha256', 'byte_count'}, 'result')
                digest(result[name]['sha256'])
                require(type(result[name]['byte_count']) is int and 0 < result[name]['byte_count'] <= MAX_FILE, 'result')
        if result['summary'] is not None:
            validate_summary(result['summary'])
        require((result['worker_result'] is None and result['worker_result_file'] is None)
            or result['worker_result'] is not None and canonical(result['worker_result_file'])
                == canonical(worker_result_pin(expected_binding, result['worker_result'])), 'result')
    if value['complete']:
        require(result is not None and result['worker_exit'] == 0 and result['report'] is not None
            and result['organization_binding'] is not None and result['summary'] is not None and result['organization_dispatches'] == 2
            and 6 <= result['storage_dispatches'] <= 24, 'result')
        # The output-only check revalidates the complete helper receipt and its
        # exact external worker exit/count, not merely a parent boolean.
        broker = type('OutputCensus', (), {'failed': False, 'pending': None,
            'initial': (None,) * 6, 'dispatches': result['storage_dispatches'],
            'ordinal': result['storage_dispatches']})()
        validate_result(result['worker_result'], actual_worker_exit=result['worker_exit'], broker=broker)
        require(result['worker_result']['complete'] is True, 'result')
    elif result is not None and result['worker_result'] is not None:
        broker = type('OutputCensus', (), {'failed': True, 'pending': None, 'initial': (),
            'dispatches': result['storage_dispatches'], 'ordinal': result['storage_dispatches']})()
        validate_result(result['worker_result'], actual_worker_exit=result['worker_exit'], broker=broker)
        require(result['worker_result']['complete'] is False, 'result')
    return value


def validate_summary(value):
    require(type(value) is dict and set(value) == set(EXPECTED) | PROJECTION_FIELDS
        and canonical({key: value[key] for key in EXPECTED}) == canonical(EXPECTED)
        and value['activation_manifest_key'] == 'arv2/newrule-plain-v1/'
            + EXPECTED['parent_proof_sha256'][:24] + '/transport-manifest.json'
        and type(value['activation_manifest_byte_count']) is int
        and 0 < value['activation_manifest_byte_count'] <= 32 * 1024 * 1024, 'result')
    digest(value['project_source_manifest_sha256'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('publish', 'worker'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    for name in ('control-fd', 'request-fd', 'reply-fd'):
        parser.add_argument('--' + name, type=int)
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args(argv)
    deadline = args.deadline if args.operation == 'worker' else time.monotonic() + DEADLINE_SECONDS
    try:
        remaining(deadline)
        with prep.frozen.helpers._alarm(deadline):
            preflight(args, deadline)
            _, _, environment = modules()
            environment._bootstrap_cli_logging()
            result = worker(args, deadline) if args.operation == 'worker' else publish(args, deadline)
            if args.operation == 'worker':
                value = {'schema': SCHEMA, 'operation': 'worker', 'binding': binding(args), 'result': result, **FALSE_FLAGS}
            else:
                value = {'schema': SCHEMA, 'operation': 'publish', 'binding': binding(args),
                    'complete': result['complete'], 'failure_code': result['failure_code'],
                    'result': result, **FALSE_FLAGS}
            raw = canonical(value)
            require(len(raw) <= MAX_OUTPUT, 'bound')
            print(raw.decode('ascii'))
            return 0 if result['complete'] else 2
    except BaseException as error:
        value = {'schema': SCHEMA, 'operation': args.operation, 'binding': binding(args),
            'complete': False, 'failure_code': finite(error), 'result': None, **FALSE_FLAGS}
        print(canonical(value).decode('ascii'))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
