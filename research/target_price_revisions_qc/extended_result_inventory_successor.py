"""Named strict-budget successor to the immutable executed inventory helper.

Only a newly claimed own-job metadata read is permitted. It opens the fixed
role filename once, validates that descriptor against the remaining budget
before reading any body, and never reads more than that validated size. The
executed predecessor/reader and their source hashes stay unchanged. No inputs,
credentials, network, QC launches, new looks, retries or spent-claim renewal.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from . import extended_result_inventory as predecessor

reader, e = predecessor.reader, predecessor.e
LANE, PRIVATE_ROOT = predecessor.LANE, predecessor.PRIVATE_ROOT
SOURCE_RELATIVE = reader.PREFIX + 'extended_result_inventory_successor.py'
SOURCE_PATHS = (*predecessor.SOURCE_PATHS, SOURCE_RELATIVE)
PREDECESSOR_SHA256 = '110d7d8df326a0f4d679177ce26f870537e79cacda0de60b30ca2a0fa5cc4217'
MAX_FILE, MAX_TOTAL, MAX_SECONDS = predecessor.MAX_FILE, predecessor.MAX_TOTAL, predecessor.MAX_SECONDS
Refusal = predecessor.Refusal
_FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')
_ARGS = ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc',
    'read_operation_id', 'qc_operation_id', 'candidate_id', 'attempt', 'project_id', 'backtest_id',
    'action', 'collection_sequence', 'order_pages', 'mode')


def _fail(): raise Refusal('strict-budget own-job inventory refused; no automatic retry')


def _verify_imports():
    if Path(__file__) != LANE / SOURCE_RELATIVE or Path(predecessor.__file__) != LANE / predecessor.SOURCE_RELATIVE: _fail()
    predecessor._verify_imports()


def _sources(head):
    sources = predecessor._sources(head)
    reader._guard(head); directory = reader._open_directory((LANE / SOURCE_RELATIVE).parent)
    try: raw = reader._read(directory, Path(SOURCE_RELATIVE).name, private=False)
    finally: os.close(directory)
    reader._guard(head)
    recorded = subprocess.run(['git', 'show', head + ':' + SOURCE_RELATIVE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    if raw != recorded or reader._sha(sources[predecessor.SOURCE_RELATIVE]) != PREDECESSOR_SHA256: _fail()
    sources[SOURCE_RELATIVE] = raw; reader._guard(head)
    return sources


def _plan(**arguments):
    if set(arguments) != set(_ARGS): _fail()
    hashes, operation = arguments['source_hashes'], arguments['read_operation_id']
    if (type(hashes) is not dict or set(hashes) != set(SOURCE_PATHS)
            or hashes.get(predecessor.SOURCE_RELATIVE) != PREDECESSOR_SHA256
            or type(operation) is not str or re.fullmatch(r'TPR-EXT26-INVENTORY-V2-[A-Za-z0-9-]{1,50}', operation) is None): _fail()
    e._hash(hashes[SOURCE_RELATIVE])
    old_args = dict(arguments); old_args['source_hashes'] = {name: hashes[name] for name in predecessor.SOURCE_PATHS}
    plan = predecessor._plan(**old_args)
    plan.update(schema='tpr-ext26-result-inventory-successor-plan-v1', source_hashes=dict(hashes),
        predecessor_source=predecessor.SOURCE_RELATIVE, predecessor_sha256=PREDECESSOR_SHA256,
        strict_read_policy='opened-descriptor-size-before-body-and-remaining-bound-v1')
    return plan


def _validate_plan(plan):
    if e.canonical(plan) != e.canonical(_plan(**{key: plan[key] for key in _ARGS})): _fail()


def _budgeted_read(directory, name, remaining):
    """No pre-stat/open race can cause a body read beyond the reserved budget."""
    if (type(name) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,220}', name) is None
            or type(remaining) is not int or not 0 < remaining <= MAX_TOTAL): _fail()
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= min(MAX_FILE, remaining)): _fail()
        # The actual opened inode, not a preceding pathname observation, grants
        # the body size. Replaced names/changed bytes remain refusal evidence.
        named_before = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if any(getattr(before, key) != getattr(named_before, key) for key in _FIELDS): _fail()
        pieces, left = [], before.st_size
        while left:
            part = os.read(fd, min(65536, left))
            if not part or len(part) > left: _fail()
            pieces.append(part); left -= len(part)
        raw = b''.join(pieces)
        after, named_after = os.fstat(fd), os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (len(raw) != before.st_size or len(raw) > remaining
                or any(getattr(before, key) != getattr(after, key) or getattr(before, key) != getattr(named_after, key) for key in _FIELDS)): _fail()
        return raw
    finally:
        if fd is not None: os.close(fd)


def _execute(plan, sources, path, *, clock, guard):
    _validate_plan(plan)
    if (plan['mode'] == 'production' and path != PRIVATE_ROOT
            or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE))): _fail()
    start, total, directory, read_inflight = time.monotonic(), 0, None, False
    def check():
        guard(plan['git_head']); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not reader._clock(plan['created_utc']) <= current < reader._clock(plan['expires_utc'])
                or time.monotonic() - start >= MAX_SECONDS
                or {name: reader._sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = reader._open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['read_operation_id']; check()
        predecessor._FIXED_PUBLISH(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-result-inventory-successor-receipt-v1', 'study_id': e.STUDY_ID,
            'read_operation_id': operation, **{key: plan[key] for key in ('qc_operation_id', 'candidate_id', 'attempt',
                'project_id', 'backtest_id', 'action', 'collection_sequence', 'order_pages')},
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'predecessor_source': predecessor.SOURCE_RELATIVE, 'predecessor_sha256': PREDECESSOR_SHA256,
            'strict_read_policy': plan['strict_read_policy'], 'plan_sha256': reader._sha(e.canonical(plan)),
            'owner_instruction_sha256': plan['owner_instruction_sha256'], 'read_inventory': {}, 'read_bytes': 0,
            'read_attempts': 0, 'failed_read_body_bytes_unknown': False,
            'read_bytes_semantics': 'retained custody-verified bytes; unsuccessful-read body bytes may be unknown',
            'body_budget_enforced_before_read': True, 'inventory': None, 'inventory_sha256': None, 'inventory_bytes': None,
            'own_job_lineage_verified': False, 'native_collection_lineage_verified': False,
            'accounting_metrics_computed': False, 'original_strategy_intent_verified': False, 'private_journal_replay_verified': False,
            'provider_authenticity_attested': False, 'signal_input_reads': 0, 'provider_input_reads': 0,
            'network': False, 'credentials': False, 'object_export': False, 'automatic_retry': False,
            'new_looks': 0, 'quantconnect_attempts': 0, 'old_receipts_renewed': False, 'canonical_admission': False, 'trading': False}
        try:
            data = {}
            for role, name in plan['files'].items():
                check(); report['read_attempts'] += 1; read_inflight = True
                raw = _budgeted_read(directory, name, MAX_TOTAL - total); total += len(raw); read_inflight = False
                data[role] = raw; report['read_inventory'][role] = {'sha256': reader._sha(raw), 'bytes': len(raw)}
            check(); manifest, _, terminal, _ = predecessor._FIXED_BINDING(plan, data)
            if plan['action'] == 'metrics':
                if terminal not in {'Completed', 'Completed.'}: _fail()
                predecessor._native_lineage(plan, manifest, data, sources[reader.PREFIX + 'extended_calendar.json'])
                report['native_collection_lineage_verified'] = True
            check(); inventory = dict(report['read_inventory']); raw_inventory = e.canonical(inventory)
            report.update(status='COMPLETED', own_job_lineage_verified=True, inventory=inventory,
                inventory_sha256=reader._sha(raw_inventory), inventory_bytes=len(raw_inventory))
        except (Exception, KeyboardInterrupt):
            report['inventory'] = None; report['failed_read_body_bytes_unknown'] = read_inflight
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); predecessor._FIXED_PUBLISH(directory, operation + '.result.json', raw)
        return raw
    finally:
        if directory is not None: os.close(directory)


def run_inventory(**arguments):
    _verify_imports(); head = reader._guard(); sources = _sources(head)
    plan = _plan(source_hashes={name: reader._sha(raw) for name, raw in sources.items()}, git_head=head, mode='production', **arguments)
    def committed_guard(expected): reader._guard(expected); _verify_imports()
    with reader._deadline():
        raw = _execute(plan, sources, PRIVATE_ROOT, clock=lambda: datetime.now(timezone.utc), guard=committed_guard)
        if _sources(head) != sources: _fail()
        return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('read-operation-id', 'qc-operation-id', 'candidate-id', 'attempt', 'project-id', 'backtest-id',
                   'action', 'owner-instruction-sha256', 'created-utc', 'expires-utc'): parser.add_argument('--' + option, required=True)
    parser.add_argument('--collection-sequence', type=int, default=0); parser.add_argument('--order-pages', type=int, default=0)
    arguments = vars(parser.parse_args(argv))
    try:
        arguments['attempt'] = e._integer(e.JsonNumber(arguments['attempt']), 3)
        arguments['project_id'] = e._integer(e.JsonNumber(arguments['project_id']))
        if arguments['backtest_id'] == 'none': arguments['backtest_id'] = None
        raw = run_inventory(**arguments); print(raw.decode(), end='')
        return 0 if e.parse_json(raw)['status'] == 'COMPLETED' else 1
    except (Exception, KeyboardInterrupt):
        print(e.canonical({'status': 'REFUSED_OR_UNCERTAIN', 'scope_spent': None, 'automatic_retry': False}).decode(), end='')
        return 1


if __name__ == '__main__': raise SystemExit(main())
