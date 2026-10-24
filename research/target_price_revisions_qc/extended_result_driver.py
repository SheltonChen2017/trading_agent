"""Fresh, bounded own-job processing of retained EXT26 QC evidence.

No credential, provider, QC, restricted Object Store export or generic pathname
entry point exists. Explicit role/hash inventories authorize one immutable read
claim; supplied hashes bind bytes, not provider authenticity or complete private
ledger custody. Failed/uncertain processing remains spent with no automatic retry.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import time
from types import FunctionType

from . import extended_evidence as e, extended_metrics as metrics, extended_native as native

ops = native.collector
LANE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
PRIVATE_ROOT = LANE / 'artifacts/target_price_extended' / e.STUDY_ID / 'operations'
PREFIX = 'research/target_price_revisions_qc/'
SOURCE_PATHS = ('research/__init__.py', PREFIX + '__init__.py') + tuple(PREFIX + name for name in (
    'extended_result_driver.py', 'extended_native.py', 'extended_metrics.py', 'extended_operations.py',
    'extended_evidence.py', 'extended_calendar.json', 'extended_study_freeze.json'))
MAX_FILE, MAX_TOTAL, MAX_SECONDS = 16 * 1024 * 1024, 128 * 1024 * 1024, 120
DISCOVERY_QC_OPERATION = 'TPR-EXT26-QC-20261010-001'
DISCOVERY_CANDIDATE = next(name for name, arm in e.CANDIDATES.items() if arm == 'tpr_on')
DISCOVERY_FILES = {'operations_manifest': 'manifest.' + DISCOVERY_QC_OPERATION + '.json',
    'request_projection': 'request.0002.projection.json', 'request_spent': 'request.0002.spent.json',
    'request_terminal': 'request.0002.terminal.json',
    'stage_spent': DISCOVERY_CANDIDATE + '.project-create.spent.json',
    'stage_transport': DISCOVERY_CANDIDATE + '.project-create.transport.json'}
_FIXED = ((native, 'normalize_nav'), (native, 'normalize_orders'), (metrics, 'nav_metrics'),
          (metrics, 'execution_metrics'), (ops, 'validate_manifest'), (ops, 'compact_aggregate'), (e, 'canonical'))
_FUNCTIONS = tuple(getattr(module, name) for module, name in _FIXED)


class Refusal(ValueError):
    """Closed refusal without private exception text."""


def _fail(): raise Refusal('own-job result processing refused; no automatic retry')

def _sha(raw): return hashlib.sha256(raw).hexdigest()

def _now(): return datetime.now(timezone.utc)


def _clock(value):
    if type(value) is not str or len(value) > 64: _fail()
    try: result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: _fail()
    if result.tzinfo is None or result.utcoffset() != timedelta(0): _fail()
    return result


def _guard(head=None):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    try:
        results = [subprocess.run(['git', *args], cwd=LANE, capture_output=True, timeout=5, check=True).stdout.decode().strip()
                   for args in (('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
                                ('rev-parse', 'HEAD'), ('status', '--short'))]
    except (OSError, UnicodeError, subprocess.SubprocessError): _fail()
    if results[:2] != [str(LANE), BRANCH] or head is not None and results[2] != head: _fail()
    return e._hash(results[2], 40)


def _open_directory(path):
    if type(path) is not type(LANE) or not path.is_absolute(): _fail()
    fd = None
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in path.parts[1:]:
            if component in ('.', '..'): _fail()
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        result, fd = fd, None
        return result
    finally:
        if fd is not None: os.close(fd)


def _read(directory, name, *, private, expected=None):
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not (1 if private else 0) <= before.st_size <= MAX_FILE
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        chunks, remaining = [], before.st_size
        while remaining:
            piece = os.read(fd, min(65536, remaining))
            if not piece: _fail()
            chunks.append(piece); remaining -= len(piece)
        after, raw = os.fstat(fd), b''.join(chunks)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')
        if any(getattr(before, key) != getattr(after, key) for key in fields): _fail()
        if expected is not None and (len(raw) != e._integer(expected['bytes'], MAX_FILE) or _sha(raw) != expected['sha256']): _fail()
        return raw
    finally:
        if fd is not None: os.close(fd)


def _publish(directory, name, raw):
    fd = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if not count: _fail()
            view = view[count:]
        os.fsync(fd); os.fsync(directory)
    finally:
        if fd is not None: os.close(fd)


def _verify_imports():
    if Path(__file__) != LANE / (PREFIX + 'extended_result_driver.py'): _fail()
    for module, filename in ((e, 'extended_evidence.py'), (metrics, 'extended_metrics.py'),
                             (native, 'extended_native.py'), (ops, 'extended_operations.py')):
        if Path(module.__file__) != LANE / (PREFIX + filename): _fail()
    for (module, name), original in zip(_FIXED, _FUNCTIONS):
        if getattr(module, name) is not original or type(original) is not FunctionType or Path(original.__code__.co_filename) != Path(module.__file__): _fail()


def _sources(head):
    result = {}
    for relative in SOURCE_PATHS:
        _guard(head); directory = _open_directory((LANE / relative).parent)
        try: raw = _read(directory, Path(relative).name, private=False)
        finally: os.close(directory)
        _guard(head)
        committed = subprocess.run(['git', 'show', head + ':' + relative], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        result[relative] = raw
    if (_sha(result[PREFIX + 'extended_calendar.json']) != metrics.CALENDAR_SHA256
            or _sha(result[PREFIX + 'extended_study_freeze.json']) != e.FREEZE_SHA256): _fail()
    _guard(head)
    return result


def _names(candidate, attempt, operation, action, has_job, sequence, pages):
    base = candidate + '.attempt.' + str(attempt)
    names = {'operations_manifest': 'manifest.' + operation + '.json', 'execution_manifest': base + '.manifest.json',
        'reservation': base + '.reservation.json', 'compile_response': base + '.compile-response.json', 'closure': base + '.closure.json'}
    if has_job:
        names.update(compile_receipt=base + '.compile-verified.json', readback=base + '.launch-readback.json',
                     launch=base + '.launch.json', terminal=base + '.terminal.json')
    if action == 'metrics':
        native_prefix = base + '.native.' + operation
        collection_prefix = base + '.collection.' + f'{sequence:04d}'
        names.update(nav_series=native_prefix + '.chart.account-nav.normalized-nav.json',
            nav_envelope=native_prefix + '.chart.account-nav.envelope.json', orders_collection=collection_prefix + '.completed.json')
        for index in range(pages): names['orders_page_' + str(index)] = collection_prefix + '.orders.' + f'{99 * index:05d}' + '.envelope.json'
        for role, marker in (('summary', 'EXT26_SUMMARY'), ('index', 'EXT26_EVIDENCE_INDEX')):
            names[role + '_aggregate'] = native_prefix + '.' + marker + '.aggregate.json'
            names[role + '_envelope'] = native_prefix + '.' + marker + '.envelope.json'
    return names


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          read_operation_id, qc_operation_id, candidate_id, attempt, project_id, backtest_id,
          action, inventory, collection_sequence=0, order_pages=0, mode='production'):
    if (type(read_operation_id) is not str or re.fullmatch(r'TPR-EXT26-RESULT-[A-Za-z0-9-]{1,60}', read_operation_id) is None
            or type(qc_operation_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,80}', qc_operation_id) is None
            or candidate_id not in e.CANDIDATES or type(attempt) is not int or not 1 <= attempt <= 3
            or type(project_id) is not int or action not in {'diagnostics', 'metrics'} or mode not in {'production', 'offline-fixture'}): _fail()
    e._integer(project_id); e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if backtest_id is not None: e._id(backtest_id)
    if action == 'metrics':
        if backtest_id is None or type(collection_sequence) is not int or not 1 <= collection_sequence <= 3 or type(order_pages) is not int or not 1 <= order_pages <= 506: _fail()
    elif collection_sequence != 0 or order_pages != 0: _fail()
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 172800: _fail()
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    names = _names(candidate_id, attempt, qc_operation_id, action, backtest_id is not None, collection_sequence, order_pages)
    if type(inventory) is not dict or set(inventory) != set(names): _fail()
    total = 0
    for row in inventory.values():
        e._closed(row, {'sha256', 'bytes'}); e._hash(row['sha256']); total += e._integer(row['bytes'], MAX_FILE)
    if total > MAX_TOTAL: _fail()
    return {'schema': 'tpr-ext26-result-plan-v1', 'study_id': e.STUDY_ID, 'read_operation_id': read_operation_id,
        'qc_operation_id': qc_operation_id, 'candidate_id': candidate_id, 'attempt': attempt, 'project_id': project_id,
        'backtest_id': backtest_id, 'action': action, 'collection_sequence': collection_sequence, 'order_pages': order_pages,
        'git_head': git_head, 'source_hashes': source_hashes, 'owner_instruction_sha256': owner_instruction_sha256,
        'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(), 'inventory': inventory, 'mode': mode,
        'lane_root': str(LANE), 'lane_branch': BRANCH, 'private_root': str(PRIVATE_ROOT),
        'max_file_bytes': MAX_FILE, 'max_total_bytes': MAX_TOTAL, 'max_seconds': MAX_SECONDS,
        'credentials': False, 'network': False, 'object_export': False, 'quantconnect_attempts': 0,
        'development_looks': 0, 'old_receipts_renewed': False, 'canonical_admission': False, 'trading': False}


def _validate_plan(plan):
    arguments = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc',
        'read_operation_id', 'qc_operation_id', 'candidate_id', 'attempt', 'project_id', 'backtest_id', 'action', 'inventory',
        'collection_sequence', 'order_pages', 'mode')}
    if e.canonical(plan) != e.canonical(_plan(**arguments)): _fail()


def _diagnostic(strings):
    kinds = {'AttributeError', 'TypeError', 'NameError', 'ImportError', 'ModuleNotFoundError', 'KeyError',
             'ValueError', 'RuntimeError', 'SyntaxError', 'IndentationError', 'MemoryError', 'TimeoutError'}
    found, frames = set(), set()
    for text in strings:
        if type(text) is not str or len(text) > MAX_FILE: _fail()
        found.update(name for name in kinds if re.search(r'\b' + name + r'\b', text))
        for file, number in re.findall(r'\b(main\.py|extended_core\.py|extended_loader\.py)\b[^\n]{0,30}?\b(?:line\s+|:)([1-9][0-9]{0,5})\b', text):
            frames.add((file, int(number)))
    return {'known_error_types': sorted(found), 'code_frames': [{'file': file, 'line': line} for file, line in sorted(frames)[:64]],
            'private_error_text_returned': False, 'unknown_error_classification': not bool(found)}


def _text(value):
    if type(value) is str: return [value]
    if type(value) is list: return [text for child in value for text in _text(child)]
    if type(value) is dict: return [text for child in value.values() for text in _text(child)]
    return []


def _binding(plan, data):
    candidates = ops.validate_manifest(e.parse_json(data['operations_manifest']))
    manifest = e._manifest(data['execution_manifest'], _sha(data['execution_manifest']))
    candidate, attempt, project = plan['candidate_id'], plan['attempt'], plan['project_id']
    operations_manifest = e.parse_json(data['operations_manifest'])
    if operations_manifest['operation_id'] != plan['qc_operation_id']: _fail()
    specification = candidates[candidate]
    if (manifest['candidate_id'] != candidate or e._integer(manifest['project_id']) != project
            or manifest['config_sha256'] != specification['config_sha256'] or manifest['source_hashes'] != specification['source_hashes']
            or manifest['input_hashes'] != specification['input_hashes']): _fail()
    reservation = e._reservation(data['reservation'], manifest, _sha(data['execution_manifest']))
    if e._integer(reservation['attempt'], 3) != attempt: _fail()
    compile_id, state = e._compile(data['compile_response'], manifest)
    closure = e.parse_json(data['closure'])
    e._closed(closure, {'schema', 'candidate_id', 'attempt', 'manifest_sha256', 'reservation_sha256', 'outcome',
        'compile_response_sha256', 'launch_sha256', 'backtest_response_sha256'})
    if (closure['schema'] != 'tpr-ext26-closed-attempt-v1' or closure['candidate_id'] != candidate
            or e._integer(closure['attempt'], 3) != attempt or closure['manifest_sha256'] != _sha(data['execution_manifest'])
            or closure['reservation_sha256'] != _sha(data['reservation']) or closure['compile_response_sha256'] != _sha(data['compile_response'])): _fail()
    if plan['backtest_id'] is None:
        if state not in {'BuildError', 'Error', 'Failed'} or closure['outcome'] != 'compile_failure' or closure['launch_sha256'] is not None or closure['backtest_response_sha256'] is not None: _fail()
        return manifest, compile_id, 'compile_failure', _diagnostic(_text(e.parse_json(data['compile_response'])['response']))
    binding = e.validate_execution_binding(data['execution_manifest'], expected_manifest_sha256=_sha(data['execution_manifest']),
        config_raw=specification['config_raw'].encode(), reservation_raw=data['reservation'], compile_response_raw=data['compile_response'],
        compile_receipt_raw=data['compile_receipt'], readback_raw=data['readback'], launch_raw=data['launch'])
    if (binding['backtest_id'] != plan['backtest_id'] or closure['outcome'] != 'backtest_terminal'
            or closure['launch_sha256'] != _sha(data['launch']) or closure['backtest_response_sha256'] != _sha(data['terminal'])): _fail()
    request, response = e._envelope(data['terminal'], {'projectId', 'backtestId'}, 'backtests/read')
    e._project(request, response, manifest); terminal = response.get('backtest')
    if (request['backtestId'] != plan['backtest_id'] or type(terminal) is not dict or terminal.get('backtestId') != plan['backtest_id']
            or terminal.get('completed') is not True or terminal.get('status') not in {'Completed', 'Completed.', 'Runtime Error', 'Error', 'Stopped', 'Cancelled'}
            or 'error' not in terminal): _fail()
    if 'projectId' in terminal and e._integer(terminal['projectId']) != project: _fail()
    if terminal['error'] is not None and (type(terminal['error']) is not str or not terminal['error']): _fail()
    status = terminal['status']
    if status in {'Runtime Error', 'Error'} and terminal['error'] is None: _fail()
    if status in {'Completed', 'Completed.'} and (type(terminal.get('progress')) is not e.JsonNumber or terminal['progress'].fraction() != 1 or terminal['error'] is not None): _fail()
    return manifest, compile_id, status, _diagnostic(_text(terminal.get('error')))


def _aggregate(plan, manifest, data, role, marker):
    raw = data[role + '_envelope']
    envelope = native._envelope(raw, _sha(raw), 'backtests/read/log', plan['project_id'], plan['backtest_id'])
    if e.canonical(envelope['request']) != e.canonical({'projectId': plan['project_id'], 'backtestId': plan['backtest_id'], 'start': 0, 'end': 100, 'query': marker}): _fail()
    response = envelope['response']
    if type(response.get('length')) is not e.JsonNumber or response['length'].fraction() != 1 or type(response.get('logs')) is not list or len(response['logs']) != 1: _fail()
    aggregate = ops.compact_aggregate(response['logs'][0], marker, manifest, plan['attempt'], plan['backtest_id'])
    if e.canonical(aggregate) != data[role + '_aggregate']: _fail()
    return aggregate


def _metrics(plan, manifest, compile_id, data, calendar):
    binding = {key: plan[key] for key in ('candidate_id', 'project_id', 'backtest_id', 'attempt')}
    series, nav_census = native.normalize_nav(data['nav_series'], data['nav_envelope'], calendar,
        expected_series_sha256=_sha(data['nav_series']), expected_envelope_sha256=_sha(data['nav_envelope']), **binding)
    orders = native.normalize_orders([data['orders_page_' + str(index)] for index in range(plan['order_pages'])], data['orders_collection'], calendar,
        expected_collection_sha256=_sha(data['orders_collection']), **binding)
    summary = _aggregate(plan, manifest, data, 'summary', 'EXT26_SUMMARY')
    index = _aggregate(plan, manifest, data, 'index', 'EXT26_EVIDENCE_INDEX')
    order_census = e.parse_json(orders.public)
    count = int(order_census['order_count'].lexeme)
    pages = list(orders.pages)
    metrics_binding = {'schema': 'tpr-ext26-metrics-binding-v1', 'candidate_id': manifest['candidate_id'],
        'project_id': plan['project_id'], 'compile_id': compile_id, 'backtest_id': plan['backtest_id'],
        'freeze_sha256': e.FREEZE_SHA256, 'config_sha256': manifest['config_sha256'], 'source_hashes': manifest['source_hashes'],
        'input_hashes': manifest['input_hashes'], 'series_sha256': _sha(series),
        'native_backtest_projection_sha256': _sha(e.canonical(e.parse_json(data['terminal'])['response']['backtest'])),
        'order_collection_sha256': _sha(data['orders_collection']), 'summary_aggregate_sha256': _sha(data['summary_aggregate']),
        'index_aggregate_sha256': _sha(data['index_aggregate'])}
    metrics._binding(metrics_binding, manifest['candidate_id'], series)
    result = {'schema': 'tpr-ext26-own-job-metrics-v1', 'study_id': e.STUDY_ID, **binding,
        'compile_id': compile_id, 'freeze_sha256': e.FREEZE_SHA256, 'config_sha256': manifest['config_sha256'],
        'source_hashes': manifest['source_hashes'], 'input_hashes': manifest['input_hashes'],
        'metrics_binding': metrics_binding, 'nav_census': e.parse_json(nav_census), 'order_census': order_census,
        'nav_metrics': metrics.nav_metrics(series, calendar, expected_series_sha256=_sha(series)),
        'execution_metrics': metrics.execution_metrics(pages, series, calendar, expected_orders_sha256=metrics.order_pages_identity(pages),
            expected_series_sha256=_sha(series), expected_order_count=count),
        'summary': summary, 'evidence_index_receipt': index, 'summary_aggregate_sha256': _sha(data['summary_aggregate']),
        'index_aggregate_sha256': _sha(data['index_aggregate']), 'meaningful_native_orders': count > 0,
        'classification': ('diagnostic_zero_native_orders' if count == 0 else 'diagnostic_native_fill_observations_incomplete'
            if order_census['native_event_count'].fraction() == 0 or order_census['orders_missing_fill_observations'].fraction() != 0
            else 'native_metrics_require_accounting_audit'),
        'full_cloud_journal_exported': False, 'independent_input_row_replay': False, 'provider_authenticity_attested': False,
        'point_in_time_data': False, 'independent_sleeve_pnl_observed': False, 'strategy_accepted': False, 'canonical_admission': False,
        'confirmatory_alpha': False, 'new_looks': 0, 'quantconnect_attempts': 0}
    return result, orders


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    try: yield
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def _execute(plan, sources, path, *, clock, guard):
    _validate_plan(plan)
    if plan['mode'] == 'production' and path != PRIVATE_ROOT or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE)): _fail()
    start, total, directory = time.monotonic(), 0, None
    def check():
        guard(plan['git_head']); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0) or not _clock(plan['created_utc']) <= current < _clock(plan['expires_utc'])
                or time.monotonic() - start >= MAX_SECONDS or {key: _sha(raw) for key, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = _open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        check(); operation = plan['read_operation_id']
        _publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-result-receipt-v1', 'read_operation_id': operation, 'study_id': e.STUDY_ID,
            'candidate_id': plan['candidate_id'], 'attempt': plan['attempt'], 'project_id': plan['project_id'], 'backtest_id': plan['backtest_id'],
            'qc_operation_id': plan['qc_operation_id'], 'action': plan['action'], 'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True,
            'plan_sha256': _sha(e.canonical(plan)), 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'owner_instruction_sha256': plan['owner_instruction_sha256'], 'read_inventory': {}, 'read_bytes': 0,
            'terminal_status': None, 'compile_id': None, 'diagnostic': None, 'metrics': None, 'private_output_hashes': {},
            'automatic_retry': False, 'old_receipts_renewed': False, 'new_looks': 0, 'quantconnect_attempts': 0,
            'full_cloud_journal_exported': False, 'independent_input_row_replay': False, 'canonical_admission': False, 'trading': False}
        try:
            names = _names(plan['candidate_id'], plan['attempt'], plan['qc_operation_id'], plan['action'], plan['backtest_id'] is not None,
                plan['collection_sequence'], plan['order_pages'])
            data = {}
            for role, name in names.items():
                check(); size = e._integer(plan['inventory'][role]['bytes'], MAX_FILE)
                if total + size > MAX_TOTAL: _fail()
                raw = _read(directory, name, private=True, expected=plan['inventory'][role]); total += len(raw)
                data[role] = raw; report['read_inventory'][role] = {'sha256': _sha(raw), 'bytes': len(raw)}
            check(); manifest, compile_id, terminal, diagnostic = _binding(plan, data)
            report.update(compile_id=compile_id, terminal_status=terminal, diagnostic=diagnostic)
            if plan['action'] == 'metrics':
                if terminal not in {'Completed', 'Completed.'}: _fail()
                result, orders = _metrics(plan, manifest, compile_id, data, sources[PREFIX + 'extended_calendar.json'])
                for kind, pages in (('normalized-orders', orders.pages), ('order-observations', orders.observations)):
                    for number, raw in enumerate(pages):
                        check(); name = operation + '.' + kind + '.' + f'{number:04d}' + '.json'
                        _publish(directory, name, raw); report['private_output_hashes'][kind + '.' + str(number)] = _sha(raw)
                report['metrics'] = result
            check(); report['status'] = 'COMPLETED'
        except (Exception, KeyboardInterrupt):
            report['metrics'] = None
        report.update(read_bytes=total, ended_utc=clock().isoformat())
        guard(plan['git_head']); raw = e.canonical(report)
        _publish(directory, operation + '.result.json', raw)
        return raw
    finally:
        if directory is not None: os.close(directory)


def run_result(**arguments):
    _verify_imports(); head = _guard(); sources = _sources(head)
    plan = _plan(source_hashes={key: _sha(raw) for key, raw in sources.items()}, git_head=head, mode='production', **arguments)
    def committed_guard(expected_head):
        _guard(expected_head); _verify_imports()
    with _deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=_now, guard=committed_guard)
        # Source changes after processing cannot be returned as an accepted
        # CLI result; immutable spent/report files still remain retained.
        if _sources(head) != sources: _fail()
        return raw


def _discovery_plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
                    read_operation_id, qc_operation_id, mode='production'):
    if (type(read_operation_id) is not str or re.fullmatch(r'TPR-EXT26-PROJECT-DIAG-[A-Za-z0-9-]{1,48}', read_operation_id) is None
            or qc_operation_id != DISCOVERY_QC_OPERATION or mode not in {'production', 'offline-fixture'}
            or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for identity in source_hashes.values(): e._hash(identity)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 172800: _fail()
    return {'schema': 'tpr-ext26-project-discovery-plan-v1', 'study_id': e.STUDY_ID,
        'read_operation_id': read_operation_id, 'qc_operation_id': qc_operation_id, 'candidate_id': DISCOVERY_CANDIDATE,
        'request_slot': 2, 'action': 'project-discovery', 'mode': mode, 'source_hashes': source_hashes,
        'git_head': git_head, 'owner_instruction_sha256': owner_instruction_sha256,
        'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'files': dict(DISCOVERY_FILES), 'max_file_bytes': MAX_FILE, 'max_total_bytes': MAX_TOTAL, 'max_seconds': MAX_SECONDS,
        'lane_root': str(LANE), 'lane_branch': BRANCH, 'private_root': str(PRIVATE_ROOT),
        'credentials': False, 'network': False, 'object_export': False, 'new_looks': 0,
        'quantconnect_attempts': 0, 'old_receipts_renewed': False, 'project_creation_repeated': False,
        'project_receipt_created': False, 'privacy_attested': False, 'canonical_admission': False, 'trading': False}


def _project_census(data):
    manifest = e.parse_json(data['operations_manifest']); candidates = ops.validate_manifest(manifest)
    if manifest['operation_id'] != DISCOVERY_QC_OPERATION: _fail()
    intended = {'name': candidates[DISCOVERY_CANDIDATE]['project_name'], 'language': 'Py'}
    manifest_sha, payload_sha = _sha(data['operations_manifest']), _sha(e.canonical(intended))
    for role in ('request_spent', 'stage_spent'):
        row = e.parse_json(data[role])
        keys = {'at', 'endpoint', 'payload_sha256', 'manifest_sha256'} if role == 'request_spent' else {'at', 'payload_sha256', 'manifest_sha256'}
        e._closed(row, keys); _clock(row['at'])
        if row['manifest_sha256'] != manifest_sha or row['payload_sha256'] != payload_sha or role == 'request_spent' and row['endpoint'] != 'projects/create': _fail()
    transport = e.parse_json(data['stage_transport']); e._closed(transport, {'at', 'endpoint'}); _clock(transport['at'])
    if transport['endpoint'] != 'projects/create': _fail()
    projection = e.parse_json(data['request_projection'])
    e._closed(projection, {'schema', 'redaction_policy', 'original_wire_sha256', 'original_wire_bytes', 'projection_sha256', 'projection'})
    if (projection['schema'] != 'tpr-ext26-wire-projection-v1' or projection['redaction_policy'] != e.REDACTION_POLICY
            or projection['projection_sha256'] != _sha(e.canonical(projection['projection']))): _fail()
    e._hash(projection['original_wire_sha256']); e._integer(projection['original_wire_bytes'], MAX_FILE)
    terminal = e.parse_json(data['request_terminal'])
    e._closed(terminal, {'at', 'status', 'original_wire_sha256', 'projection_sha256'}); _clock(terminal['at'])
    if terminal['status'] != 'succeeded' or any(terminal[key] != projection[key] for key in ('original_wire_sha256', 'projection_sha256')): _fail()
    body = projection['projection']
    if type(body) is not dict or body.get('success') is not True or type(body.get('projects')) is not list or len(body['projects']) != 1 or type(body['projects'][0]) is not dict: _fail()
    project = body['projects'][0]
    def boolean(name):
        value = project.get(name)
        return {'present': name in project, 'typed_boolean': type(value) is bool, 'value': value if type(value) is bool else None}
    def integer(name):
        value = project.get(name)
        try: result = e._integer(value)
        except ValueError: result = None
        return {'present': name in project, 'typed_positive_integer': result is not None, 'value': result}
    organization = project.get('organizationId'); organization_sha = None
    try:
        organization_sha = _sha(e._id(organization).encode('utf-8'))
    except ValueError: pass
    collaborators = project.get('collaborators')
    return {'schema': 'tpr-ext26-project-create-field-census-v1', 'candidate_id': DISCOVERY_CANDIDATE,
        'intended_name_match': type(project.get('name')) is str and project['name'] == intended['name'],
        'project_id': integer('projectId'), 'owner': boolean('owner'), 'is_public': boolean('isPublic'),
        'max_file_size': integer('maxFileSize'), 'lean_version_id': integer('leanVersionId'),
        'organization_id_present': 'organizationId' in project, 'organization_id_typed': organization_sha is not None,
        'organization_id_sha256': organization_sha,
        'collaborators_present': 'collaborators' in project, 'collaborators_typed_list': type(collaborators) is list,
        'collaborators_count': len(collaborators) if type(collaborators) is list else None,
        'collaborator_owner_true_count': sum(type(row) is dict and row.get('owner') is True for row in collaborators) if type(collaborators) is list else None,
        'other_project_field_count': len(set(project) - {'name', 'projectId', 'owner', 'isPublic', 'maxFileSize', 'leanVersionId', 'organizationId', 'collaborators'}),
        'request_payload_sha256': payload_sha, 'operations_manifest_sha256': manifest_sha,
        'original_wire_sha256': projection['original_wire_sha256'], 'original_wire_bytes': projection['original_wire_bytes'],
        'projection_sha256': projection['projection_sha256'], 'request_terminal': 'succeeded',
        'privacy_attested': False, 'project_creation_repeated': False, 'project_receipt_created': False,
        'provider_authenticity_attested': False, 'canonical_admission': False}


def _project_admission(data, census, plan):
    """Private native metadata only; not privacy acceptance or project adoption."""
    project = e.parse_json(data['request_projection'])['projection']['projects'][0]
    organization = project.get('organizationId')
    try: organization = e._id(organization)
    except ValueError: organization = None
    return {'schema': 'tpr-ext26-project-discovery-admission-v1', 'study_id': e.STUDY_ID,
        'candidate_id': DISCOVERY_CANDIDATE, 'origin_operation_id': DISCOVERY_QC_OPERATION,
        'discovery_read_operation_id': plan['read_operation_id'], 'discovery_plan_sha256': _sha(e.canonical(plan)),
        'field_census_sha256': _sha(e.canonical(census)), 'six_file_hashes': {role: _sha(raw) for role, raw in data.items()},
        'response_wire_sha256': census['original_wire_sha256'], 'response_projection_sha256': census['projection_sha256'],
        'request_payload_sha256': census['request_payload_sha256'],
        'project': {'project_id': census['project_id']['value'], 'name': DISCOVERY_CANDIDATE + '-private' if census['intended_name_match'] else None,
            'organization_id': organization, 'owner': census['owner']['value'],
            'lean_version_id': census['lean_version_id']['value'], 'max_file_size': census['max_file_size']['value']},
        'privacy': {'is_public_returned': census['is_public']['present'], 'is_public': census['is_public']['value'],
            'documented_default_private': False, 'returned_private_field_false': census['is_public']['value'] is False,
            'privacy_attested': False}, 'admitted': False}


def _discover(plan, sources, path, *, clock, guard):
    arguments = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'read_operation_id', 'qc_operation_id', 'mode')}
    if e.canonical(plan) != e.canonical(_discovery_plan(**arguments)): _fail()
    if plan['mode'] == 'production' and path != PRIVATE_ROOT or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE)): _fail()
    start, directory, total = time.monotonic(), None, 0
    def check():
        guard(plan['git_head']); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0) or not _clock(plan['created_utc']) <= current < _clock(plan['expires_utc'])
                or time.monotonic() - start >= MAX_SECONDS or {key: _sha(raw) for key, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = _open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['read_operation_id']; check()
        _publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-project-discovery-receipt-v1', 'read_operation_id': operation,
            'qc_operation_id': DISCOVERY_QC_OPERATION, 'candidate_id': DISCOVERY_CANDIDATE, 'study_id': e.STUDY_ID,
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'plan_sha256': _sha(e.canonical(plan)), 'owner_instruction_sha256': plan['owner_instruction_sha256'],
            'read_inventory': {}, 'read_bytes': 0, 'field_census': None, 'project_admission_name': None,
            'project_admission_sha256': None, 'project_admission_bytes': None, 'automatic_retry': False,
            'project_creation_repeated': False, 'project_receipt_created': False, 'old_receipts_renewed': False,
            'new_looks': 0, 'quantconnect_attempts': 0, 'privacy_attested': False, 'canonical_admission': False, 'trading': False}
        try:
            data = {}
            for role, name in DISCOVERY_FILES.items():
                check(); raw = _read(directory, name, private=True)
                if total + len(raw) > MAX_TOTAL: _fail()
                total += len(raw); data[role] = raw
                report['read_inventory'][role] = {'sha256': _sha(raw), 'bytes': len(raw)}
            check(); census = _project_census(data); admission = e.canonical(_project_admission(data, census, plan))
            name = operation + '.project-admission.json'; _publish(directory, name, admission)
            report.update(field_census=census, project_admission_name=name, project_admission_sha256=_sha(admission),
                          project_admission_bytes=len(admission), status='COMPLETED')
        except (Exception, KeyboardInterrupt):
            report['field_census'] = None
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); _publish(directory, operation + '.result.json', raw)
        return raw
    finally:
        if directory is not None: os.close(directory)


def run_project_discovery(**arguments):
    _verify_imports(); head = _guard(); sources = _sources(head)
    plan = _discovery_plan(source_hashes={key: _sha(raw) for key, raw in sources.items()}, git_head=head, mode='production', **arguments)
    def committed_guard(expected_head):
        _guard(expected_head); _verify_imports()
    with _deadline():
        raw = _discover(plan, sources, PRIVATE_ROOT, clock=_now, guard=committed_guard)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('read-operation-id', 'qc-operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc', 'action'):
        parser.add_argument('--' + option, required=True)
    for option in ('candidate-id', 'project-id', 'attempt', 'backtest-id', 'inventory-json', 'inventory-sha256'):
        parser.add_argument('--' + option)
    parser.add_argument('--collection-sequence', type=int, default=0); parser.add_argument('--order-pages', type=int, default=0)
    args = vars(parser.parse_args(argv))
    try:
        if args['action'] == 'project-discovery':
            if any(args[name] is not None for name in ('candidate_id', 'project_id', 'attempt', 'backtest_id', 'inventory_json', 'inventory_sha256')) or args['collection_sequence'] != 0 or args['order_pages'] != 0: _fail()
            raw = run_project_discovery(**{name: args[name] for name in ('read_operation_id', 'qc_operation_id', 'owner_instruction_sha256', 'created_utc', 'expires_utc')})
            print(raw.decode(), end=''); return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
        inventory_raw = args.pop('inventory_json').encode(); expected = args.pop('inventory_sha256')
        if _sha(inventory_raw) != e._hash(expected): _fail()
        args['inventory'] = e.parse_json(inventory_raw)
        args['project_id'], args['attempt'] = e._integer(e.JsonNumber(args['project_id'])), e._integer(e.JsonNumber(args['attempt']), 3)
        if args['backtest_id'] == 'none': args['backtest_id'] = None
        raw = run_result(**args); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end='')
        return 1


if __name__ == '__main__': raise SystemExit(main())
