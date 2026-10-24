"""Fresh, metadata-only census of the fixed EXT26 operation003 gzip uploads.

No payload, compressed file, outcome, credential, retry or transport is opened.
Only exact matching object/set stage/request proofs admit response projections;
all other request metadata is counted without reading its response. Unknown
stages remain unknown. Independent provider authenticity is not asserted.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import errno
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import time

from . import extended_evidence as e, extended_operations as ops, extended_upload_diagnostic as old

LANE, BRANCH, PRIVATE_ROOT = ops.LANE, ops.BRANCH, ops.PRIVATE_ROOT
PREFIX = 'research/target_price_revisions_qc/'
QC_OPERATION = 'TPR-EXT26-QC-20261010-003'
ON = 'TPR-CAP-TILT-EXT26-ON-BASE-v1'
BUNDLE = PREFIX + 'extended_source_bundle_compressed.json'
BUNDLE_SHA256 = '223efa83c9ed7ed2bc17547f31583886e7705559635a38946bf55010902f0a92'
MANIFEST_SHA256 = 'caa3a8609ab50fb2d977e2279586dc9b3bc58e7e0434df5433b88cc251776c57'
INITIALIZERS = old.INITIALIZERS
SOURCE_PATHS = tuple(INITIALIZERS) + tuple(PREFIX + name for name in (
    'extended_compressed_upload_diagnostic.py', 'extended_upload_diagnostic.py', 'extended_operations.py', 'extended_evidence.py')) + (BUNDLE,)
SOURCE_PINS = {**INITIALIZERS, BUNDLE: BUNDLE_SHA256,
    PREFIX + 'extended_operations.py': '824b3f0c180f1aeb7038d8f280c44507b5c39687fcccc87c539f242d9256d167',
    PREFIX + 'extended_upload_diagnostic.py': '9bb026bc7caf45762f84e68725f3db9768ad3d703d03549764899afc68be5b2c'}
MAX_FILE, MAX_TOTAL, MAX_SECONDS, REQUEST_SLOTS = 16 * 1024 * 1024, 128 * 1024 * 1024, 120, 128
Refusal = e.EvidenceError
_sha, _clock, _guard, _open_directory, _publish = old._sha, old._clock, old._guard, old._open_directory, old._publish


def _fail(): raise Refusal('compressed upload metadata diagnostic refused; no automatic retry')
def _now(): return datetime.now(timezone.utc)


def _read(directory, name, *, private=True, optional=False, maximum=MAX_FILE):
    ops._name(name); fd = None
    try:
        try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except OSError as exc:
            if optional and exc.errno == errno.ENOENT: return None
            raise
        before = os.fstat(fd)
        if (type(maximum) is not int or not 0 <= maximum <= MAX_FILE or not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1 or not (1 if private else 0) <= before.st_size <= maximum
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        pieces, remaining = [], before.st_size
        while remaining:
            raw = os.read(fd, min(65536, remaining))
            if not raw: _fail()
            pieces.append(raw); remaining -= len(raw)
        after = os.fstat(fd); named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if any(getattr(before, key) != getattr(value, key) for value in (after, named) for key in
            ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')): _fail()
        return b''.join(pieces)
    finally:
        if fd is not None: os.close(fd)


def _sources(head):
    sources = {}
    for name in SOURCE_PATHS:
        _guard(head); directory = _open_directory((LANE / name).parent)
        try: raw = _read(directory, Path(name).name, private=False)
        finally: os.close(directory)
        committed = subprocess.run(['git', 'show', head + ':' + name], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        sources[name] = raw
    if any(_sha(sources[name]) != value for name, value in SOURCE_PINS.items()): _fail()
    _guard(head); return sources


def _literal(source, variable):
    if type(source) is not str: _fail()
    try:
        nodes = ast.parse(source).body
        if (len(nodes) != 1 or type(nodes[0]) is not ast.Assign or len(nodes[0].targets) != 1
                or type(nodes[0].targets[0]) is not ast.Name or nodes[0].targets[0].id != variable
                or type(nodes[0].value) is not ast.Constant or type(nodes[0].value.value) is not str): _fail()
        return nodes[0].value.value
    except (SyntaxError, TypeError, ValueError): _fail()


def _inventory(bundle_raw):
    if _sha(bundle_raw) != BUNDLE_SHA256: _fail()
    bundle = e.parse_json(bundle_raw)
    e._closed(bundle, {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'})
    if bundle['schema'] != 'tpr-ext26-source-bundle-v1' or type(bundle['candidates']) is not list: _fail()
    candidates = [row for row in bundle['candidates'] if type(row) is dict and row.get('candidate_id') == ON]
    if len(candidates) != 1: _fail()
    files = candidates[0].get('files')
    if type(files) is not dict or type(files.get('compressed_packet.py')) is not str: _fail()
    source = files['compressed_packet.py']
    try: text = _literal(source, 'COMPRESSION_JSON')
    except ValueError:
        imports = re.findall(r'^from (compressed_packet_part[0-9]+) import PART_JSON as (P[0-9]+)$', source, flags=re.M)
        if not 1 <= len(imports) <= 8 or imports != [('compressed_packet_part' + str(index), 'P' + str(index)) for index in range(len(imports))]: _fail()
        expected = '\n'.join('from ' + name + ' import PART_JSON as ' + alias for name, alias in imports)
        expected += '\nCOMPRESSION_JSON = ' + ' + '.join(alias for _, alias in imports) + '\n'
        if source != expected or {name for name in files if name.startswith('compressed_packet')} != {'compressed_packet.py', *(name + '.py' for name, _ in imports)}: _fail()
        text = ''.join(_literal(files[name + '.py'], 'PART_JSON') for name, _ in imports)
    else:
        if {name for name in files if name.startswith('compressed_packet')} != {'compressed_packet.py'}: _fail()
    mapping_raw = text.encode('utf-8'); mapping = e.parse_json(mapping_raw)
    e._closed(mapping, ('schema study_id freeze_sha256 preparation_sha256 bundle_sha256 processing_operation_id processing_plan_sha256 encoding gzip_level gzip_mtime payloads').split())
    if (mapping['schema'] != 'tpr-ext26-gzip-input-map-v1' or mapping['study_id'] != e.STUDY_ID
            or mapping['freeze_sha256'] != e.FREEZE_SHA256 or mapping['preparation_sha256'] != bundle['preparation_sha256']
            or mapping['encoding'] != 'gzip' or mapping['gzip_level'] != e.JsonNumber('9') or mapping['gzip_mtime'] != e.JsonNumber('0')
            or type(mapping['payloads']) is not list or len(mapping['payloads']) != 72): _fail()
    originals = {row['sha256']: row for row in bundle['inputs']}
    if len(originals) != 72: _fail()
    seen_plain, seen_gzip = set(), set()
    for row in mapping['payloads']:
        e._closed(row, ('plain_name logical_key plain_sha256 plain_bytes stored_name stored_key gzip_sha256 gzip_bytes').split())
        plain, compressed = e._hash(row['plain_sha256']), e._hash(row['gzip_sha256'])
        original = originals.get(plain)
        if (original is None or any(row[left] != original[right] for left, right in
                (('plain_name', 'name'), ('logical_key', 'key'), ('plain_sha256', 'sha256'), ('plain_bytes', 'bytes')))
                or row['stored_name'] != 'gzip.' + compressed + '.json'
                or row['stored_key'] != row['logical_key'].rsplit('/', 1)[0] + '/' + row['stored_name']
                or plain in seen_plain or compressed in seen_gzip): _fail()
        e._integer(row['gzip_bytes'], ops.MAX_INPUT_BYTES); seen_plain.add(plain); seen_gzip.add(compressed)
    return bundle, mapping['payloads'], _sha(mapping_raw)


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          read_operation_id, expected_manifest_sha256, mode='production'):
    if (type(read_operation_id) is not str or re.fullmatch(r'TPR-EXT26-COMPRESSED-UPLOAD-DIAG-[A-Za-z0-9-]{1,48}', read_operation_id) is None
            or mode not in {'production', 'offline-fixture'} or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)
            or e._hash(expected_manifest_sha256) != MANIFEST_SHA256): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for value in source_hashes.values(): e._hash(value)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 86400: _fail()
    return {'schema': 'tpr-ext26-compressed-upload-diagnostic-plan-v1', 'study_id': e.STUDY_ID,
        'read_operation_id': read_operation_id, 'qc_operation_id': QC_OPERATION, 'candidate_id': ON,
        'expected_manifest_sha256': expected_manifest_sha256, 'bundle_sha256': BUNDLE_SHA256,
        'source_hashes': source_hashes, 'git_head': git_head, 'owner_instruction_sha256': owner_instruction_sha256,
        'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(), 'mode': mode,
        'lane_root': str(LANE), 'lane_branch': BRANCH, 'private_root': str(PRIVATE_ROOT),
        'request_slots': REQUEST_SLOTS, 'input_count': 72, 'max_file_bytes': MAX_FILE,
        'max_total_bytes': MAX_TOTAL, 'max_seconds': MAX_SECONDS, 'licensed_payload_reads': False,
        'gzip_reads': False, 'unrelated_response_reads': False, 'outcome_reads': False,
        'network': False, 'credentials': False, 'automatic_retry': False, 'upload_repeated': False,
        'old_receipts_renewed': False, 'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False, 'trading': False}


def _census(plan, sources, read):
    bundle, inputs, mapping_sha = _inventory(sources[BUNDLE])
    raw_manifest = read('manifest.' + QC_OPERATION + '.json')
    if raw_manifest is None or _sha(raw_manifest) != MANIFEST_SHA256: _fail()
    manifest = e.parse_json(raw_manifest); ops.validate_manifest(manifest)
    if manifest['operation_id'] != QC_OPERATION or any(manifest[key] != bundle[key] for key in ('inputs', 'candidates', 'preparation_sha256')): _fail()
    begin, end = _clock(manifest['created_utc']), _clock(manifest['expires_utc'])
    stages, by_payload = [], {}
    for item in inputs:
        prefix = 'compressed-input.' + item['gzip_sha256']
        observed = {role: read(prefix + suffix) for role, suffix in
            (('read', '.read.spent.json'), ('upload', '.upload.spent.json'), ('transport', '.upload.transport.json'), ('completed', '.completed.json'))}
        observed = {role: e.parse_json(raw) if raw is not None else None for role, raw in observed.items()}
        schemas = {'read': {'at', 'name', 'gzip_sha256', 'mapping_sha256', 'manifest_sha256'},
            'upload': {'at', 'manifest_sha256', 'payload_sha256'}, 'transport': {'at', 'endpoint'},
            'completed': {'schema', 'mapping_sha256', 'plain_sha256', 'plain_bytes', 'logical_key', 'gzip_sha256', 'gzip_bytes', 'stored_key'}}
        for role, value in observed.items():
            if value is None: continue
            e._closed(value, schemas[role])
            if role != 'completed' and not begin <= _clock(value['at']) <= end: _fail()
        if observed['read'] is not None and any(observed['read'][key] != expected for key, expected in
            (('name', item['stored_name']), ('gzip_sha256', item['gzip_sha256']), ('mapping_sha256', mapping_sha), ('manifest_sha256', MANIFEST_SHA256))): _fail()
        if observed['upload'] is not None:
            if (observed['read'] is None or observed['upload']['manifest_sha256'] != MANIFEST_SHA256
                    or _clock(observed['read']['at']) > _clock(observed['upload']['at'])): _fail()
            payload = e._hash(observed['upload']['payload_sha256'])
            if payload in by_payload: _fail()
            by_payload[payload] = len(stages)
        if observed['transport'] is not None and (observed['upload'] is None or observed['transport']['endpoint'] != 'object/set'
                or _clock(observed['upload']['at']) > _clock(observed['transport']['at'])): _fail()
        if observed['completed'] is not None:
            expected = {'schema': 'tpr-ext26-gzip-upload-v1', 'mapping_sha256': mapping_sha,
                **{key: item[key] for key in ('plain_sha256', 'plain_bytes', 'logical_key', 'gzip_sha256', 'gzip_bytes', 'stored_key')}}
            if observed['completed'] != expected: _fail()
        stages.append((item, observed, []))
    spent, unrelated = 0, 0
    for number in range(1, REQUEST_SLOTS + 1):
        prefix = 'request.' + f'{number:04d}'
        raw = read(prefix + '.spent.json')
        if raw is None: continue
        value = e.parse_json(raw); e._closed(value, {'at', 'endpoint', 'payload_sha256', 'manifest_sha256'})
        _clock(value['at']); e._hash(value['payload_sha256']); e._hash(value['manifest_sha256'])
        if value['endpoint'] not in ops.ENDPOINTS: _fail()
        spent += 1
        if value['endpoint'] != 'object/set' or value['manifest_sha256'] != MANIFEST_SHA256:
            unrelated += 1; continue
        if value['payload_sha256'] not in by_payload: _fail()
        item, observed, requests = stages[by_payload[value['payload_sha256']]]
        if requests or observed['transport'] is None or not _clock(observed['transport']['at']) <= _clock(value['at']) <= end: _fail()
        terminal_raw, projection_raw = read(prefix + '.terminal.json'), read(prefix + '.projection.json')
        terminal = e.parse_json(terminal_raw) if terminal_raw is not None else None
        projection = old._projection(projection_raw) if projection_raw is not None else None
        if terminal is not None:
            if terminal.get('status') == 'succeeded':
                e._closed(terminal, {'at', 'status', 'original_wire_sha256', 'projection_sha256'})
                if (projection is None or projection['projection'].get('success') is not True
                        or any(terminal[key] != projection[key] for key in ('original_wire_sha256', 'projection_sha256'))): _fail()
            elif terminal.get('status') == 'failed_or_unknown':
                e._closed(terminal, {'at', 'status', 'automatic_retry'})
                if terminal['automatic_retry'] is not False: _fail()
            else: _fail()
            if not _clock(value['at']) <= _clock(terminal['at']) <= end: _fail()
        requests.append({'sequence': number, 'terminal': terminal, 'projection': projection})
    answer, counts = [], {}
    for item, observed, requests in stages:
        request = requests[0] if requests else None
        terminal = request['terminal'] if request else None
        if observed['completed'] is not None:
            if terminal is None or terminal['status'] != 'succeeded': _fail()
            state = 'completed'
        elif request is not None:
            state = 'failed_or_unknown' if terminal is not None and terminal['status'] == 'failed_or_unknown' else 'request_succeeded_no_completion' if terminal else 'request_terminal_unavailable'
        elif observed['transport'] is not None: state = 'transport_admitted_no_request'
        elif observed['upload'] is not None: state = 'upload_claimed_no_transport'
        elif observed['read'] is not None: state = 'input_read_claimed_no_upload'
        else: state = 'unattempted'
        counts[state] = counts.get(state, 0) + 1
        projection = request['projection'] if request else None
        answer.append({'plain_sha256': item['plain_sha256'], 'gzip_sha256': item['gzip_sha256'], 'status': state,
            'request_sequence': request['sequence'] if request else None, 'terminal_status': terminal['status'] if terminal else None,
            'original_wire_sha256': projection['original_wire_sha256'] if projection else None,
            'projection_sha256': projection['projection_sha256'] if projection else None,
            'error_classification': old._errors(projection['projection']) if projection and state != 'completed' else None})
    return {'input_count': 72, 'mapping_sha256': mapping_sha, 'counts': counts, 'inputs': answer,
        'spent_request_count': spent, 'unrelated_spent_request_count': unrelated, 'request_slot_limit': REQUEST_SLOTS,
        'snapshot_census_only': True, 'unrelated_responses_read': False, 'licensed_payloads_read': False,
        'gzip_payloads_read': False, 'provider_authenticity_attested': False, 'all_uploads_completed': counts.get('completed') == 72}


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    previous = signal.getsignal(signal.SIGALRM); signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    try: yield
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def _execute(plan, sources, path, *, clock, guard):
    arguments = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc',
        'read_operation_id', 'expected_manifest_sha256', 'mode')}
    if e.canonical(plan) != e.canonical(_plan(**arguments)): _fail()
    if plan['mode'] == 'production' and path != PRIVATE_ROOT or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE)): _fail()
    started, directory, total = time.monotonic(), None, 0
    def check():
        guard(plan['git_head']); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0) or not _clock(plan['created_utc']) <= now < _clock(plan['expires_utc'])
                or time.monotonic() - started >= MAX_SECONDS or {name: _sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = _open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['read_operation_id']; _publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-compressed-upload-diagnostic-receipt-v1', 'study_id': e.STUDY_ID,
            'read_operation_id': operation, 'qc_operation_id': QC_OPERATION, 'candidate_id': ON,
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'failure': None, 'failure_metadata_name': None,
            'plan_sha256': _sha(e.canonical(plan)), 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'owner_instruction_sha256': plan['owner_instruction_sha256'], 'read_inventory': {}, 'absent_metadata': [],
            'read_bytes': 0, 'census': None, 'automatic_retry': False, 'upload_repeated': False,
            'old_receipts_renewed': False, 'licensed_payload_reads': False, 'gzip_reads': False, 'unrelated_response_reads': False,
            'outcome_reads': False, 'new_looks': 0, 'quantconnect_attempts': 0, 'canonical_admission': False, 'trading': False}
        def read(name):
            nonlocal total
            check(); report['failure_metadata_name'] = name
            raw = _read(directory, name, optional=True, maximum=min(MAX_FILE, MAX_TOTAL - total))
            if raw is None: report['absent_metadata'].append(name); return None
            total += len(raw); report['read_inventory'][name] = {'sha256': _sha(raw), 'bytes': len(raw)}
            return raw
        try:
            report['census'] = _census(plan, sources, read); check()
            report.update(status='COMPLETED', failure_metadata_name=None)
        except (Exception, KeyboardInterrupt): report['failure'] = 'refused_or_bound_hit_no_retry'
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); _publish(directory, operation + '.result.json', raw); return raw
    finally:
        if directory is not None: os.close(directory)


def run(**arguments):
    for module, name in ((e, 'extended_evidence.py'), (ops, 'extended_operations.py'), (old, 'extended_upload_diagnostic.py')):
        if Path(module.__file__) != LANE / (PREFIX + name): _fail()
    if Path(__file__) != LANE / (PREFIX + 'extended_compressed_upload_diagnostic.py'): _fail()
    head = _guard(); sources = _sources(head)
    plan = _plan(**arguments, source_hashes={name: _sha(raw) for name, raw in sources.items()}, git_head=head)
    with _deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=_now, guard=_guard)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('read-operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc', 'expected-manifest-sha256'):
        parser.add_argument('--' + name, required=True)
    try:
        raw = run(**vars(parser.parse_args(argv))); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end=''); return 1


if __name__ == '__main__': raise SystemExit(main())
