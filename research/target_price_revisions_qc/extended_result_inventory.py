"""Fresh bounded metadata inventory for exactly one retained EXT26 own job.

The executed controller/result reader stay immutable. A durable exclusive claim
precedes every private stat/hash/body read. Only fixed result-reader roles are
opened; no directory discovery, credentials, network, data packets, providers,
Object Store export, accounting metrics, automatic retries or counter resets.
Hash inventories bind explicit bytes, not provider authenticity or canonical
strategy acceptance. OFF does not open signal/provider input resources.
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
from types import FunctionType

from . import extended_result_driver as reader

e = reader.e
LANE, PRIVATE_ROOT = reader.LANE, reader.PRIVATE_ROOT
SOURCE_RELATIVE = reader.PREFIX + 'extended_result_inventory.py'
SOURCE_PATHS = (*reader.SOURCE_PATHS, SOURCE_RELATIVE)
MAX_FILE, MAX_TOTAL, MAX_SECONDS = reader.MAX_FILE, reader.MAX_TOTAL, reader.MAX_SECONDS
_FIXED_NAMES, _FIXED_BINDING = reader._names, reader._binding
_FIXED_READ, _FIXED_PUBLISH = reader._read, reader._publish


class Refusal(ValueError):
    """Closed inventory refusal without private values."""


def _fail(): raise Refusal('own-job metadata inventory refused; no automatic retry')


def _verify_imports():
    if Path(__file__) != LANE / SOURCE_RELATIVE or Path(reader.__file__) != LANE / (reader.PREFIX + 'extended_result_driver.py'): _fail()
    reader._verify_imports()
    for observed, fixed in ((reader._names, _FIXED_NAMES), (reader._binding, _FIXED_BINDING),
                            (reader._read, _FIXED_READ), (reader._publish, _FIXED_PUBLISH)):
        if observed is not fixed or type(fixed) is not FunctionType or Path(fixed.__code__.co_filename) != Path(reader.__file__): _fail()


def _sources(head):
    result = reader._sources(head)
    reader._guard(head); directory = reader._open_directory((LANE / SOURCE_RELATIVE).parent)
    try: raw = reader._read(directory, Path(SOURCE_RELATIVE).name, private=False)
    finally: os.close(directory)
    reader._guard(head)
    committed = subprocess.run(['git', 'show', head + ':' + SOURCE_RELATIVE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    if raw != committed: _fail()
    result[SOURCE_RELATIVE] = raw; reader._guard(head)
    return result


def _plan(*, source_hashes, git_head, owner_instruction_sha256, created_utc, expires_utc,
          read_operation_id, qc_operation_id, candidate_id, attempt, project_id, backtest_id,
          action, collection_sequence=0, order_pages=0, mode='production'):
    if (type(read_operation_id) is not str or re.fullmatch(r'TPR-EXT26-INVENTORY-[A-Za-z0-9-]{1,60}', read_operation_id) is None
            or type(qc_operation_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,80}', qc_operation_id) is None
            or type(candidate_id) is not str or candidate_id not in e.CANDIDATES or type(attempt) is not int or not 1 <= attempt <= 3
            or type(project_id) is not int or action not in {'diagnostics', 'metrics'} or mode not in {'production', 'offline-fixture'}): _fail()
    e._integer(project_id); e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if backtest_id is not None: e._id(backtest_id)
    if action == 'metrics':
        if backtest_id is None or type(collection_sequence) is not int or not 1 <= collection_sequence <= 3 or type(order_pages) is not int or not 1 <= order_pages <= 506: _fail()
    elif type(collection_sequence) is not int or collection_sequence != 0 or type(order_pages) is not int or order_pages != 0: _fail()
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    created, expires = reader._clock(created_utc), reader._clock(expires_utc)
    if not 0 < (expires - created).total_seconds() <= 172800: _fail()
    return {'schema': 'tpr-ext26-result-inventory-plan-v1', 'study_id': e.STUDY_ID,
        'read_operation_id': read_operation_id, 'qc_operation_id': qc_operation_id, 'candidate_id': candidate_id,
        'attempt': attempt, 'project_id': project_id, 'backtest_id': backtest_id, 'action': action,
        'collection_sequence': collection_sequence, 'order_pages': order_pages, 'mode': mode,
        'source_hashes': dict(source_hashes), 'git_head': git_head, 'owner_instruction_sha256': owner_instruction_sha256,
        'created_utc': created.isoformat(), 'expires_utc': expires.isoformat(),
        'files': _FIXED_NAMES(candidate_id, attempt, qc_operation_id, action, backtest_id is not None, collection_sequence, order_pages),
        'lane_root': str(LANE), 'lane_branch': reader.BRANCH, 'private_root': str(PRIVATE_ROOT),
        'max_file_bytes': MAX_FILE, 'max_total_bytes': MAX_TOTAL, 'max_seconds': MAX_SECONDS,
        'credentials': False, 'network': False, 'object_export': False, 'signal_input_reads': 0,
        'provider_input_reads': 0, 'new_looks': 0, 'quantconnect_attempts': 0,
        'old_receipts_renewed': False, 'canonical_admission': False, 'trading': False}


def _validate_plan(plan):
    keys = ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'read_operation_id',
        'qc_operation_id', 'candidate_id', 'attempt', 'project_id', 'backtest_id', 'action', 'collection_sequence', 'order_pages', 'mode')
    if e.canonical(plan) != e.canonical(_plan(**{key: plan[key] for key in keys})): _fail()


def _budgeted_read(directory, name, remaining):
    before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= min(MAX_FILE, remaining)): _fail()
    raw = _FIXED_READ(directory, name, private=True)
    after = os.stat(name, dir_fd=directory, follow_symlinks=False)
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')
    if len(raw) != before.st_size or any(getattr(before, field) != getattr(after, field) for field in fields): _fail()
    return raw


def _native_lineage(plan, manifest, data, calendar):
    """Validate collected native scope, without inventing fills/fees or metrics."""
    binding = {key: plan[key] for key in ('candidate_id', 'project_id', 'backtest_id', 'attempt')}
    reader.native.normalize_nav(data['nav_series'], data['nav_envelope'], calendar,
        expected_series_sha256=reader._sha(data['nav_series']), expected_envelope_sha256=reader._sha(data['nav_envelope']), **binding)
    collection = e.parse_json(data['orders_collection'])
    e._closed(collection, {'schema', 'candidate_id', 'attempt', 'backtest_id', 'order_count', 'pages', 'strategy_accepted', 'new_looks'})
    if (collection['schema'] != 'tpr-ext26-order-collection-v1' or collection['candidate_id'] != plan['candidate_id']
            or e._integer(collection['attempt'], 3) != plan['attempt'] or collection['backtest_id'] != plan['backtest_id']
            or collection['strategy_accepted'] is not False or reader.ops._count(collection['new_looks']) != 0
            or type(collection['pages']) is not list or len(collection['pages']) != plan['order_pages']): _fail()
    total = reader.native._ordinal(collection['order_count'], 50000)
    if max(1, (total + 98) // 99) != plan['order_pages']: _fail()
    ids = set()
    for number, descriptor in enumerate(collection['pages']):
        e._closed(descriptor, {'start', 'end', 'response_projection_sha256', 'request_response_envelope_sha256', 'returned_identity_checks'})
        raw = data['orders_page_' + str(number)]
        envelope = reader.native._envelope(raw, descriptor['request_response_envelope_sha256'], 'backtests/orders/read', plan['project_id'], plan['backtest_id'])
        request = {'projectId': plan['project_id'], 'backtestId': plan['backtest_id'], 'start': number * 99, 'end': (number + 1) * 99}
        if (e.canonical(envelope['request']) != e.canonical(request)
                or e.canonical({'start': descriptor['start'], 'end': descriptor['end']}) != e.canonical({'start': request['start'], 'end': request['end']})
                or descriptor['response_projection_sha256'] != reader._sha(e.canonical(envelope['response']))
                or e.canonical(descriptor['returned_identity_checks']) != e.canonical(envelope['returned_identity_checks'])): _fail()
        response = envelope['response']; rows = response.get('orders')
        if (reader.native._ordinal(response.get('length'), 50000) != total or type(rows) is not list
                or len(rows) != min(99, max(0, total - number * 99))): _fail()
        for row in rows:
            if type(row) is not dict: _fail()
            identity = e._integer(row.get('id'))
            if identity in ids or 'algorithmId' in row and row['algorithmId'] != plan['backtest_id']: _fail()
            ids.add(identity)
    if len(ids) != total: _fail()
    reader._aggregate(plan, manifest, data, 'summary', 'EXT26_SUMMARY')
    reader._aggregate(plan, manifest, data, 'index', 'EXT26_EVIDENCE_INDEX')


def _execute(plan, sources, path, *, clock, guard):
    _validate_plan(plan)
    if (plan['mode'] == 'production' and path != PRIVATE_ROOT
            or plan['mode'] == 'offline-fixture' and (path == PRIVATE_ROOT or path.is_relative_to(LANE))): _fail()
    start, total, directory, read_inflight = time.monotonic(), 0, None, False
    def check():
        guard(plan['git_head']); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not reader._clock(plan['created_utc']) <= current < reader._clock(plan['expires_utc'])
                or time.monotonic() - start >= MAX_SECONDS or {name: reader._sha(raw) for name, raw in sources.items()} != plan['source_hashes']): _fail()
    check()
    try:
        directory = reader._open_directory(path); info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700: _fail()
        operation = plan['read_operation_id']; check()
        _FIXED_PUBLISH(directory, operation + '.claim.spent.json', e.canonical(plan))
        report = {'schema': 'tpr-ext26-result-inventory-receipt-v1', 'study_id': e.STUDY_ID, 'read_operation_id': operation,
            **{key: plan[key] for key in ('qc_operation_id', 'candidate_id', 'attempt', 'project_id', 'backtest_id', 'action', 'collection_sequence', 'order_pages')},
            'status': 'FAILED_OR_UNCERTAIN', 'scope_spent': True, 'git_head': plan['git_head'], 'source_hashes': plan['source_hashes'],
            'plan_sha256': reader._sha(e.canonical(plan)), 'owner_instruction_sha256': plan['owner_instruction_sha256'],
            'read_inventory': {}, 'read_bytes': 0, 'read_attempts': 0, 'failed_read_body_bytes_unknown': False,
            'read_bytes_semantics': 'retained custody-verified bytes; unsuccessful-read body bytes may be unknown',
            'inventory': None, 'inventory_sha256': None, 'inventory_bytes': None,
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
            check(); manifest, _, terminal, _ = _FIXED_BINDING(plan, data)
            if plan['action'] == 'metrics':
                if terminal not in {'Completed', 'Completed.'}: _fail()
                _native_lineage(plan, manifest, data, sources[reader.PREFIX + 'extended_calendar.json'])
                report['native_collection_lineage_verified'] = True
            check(); inventory = dict(report['read_inventory']); raw_inventory = e.canonical(inventory)
            report.update(status='COMPLETED', own_job_lineage_verified=True, inventory=inventory,
                inventory_sha256=reader._sha(raw_inventory), inventory_bytes=len(raw_inventory))
        except (Exception, KeyboardInterrupt):
            report['inventory'] = None
            report['failed_read_body_bytes_unknown'] = read_inflight
        report.update(read_bytes=total, ended_utc=clock().isoformat()); guard(plan['git_head'])
        raw = e.canonical(report); _FIXED_PUBLISH(directory, operation + '.result.json', raw)
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
                   'action', 'owner-instruction-sha256', 'created-utc', 'expires-utc'):
        parser.add_argument('--' + option, required=True)
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
