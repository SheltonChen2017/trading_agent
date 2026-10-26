"""One-shot metadata-only preparation of the public EXT26 source bundle.

Production reads exactly two pinned metadata files after an exclusive spent
claim. It never opens payloads, captures, outcomes, credentials, QC or operator
state. The imported pure renderer receives explicit committed public source
bytes. --emit-bundle returns its exact canonical public bundle string; this
driver writes no tracked file. POSIX cooperative custody is not hostile-parent,
Windows, provider-authenticity, PIT, rights or canonical-strategy acceptance.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import signal
import stat
import subprocess
import threading
from types import FunctionType

from . import extended_bundle as bundle, extended_evidence as e

LANE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
PRIVATE_ROOT = LANE / 'artifacts/target_price_extended' / e.STUDY_ID / 'inputs'
OPERATION_ID = 'TPR-EXT26-METADATA-BUNDLE-20261010-001'
SOURCE_RELATIVE = bundle.PREFIX + 'extended_metadata_driver.py'
PREPARATION_SHA256 = '08e1d006b9ffef3554873722d5c40ebf739ff7e6dd2c372e78069ddf6cf2808f'
MANIFEST_SHA256 = 'a9cbf9ad3ec485a11a2bf5c699326b4ca792579c43efb0e5b3a388a24ab36838'
METADATA_FILES = {'preparation.json': (PREPARATION_SHA256, 262144), MANIFEST_SHA256 + '.json': (MANIFEST_SHA256, 128 * 1024)}
BUNDLE_SOURCES = tuple(sorted(bundle.REQUIRED_SOURCES | {SOURCE_RELATIVE,
    bundle.PREFIX + 'extended_native.py', bundle.PREFIX + 'extended_metrics.py'}))
SOURCE_PATHS = BUNDLE_SOURCES + ('research/__init__.py', bundle.PREFIX + '__init__.py')
MAX_ELAPSED_SECONDS = 120
RENDERED_NAME = OPERATION_ID + '.source-bundle.json'
_FIXED_RENDER, _FIXED_CANONICAL = bundle.render_bundle, e.canonical


class Refusal(ValueError):
    """Closed refusal, never private body or exception text."""


def _fail(): raise Refusal('extended metadata processing refused; no automatic retry')


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _now(): return datetime.now(timezone.utc)


def _clock(value):
    parsed = bundle._clock(value)
    if parsed.utcoffset() != timedelta(0): _fail()
    return parsed


def _verify_imports():
    modules = ((bundle, bundle.PREFIX + 'extended_bundle.py'), (e, bundle.PREFIX + 'extended_evidence.py'))
    if Path(__file__) != LANE / SOURCE_RELATIVE or any(Path(module.__file__) != LANE / relative for module, relative in modules): _fail()
    for function, relative in ((_FIXED_RENDER, bundle.PREFIX + 'extended_bundle.py'), (_FIXED_CANONICAL, bundle.PREFIX + 'extended_evidence.py')):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE / relative: _fail()
    if bundle.render_bundle is not _FIXED_RENDER or e.canonical is not _FIXED_CANONICAL: _fail()


def _guard(expected_head=None):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    commands = (['git', 'rev-parse', '--show-toplevel'], ['git', 'branch', '--show-current'],
        ['git', 'rev-parse', 'HEAD'], ['git', 'status', '--short'])
    try:
        observed = [subprocess.run(command, cwd=LANE, capture_output=True, timeout=5, check=True).stdout.decode().strip() for command in commands]
    except (OSError, UnicodeError, subprocess.SubprocessError): _fail()
    if observed[:2] != [str(LANE), BRANCH]: _fail()
    head = e._hash(observed[2], 40)
    if expected_head is not None and head != expected_head: _fail()
    return head


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


def _read_file(directory, name, maximum, *, private, expected_sha=None):
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not (0 if not private else 1) <= before.st_size <= maximum
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        chunks, remaining = [], before.st_size
        while remaining:
            piece = os.read(fd, min(65536, remaining))
            if not piece: _fail()
            chunks.append(piece); remaining -= len(piece)
        raw, after = b''.join(chunks), os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')
        if any(getattr(before, key) != getattr(after, key) for key in fields) or expected_sha is not None and _sha(raw) != expected_sha: _fail()
        return raw
    finally:
        if fd is not None: os.close(fd)


def _read_public(relative):
    if relative not in SOURCE_PATHS: _fail()
    path = LANE / relative; directory = _open_directory(path.parent)
    try: return _read_file(directory, path.name, 262144, private=False)
    finally: os.close(directory)


def _bound_sources(head):
    sources = {}
    for relative in SOURCE_PATHS:
        _guard(head); raw = _read_public(relative)
        recorded = subprocess.run(['git', 'show', head + ':' + relative], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
        if raw != recorded: _fail()
        sources[relative] = raw
    _guard(head)
    return sources


def _source_identity(sources):
    if type(sources) is not dict or set(sources) != set(SOURCE_PATHS): _fail()
    if any(type(raw) is not bytes or len(raw) > 262144 for raw in sources.values()): _fail()
    if (_sha(sources[bundle.PREFIX + 'extended_calendar.json']) != bundle.CALENDAR_SHA256
            or _sha(sources[bundle.PREFIX + 'extended_study_freeze.json']) != e.FREEZE_SHA256): _fail()
    return {relative: _sha(raw) for relative, raw in sources.items()}


def _plan(sources, *, head, owner_instruction_sha256, created_utc, expires_utc, mode):
    created, expires = _clock(created_utc), _clock(expires_utc)
    if mode not in {'production', 'offline-fixture'} or not 0 < (expires - created).total_seconds() <= 172800: _fail()
    return {'schema': 'tpr-ext26-metadata-plan-v1', 'operation_id': OPERATION_ID, 'study_id': e.STUDY_ID,
        'mode': mode, 'git_head': e._hash(head, 40), 'source_hashes': _source_identity(sources),
        'owner_instruction_sha256': e._hash(owner_instruction_sha256), 'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'preparation_sha256': PREPARATION_SHA256, 'manifest_sha256': MANIFEST_SHA256,
        'metadata_files': sorted(METADATA_FILES), 'metadata_reads_max': 2, 'private_payload_reads': 0,
        'metadata_only_output': RENDERED_NAME, 'metadata_only_output_max_bytes': 2 * 1024 * 1024,
        'recovery_read_authority': 'separate-fresh-named-metadata-only-scope-required',
        'max_elapsed_seconds': MAX_ELAPSED_SECONDS, 'lane_root': str(LANE), 'lane_branch': BRANCH,
        'private_root': str(PRIVATE_ROOT), 'outcomes': False, 'credentials': False, 'network': False,
        'quantconnect': False, 'canonical_admission': False, 'trading': False, 'old_receipts_renewed': False}


def _open_inputs(path, mode):
    if mode == 'production' and path != PRIVATE_ROOT or mode == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE)): _fail()
    fd = _open_directory(path)
    metadata = os.fstat(fd)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        os.close(fd); _fail()
    return fd


def _publish(directory, name, raw):
    fd = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        remaining = memoryview(raw)
        while remaining:
            count = os.write(fd, remaining)
            if not count: _fail()
            remaining = remaining[count:]
        os.fsync(fd); os.fsync(directory)
    finally:
        if fd is not None: os.close(fd)


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0): _fail()
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_): _fail()
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, MAX_ELAPSED_SECONDS)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


@dataclass(frozen=True)
class MetadataResult:
    receipt: bytes
    source_bundle: bytes | None


def _execute(plan, sources, path, *, clock, guard):
    reads, directory = 0, None
    def check():
        guard(plan['git_head'])
        current = clock()
        if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0) or not _clock(plan['created_utc']) <= current < _clock(plan['expires_utc']): _fail()
        if _source_identity(sources) != plan['source_hashes']: _fail()
    check()
    try:
        directory = _open_inputs(path, plan['mode'])
        check()
        # O_EXCL durable claim is irreversible, even if a later read fails.
        _publish(directory, OPERATION_ID + '.metadata-claim.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-metadata-result-v1', 'operation_id': OPERATION_ID, 'study_id': e.STUDY_ID,
            'status': 'FAILED', 'scope_spent': True, 'git_head': plan['git_head'], 'plan_sha256': _sha(e.canonical(plan)),
            'source_hashes': plan['source_hashes'], 'owner_instruction_sha256': plan['owner_instruction_sha256'],
            'preparation_sha256': PREPARATION_SHA256, 'manifest_sha256': MANIFEST_SHA256, 'metadata_reads': 0,
            'private_payload_reads': 0, 'source_bundle_sha256': None, 'source_bundle_bytes': None,
            'source_bundle_path': None,
            'payload_count': None, 'payload_bytes': None, 'cloud_source_counts': None,
            'outcome_reads': 0, 'development_looks': 0, 'quantconnect_attempts': 0,
            'point_in_time_data': False, 'rights_verified': False, 'canonical_admission': False, 'trading': False,
            'automatic_retry': False, 'old_receipts_renewed': False, 'ended_utc': None}
        rendered = None
        try:
            metadata = {}
            for name, (identity, maximum) in METADATA_FILES.items():
                # Counts attempted bounded file accesses, including refusals.
                check(); reads += 1
                metadata[name] = _read_file(directory, name, maximum, private=True, expected_sha=identity)
            receipt, manifest = metadata['preparation.json'], metadata[MANIFEST_SHA256 + '.json']
            parsed = e.parse_json(receipt)
            inventory = [{'name': row['sha256'] + '.json', 'sha256': row['sha256'], 'bytes': row['bytes']} for row in parsed['payloads']]
            inventory.append({'name': MANIFEST_SHA256 + '.json', 'sha256': MANIFEST_SHA256, 'bytes': len(manifest)})
            check()
            output = _FIXED_RENDER(sources[bundle.PREFIX + 'extended_calendar.json'], receipt, manifest,
                expected_preparation_sha256=PREPARATION_SHA256, expected_manifest_sha256=MANIFEST_SHA256,
                input_inventory=inventory, templates={bundle.PREFIX + name: sources[bundle.PREFIX + name] for name in bundle.TEMPLATE_NAMES},
                repository_source_hashes={relative: plan['source_hashes'][relative] for relative in BUNDLE_SOURCES})
            # canonical() already supplies one LF for apply_patch publication.
            # Never append a second or alter embedded source/config framing.
            rendered = e.canonical(output)
            if not 0 < len(rendered) <= 2 * 1024 * 1024: _fail()
            check()
            _publish(directory, RENDERED_NAME, rendered)
            check()
            report.update(status='COMPLETED', source_bundle_sha256=_sha(rendered), source_bundle_bytes=len(rendered),
                source_bundle_path=str(path / RENDERED_NAME),
                payload_count=len(output['inputs']), payload_bytes=sum(row['bytes'] for row in output['inputs']),
                cloud_source_counts={row['candidate_id']: len(row['files']) for row in output['candidates']})
        except (Exception, KeyboardInterrupt):
            rendered = None
        report.update(metadata_reads=reads, ended_utc=clock().isoformat())
        guard(plan['git_head'])
        _publish(directory, OPERATION_ID + '.metadata-result.json', e.canonical(report))
        return MetadataResult(e.canonical(report), rendered)
    finally:
        if directory is not None: os.close(directory)


def run_metadata(*, owner_instruction_sha256, created_utc, expires_utc):
    _verify_imports(); head = _guard(); sources = _bound_sources(head)
    plan = _plan(sources, head=head, owner_instruction_sha256=owner_instruction_sha256, created_utc=created_utc, expires_utc=expires_utc, mode='production')
    with _deadline(): return _execute(plan, sources, PRIVATE_ROOT, clock=_now, guard=_guard)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('owner-instruction-sha256', 'created-utc', 'expires-utc'): parser.add_argument('--' + option, required=True)
    parser.add_argument('--emit-bundle', action='store_true', help='Return exact public source-bundle string; no tracked writes')
    args = vars(parser.parse_args(argv)); emit = args.pop('emit_bundle')
    try:
        result = run_metadata(**args); report = e.parse_json(result.receipt)
        output = {'receipt': report}
        if emit and result.source_bundle is not None: output['source_bundle_raw'] = result.source_bundle.decode()
        print(e.canonical(output).decode(), end='')
        return 0 if report['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'receipt': {'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}}).decode(), end='')
        return 1


if __name__ == '__main__': raise SystemExit(main())
