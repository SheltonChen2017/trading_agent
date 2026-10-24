"""One-use offline reconciliation of finite R298 A2 markers, not its source corpus.

Invoke only under a separately committed exact decision and the frozen native
network-denying sandbox. The original evidence.json is listed but NEVER opened.
Authenticated markers establish a recorded prefix, not an HTTP cause, measured
provider contact, absence of unjournaled effects, or authority for attempt three.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from types import SimpleNamespace

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_recovery as frozen
from scripts import arv2_r298_recovery_evidence as evidence
from scripts import arv2_r298_recovery_remote as remote

SOURCE = ROOT / 'scripts/read_arv2_r298_a2_stage.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_recovery/R298-20261024-A'
OUTPUT = ROOT / 'artifacts/analyst_revisions_v2/newrule_reconciliation/R310-20261024-A'
SCHEMA = 'arv2-r298-a2-stage-reconciliation-v1'
OLD_HEAD = 'dfa3490a411ea895ed9ae8e2cbf43dbfccf4998f'
OLD_CALLER = 'c33a3b110072d072d9ef1b9272b128981e1115744caf9e980fd7df1d654b01e4'
OLD_PROFILE = '3e9038f4a8ec8fbb2dceecd887d8b8d9ea3de6b234fc51fe3c710925cbeb5978'
EVIDENCE_PIN = {'sha256': 'c4fc71e3bdcda49db183fc283953f66f181497e802017460134fb5dc6ada928f', 'byte_count': 36337}
REPORT_PIN = {'sha256': '8449b555f253f2df204e4e2e1286f5b04f67d630d087b19bba4f7012cb7223b7', 'byte_count': 648}
MAX_FILE = 32 * 1024
MAX_TOTAL = 512 * 1024
DEADLINE = 30
BASE_NAMES = frozenset(('claim.json', 'evidence-start.json', 'evidence.json',
    'evidence-parent-completed.json', 'evidence-report.json', 'recover-claim.json',
    'evidence-check-start.json', 'evidence-check-completed.json'))
RPC_MARKERS = frozenset(('inspect-project', 'inspect-backtests', 'inspect-files',
    'complete-project', 'complete-backtests', 'complete-before', 'complete-final',
    'compile-project', 'compile-backtests', 'compile-files', 'compile-create',
    'launch-compile', 'launch-project', 'launch-backtests', 'launch-files',
    'launch-capacity', 'launch-create', 'status-poll-000',
    *(f'complete-before-{i:02d}' for i in range(11)),
    *(f'complete-write-{i:02d}' for i in range(11)),
    *(f'compile-poll-{i:03d}' for i in range(20))))
RPC_NAMES = frozenset('rpc-' + marker + '-' + event + '.json'
    for marker in RPC_MARKERS for event in ('intent', 'observed', 'failure'))
FALSE_FLAGS = dict(frozen.FALSE_FLAGS)
FINITE = frozenset(('arguments', 'binding', 'bound', 'claim', 'context', 'source',
    'json', 'inventory', 'sequence', 'receipt', 'changed', 'file', 'directory', 'deadline'))


class Refused(ValueError):
    pass


class _EndPrefix(Exception):
    pass


def sandbox_profile(root, control, output):
    """Exact leaves plus ancestor metadata only; ancestors use O_SEARCH FDs."""
    ancestors = {root / 'artifacts', root / 'artifacts/analyst_revisions_v2', control.parent, output.parent}
    quoted = lambda path: json.dumps(str(path))
    metadata = ''.join('(require-not (literal ' + quoted(path) + '))' for path in sorted(ancestors))
    return ('(version 1)(allow default)(deny network*)'
        '(deny process-exec (literal "/usr/bin/security"))'
        '(deny file-read-data (require-all (subpath ' + quoted(root / 'artifacts') + ')'
        '(require-not (subpath ' + quoted(control) + '))'
        '(require-not (subpath ' + quoted(output) + '))))'
        '(deny file-read-metadata (require-all (subpath ' + quoted(root / 'artifacts') + ')'
        '(require-not (subpath ' + quoted(control) + '))'
        '(require-not (subpath ' + quoted(output) + '))' + metadata + '))'
        '(deny file-read-data (literal ' + quoted(control / 'evidence.json') + '))'
        '(deny file-write* (require-all (subpath ' + quoted(root / 'artifacts') + ')'
        '(require-not (subpath ' + quoted(output) + '))'
        '(require-not (literal ' + quoted(output.parent) + '))'
        '(require-not (literal ' + quoted(output.parent.parent) + '))))')


SANDBOX = sandbox_profile(ROOT, CONTROL, OUTPUT)


def require(condition, code):
    if not condition:
        raise Refused(code)


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
    except (TypeError, ValueError, UnicodeError):
        raise Refused('json') from None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_FILE, 'bound')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'json')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('json') from None
    require(type(value) is dict and canonical(value) == raw, 'json')
    return value


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'binding')


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'binding')


def same(left, right):
    require(type(left) is type(right) and canonical(left) == canonical(right), 'binding')


def old_binding():
    return {'schema': frozen.SCHEMA, 'expected_head': OLD_HEAD,
        'caller_sha256': OLD_CALLER, 'profile_sha256': OLD_PROFILE,
        'project_id': remote.PROJECT_ID}


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'source': str(SOURCE),
        'control': str(CONTROL), 'output': str(OUTPUT), 'old_binding': old_binding(),
        'evidence_pin': EVIDENCE_PIN, 'evidence_report_pin': REPORT_PIN,
        'deadline_seconds': DEADLINE, 'max_file_bytes': MAX_FILE,
        'max_total_bytes': MAX_TOTAL, 'native_sandbox': SANDBOX,
        'evidence_payload_read': False, 'provider_request_count': None,
        'operational_retry_authority': False, **FALSE_FLAGS}


def _remaining(deadline):
    require(time.monotonic() < deadline, 'deadline')


def _metadata(info):
    return tuple(getattr(info, key, None) for key in ('st_dev', 'st_ino', 'st_mode',
        'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'))


def _open_directory(path, stack, *, search_only=False):
    """No following symlinks; retain all ancestor descriptors until completion."""
    require(path.is_absolute() and '..' not in path.parts, 'directory')
    fd = os.open('/', os.O_SEARCH | os.O_DIRECTORY)
    stack.callback(os.close, fd)
    chain = []
    for index, part in enumerate(path.parts[1:], 1):
        mode = os.O_SEARCH if search_only or index < len(path.parts) - 1 else os.O_RDONLY
        child = os.open(part, mode | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        stack.callback(os.close, child)
        info = os.fstat(child)
        require(stat.S_ISDIR(info.st_mode), 'directory')
        chain.append((fd, part, child, (info.st_dev, info.st_ino)))
        fd = child
    return fd, chain


def _verify_chain(chain):
    for parent, name, child, identity in chain:
        held = os.fstat(child)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        require(stat.S_ISDIR(named.st_mode)
            and (held.st_dev, held.st_ino) == identity
            and _metadata(held) == _metadata(named), 'changed')


def _read_selected(directory, name, stack):
    require(name != 'evidence.json' and re.fullmatch(r'[a-z0-9-]+\.json', name), 'file')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    stack.callback(os.close, fd)
    before = os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
        and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
        and 0 < before.st_size <= MAX_FILE, 'file')
    require(_metadata(before) == _metadata(os.stat(name, dir_fd=directory, follow_symlinks=False)), 'changed')
    chunks = bytearray()
    while len(chunks) <= MAX_FILE:
        chunk = os.read(fd, min(65536, MAX_FILE + 1 - len(chunks)))
        if not chunk:
            break
        chunks.extend(chunk)
    require(len(chunks) == before.st_size and _metadata(before) == _metadata(os.fstat(fd)), 'changed')
    return bytes(chunks), (name, fd, _metadata(before))


def _allowed_name(name):
    return (name in BASE_NAMES or name in ('initial-inventory.json', 'completed-inventory.json',
        'compile-receipt.json', 'launch-receipt.json', 'own-status.json', 'recover-report.json')
        or re.fullmatch(r'compile-status-(?:0[0-9]|1[0-9])\.json', name) is not None
        or name in RPC_NAMES)


def _read_documents(deadline, validator=None):
    with ExitStack() as stack:
        directory, chain = _open_directory(CONTROL, stack)
        before = os.fstat(directory)
        names = frozenset(os.listdir(directory))
        require(before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o700
            and BASE_NAMES <= names and len(names) <= 256 and all(_allowed_name(n) for n in names), 'inventory')
        documents, held, total = {}, [], 0
        for name in sorted(names - {'evidence.json'}):
            _remaining(deadline)
            raw, identity = _read_selected(directory, name, stack)
            total += len(raw)
            require(total <= MAX_TOTAL, 'bound')
            if name == 'evidence-report.json':
                same({'sha256': sha(raw), 'byte_count': len(raw)}, REPORT_PIN)
            documents[name] = parse(raw)
            held.append(identity)
        result = (documents, names) if validator is None else validator(documents, names)
        _verify_chain(chain)
        for name, fd, metadata in held:
            require(metadata == _metadata(os.fstat(fd)) ==
                _metadata(os.stat(name, dir_fd=directory, follow_symlinks=False)), 'changed')
        require(_metadata(before) == _metadata(os.fstat(directory))
            and names == frozenset(os.listdir(directory)), 'changed')
        return result


def _base(documents, names):
    require(type(documents) is dict and type(names) is frozenset and BASE_NAMES <= names
        and set(documents) == names - {'evidence.json'} and len(names) <= 256, 'inventory')
    binding = old_binding()
    for name in ('claim.json', 'evidence-start.json'):
        same(documents[name], binding)
    same(documents['evidence-parent-completed.json'], {**binding, 'evidence': EVIDENCE_PIN})
    same(documents['recover-claim.json'], {**binding, 'evidence_sha256': EVIDENCE_PIN['sha256'],
        'attempt_id': 2, 'shared_look': 1, 'development_look': 1})
    same(documents['evidence-check-start.json'], {**binding, 'evidence_sha256': EVIDENCE_PIN['sha256']})
    checked = documents['evidence-check-completed.json']
    exact(checked, {*binding, 'evidence_sha256', 'evidence_bytes', 'report_sha256', 'organization_id_sha256'})
    same({k: checked[k] for k in binding}, binding)
    same({'sha256': checked['evidence_sha256'], 'byte_count': checked['evidence_bytes']}, EVIDENCE_PIN)
    require(checked['organization_id_sha256'] == evidence.ORGANIZATION, 'binding')
    digest(checked['report_sha256'])
    report = {**binding, 'operation_completed': True, **FALSE_FLAGS, 'result': {
        'evidence': EVIDENCE_PIN, 'attempt_claim_authenticated': True,
        'project_id': remote.PROJECT_ID, 'provider_request_count': None}}
    same(documents['evidence-report.json'], report)
    raw = canonical(report)
    same({'sha256': sha(raw), 'byte_count': len(raw)}, REPORT_PIN)


def _inventory(value, sources, *, complete=False):
    exact(value, ('project_id', 'projection_sha256', 'files'))
    require(type(value['project_id']) is int and value['project_id'] == remote.PROJECT_ID
        and value['projection_sha256'] == remote.PROJECTION_SHA256, 'receipt')
    rows = value['files']
    require(type(rows) is list and len(rows) <= 11, 'receipt')
    names = []
    for row in rows:
        exact(row, ('name', 'byte_count', 'sha256'))
        name = row['name']
        require(type(name) is str and name in sources and name not in names, 'receipt')
        names.append(name)
        accepted = [sources[name]]
        if not complete:
            accepted += [b'#', b'#\n'] + ([remote.DEFAULT_MAIN] if name == 'main.py' else [])
        require(type(row['byte_count']) is int and any(row['byte_count'] == len(raw)
            and row['sha256'] == sha(raw) for raw in accepted), 'receipt')
    require(names == sorted(names) and (not complete or set(names) == set(sources)), 'receipt')
    return {row['name']: row for row in rows}


def _cloud_id(value):
    require(type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value), 'receipt')
    return value


def validate_documents(documents, names, sources):
    """Pure, strict interrupted-prefix validation; no old corpus or network."""
    _base(documents, names)
    require(type(sources) is dict and set(sources) == remote.SOURCE_NAMES and all(
        type(raw) is bytes and 0 < len(raw) <= 64000 and raw.isascii() for raw in sources.values()), 'source')
    used = set(BASE_NAMES - {'evidence.json'})
    summary = {'schema': SCHEMA, 'stage_authenticated': True, 'old_attempt_id': 2,
        'project_id': remote.PROJECT_ID, 'rpc_intent_count': 0, 'rpc_observed_count': 0,
        'rpc_failure_count': 0, 'last_recorded_marker': None, 'last_recorded_endpoint': None,
        'last_recorded_event': None, 'recorded_application_dispatch_count': None,
        'compile_id': None, 'backtest_id': None, 'recorded_status': None,
        'initial_inventory_recorded': False, 'completed_inventory_recorded': False,
        'rpc_markers': [], 'receipts_present': [],
        'provider_request_count': None, 'lost_cause_recovered': False,
        'no_unjournaled_effects_proven': False, 'operational_retry_authority': False, **FALSE_FLAGS}
    binding = old_binding()

    def take(name):
        if name not in documents:
            raise _EndPrefix()
        require(name not in used, 'sequence')
        used.add(name)
        return documents[name]

    def rpc(marker, endpoint, payload):
        for event in ('intent', 'observed'):
            failure_name = 'rpc-' + marker + '-failure.json'
            if event == 'observed' and failure_name in documents:
                failed = take(failure_name)
                exact(failed, {*binding, 'intent_marker', 'endpoint', 'application_dispatch_count',
                    'category', 'http_status', 'provider_request_count'})
                same({key: failed[key] for key in binding}, binding)
                require(failed['intent_marker'] == marker and failed['endpoint'] == endpoint
                    and type(failed['application_dispatch_count']) is int
                    and failed['application_dispatch_count'] == summary['rpc_intent_count']
                    and failed['category'] in ('unknown', 'status_or_bound_refusal', 'http_failure', 'http_non_json')
                    and (failed['http_status'] is None or (type(failed['http_status']) is int and 100 <= failed['http_status'] <= 599))
                    and failed['provider_request_count'] is None, 'receipt')
                require((failed['category'] in ('http_failure', 'http_non_json')) ==
                    (failed['http_status'] is not None), 'receipt')
                summary.update(rpc_failure_count=1, last_recorded_event='failure',
                    recorded_application_dispatch_count=failed['application_dispatch_count'])
                raise _EndPrefix()
            row = take('rpc-' + marker + '-' + event + '.json')
            exact(row, {*binding, 'event', 'endpoint', 'sha256'})
            same({key: row[key] for key in binding}, binding)
            require(row['event'] == event and row['endpoint'] == endpoint, 'sequence')
            digest(row['sha256'])
            if event == 'intent':
                require(row['sha256'] == sha(canonical(payload)), 'sequence')
                summary['rpc_intent_count'] += 1
                summary['rpc_markers'].append(marker)
            else:
                summary['rpc_observed_count'] += 1
            summary.update(last_recorded_marker=marker, last_recorded_endpoint=endpoint,
                last_recorded_event=event)

    def owned(prefix):
        rpc(prefix + '-project', 'projects/read', {'projectId': remote.PROJECT_ID})
        rpc(prefix + '-backtests', 'backtests/list', {'projectId': remote.PROJECT_ID, 'includeStatistics': False})

    def files(marker):
        rpc(marker, 'files/read', {'projectId': remote.PROJECT_ID})

    def compile_poll(marker, compile_id):
        rpc(marker, 'compile/read', {'projectId': remote.PROJECT_ID, 'compileId': compile_id})

    try:
        owned('inspect')
        files('inspect-files')
        initial = take('initial-inventory.json')
        observed = _inventory(initial, sources)
        summary['initial_inventory_recorded'] = True
        owned('complete')
        files('complete-before')
        for index, (name, raw) in enumerate(sorted(sources.items())):
            expected = {'name': name, 'byte_count': len(raw), 'sha256': sha(raw)}
            if observed.get(name) == expected:
                continue
            files(f'complete-before-{index:02d}')
            rpc(f'complete-write-{index:02d}', 'files/update' if name in observed else 'files/create',
                {'projectId': remote.PROJECT_ID, 'name': name, 'content': raw.decode('ascii')})
            observed[name] = expected
        files('complete-final')
        completed = take('completed-inventory.json')
        _inventory(completed, sources, complete=True)
        summary['completed_inventory_recorded'] = True
        owned('compile')
        files('compile-files')
        rpc('compile-create', 'compile/create', {'projectId': remote.PROJECT_ID})
        compiled = take('compile-receipt.json')
        exact(compiled, ('project_id', 'compile_id', 'projection_sha256', 'source_manifest_sha256'))
        require(type(compiled['project_id']) is int and compiled['project_id'] == remote.PROJECT_ID
            and compiled['projection_sha256'] == remote.PROJECTION_SHA256
            and compiled['source_manifest_sha256'] == sha(canonical(completed)), 'receipt')
        compile_id = _cloud_id(compiled['compile_id'])
        summary['compile_id'] = compile_id
        for index in range(20):
            compile_poll(f'compile-poll-{index:03d}', compile_id)
            state = take(f'compile-status-{index:02d}.json')
            exact(state, ('project_id', 'compile_id', 'state'))
            require(type(state['project_id']) is int and state['project_id'] == remote.PROJECT_ID
                and state['compile_id'] == compile_id and state['state'] in ('InQueue', 'Building', 'BuildSuccess', 'BuildError'), 'receipt')
            summary['recorded_status'] = state['state']
            if state['state'] == 'BuildError':
                raise _EndPrefix()
            if state['state'] == 'BuildSuccess':
                break
        else:
            raise _EndPrefix()
        compile_poll('launch-compile', compile_id)
        owned('launch')
        files('launch-files')
        rpc('launch-capacity', 'projects/nodes/read', {'projectId': remote.PROJECT_ID})
        launch = documents.get('launch-receipt.json')
        if type(launch) is dict and launch.get('state') == 'wait':
            same(take('launch-receipt.json'), {'project_id': remote.PROJECT_ID, 'state': 'wait', 'available_count': 0})
            summary['recorded_status'] = 'capacity_wait'
            result = {'terminal': 'capacity_wait', 'project_id': remote.PROJECT_ID, 'compile_id': compile_id}
        else:
            name = f'{remote.PROJECT_NAME} A2 {remote.PROJECTION_SHA256[:8]}'
            rpc('launch-create', 'backtests/create', {'projectId': remote.PROJECT_ID, 'compileId': compile_id, 'backtestName': name})
            launch = take('launch-receipt.json')
            exact(launch, ('project_id', 'compile_id', 'backtest_id', 'backtest_name', 'status', 'projection_sha256'))
            require(type(launch['project_id']) is int and launch['project_id'] == remote.PROJECT_ID
                and launch['compile_id'] == compile_id and launch['backtest_name'] == name
                and launch['status'] in ('In Queue...', 'In Progress...')
                and launch['projection_sha256'] == remote.PROJECTION_SHA256, 'receipt')
            summary['backtest_id'] = _cloud_id(launch['backtest_id'])
            summary['recorded_status'] = launch['status']
            rpc('status-poll-000', 'backtests/list', {'projectId': remote.PROJECT_ID, 'includeStatistics': False})
            status = take('own-status.json')
            require(status.get('status') in ('In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'), 'receipt')
            same(status, {**launch, 'status': status['status']})
            summary['recorded_status'] = status['status']
            if status['status'] == 'Runtime Error':
                raise _EndPrefix()
            result = {'terminal': 'own_status_observed', 'launch': launch, 'status': status}
        report = take('recover-report.json')
        same(report, {**binding, 'result': {**result, 'application_dispatch_count': summary['rpc_intent_count'],
            'provider_request_count': None}, 'operation_completed': True, **FALSE_FLAGS})
    except _EndPrefix:
        pass
    require(used == set(documents), 'sequence')
    summary['control_file_count'] = len(names)
    summary['receipts_present'] = sorted(name for name in used - (BASE_NAMES - {'evidence.json'})
        if not name.startswith('rpc-'))
    return summary


def validate_report(value):
    """Validate a newly published finite summary, not old operational controls.

    A caller must separately bind the exact reviewed reader bytes/profile, clean
    invocation HEAD, externally observed actual exit zero and report byte pin.
    This schema validator never supplies invocation or third-attempt authority.
    """
    keys = {'schema', 'stage_authenticated', 'old_attempt_id', 'project_id', 'rpc_intent_count',
        'rpc_observed_count', 'rpc_failure_count', 'last_recorded_marker', 'last_recorded_endpoint',
        'last_recorded_event', 'recorded_application_dispatch_count', 'compile_id', 'backtest_id',
        'recorded_status', 'initial_inventory_recorded', 'completed_inventory_recorded',
        'rpc_markers', 'receipts_present', 'provider_request_count', 'lost_cause_recovered',
        'no_unjournaled_effects_proven', 'operational_retry_authority', 'control_file_count',
        'expected_head', 'reader_sha256', 'profile_sha256', 'claim_sha256', 'claim_bytes',
        'old_binding', *FALSE_FLAGS}
    exact(value, keys)
    require(value['schema'] == SCHEMA and value['stage_authenticated'] is True
        and type(value['old_attempt_id']) is int and value['old_attempt_id'] == 2
        and type(value['project_id']) is int and value['project_id'] == remote.PROJECT_ID, 'binding')
    same(value['old_binding'], old_binding())
    require(type(value['expected_head']) is str and re.fullmatch('[0-9a-f]{40}', value['expected_head']), 'binding')
    for key in ('reader_sha256', 'profile_sha256', 'claim_sha256'):
        digest(value[key])
    require(value['profile_sha256'] == sha(canonical(profile_record())), 'binding')
    require(type(value['claim_bytes']) is int and 0 < value['claim_bytes'] <= MAX_FILE, 'bound')
    claim_raw = canonical({'schema': SCHEMA, 'expected_head': value['expected_head'],
        'reader_sha256': value['reader_sha256'], 'profile_sha256': value['profile_sha256'],
        'old_binding': old_binding(), 'attempt_consumed': True})
    require(value['claim_bytes'] == len(claim_raw) and value['claim_sha256'] == sha(claim_raw), 'claim')
    for key in ('rpc_intent_count', 'rpc_observed_count', 'rpc_failure_count', 'control_file_count'):
        require(type(value[key]) is int and 0 <= value[key] <= 256, 'bound')
    markers = value['rpc_markers']
    require(type(markers) is list and len(markers) <= 60 and all(type(item) is str
        and item in RPC_MARKERS for item in markers)
        and len(markers) == len(set(markers)) == value['rpc_intent_count'], 'sequence')
    require(value['rpc_observed_count'] <= value['rpc_intent_count'] <= value['rpc_observed_count'] + 1
        and value['rpc_failure_count'] in (0, 1), 'sequence')
    if not markers:
        require(value['last_recorded_marker'] is None and value['last_recorded_endpoint'] is None
            and value['last_recorded_event'] is None and value['rpc_failure_count'] == 0, 'sequence')
    else:
        require(value['last_recorded_marker'] == markers[-1] and value['last_recorded_endpoint'] in remote.ENDPOINTS
            and value['last_recorded_event'] in ('intent', 'observed', 'failure'), 'sequence')
        require((value['last_recorded_event'] == 'observed') ==
            (value['rpc_intent_count'] == value['rpc_observed_count']), 'sequence')
        require((value['last_recorded_event'] == 'failure') == (value['rpc_failure_count'] == 1), 'sequence')
    count = value['recorded_application_dispatch_count']
    require((count is None and value['rpc_failure_count'] == 0) or
        (type(count) is int and count == value['rpc_intent_count'] and value['rpc_failure_count'] == 1), 'sequence')
    receipts = value['receipts_present']
    require(type(receipts) is list and all(type(name) is str and _allowed_name(name)
        and not name.startswith('rpc-') and name not in BASE_NAMES for name in receipts)
        and receipts == sorted(set(receipts)), 'receipt')
    for key, filename in (('initial_inventory_recorded', 'initial-inventory.json'),
        ('completed_inventory_recorded', 'completed-inventory.json')):
        require(type(value[key]) is bool and value[key] == (filename in receipts), 'receipt')
    require(value['control_file_count'] == len(BASE_NAMES) + value['rpc_intent_count']
        + value['rpc_observed_count'] + value['rpc_failure_count'] + len(receipts), 'inventory')
    for key, filename in (('compile_id', 'compile-receipt.json'), ('backtest_id', 'launch-receipt.json')):
        if value[key] is not None:
            _cloud_id(value[key])
            require(filename in receipts, 'receipt')
    require((value['compile_id'] is not None) == ('compile-receipt.json' in receipts), 'receipt')
    require(value['recorded_status'] is None or value['recorded_status'] in (
        'InQueue', 'Building', 'BuildSuccess', 'BuildError', 'capacity_wait', 'In Queue...',
        'In Progress...', 'Completed.', 'Runtime Error'), 'receipt')
    require(value['provider_request_count'] is None and all(value[key] is False for key in (
        *FALSE_FLAGS, 'lost_cause_recovered', 'no_unjournaled_effects_proven', 'operational_retry_authority')), 'binding')
    return json.loads(canonical(value))


def _preflight(expected_head, reader_sha256, deadline):
    require(Path(__file__).absolute() == SOURCE and Path.cwd() == ROOT
        and ROOT.resolve() == ROOT and sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and Path(sys.executable) == frozen.frozen.PYTHON, 'context')
    require(type(expected_head) is str and re.fullmatch('[0-9a-f]{40}', expected_head), 'arguments')
    digest(reader_sha256)
    require(not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'context')
    frozen._preflight(SimpleNamespace(operation='recover', expected_head=expected_head,
        caller_sha256=OLD_CALLER, evidence_sha256=EVIDENCE_PIN['sha256'], control_fd=None), deadline)
    require(frozen.sha(frozen.canonical(frozen.profile_record())) == OLD_PROFILE, 'source')
    require(frozen.helpers._source_digest(SOURCE) == reader_sha256, 'source')
    blob = frozen.v5._git(['cat-file', 'blob', expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()], deadline, 128 * 1024)
    require(sha(blob) == reader_sha256, 'source')
    _remaining(deadline)


def _claim_and_read(expected_head, reader_sha256, deadline):
    """Exclusive separate claim before any old-leaf access; retain all failures."""
    with ExitStack() as stack:
        parent, chain = _open_directory(OUTPUT.parent.parent, stack, search_only=True)
        try:
            os.mkdir(OUTPUT.parent.name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
        parent, chain = _open_directory(OUTPUT.parent, stack, search_only=True)
        info = os.fstat(parent)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'directory')
        os.mkdir(OUTPUT.name, 0o700, dir_fd=parent)  # Existing/partial claim is spent.
        os.fsync(parent)
        output, own_chain = _open_directory(OUTPUT, stack)
        fd = os.open('claim.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=output)
        try:
            raw = canonical({'schema': SCHEMA, 'expected_head': expected_head,
                'reader_sha256': reader_sha256, 'profile_sha256': sha(canonical(profile_record())),
                'old_binding': old_binding(), 'attempt_consumed': True})
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'claim')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(output)
        claim_raw, identity = _read_selected(output, 'claim.json', stack)
        require(claim_raw == raw and os.listdir(output) == ['claim.json'], 'claim')
        output_metadata = _metadata(os.fstat(output))
        _verify_chain(own_chain)
        _remaining(deadline)
        projected = evidence.reconstruct_projection()  # Public source only, never collect_documents.
        sources = {entry.project_path: entry.source_bytes for entry in projected.source_files}
        result = _read_documents(deadline, lambda documents, names: validate_documents(documents, names, sources))
        _preflight(expected_head, reader_sha256, deadline)
        _verify_chain(chain)
        _verify_chain(own_chain)
        name, claim_fd, before = identity
        require(before == _metadata(os.fstat(claim_fd)) == _metadata(os.stat(name, dir_fd=output, follow_symlinks=False))
            and output_metadata == _metadata(os.fstat(output)) and os.listdir(output) == ['claim.json'], 'changed')
        report = {**result, 'expected_head': expected_head, 'reader_sha256': reader_sha256,
            'profile_sha256': sha(canonical(profile_record())),
            'old_binding': old_binding(), 'claim_sha256': sha(raw), 'claim_bytes': len(raw)}
        validate_report(report)
        report_raw = canonical(report)
        require(len(report_raw) <= MAX_FILE, 'bound')
        fd = os.open('report.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=output)
        try:
            view = memoryview(report_raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'file')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(output)
        retained, report_identity = _read_selected(output, 'report.json', stack)
        require(retained == report_raw and set(os.listdir(output)) == {'claim.json', 'report.json'}, 'changed')
        _verify_chain(own_chain)
        for name, held, before in (identity, report_identity):
            require(before == _metadata(os.fstat(held)) == _metadata(os.stat(name, dir_fd=output, follow_symlinks=False)), 'changed')
        _remaining(deadline)
        return {'schema': SCHEMA, 'stage_authenticated': True,
            'report': {'sha256': sha(report_raw), 'byte_count': len(report_raw)},
            'summary': report, **FALSE_FLAGS}


def finite_failure(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unclassified_refusal'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--reader-sha256', required=True)
    args = parser.parse_args(argv)
    deadline = time.monotonic() + DEADLINE
    try:
        with frozen.helpers._alarm(deadline):
            _preflight(args.expected_head, args.reader_sha256, deadline)
            from scripts import arv2_newrule_execution_environment as environment
            environment._bootstrap_cli_logging()
            environment.require_safe_environment()
            result = _claim_and_read(args.expected_head, args.reader_sha256, deadline)
            raw = canonical(result)
            require(len(raw) <= MAX_FILE, 'bound')
            print(raw.decode('ascii'), end='')
            return 0
    except BaseException as error:
        print(canonical({'schema': SCHEMA, 'stage_authenticated': False,
            'failure_code': finite_failure(error), 'attempt_consumption': 'consumed_or_ambiguous_no_retry',
            'provider_request_count': None, **FALSE_FLAGS}).decode('ascii'), end='')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
