"""Fresh single-use lossless preparation transport, without source reaccess.

The exact 72 already prepared inputs remain untouched. A new processing claim
precedes every private input read; all original and compressed bytes are mutually
hash/size/roundtrip checked. Only closed hash/key/count metadata is returned.
No provider, credential, QC, cleanup, upload, outcome or automatic retry exists.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import threading
import time
import zlib

from . import extended_evidence as e, extended_compressed_store as storage

LANE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
PRIVATE_ROOT = LANE / 'artifacts/target_price_extended' / e.STUDY_ID / 'inputs'
PREFIX = 'research/target_price_revisions_qc/'
BUNDLE = PREFIX + 'extended_source_bundle_successor.json'
BUNDLE_SHA256 = '799e6eaa452860e1223ff9e35e8e4b5fa814161e9cd6cbb9d0bc27a6ae590f7b'
INITIALIZERS = {'research/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    PREFIX + '__init__.py': '3bc79e69bc0c775d8ef0ec154551436011cba407f37690c27ccbeb9000153c59'}
SOURCE_PATHS = tuple(INITIALIZERS) + tuple(PREFIX + name for name in (
    'extended_compression.py', 'extended_compressed_store.py', 'extended_evidence.py')) + (BUNDLE,)
MAX_FILE, MAX_ORIGINAL, MAX_DERIVED, MAX_SECONDS = 32 * 1024 * 1024, 500 * 1024 * 1024, 256 * 1024 * 1024, 900
INPUT_COUNT, ORIGINAL_BYTES = 72, 241804159
Refusal = e.EvidenceError


def _fail(): raise Refusal('fresh lossless input processing refused; no automatic retry')
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


def _name(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,220}', value) is None: _fail()
    return value


def _read(directory, name, *, private, maximum=MAX_FILE):
    _name(name); fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not (1 if private else 0) <= before.st_size <= maximum
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        pieces, remaining = [], before.st_size
        while remaining:
            raw = os.read(fd, min(65536, remaining))
            if not raw: _fail()
            pieces.append(raw); remaining -= len(raw)
        after = os.fstat(fd)
        if any(getattr(before, key) != getattr(after, key) for key in
            ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')): _fail()
        return b''.join(pieces)
    finally:
        if fd is not None: os.close(fd)


def _publish(directory, name, raw):
    _name(name); fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
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
    if any(_sha(result[name]) != identity for name, identity in {**INITIALIZERS, BUNDLE: BUNDLE_SHA256}.items()): _fail()
    _guard(head); return result


def _inventory(bundle_raw):
    if _sha(bundle_raw) != BUNDLE_SHA256: _fail()
    bundle = e.parse_json(bundle_raw)
    e._closed(bundle, {'schema', 'candidates', 'inputs', 'preparation_sha256', 'repository_sources'})
    if bundle['schema'] != 'tpr-ext26-source-bundle-v1' or type(bundle['inputs']) is not list or len(bundle['inputs']) != INPUT_COUNT: _fail()
    preparation = e._hash(bundle['preparation_sha256'])
    prefix = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + preparation + '/'
    rows, seen, total = [], set(), 0
    for item in bundle['inputs']:
        e._closed(item, {'name', 'sha256', 'bytes', 'key'})
        identity = e._hash(item['sha256']); size = e._integer(item['bytes'], MAX_FILE)
        if item['name'] != identity + '.json' or item['key'] != prefix + item['name'] or identity in seen: _fail()
        seen.add(identity); total += size; rows.append({**item, 'bytes': size})
    if total != ORIGINAL_BYTES or total > MAX_ORIGINAL or rows != sorted(rows, key=lambda item: item['name']): _fail()
    return preparation, rows


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          operation_id, bundle_raw, expected_bundle_sha256, mode='production'):
    if (type(operation_id) is not str or re.fullmatch(r'TPR-EXT26-COMPRESS-[A-Za-z0-9-]{1,48}', operation_id) is None
            or mode not in {'production', 'offline-fixture'} or e._hash(expected_bundle_sha256) != BUNDLE_SHA256
            or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS)): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    for identity in source_hashes.values(): e._hash(identity)
    preparation, rows = _inventory(bundle_raw)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 86400: _fail()
    return {'schema': 'tpr-ext26-compression-plan-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'operation_id': operation_id, 'source_hashes': source_hashes, 'git_head': git_head,
        'owner_instruction_sha256': owner_instruction_sha256, 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'bundle_sha256': expected_bundle_sha256, 'preparation_sha256': preparation, 'inputs': rows,
        'input_count': INPUT_COUNT, 'original_bytes': ORIGINAL_BYTES, 'max_file_bytes': MAX_FILE,
        'max_original_read_bytes': MAX_ORIGINAL, 'max_derived_bytes': MAX_DERIVED, 'max_seconds': MAX_SECONDS,
        'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'gzip_filename': '', 'mode': mode,
        'lane_root': str(LANE), 'lane_branch': BRANCH, 'private_root': str(PRIVATE_ROOT),
        'source_reaccess': False, 'outcome_reads': False, 'network': False, 'credentials': False,
        'cloud_uploads': 0, 'cloud_deletes': 0, 'quantconnect_attempts': 0, 'development_looks': 0,
        'automatic_retry': False, 'old_receipts_renewed': False, 'canonical_admission': False, 'trading': False}


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, lambda *_: _fail()); signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
    try: yield
    finally: signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def _execute(plan, sources, path, *, clock, guard):
    args = {key: plan[key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'operation_id', 'mode')}
    expected = _plan(**args, bundle_raw=sources[BUNDLE], expected_bundle_sha256=plan['bundle_sha256'])
    if e.canonical(plan) != e.canonical(expected): _fail()
    if plan['mode'] == 'production' and path != PRIVATE_ROOT or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE)): _fail()
    started, directory, original_total, derived_total = time.monotonic(), None, 0, 0
    original_read_bytes, derived_read_bytes = 0, 0
    def check():
        guard(plan['git_head']); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not _clock(plan['created_utc']) <= now < _clock(plan['expires_utc'])
                or time.monotonic() - started >= MAX_SECONDS or {name: _sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = _open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['operation_id']; check()
        _publish(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-compression-receipt-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
            'operation_id': operation, 'plan_sha256': _sha(e.canonical(plan)), 'git_head': plan['git_head'],
            'source_hashes': plan['source_hashes'], 'owner_instruction_sha256': plan['owner_instruction_sha256'],
            'bundle_sha256': plan['bundle_sha256'], 'preparation_sha256': plan['preparation_sha256'],
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'failure': None, 'input_count': INPUT_COUNT,
            'processed_count': 0, 'original_bytes': 0, 'gzip_bytes': 0, 'ratio': None, 'payloads': [],
            'original_read_bytes': 0, 'derived_read_bytes': 0, 'stored_derived_bytes': 0,
            'mapping_name': None, 'mapping_sha256': None, 'mapping_bytes': None,
            'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'gzip_filename': '',
            'python_version': platform.python_version(), 'zlib_compile_version': zlib.ZLIB_VERSION,
            'zlib_runtime_version': zlib.ZLIB_RUNTIME_VERSION, 'originals_retained_unchanged': False,
            'decompressed_bytes_exact': False, 'source_reaccess': False, 'outcome_reads': False,
            'cloud_uploads': 0, 'cloud_deletes': 0, 'quantconnect_attempts': 0, 'development_looks': 0,
            'automatic_retry': False, 'old_receipts_renewed': False, 'canonical_admission': False, 'trading': False}
        try:
            for item in plan['inputs']:
                check(); raw = _read(directory, item['name'], private=True, maximum=min(item['bytes'], MAX_ORIGINAL - original_read_bytes))
                original_read_bytes += len(raw)
                if len(raw) != item['bytes'] or _sha(raw) != item['sha256']: _fail()
                original_total += len(raw)
                encoded = storage.encode_gzip(raw, maximum=MAX_FILE)
                # Second independently invoked bounded decoder and exact byte
                # comparison, not just a hash or compressor success receipt.
                decoded = storage.decode_gzip(encoded, plain_bytes=len(raw), plain_sha256=_sha(raw),
                    gzip_bytes=len(encoded), gzip_sha256=_sha(encoded), maximum=MAX_FILE)
                if decoded != raw or derived_total + len(encoded) > MAX_DERIVED: _fail()
                compressed = _sha(encoded); name = 'gzip.' + compressed + '.json'
                check(); _publish(directory, name, encoded)
                reread = _read(directory, name, private=True, maximum=min(len(encoded), MAX_DERIVED - derived_read_bytes))
                derived_read_bytes += len(reread)
                if reread != encoded: _fail()
                # Revalidate the original after compression before claiming its
                # unchanged custody; no original is rewritten or renamed.
                revalidated = _read(directory, item['name'], private=True, maximum=min(item['bytes'], MAX_ORIGINAL - original_read_bytes))
                original_read_bytes += len(revalidated)
                if revalidated != raw: _fail()
                derived_total += len(encoded)
                report['payloads'].append({'plain_name': item['name'], 'logical_key': item['key'],
                    'plain_sha256': item['sha256'], 'plain_bytes': len(raw), 'stored_name': name,
                    'stored_key': item['key'].rsplit('/', 1)[0] + '/' + name,
                    'gzip_sha256': compressed, 'gzip_bytes': len(encoded)})
                report['processed_count'] = len(report['payloads'])
            check()
            if original_total != ORIGINAL_BYTES or len(report['payloads']) != INPUT_COUNT: _fail()
            mapping = {'schema': 'tpr-ext26-gzip-input-map-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
                'preparation_sha256': plan['preparation_sha256'], 'bundle_sha256': plan['bundle_sha256'],
                'processing_operation_id': operation, 'processing_plan_sha256': report['plan_sha256'],
                'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'payloads': report['payloads']}
            mapping_raw = e.canonical(mapping); storage.validate_mapping(mapping_raw)
            if derived_total + len(mapping_raw) > MAX_DERIVED: _fail()
            mapping_name = operation + '.mapping.json'; _publish(directory, mapping_name, mapping_raw)
            revalidated_mapping = _read(directory, mapping_name, private=True, maximum=min(len(mapping_raw), MAX_DERIVED - derived_read_bytes))
            derived_read_bytes += len(revalidated_mapping)
            if revalidated_mapping != mapping_raw: _fail()
            report.update(status='COMPLETED', mapping_name=mapping_name, mapping_sha256=_sha(mapping_raw), mapping_bytes=len(mapping_raw),
                originals_retained_unchanged=True, decompressed_bytes_exact=True,
                ratio={'numerator': derived_total, 'denominator': original_total})
        except (Exception, KeyboardInterrupt): report['failure'] = 'refused_or_bound_hit_no_retry'
        report.update(original_bytes=original_total, gzip_bytes=derived_total, original_read_bytes=original_read_bytes,
            derived_read_bytes=derived_read_bytes, stored_derived_bytes=derived_total + (report['mapping_bytes'] or 0), ended_utc=clock().isoformat())
        guard(plan['git_head']); raw = e.canonical(report); _publish(directory, operation + '.result.json', raw)
        return raw
    finally:
        if directory is not None: os.close(directory)


def run(**arguments):
    for module, name in ((e, 'extended_evidence.py'), (storage, 'extended_compressed_store.py')):
        if Path(module.__file__) != LANE / (PREFIX + name): _fail()
    if Path(__file__) != LANE / (PREFIX + 'extended_compression.py'): _fail()
    head = _guard(); sources = _sources(head)
    plan = _plan(source_hashes={name: _sha(raw) for name, raw in sources.items()}, git_head=head,
        bundle_raw=sources[BUNDLE], mode='production', **arguments)
    with _deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=_now, guard=_guard)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('operation-id', 'owner-instruction-sha256', 'created-utc', 'expires-utc', 'expected-bundle-sha256'):
        parser.add_argument('--' + name, required=True)
    args = vars(parser.parse_args(argv))
    try:
        raw = run(**args); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end='')
        return 1


if __name__ == '__main__': raise SystemExit(main())
