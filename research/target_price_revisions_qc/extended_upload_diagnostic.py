"""Single-use metadata-only diagnosis of the frozen EXT26 ON input uploads.

No licensed input, credential, transport or retry entry point exists. Request
spent records are censused in a fixed range; response metadata is read only for
exact ON object/set stage/payload proofs. OFF source/outcome responses are never
opened. Missing observations remain unknown, not successful uploads.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import time

from . import extended_evidence as e, extended_operations as ops

LANE, BRANCH, PRIVATE_ROOT = ops.LANE, ops.BRANCH, ops.PRIVATE_ROOT
PREFIX = 'research/target_price_revisions_qc/'
QC_OPERATION = 'TPR-EXT26-QC-20261010-002'
ON = next(name for name, arm in e.CANDIDATES.items() if arm == 'tpr_on')
BUNDLE = PREFIX + 'extended_source_bundle_successor.json'
BUNDLE_SHA256 = '799e6eaa452860e1223ff9e35e8e4b5fa814161e9cd6cbb9d0bc27a6ae590f7b'
MANIFEST_SHA256 = 'd20d96f9a69ddaccbc8e0866794e1106897b19cbfa8aa72fc9f6f4458669ab9b'
BASE_SHA256 = '824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167'
INITIALIZERS = {'research/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    PREFIX + '__init__.py': '3bc79e69bc0c775d8ef0ec154551436011cba407f37690c27ccbeb9000153c59'}
SOURCE_PATHS = tuple(INITIALIZERS) + tuple(PREFIX + name for name in (
    'extended_upload_diagnostic.py', 'extended_operations.py', 'extended_evidence.py')) + (BUNDLE,)
MAX_FILE, MAX_TOTAL, MAX_SECONDS, REQUEST_SLOTS, INPUT_COUNT = 16 * 1024 * 1024, 128 * 1024 * 1024, 120, 96, 72
Refusal = e.EvidenceError


def _fail(): raise Refusal('upload metadata diagnostic refused; no automatic retry')
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _now(): return datetime.now(timezone.utc)


def _clock(value):
    if type(value) is not str or len(value) > 64: _fail()
    try: answer = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: _fail()
    if answer.tzinfo is None or answer.utcoffset() != timedelta(0): _fail()
    return answer


def _guard(head=None):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    try:
        values = [subprocess.run(['git', *args], cwd=LANE, capture_output=True, check=True, timeout=5).stdout.decode().strip()
            for args in (('rev-parse', '--show-toplevel'), ('branch', '--show-current'), ('rev-parse', 'HEAD'), ('status', '--short'))]
    except (OSError, UnicodeError, subprocess.SubprocessError): _fail()
    if values[:2] != [str(LANE), BRANCH] or head is not None and values[2] != head: _fail()
    return e._hash(values[2], 40)


def _open_directory(path):
    if type(path) is not type(LANE) or not path.is_absolute(): _fail()
    fd = None
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in path.parts[1:]:
            if component in ('.', '..'): _fail()
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        answer, fd = fd, None
        return answer
    finally:
        if fd is not None: os.close(fd)


def _read(directory, name, *, private=True, optional=False, maximum=MAX_FILE):
    ops._name(name); fd = None
    try:
        try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except OSError as exc:
            if optional and exc.errno == errno.ENOENT: return None
            raise
        before = os.fstat(fd)
        if (type(maximum) is not int or not 0 <= maximum <= MAX_FILE
                or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not (1 if private else 0) <= before.st_size <= maximum
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        chunks, remaining = [], before.st_size
        while remaining:
            raw = os.read(fd, min(65536, remaining))
            if not raw: _fail()
            chunks.append(raw); remaining -= len(raw)
        after = os.fstat(fd)
        if any(getattr(before, name) != getattr(after, name) for name in
               ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')): _fail()
        return b''.join(chunks)
    finally:
        if fd is not None: os.close(fd)


def _publish(directory, name, raw):
    ops._name(name); fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if not count: _fail()
            view = view[count:]
        os.fsync(fd); os.fsync(directory)
    finally: os.close(fd)


def _sources(head):
    result = {}
    for relative in SOURCE_PATHS:
        _guard(head); directory = _open_directory((LANE / relative).parent)
        try: raw = _read(directory, Path(relative).name, private=False)
        finally: os.close(directory)
        committed = subprocess.run(['git', 'show', head + ':' + relative], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        result[relative] = raw
    expected = {**INITIALIZERS, BUNDLE: BUNDLE_SHA256, PREFIX + 'extended_operations.py': BASE_SHA256}
    if any(_sha(result[name]) != identity for name, identity in expected.items()): _fail()
    _guard(head)
    return result


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          read_operation_id, expected_manifest_sha256, mode='production'):
    if (type(read_operation_id) is not str or re.fullmatch(r'TPR-EXT26-UPLOAD-DIAG-[A-Za-z0-9-]{1,48}', read_operation_id) is None
            or mode not in {'production', 'offline-fixture'} or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)
            or e._hash(expected_manifest_sha256) != MANIFEST_SHA256): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for identity in source_hashes.values(): e._hash(identity)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 86400: _fail()
    return {'schema': 'tpr-ext26-upload-diagnostic-plan-v1', 'study_id': e.STUDY_ID, 'read_operation_id': read_operation_id,
        'qc_operation_id': QC_OPERATION, 'candidate_id': ON, 'expected_manifest_sha256': expected_manifest_sha256,
        'bundle_sha256': BUNDLE_SHA256, 'git_head': git_head, 'source_hashes': source_hashes,
        'owner_instruction_sha256': owner_instruction_sha256, 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'request_slots': REQUEST_SLOTS, 'input_count': INPUT_COUNT, 'max_file_bytes': MAX_FILE, 'max_total_bytes': MAX_TOTAL,
        'max_seconds': MAX_SECONDS, 'mode': mode, 'lane_root': str(LANE), 'lane_branch': BRANCH, 'private_root': str(PRIVATE_ROOT),
        'licensed_payload_reads': False, 'off_response_reads': False, 'network': False, 'credentials': False,
        'automatic_retry': False, 'upload_repeated': False, 'old_receipts_renewed': False,
        'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False, 'trading': False}


def _errors(body):
    """Only closed classes/explicit numeric code fields; never echo error text."""
    classes, codes, http_codes = set(), set(), set()
    patterns = {'quota': r'\b(quota|storage limit|insufficient storage|capacity|organization storage)\b',
        'size': r'\b(size|too large|maximum bytes|payload too|content length|file limit)\b',
        'timeout': r'\b(timeout|timed out|deadline)\b', 'http': r'\b(http|status code|unauthorized|forbidden|rate limit)\b'}
    def visit(value, key='', depth=0):
        if depth > 16: _fail()
        if type(value) is str:
            for kind, pattern in patterns.items():
                if re.search(pattern, value.lower()): classes.add(kind)
        elif type(value) is list:
            if len(value) > 4096: _fail()
            for item in value: visit(item, key, depth + 1)
        elif type(value) is dict:
            for name in ('errors', 'error', 'message', 'code', 'errorCode', 'statusCode', 'httpStatus'):
                if name in value: visit(value[name], name, depth + 1)
        elif type(value) is e.JsonNumber:
            try: number = e._integer(value, 1000000)
            except ValueError: return
            if key in {'code', 'errorCode'}: codes.add(number)
            if key in {'statusCode', 'httpStatus'} and number in {400, 401, 403, 404, 408, 413, 429, 500, 502, 503, 504}:
                http_codes.add(number); classes.add('http')
    visit(body)
    return {'classes': sorted(classes), 'explicit_api_error_codes': sorted(codes), 'explicit_http_status_codes': sorted(http_codes),
        'unknown_classification': not bool(classes or codes or http_codes), 'message_text_returned': False,
        'account_ids_returned': False, 'http_transport_status_observed': False}


def _projection(raw):
    value = e.parse_json(raw)
    e._closed(value, {'schema', 'redaction_policy', 'original_wire_sha256', 'original_wire_bytes', 'projection_sha256', 'projection'})
    if (value['schema'] != 'tpr-ext26-wire-projection-v1' or value['redaction_policy'] != e.REDACTION_POLICY
            or value['projection_sha256'] != _sha(e.canonical(value['projection']))): _fail()
    e._hash(value['original_wire_sha256']); e._integer(value['original_wire_bytes'], MAX_FILE)
    if type(value['projection']) is not dict: _fail()
    return value


def _census(plan, sources, read):
    if _sha(sources[BUNDLE]) != plan['bundle_sha256']: _fail()
    bundle = e.parse_json(sources[BUNDLE]); e._closed(bundle, {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'})
    raw_manifest = read('manifest.' + QC_OPERATION + '.json')
    if raw_manifest is None or _sha(raw_manifest) != plan['expected_manifest_sha256']: _fail()
    manifest = e.parse_json(raw_manifest); ops.validate_manifest(manifest)
    if (manifest['operation_id'] != QC_OPERATION or manifest['inputs'] != bundle['inputs']
            or manifest['candidates'] != bundle['candidates'] or manifest['preparation_sha256'] != bundle['preparation_sha256']
            or bundle['schema'] != 'tpr-ext26-source-bundle-v1' or len(manifest['inputs']) != INPUT_COUNT): _fail()
    begin, end = _clock(manifest['created_utc']), _clock(manifest['expires_utc'])
    stages, by_payload = [], {}
    for item in manifest['inputs']:
        identity = item['sha256']; base = 'input.' + identity
        values = {role: read(base + suffix) for role, suffix in
            (('read', '.read.spent.json'), ('upload', '.upload.spent.json'), ('transport', '.upload.transport.json'), ('completed', '.completed.json'))}
        values = {role: e.parse_json(raw) if raw is not None else None for role, raw in values.items()}
        for role, keys in (('read', {'at', 'name', 'sha256', 'manifest_sha256'}),
                           ('upload', {'at', 'manifest_sha256', 'payload_sha256'}), ('transport', {'at', 'endpoint'}),
                           ('completed', {'sha256', 'key', 'bytes'})):
            value = values[role]
            if value is None: continue
            e._closed(value, keys)
            if role != 'completed' and not begin <= _clock(value['at']) <= end: _fail()
        if values['read'] is not None and any(values['read'][key] != expected for key, expected in
            (('name', item['name']), ('sha256', identity), ('manifest_sha256', plan['expected_manifest_sha256']))): _fail()
        if values['upload'] is not None:
            if values['read'] is None or values['upload']['manifest_sha256'] != plan['expected_manifest_sha256']: _fail()
            payload = e._hash(values['upload']['payload_sha256'])
            if payload in by_payload or _clock(values['read']['at']) > _clock(values['upload']['at']): _fail()
            by_payload[payload] = len(stages)
        if values['transport'] is not None and (values['upload'] is None or values['transport']['endpoint'] != 'object/set'
                or _clock(values['upload']['at']) > _clock(values['transport']['at'])): _fail()
        if values['completed'] is not None and values['completed'] != {key: item[key] for key in ('sha256', 'key', 'bytes')}: _fail()
        stages.append((item, values, []))
    spent_count, unrelated = 0, 0
    for sequence in range(1, REQUEST_SLOTS + 1):
        prefix = 'request.' + f'{sequence:04d}'
        raw = read(prefix + '.spent.json')
        if raw is None: continue
        row = e.parse_json(raw); e._closed(row, {'at', 'endpoint', 'payload_sha256', 'manifest_sha256'})
        _clock(row['at']); e._hash(row['payload_sha256']); e._hash(row['manifest_sha256'])
        if type(row['endpoint']) is not str or row['endpoint'] not in ops.ENDPOINTS: _fail()
        spent_count += 1
        if row['endpoint'] != 'object/set' or row['manifest_sha256'] != plan['expected_manifest_sha256']:
            unrelated += 1; continue
        if row['payload_sha256'] not in by_payload: _fail()
        item, values, requests = stages[by_payload[row['payload_sha256']]]
        if requests or values['transport'] is None or not _clock(values['transport']['at']) <= _clock(row['at']) <= end: _fail()
        terminal_raw, projection_raw = read(prefix + '.terminal.json'), read(prefix + '.projection.json')
        terminal = e.parse_json(terminal_raw) if terminal_raw is not None else None
        projection = _projection(projection_raw) if projection_raw is not None else None
        if terminal is not None:
            if terminal.get('status') == 'succeeded':
                e._closed(terminal, {'at', 'status', 'original_wire_sha256', 'projection_sha256'})
                if (projection is None or projection['projection'].get('success') is not True
                        or any(terminal[key] != projection[key] for key in ('original_wire_sha256', 'projection_sha256'))): _fail()
            elif terminal.get('status') == 'failed_or_unknown':
                e._closed(terminal, {'at', 'status', 'automatic_retry'})
                if terminal['automatic_retry'] is not False: _fail()
            else: _fail()
            if not _clock(row['at']) <= _clock(terminal['at']) <= end: _fail()
        requests.append({'sequence': sequence, 'terminal': terminal, 'projection': projection})
    answer, counts = [], {}
    for item, values, requests in stages:
        request = requests[0] if requests else None
        terminal = request['terminal'] if request else None
        if values['completed'] is not None:
            if terminal is None or terminal['status'] != 'succeeded': _fail()
            state = 'completed'
        elif request is not None:
            state = 'failed_or_unknown' if terminal is not None and terminal['status'] == 'failed_or_unknown' else 'request_succeeded_no_completion' if terminal is not None else 'request_terminal_unavailable'
        elif values['transport'] is not None: state = 'transport_admitted_no_request'
        elif values['upload'] is not None: state = 'upload_claimed_no_transport'
        elif values['read'] is not None: state = 'input_read_claimed_no_upload'
        else: state = 'unattempted'
        counts[state] = counts.get(state, 0) + 1
        projection = request['projection'] if request else None
        answer.append({'input_sha256': item['sha256'], 'status': state, 'request_sequence': request['sequence'] if request else None,
            'terminal_status': terminal['status'] if terminal else None,
            'original_wire_sha256': projection['original_wire_sha256'] if projection else None,
            'projection_sha256': projection['projection_sha256'] if projection else None,
            'error_classification': _errors(projection['projection']) if projection and state != 'completed' else None})
    return {'input_count': len(answer), 'counts': counts, 'inputs': answer, 'spent_request_count': spent_count,
        'unrelated_spent_request_count': unrelated, 'request_slot_limit': REQUEST_SLOTS,
        'snapshot_census_only': True, 'unrelated_responses_read': False, 'licensed_payloads_read': False,
        'provider_authenticity_attested': False, 'all_uploads_completed': counts.get('completed') == INPUT_COUNT}


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    try: yield
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def _execute(plan, sources, path, *, clock, guard):
    arguments = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc',
        'read_operation_id', 'expected_manifest_sha256', 'mode')}
    if e.canonical(plan) != e.canonical(_plan(**arguments)): _fail()
    if plan['mode'] == 'production' and path != PRIVATE_ROOT or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE)): _fail()
    started, directory, total = time.monotonic(), None, 0
    def check():
        guard(plan['git_head']); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not _clock(plan['created_utc']) <= current < _clock(plan['expires_utc'])
                or time.monotonic() - started >= MAX_SECONDS or {key: _sha(raw) for key, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = _open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['read_operation_id']; check()
        _publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-upload-diagnostic-receipt-v1', 'read_operation_id': operation, 'qc_operation_id': QC_OPERATION,
            'candidate_id': ON, 'study_id': e.STUDY_ID, 'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True,
            'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'], 'plan_sha256': _sha(e.canonical(plan)),
            'owner_instruction_sha256': plan['owner_instruction_sha256'], 'read_inventory': {}, 'absent_metadata': [],
            'census': None, 'read_bytes': 0, 'automatic_retry': False, 'upload_repeated': False, 'old_receipts_renewed': False,
            'new_looks': 0, 'quantconnect_attempts': 0, 'licensed_payload_reads': False, 'off_response_reads': False,
            'canonical_admission': False, 'trading': False}
        def read(name):
            nonlocal total
            check(); raw = _read(directory, name, optional=True, maximum=min(MAX_FILE, MAX_TOTAL - total))
            if raw is None: report['absent_metadata'].append(name); return None
            if total + len(raw) > MAX_TOTAL: _fail()
            total += len(raw); report['read_inventory'][name] = {'sha256': _sha(raw), 'bytes': len(raw)}
            return raw
        try:
            report['census'] = _census(plan, sources, read); check(); report['status'] = 'COMPLETED'
        except (Exception, KeyboardInterrupt): report['census'] = None
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); _publish(directory, operation + '.result.json', raw)
        return raw
    finally:
        if directory is not None: os.close(directory)


def run(**arguments):
    if Path(__file__) != LANE / (PREFIX + 'extended_upload_diagnostic.py') or Path(e.__file__) != LANE / (PREFIX + 'extended_evidence.py') or Path(ops.__file__) != LANE / (PREFIX + 'extended_operations.py'): _fail()
    head = _guard(); sources = _sources(head)
    plan = _plan(source_hashes={name: _sha(raw) for name, raw in sources.items()}, git_head=head, mode='production', **arguments)
    with _deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=_now, guard=_guard)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('read-operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc', 'expected-manifest-sha256'):
        parser.add_argument('--' + name, required=True)
    args = vars(parser.parse_args(argv))
    try:
        raw = run(**args); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end='')
        return 1


if __name__ == '__main__': raise SystemExit(main())
