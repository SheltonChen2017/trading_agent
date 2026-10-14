"""Fresh metadata-only rendering of the unchanged-input compressed successor.

Exactly two compression metadata files are read after a new exclusive claim.
No input payload, source capture, outcome, credential or cloud API is opened.
The old bundle/config/input identities stay immutable; only named runtime and
storage successors plus prospective ON1/OFF2 attempt literals are rendered.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import threading
import time

from . import extended_evidence as e, extended_bundle as old, extended_compression as compression
from . import extended_compressed_store as storage

LANE, BRANCH, PRIVATE_ROOT, PREFIX = compression.LANE, compression.BRANCH, compression.PRIVATE_ROOT, compression.PREFIX
BUNDLE = compression.BUNDLE
BUNDLE_SHA256 = compression.BUNDLE_SHA256
COMPRESSION_OPERATION = 'TPR-EXT26-COMPRESS-20261010-001'
RECEIPT_NAME, MAPPING_NAME = COMPRESSION_OPERATION + '.result.json', COMPRESSION_OPERATION + '.mapping.json'
MAX_FILE, MAX_TOTAL, MAX_SECONDS = 128 * 1024, 256 * 1024, 120
ORIGINAL_SOURCES = frozenset(PREFIX + name for name in (
    'cap_observer.py', 'cap_tilt.py', 'extended_algorithm.py', 'extended_bundle.py', 'extended_calendar.json',
    'extended_construction.py', 'extended_core.py', 'extended_driver.py', 'extended_driver_successor.py',
    'extended_evidence.py', 'extended_loader.py', 'extended_metadata_driver.py', 'extended_metrics.py',
    'extended_native.py', 'extended_operations.py', 'extended_operations_successor.py', 'extended_result_driver.py',
    'extended_study_freeze.json'))
NEW_SOURCES = frozenset(PREFIX + name for name in (
    'extended_algorithm_successor.py', 'extended_runtime_successor.py', 'extended_compressed_store.py',
    'extended_compression.py', 'extended_bundle_compressed.py', 'extended_operations_compressed.py', 'extended_driver_compressed.py'))
REPOSITORY_SOURCES = ORIGINAL_SOURCES | NEW_SOURCES | {BUNDLE}
SOURCE_PATHS = tuple(sorted(REPOSITORY_SOURCES | set(compression.INITIALIZERS)))
RECEIPT_KEYS = frozenset(('schema study_id freeze_sha256 operation_id plan_sha256 git_head source_hashes owner_instruction_sha256 '
    'bundle_sha256 preparation_sha256 status scope_spent failure input_count processed_count original_bytes gzip_bytes ratio payloads '
    'original_read_bytes derived_read_bytes stored_derived_bytes mapping_name mapping_sha256 mapping_bytes encoding gzip_level gzip_mtime '
    'gzip_filename python_version zlib_compile_version zlib_runtime_version originals_retained_unchanged decompressed_bytes_exact '
    'source_reaccess outcome_reads cloud_uploads cloud_deletes quantconnect_attempts development_looks automatic_retry old_receipts_renewed '
    'canonical_admission trading ended_utc').split())
Refusal = e.EvidenceError


def _fail(): raise Refusal('compressed source bundle metadata refused; no automatic retry')
def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _count(value, maximum=2**63 - 1):
    if type(value) is not e.JsonNumber or value.fraction().denominator != 1 or not 0 <= value.fraction() <= maximum: _fail()
    return int(value.fraction())


def validate_compression(receipt_raw, mapping_raw, original_bundle_raw, *, expected_receipt_sha256,
                         expected_mapping_sha256, source_hashes, now):
    if (type(receipt_raw) is not bytes or type(mapping_raw) is not bytes or not 0 < len(receipt_raw) <= MAX_FILE
            or not 0 < len(mapping_raw) <= MAX_FILE or _sha(receipt_raw) != e._hash(expected_receipt_sha256)
            or _sha(mapping_raw) != e._hash(expected_mapping_sha256) or _sha(original_bundle_raw) != BUNDLE_SHA256): _fail()
    receipt, mapping, original = e.parse_json(receipt_raw), e.parse_json(mapping_raw), e.parse_json(original_bundle_raw)
    e._closed(receipt, RECEIPT_KEYS); storage.validate_mapping(mapping_raw)
    if (receipt['schema'] != 'tpr-ext26-compression-receipt-v1' or receipt['study_id'] != e.STUDY_ID
            or receipt['freeze_sha256'] != e.FREEZE_SHA256 or receipt['operation_id'] != COMPRESSION_OPERATION
            or receipt['bundle_sha256'] != BUNDLE_SHA256 or receipt['preparation_sha256'] != original['preparation_sha256']
            or receipt['status'] != 'COMPLETED' or receipt['scope_spent'] is not True or receipt['failure'] is not None
            or receipt['originals_retained_unchanged'] is not True or receipt['decompressed_bytes_exact'] is not True
            or receipt['encoding'] != 'gzip' or _count(receipt['gzip_level']) != 9 or _count(receipt['gzip_mtime']) != 0
            or receipt['gzip_filename'] != '' or receipt['mapping_name'] != MAPPING_NAME
            or receipt['mapping_sha256'] != expected_mapping_sha256 or _count(receipt['mapping_bytes']) != len(mapping_raw)
            or _count(receipt['input_count']) != 72 or _count(receipt['processed_count']) != 72
            or receipt['payloads'] != mapping['payloads']): _fail()
    for key in ('source_reaccess', 'outcome_reads', 'automatic_retry', 'old_receipts_renewed', 'canonical_admission', 'trading'):
        if receipt[key] is not False: _fail()
    for key in ('cloud_uploads', 'cloud_deletes', 'quantconnect_attempts', 'development_looks'):
        if _count(receipt[key]) != 0: _fail()
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    if (type(receipt['source_hashes']) is not dict or set(receipt['source_hashes']) != set(compression.SOURCE_PATHS)
            or any(receipt['source_hashes'][name] != source_hashes[name] for name in compression.SOURCE_PATHS)): _fail()
    for name, identity in compression.INITIALIZERS.items():
        if source_hashes[name] != identity: _fail()
    e._hash(receipt['git_head'], 40); e._hash(receipt['plan_sha256']); e._hash(receipt['owner_instruction_sha256'])
    ended = compression._clock(receipt['ended_utc'])
    if type(now) is not datetime or now.utcoffset() != timedelta(0) or not ended <= now < ended + timedelta(hours=24): _fail()
    original_rows = {item['sha256']: item for item in original['inputs']}
    if len(original_rows) != 72 or len(mapping['payloads']) != 72: _fail()
    total, zipped = 0, 0
    for row in mapping['payloads']:
        item = original_rows.get(row['plain_sha256'])
        if item is None or any(row[left] != item[right] for left, right in
            (('plain_name', 'name'), ('logical_key', 'key'), ('plain_sha256', 'sha256'), ('plain_bytes', 'bytes'))): _fail()
        total += _count(row['plain_bytes']); zipped += _count(row['gzip_bytes'])
    if (total != compression.ORIGINAL_BYTES or _count(receipt['original_bytes']) != total or _count(receipt['gzip_bytes']) != zipped
            or _count(receipt['original_read_bytes']) != 2 * total
            or _count(receipt['derived_read_bytes']) != zipped + len(mapping_raw)
            or _count(receipt['stored_derived_bytes']) != zipped + len(mapping_raw)
            or 2 * total > compression.MAX_ORIGINAL or zipped + len(mapping_raw) > compression.MAX_DERIVED
            or receipt['ratio'] != {'numerator': e.JsonNumber(str(zipped)), 'denominator': e.JsonNumber(str(total))}
            or mapping['processing_operation_id'] != COMPRESSION_OPERATION
            or mapping['processing_plan_sha256'] != receipt['plan_sha256']
            or mapping['preparation_sha256'] != receipt['preparation_sha256'] or mapping['bundle_sha256'] != BUNDLE_SHA256): _fail()
    return receipt, mapping, original


def _packets(mapping_raw):
    text = mapping_raw.decode('utf-8')
    single = 'COMPRESSION_JSON = ' + repr(text) + '\n'
    if len(single.encode()) <= 60000: return {'compressed_packet.py': single}
    parts, declarations, imports = {}, [], []
    for number, start in enumerate(range(0, len(text), 20000)):
        name = 'compressed_packet_part' + str(number)
        parts[name + '.py'] = 'PART_JSON = ' + repr(text[start:start + 20000]) + '\n'
        imports.append('from ' + name + ' import PART_JSON as P' + str(number))
        declarations.append('P' + str(number))
    parts['compressed_packet.py'] = '\n'.join(imports) + '\nCOMPRESSION_JSON = ' + ' + '.join(declarations) + '\n'
    return parts


def render(original_bundle_raw, receipt_raw, mapping_raw, *, expected_receipt_sha256, expected_mapping_sha256,
           source_hashes, templates, now):
    _, _, original = validate_compression(receipt_raw, mapping_raw, original_bundle_raw,
        expected_receipt_sha256=expected_receipt_sha256, expected_mapping_sha256=expected_mapping_sha256,
        source_hashes=source_hashes, now=now)
    expected = {PREFIX + name for name in ('extended_algorithm_successor.py', 'extended_runtime_successor.py', 'extended_compressed_store.py')}
    if type(templates) is not dict or set(templates) != expected: _fail()
    for name, raw in templates.items():
        if type(raw) is not bytes or _sha(raw) != source_hashes[name]: _fail()
    output = deepcopy(original)
    cases = []
    for row in original['candidates']:
        candidate = row['candidate_id']; arm = e.CANDIDATES[candidate]
        main = templates[PREFIX + 'extended_algorithm_successor.py'].decode()
        main = old._replace(main, '__EXTENDED_CONFIG_SHA256__', _sha(row['config_raw'].encode()))
        attempt = 1 if arm == 'tpr_on' else 2
        main = old._replace(main, '__ATTEMPT_NUMBER__', str(attempt))
        files = dict(row['files']); files['main.py'] = main
        files['extended_runtime_successor.py'] = templates[PREFIX + 'extended_runtime_successor.py'].decode()
        files['extended_compressed_store.py'] = templates[PREFIX + 'extended_compressed_store.py'].decode()
        if arm == 'tpr_on': files.update(_packets(mapping_raw))
        elif any(name.startswith(('signal_packet', 'compressed_packet')) for name in files): _fail()
        for text in files.values(): old._source(text)
        if (old._literal(main, 'EXPECTED_ATTEMPT') != attempt
                or old._literal(main, 'EXPECTED_CONFIG_SHA256') != _sha(row['config_raw'].encode())
                or files['extended_config.py'] != row['files']['extended_config.py']): _fail()
        cases.append({**row, 'planned_attempt': attempt, 'files': files})
    if len(cases) != 2 or {row['candidate_id'] for row in cases} != set(e.CANDIDATES): _fail()
    output['candidates'], output['repository_sources'] = cases, sorted(REPOSITORY_SOURCES)
    if len(output['repository_sources']) > 31 or output['inputs'] != original['inputs'] or output['preparation_sha256'] != original['preparation_sha256']: _fail()
    return output


def _sources(head):
    sources = {}
    for name in SOURCE_PATHS:
        compression._guard(head); directory = compression._open_directory((LANE / name).parent)
        try: raw = compression._read(directory, Path(name).name, private=False, maximum=e.MAX_BYTES)
        finally: os.close(directory)
        committed = subprocess.run(['git', 'show', head + ':' + name], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != committed: _fail()
        sources[name] = raw
    if any(_sha(sources[name]) != identity for name, identity in {**compression.INITIALIZERS, BUNDLE: BUNDLE_SHA256}.items()): _fail()
    compression._guard(head); return sources


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc, read_operation_id,
          expected_receipt_sha256, expected_mapping_sha256, mode='production'):
    if (type(read_operation_id) is not str or re.fullmatch(r'TPR-EXT26-COMPRESSED-BUNDLE-[A-Za-z0-9-]{1,48}', read_operation_id) is None
            or mode not in {'production', 'offline-fixture'} or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)): _fail()
    for value in (owner_instruction_sha256, expected_receipt_sha256, expected_mapping_sha256): e._hash(value)
    e._hash(git_head, 40)
    for value in source_hashes.values(): e._hash(value)
    created, expires = compression._clock(created_utc), compression._clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 86400: _fail()
    return {'schema': 'tpr-ext26-compressed-bundle-plan-v1', 'study_id': e.STUDY_ID, 'read_operation_id': read_operation_id,
        'compression_operation_id': COMPRESSION_OPERATION, 'git_head': git_head, 'source_hashes': source_hashes,
        'owner_instruction_sha256': owner_instruction_sha256, 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'expected_receipt_sha256': expected_receipt_sha256, 'expected_mapping_sha256': expected_mapping_sha256,
        'files': [RECEIPT_NAME, MAPPING_NAME], 'bundle_sha256': BUNDLE_SHA256, 'max_file_bytes': MAX_FILE,
        'max_total_bytes': MAX_TOTAL, 'max_seconds': MAX_SECONDS, 'mode': mode, 'private_root': str(PRIVATE_ROOT),
        'payload_reads': False, 'outcome_reads': False, 'credentials': False, 'network': False,
        'quantconnect_attempts': 0, 'development_looks': 0, 'automatic_retry': False, 'canonical_admission': False}


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    try: yield
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def _execute(plan, sources, path, *, clock, guard):
    arguments = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc',
        'read_operation_id', 'expected_receipt_sha256', 'expected_mapping_sha256', 'mode')}
    if e.canonical(plan) != e.canonical(_plan(**arguments)): _fail()
    if plan['mode'] == 'production' and path != PRIVATE_ROOT or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE)): _fail()
    started, directory, total = time.monotonic(), None, 0
    def check():
        guard(plan['git_head']); now = clock()
        if (not compression._clock(plan['created_utc']) <= now < compression._clock(plan['expires_utc'])
                or time.monotonic() - started >= MAX_SECONDS or {name: _sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = compression._open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['read_operation_id']; check()
        compression._publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-compressed-bundle-receipt-v1', 'read_operation_id': operation,
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'plan_sha256': _sha(e.canonical(plan)),
            'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'], 'bundle': None, 'bundle_sha256': None,
            'read_inventory': {}, 'read_bytes': 0, 'payload_reads': False, 'outcome_reads': False,
            'quantconnect_attempts': 0, 'development_looks': 0, 'automatic_retry': False, 'canonical_admission': False}
        try:
            data = {}
            for name, expected in ((RECEIPT_NAME, plan['expected_receipt_sha256']), (MAPPING_NAME, plan['expected_mapping_sha256'])):
                check(); raw = compression._read(directory, name, private=True, maximum=min(MAX_FILE, MAX_TOTAL - total))
                total += len(raw); report['read_inventory'][name] = {'sha256': _sha(raw), 'bytes': len(raw)}
                if _sha(raw) != expected: _fail()
                data[name] = raw
            check(); templates = {name: sources[name] for name in (PREFIX + 'extended_algorithm_successor.py', PREFIX + 'extended_runtime_successor.py', PREFIX + 'extended_compressed_store.py')}
            bundle = render(sources[BUNDLE], data[RECEIPT_NAME], data[MAPPING_NAME], expected_receipt_sha256=plan['expected_receipt_sha256'],
                expected_mapping_sha256=plan['expected_mapping_sha256'], source_hashes=plan['source_hashes'], templates=templates, now=clock())
            report.update(status='COMPLETED', bundle=bundle, bundle_sha256=_sha(e.canonical(bundle)))
        except (Exception, KeyboardInterrupt): report['bundle'] = None
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); compression._publish(directory, operation + '.result.json', raw); return raw
    finally:
        if directory is not None: os.close(directory)


def run(**arguments):
    if Path(__file__) != LANE / (PREFIX + 'extended_bundle_compressed.py'): _fail()
    for module, name in ((e, 'extended_evidence.py'), (old, 'extended_bundle.py'),
                         (compression, 'extended_compression.py'), (storage, 'extended_compressed_store.py')):
        if Path(module.__file__) != LANE / (PREFIX + name): _fail()
    head = compression._guard(); sources = _sources(head)
    plan = _plan(source_hashes={name: _sha(raw) for name, raw in sources.items()}, git_head=head, mode='production', **arguments)
    with _deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=compression._now, guard=compression._guard)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('read-operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc', 'expected-receipt-sha256', 'expected-mapping-sha256'):
        parser.add_argument('--' + name, required=True)
    args = vars(parser.parse_args(argv))
    try:
        raw = run(**args); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end=''); return 1


if __name__ == '__main__': raise SystemExit(main())
