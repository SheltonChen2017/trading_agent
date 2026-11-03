"""Local-only five-arm export with a durable claim before its registry read.

Run from the designated lane root after these source bytes are committed:
  python -m research.target_price_revisions_qc.comparison_20261103_prepare \
      TPR-OFFLINE-20261103-PREP-001

No QC/Safari transport, environment/credential reader, upload, native compile
or run exists here. Both services remain deferred until further owner notice.
Exported configurations are previews, never attempt reservations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from . import comparison_20261103_preflight as preflight

ROOT = Path(__file__).resolve().parents[2]
MODULE = 'research/target_price_revisions_qc/comparison_20261103_prepare.py'
RECORD = 'docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md'
REGISTRY = ('artifacts/target_price_qc_recovery_20261028/'
            'TPR-CMP28-R107-PROJECT-BINDINGS-001.json')
DESTINATION = 'artifacts/target_price_offline_20261103'
BRANCH = 'codex/strategy-target-price-revisions'
OWNER_INSTRUCTION = 'do not access qc/safari until further notice. continue to build'
OWNER_SHA256 = hashlib.sha256(OWNER_INSTRUCTION.encode('utf-8')).hexdigest()
MAX_LIFETIME_SECONDS = 180


class PreparationRefusal(ValueError):
    pass


def _fail():
    raise PreparationRefusal('local offline preparation refused') from None


def _wire(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT,
        stderr=subprocess.DEVNULL, timeout=15)


def _context():
    if (Path.cwd().resolve() != ROOT or
            Path(_git('rev-parse', '--show-toplevel').decode().strip()).resolve() != ROOT or
            _git('branch', '--show-current').decode().strip() != BRANCH):
        _fail()
    head = _git('rev-parse', 'HEAD').decode().strip()
    if re.fullmatch('[0-9a-f]{40}', head) is None:
        _fail()
    # Preserve all unrelated work; refusal rather than staging or cleaning it.
    if _git('diff', '--name-only', '-z').decode().strip('\0') not in ('', RECORD):
        _fail()
    if _git('diff', '--cached', '--name-only', '-z'):
        _fail()
    return head


def _root_fd():
    fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        actual, named = os.fstat(fd), os.stat(ROOT, follow_symlinks=False)
        if (Path.cwd().resolve() != ROOT or
                (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino)):
            _fail()
    except BaseException:
        os.close(fd)
        raise
    return fd


def _parent_fd(path):
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        _fail()
    if not relative.parts or any(part in ('', '.', '..') for part in relative.parts):
        _fail()
    fd = _root_fd()
    try:
        for index, part in enumerate(relative.parts[:-1]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            status = os.fstat(fd)
            if status.st_uid != os.getuid():
                _fail()
            if relative.parts[0] == 'artifacts' and index >= 1 and status.st_mode & 0o077:
                _fail()
    except BaseException:
        os.close(fd)
        raise
    return fd, relative.name


def _regular_bytes(path, maximum):
    parent, name = _parent_fd(path)
    try:
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            _fail()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail()
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            or len(raw) != before.st_size):
        _fail()
    return raw


def _directory(path, *, exclusive=False):
    parent, name = _parent_fd(path)
    try:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            if exclusive:
                raise
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            status = os.fstat(fd)
            if status.st_uid != os.getuid():
                _fail()
            if path.relative_to(ROOT).parts[0] == 'artifacts' and len(path.relative_to(ROOT).parts) > 1:
                if status.st_mode & 0o077:
                    _fail()
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def _retain(path, raw):
    parent, name = _parent_fd(path)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    return {'name': path.name, 'bytes': len(raw), 'sha256': _sha(raw)}


def _note(message):
    parent, name = _parent_fd(ROOT / RECORD)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, 'a', encoding='utf-8') as stream:
        stream.write('\n' + message.rstrip() + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _export_packets(destination, packets, manifest):
    if type(packets) is not dict or set(packets) != set(preflight.ARMS):
        _fail()
    _directory(destination, exclusive=True)
    inventory = {}
    for arm, files in sorted(packets.items()):
        if type(files) is not dict or not 1 <= len(files) <= 25:
            _fail()
        target = destination / arm
        _directory(target, exclusive=True)
        inventory[arm] = {}
        for name, raw in sorted(files.items()):
            if (type(name) is not str or re.fullmatch('[A-Za-z][A-Za-z0-9_]*\\.py', name) is None
                    or type(raw) is not bytes or not 0 < len(raw) <= 60000):
                _fail()
            inventory[arm][name] = _retain(target / name, raw)
    _retain(destination / 'manifest.json', manifest)
    return inventory


def prepare_workspace(operation_id):
    """Consume one fresh local scope; retain partial failures, never retry it."""
    if (type(operation_id) is not str or
            re.fullmatch('TPR-OFFLINE-20261103-[A-Z0-9-]{1,48}', operation_id) is None):
        _fail()
    head = _context()
    paths = preflight.RECOVERY_REQUIRED_SOURCES | {MODULE, preflight.MODULE}
    sources = {}
    for name in sorted(paths):
        raw = _regular_bytes(ROOT / name, 131072)
        if _git('show', head + ':' + name) != raw:
            _fail()
        sources[name] = raw
    history_raw = _git('show', head + ':' + RECORD)
    if not 0 < len(history_raw) <= 8 * 1024 * 1024:
        _fail()
    history_sha = _sha(history_raw)
    artifacts = ROOT / 'artifacts'
    _directory(artifacts)
    base = ROOT / DESTINATION
    _directory(base)
    operation = base / operation_id
    _directory(operation, exclusive=True)
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(seconds=MAX_LIFETIME_SECONDS)
    claim = {
        'schema': 'tpr-offline-preparation-claim-v1', 'operation_id': operation_id,
        'worktree': str(ROOT), 'branch': BRANCH, 'git_head': head,
        'created_utc': now.isoformat(), 'expires_utc': deadline.isoformat(),
        'latest_owner_instruction_sha256': OWNER_SHA256,
        'owner_authority': 'LOCAL_PRE_BACKTEST_ONLY_NO_QC_OR_SAFARI',
        'source_hashes': {name: _sha(raw) for name, raw in sorted(sources.items())},
        'private_inputs': [{'path': REGISTRY, 'bytes': preflight.REGISTRY_BYTES,
            'sha256': preflight.REGISTRY_SHA256}],
        'private_reads_max': 1, 'private_bytes_max': preflight.REGISTRY_BYTES,
        'processing': ['frozen_baseline', 'separate_recovery_candidate'],
        'prior_history_record_sha256': history_sha,
        'history_counts_consolidated': False,
        'reserved_attempt': None, 'financial_outcome_look': None,
        'qc_requests_authorized': 0, 'safari_requests_authorized': 0,
        'financial_runs_authorized': 0,
        'signal_packet_open_authorized': False,
    }
    claim_descriptor = _retain(operation / 'claim.json', _wire(claim))
    _note('Fresh offline build claim ' + operation_id + '; HEAD' + head +
        '; ownerLOCAL_PRE_BACKTEST_ONLY_NO_QC_OR_SAFARI; claimSHA' + claim_descriptor['sha256'] +
        ' fsynced BEFORE the one3573B registered-project read. No signal packet, '
        'credentials, provider, QC/Safari, native compile/job or financial run is authorized.')
    status, exports = 'refused', {}
    try:
        if _context() != head or datetime.now(timezone.utc) >= deadline:
            _fail()
        registry = _regular_bytes(ROOT / REGISTRY, preflight.REGISTRY_BYTES)
        if len(registry) != preflight.REGISTRY_BYTES or _sha(registry) != preflight.REGISTRY_SHA256:
            _fail()
        requests = {arm: {'operation_id': 'TPR-CMP28-' +
            ('OFF-' if arm == 'cap_off' else '') + operation_id + '-' + arm.upper().replace('_', '-'),
            'attempt': 1, 'prior_attempts_looks_sha256': history_sha} for arm in preflight.ARMS}
        for label, builder, required in (
                ('frozen', preflight.prepare_offline, preflight.REQUIRED_SOURCES),
                ('recovery_candidate', preflight.prepare_recovery_candidate,
                    preflight.RECOVERY_REQUIRED_SOURCES)):
            if _context() != head or datetime.now(timezone.utc) >= deadline:
                _fail()
            packets, manifest = builder(public_sources={name: sources[name] for name in required},
                project_bindings_raw=registry, requests=requests, git_head=head,
                owner_instruction_sha256=OWNER_SHA256)
            exports[label] = _export_packets(operation / label, packets, manifest)
        if _context() != head or datetime.now(timezone.utc) >= deadline:
            _fail()
        status = 'prepared_offline'
    finally:
        receipt = {'schema': 'tpr-offline-preparation-receipt-v1', 'operation_id': operation_id,
            'status': status, 'git_head': head, 'claim_sha256': claim_descriptor['sha256'],
            'exports': exports, 'source_builder_epochs_separate': True,
            'proposal_attempts_are_reserved': False, 'fresh_native_attempt_assignment_required': True,
            'all_qc_contacts': 0, 'all_safari_contacts': 0,
            'native_compiles': 0, 'backtests': 0,
            'source_inputs_admitted': False, 'backtesting_ready': False,
            'financial_acceptance': False, 'actual_native_results': None,
            'current_head_and_sources_must_be_refreshed_before_native_work': True}
        descriptor = _retain(operation / 'receipt.json', _wire(receipt))
        _note('Offline build ' + operation_id + ' status' + status +
            '; receiptSHA' + descriptor['sha256'] + '; QC0/Safari0/nativeCompiles0/backtests0; '
            'preview metadata is not an attempt reservation or financial/native acceptance.')
    return {'status': status, 'operation_id': operation_id, 'directory': str(operation),
        'receipt': descriptor, 'qc_contacts': 0, 'safari_contacts': 0,
        'backtests': 0, 'backtesting_ready': False}


class _BodyFreeParser(argparse.ArgumentParser):
    def error(self, message):
        _fail()


def main(argv=None):
    parser = _BodyFreeParser(description='Local-only five-arm source export; no QC/Safari access.')
    parser.add_argument('operation_id')
    try:
        args = parser.parse_args(argv)
        result = prepare_workspace(args.operation_id)
    except (Exception, KeyboardInterrupt):
        print(json.dumps({'status': 'refused', 'automatic_retry': False,
            'qc_contacts': 0, 'safari_contacts': 0,
            'backtests': 0, 'backtesting_ready': False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
