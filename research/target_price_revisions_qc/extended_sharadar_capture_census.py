"""Fresh local-only census of the exact preserved Sharadar repair projections.

Registration reads committed public source only. Index and page operations each
need a fresh five-minute plan and an irreversible claim before input observation.
No raw wire, ratings, prepared signals, outcomes, credentials, provider or QC
interface exists here. Counts describe retained bytes, never historical rights,
provider completeness, a historical identity series or permission to run ON.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

LANE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
STUDY = 'TPR-CAP-TILT-EXT26-20261010-v1'
CAPTURE = 'TPR-EXT26-SHARADAR-REPAIR-20261010-001'
INPUT_ROOT = LANE / 'artifacts/target_price_extended' / STUDY / 'sharadar_repair'
OUTPUT_ROOT = LANE / 'artifacts/target_price_extended' / STUDY / 'sharadar_coverage_census'
INDEX_NAME = CAPTURE + '.source-index.json'
INDEX_SHA256 = '73010167499c30eb2b12a2c1f5b8f76c8f37c94bd001bcebd017a5e9fe0d72e8'
INDEX_BYTES = 7871
FREEZE = '0d0f67a6d02915ff7357018ef51108fdeb3e334cbcccc7e2fa65bbeb1f1d6097'
SOURCE_PATHS = ('research/__init__.py', 'research/target_price_revisions_qc/__init__.py',
    'research/target_price_revisions_qc/extended_sharadar_capture_census.py')
MAX_SECONDS, MAX_TOTAL, MAX_METADATA = 300, 64 * 1024**2, 16384
_HASH = re.compile(r'[a-f0-9]{64}')
_OPERATION = re.compile(r'TPR-EXT26-SHARADAR-CENSUS-(INDEX|PAGES)-[A-Z0-9][A-Z0-9-]{0,63}')
_PLAN_KEYS = frozenset(('schema operation_id stage mode git_head source_hashes owner_instruction_sha256 '
    'created_utc expires_utc index_operation inventory_sha256 input_root output_root max_seconds max_total_bytes').split())
_INDEX_KEYS = frozenset(('schema operation_id study_id freeze_sha256 plan_sha256 git_sha source_hashes '
    'started_utc ended_utc pages census failure report original_capture_modified point_in_time_data '
    'current_vintage_identity action_history_no_lower_bound ticker_python_collation_asserted '
    'terminated_pagination_not_transaction_snapshot count_semantics').split())
_PAGE_INDEX_KEYS = frozenset(('request_index provider dataset page http_status wire_file wire_sha256 '
    'wire_bytes received_bytes projection_file projection_sha256 projection_bytes response_complete disposition fetch_utc').split())
_PAGE_KEYS = frozenset(('schema dataset rows source_rows row_refusals identical_duplicate_rows '
    'conflicting_duplicate_rows ticker_python_lexical_descents missing_optional_column '
    'current_vintage_not_point_in_time').split())
_FIELDS = {'tickers': frozenset(('ticker permaticker figi category exchange isdelisted').split()),
    'actions': frozenset(('ticker date action contraticker').split())}
_REFUSALS = frozenset(('invalid_native_cell invalid_native_ticker invalid_native_permaticker '
    'unknown_native_delisting invalid_native_figi conflicting_native_identity action_after_frozen_end '
    'invalid_native_action_date missing_native_action invalid_native_contraticker').split())
_DESCRIPTOR_KEYS = frozenset(('name dataset page sha256 bytes rows').split())
_INVENTORY_KEYS = frozenset(('schema study_id capture_operation index_sha256 index_bytes projections '
    'projection_bytes ticker_rows action_rows current_vintage_identity point_in_time_data '
    'provider_completeness_proven historical_entitlement_proven on_ready').split())
_FALSE_FLAGS = {'point_in_time_data': False, 'provider_completeness_proven': False,
    'historical_entitlement_proven': False, 'on_ready': False}


class CensusRefusal(ValueError):
    """Fixed body-free error; never retain source rows or exception text."""


def _fail():
    raise CensusRefusal('bounded local Sharadar census refused; no automatic retry')


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _canonical(body):
    try:
        return (json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                           allow_nan=False) + '\n').encode('ascii')
    except (TypeError, ValueError, OverflowError, RecursionError): _fail()


def _object(raw, maximum):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum: _fail()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: _fail()
            result[key] = value
        return result
    def refuse(_): _fail()
    try:
        body = json.loads(raw, object_pairs_hook=pairs, parse_float=refuse, parse_constant=refuse)
        if type(body) is not dict: _fail()
        return body
    except (TypeError, ValueError, UnicodeError, RecursionError): _fail()


def _closed(body, keys):
    if type(body) is not dict or set(body) != keys: _fail()


def _hash(value):
    if type(value) is not str or _HASH.fullmatch(value) is None: _fail()
    return value


def _count(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum: _fail()
    return value


def _clock(value):
    try:
        if type(value) is not str or len(value) > 40: _fail()
        result = datetime.fromisoformat(value)
        if result.utcoffset() != timedelta(0) or result.isoformat() != value: _fail()
        return result
    except (TypeError, ValueError, OverflowError): _fail()


def _operation(value, stage=None):
    if type(value) is not str or _OPERATION.fullmatch(value) is None: _fail()
    if stage is not None and ('-INDEX-' if stage == 'index' else '-PAGES-') not in value: _fail()
    return value


def index_inventory(raw, *, expected_sha256=None, expected_bytes=None):
    """Pure exact-index metadata projection. No licensed page is opened here."""
    expected_sha256 = INDEX_SHA256 if expected_sha256 is None else expected_sha256
    expected_bytes = INDEX_BYTES if expected_bytes is None else expected_bytes
    if type(raw) is not bytes or len(raw) != expected_bytes or _sha(raw) != _hash(expected_sha256): _fail()
    body = _object(raw, MAX_METADATA); _closed(body, _INDEX_KEYS)
    if (body['schema'] != 'tpr-ext26-sharadar-repair-index-v1' or body['operation_id'] != CAPTURE
            or body['study_id'] != STUDY or body['freeze_sha256'] != FREEZE or body['failure'] is not None
            or body['point_in_time_data'] is not False or body['original_capture_modified'] is not False
            or body['current_vintage_identity'] is not True or body['action_history_no_lower_bound'] is not True
            or body['ticker_python_collation_asserted'] is not False
            or body['terminated_pagination_not_transaction_snapshot'] is not True): _fail()
    _hash(body['plan_sha256'])
    if type(body['git_sha']) is not str or re.fullmatch(r'[a-f0-9]{40}', body['git_sha']) is None: _fail()
    if _clock(body['started_utc']) > _clock(body['ended_utc']): _fail()
    census = body['census']
    if type(census) is not list or len(census) != 2: _fail()
    for row, dataset, pages, rows, size in zip(census, ('tickers', 'actions'), (3, 5),
            (21007, 49716), (946301, 1456441)):
        _closed(row, frozenset(('provider dataset pages source_rows response_bytes terminated').split()))
        if (row != {'provider': 'sharadar', 'dataset': dataset, 'pages': pages,
                'source_rows': rows, 'response_bytes': size, 'terminated': True}
                or any(type(row[key]) is not int for key in ('pages', 'source_rows', 'response_bytes'))): _fail()
    report = body['report']
    if (type(report) is not dict or report.get('status') != 'COMPLETED'
            or report.get('capture_complete') is not True or report.get('scope_spent') is not True
            or report.get('source_rows') != 70723 or type(report.get('source_rows')) is not int
            or report.get('row_refusals') != 0 or report.get('conflicting_duplicate_rows') != 0
            or report.get('identical_duplicate_rows') != 48 or report.get('response_bytes') != 2402742
            or any(type(report.get(key)) is not int for key in ('row_refusals',
                'conflicting_duplicate_rows', 'identical_duplicate_rows', 'response_bytes'))): _fail()
    pages = body['pages']
    if type(pages) is not list or len(pages) != 8: _fail()
    descriptors = []
    for number, row in enumerate(pages, 1):
        _closed(row, _PAGE_INDEX_KEYS)
        dataset = 'tickers' if number <= 3 else 'actions'
        page = number - (1 if number <= 3 else 4)
        prefix = f'request.{number:04}'
        rows = (1007 if number == 3 else 9716 if number == 8 else 10000)
        if (row['request_index'] != number or type(row['request_index']) is not int
                or row['provider'] != 'sharadar' or row['dataset'] != dataset
                or row['page'] != page or type(row['page']) is not int
                or row['http_status'] != 200 or type(row['http_status']) is not int
                or row['wire_file'] != prefix + '.wire.csv'
                or row['projection_file'] != prefix + '.projection.json'
                or row['response_complete'] is not True or row['disposition'] != 'projected'): _fail()
        _hash(row['wire_sha256']); _clock(row['fetch_utc'])
        if not 0 < _count(row['wire_bytes'], 4 * 1024**2) == row['received_bytes']: _fail()
        descriptors.append({'name': row['projection_file'], 'dataset': dataset, 'page': page,
            'sha256': _hash(row['projection_sha256']), 'bytes': _count(row['projection_bytes'], MAX_TOTAL), 'rows': rows})
    inventory = {'schema': 'tpr-ext26-sharadar-census-inventory-v1', 'study_id': STUDY,
        'capture_operation': CAPTURE, 'index_sha256': expected_sha256, 'index_bytes': expected_bytes,
        'projections': descriptors, 'projection_bytes': sum(row['bytes'] for row in descriptors),
        'ticker_rows': 21007, 'action_rows': 49716, 'current_vintage_identity': True, **_FALSE_FLAGS}
    return validate_inventory(inventory, expected_index_sha256=expected_sha256, expected_index_bytes=expected_bytes)


def validate_inventory(body, *, expected_index_sha256=None, expected_index_bytes=None):
    expected_index_sha256 = INDEX_SHA256 if expected_index_sha256 is None else expected_index_sha256
    expected_index_bytes = INDEX_BYTES if expected_index_bytes is None else expected_index_bytes
    _closed(body, _INVENTORY_KEYS)
    if (body['schema'] != 'tpr-ext26-sharadar-census-inventory-v1' or body['study_id'] != STUDY
            or body['capture_operation'] != CAPTURE or body['index_sha256'] != expected_index_sha256
            or body['index_bytes'] != expected_index_bytes or body['ticker_rows'] != 21007
            or body['action_rows'] != 49716 or body['current_vintage_identity'] is not True
            or any(body[key] is not False for key in _FALSE_FLAGS)): _fail()
    _hash(body['index_sha256']); _count(body['index_bytes'], MAX_METADATA)
    if type(body['projections']) is not list or len(body['projections']) != 8: _fail()
    for number, row in enumerate(body['projections'], 1):
        _closed(row, _DESCRIPTOR_KEYS)
        if (row['name'] != f'request.{number:04}.projection.json'
                or row['dataset'] != ('tickers' if number <= 3 else 'actions')
                or row['page'] != number - (1 if number <= 3 else 4) or type(row['page']) is not int
                or row['rows'] != (1007 if number == 3 else 9716 if number == 8 else 10000)
                or type(row['rows']) is not int or not 0 < _count(row['bytes'], MAX_TOTAL)): _fail()
        _hash(row['sha256'])
    total = sum(row['bytes'] for row in body['projections'])
    if not 0 < _count(body['projection_bytes'], MAX_TOTAL) == total: _fail()
    return json.loads(_canonical(body))


def project_pages(raw_pages, inventory):
    """Hash-check ALL eight pages before counting any fields; aggregate only."""
    inventory = validate_inventory(inventory)
    if type(raw_pages) is not list or len(raw_pages) != 8: _fail()
    for raw, descriptor in zip(raw_pages, inventory['projections']):
        if (type(raw) is not bytes or len(raw) != descriptor['bytes']
                or _sha(raw) != descriptor['sha256']): _fail()
    years = {str(year): 0 for year in range(2020, 2027)}
    buckets = dict.fromkeys(('before_warmup', 'warmup', 'evaluation', 'after_frozen_end', 'before_2021_10_11',
        'early_window_before_2021_10_11', 'invalid_date', 'missing_date'), 0)
    tickers, identities = set(), set()
    totals = dict.fromkeys(('ticker_rows', 'action_rows', 'refused_rows', 'duplicate_rows',
        'conflicting_rows', 'ticker_python_lexical_descents', 'missing_ticker', 'missing_permaticker'), 0)
    earliest = latest = None
    previous_action = previous_ticker = None
    for raw, descriptor in zip(raw_pages, inventory['projections']):
        body = _object(raw, MAX_TOTAL); _closed(body, _PAGE_KEYS)
        dataset = descriptor['dataset']
        if (body['schema'] != 'tpr-ext26-sharadar-repair-page-v1' or body['dataset'] != dataset
                or type(body['rows']) is not list or len(body['rows']) != descriptor['rows']
                or _count(body['source_rows'], 10000) != len(body['rows'])
                or type(body['missing_optional_column']) is not bool
                or body['current_vintage_not_point_in_time'] is not True): _fail()
        refused = 0
        for item in body['rows']:
            _closed(item, frozenset(('source', 'refusals'))); row = item['source']; _closed(row, _FIELDS[dataset])
            if (any(value is not None and (type(value) is not str or len(value) > 8192) for value in row.values())
                    or type(item['refusals']) is not list or len(item['refusals']) > len(_REFUSALS)
                    or any(type(value) is not str or value not in _REFUSALS for value in item['refusals'])
                    or len(set(item['refusals'])) != len(item['refusals'])): _fail()
            refused += bool(item['refusals'])
            if dataset == 'tickers':
                totals['ticker_rows'] += 1
                for key, target in (('ticker', tickers), ('permaticker', identities)):
                    if row[key]: target.add(row[key])
                    else: totals['missing_' + key] += 1
                continue
            totals['action_rows'] += 1
            value = row['date']
            if value is None or value == '': buckets['missing_date'] += 1; continue
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value: raise ValueError
            except (TypeError, ValueError): buckets['invalid_date'] += 1; continue
            if previous_action is not None and value < previous_action: _fail()
            previous_action = value
            earliest = value if earliest is None else min(earliest, value)
            latest = value if latest is None else max(latest, value)
            if value[:4] in years: years[value[:4]] += 1
            if value < '2020-09-01': buckets['before_warmup'] += 1
            elif value < '2021-01-04': buckets['warmup'] += 1
            elif value <= '2026-10-09': buckets['evaluation'] += 1
            else: buckets['after_frozen_end'] += 1
            if value < '2021-10-11': buckets['before_2021_10_11'] += 1
            if '2020-09-01' <= value < '2021-10-11': buckets['early_window_before_2021_10_11'] += 1
        # The original producer's total adds cross-page descents separately
        # from each projection's intra-page counter. This is an audit count,
        # never a sorting gate or a claim about historical identity coverage.
        if dataset == 'tickers' and body['rows']:
            first = body['rows'][0]['source']['ticker']
            last = body['rows'][-1]['source']['ticker']
            if type(first) is str and type(previous_ticker) is str:
                totals['ticker_python_lexical_descents'] += int(first < previous_ticker)
            previous_ticker = last
        if _count(body['row_refusals'], 10000) != refused: _fail()
        totals['refused_rows'] += refused
        for source, target in (('identical_duplicate_rows', 'duplicate_rows'),
                ('conflicting_duplicate_rows', 'conflicting_rows'),
                ('ticker_python_lexical_descents', 'ticker_python_lexical_descents')):
            totals[target] += _count(body[source], 10000)
    if totals['ticker_rows'] != 21007 or totals['action_rows'] != 49716: _fail()
    if (totals['refused_rows'] != 0 or totals['duplicate_rows'] != 48
            or totals['conflicting_rows'] != 0 or totals['ticker_python_lexical_descents'] != 351): _fail()
    return {'schema': 'tpr-ext26-sharadar-local-census-v1', 'study_id': STUDY,
        'capture_operation': CAPTURE, 'inventory_sha256': _sha(_canonical(inventory)),
        'projection_files': 8, **totals, 'distinct_current_tickers': len(tickers),
        'distinct_current_permatickers': len(identities), 'action_year_counts': years,
        'action_date_buckets': buckets, 'earliest_retained_action_date': earliest,
        'latest_retained_action_date': latest,
        'early_actions_observed': buckets['early_window_before_2021_10_11'] > 0,
        'current_master_is_historical_identity_series': False,
        'current_subscription_proves_capture_entitlement': False,
        'full_as_published_history_proven': False, 'inputs_changed': False, **_FALSE_FLAGS,
        'qc_access': False, 'provider_access': False, 'outcome_reads': 0,
        'new_looks': 0, 'quantconnect_attempts': 0}


def _directory(path, *, create=False, private=True):
    path = Path(path)
    if not path.is_absolute() or any(part in ('.', '..') for part in path.parts): _fail()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:]:
            if create:
                try: os.mkdir(component, 0o700, dir_fd=fd)
                except FileExistsError: pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        info = os.fstat(fd)
        if private and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700): _fail()
        result, fd = fd, None
        return result
    finally:
        if fd is not None: os.close(fd)


def _read(directory, name, *, size=None, maximum=MAX_METADATA, sha256=None, check=lambda: None, private=True):
    if type(name) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,180}', name) is None: _fail()
    fd = None
    try:
        check(); fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not (1 if private else 0) <= before.st_size <= maximum
                or size is not None and before.st_size != size
                or private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600)): _fail()
        pieces, remaining = [], before.st_size
        while remaining:
            check(); piece = os.read(fd, min(65536, remaining))
            if not piece: _fail()
            pieces.append(piece); remaining -= len(piece)
        raw, after = b''.join(pieces), os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_mode', 'st_uid')
        if any(getattr(before, key) != getattr(after, key) for key in fields): _fail()
        if sha256 is not None and _sha(raw) != _hash(sha256): _fail()
        check(); return raw
    finally:
        if fd is not None: os.close(fd)


def _publish(directory, name, raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_METADATA: _fail()
    temporary = '.pending-' + uuid.uuid4().hex
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            if written <= 0: _fail()
            offset += written
        os.fsync(fd)
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        os.fsync(directory)
    finally:
        try:
            named, owned = os.stat(temporary, dir_fd=directory, follow_symlinks=False), os.fstat(fd)
            if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino):
                os.unlink(temporary, dir_fd=directory); os.fsync(directory)
        finally: os.close(fd)


def _guard(expected=None):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    try:
        def git(*args):
            return subprocess.run(['git', *args], cwd=LANE, capture_output=True,
                timeout=5, check=True).stdout.decode().strip()
        if git('rev-parse', '--show-toplevel') != str(LANE) or git('branch', '--show-current') != BRANCH: _fail()
        head = git('rev-parse', 'HEAD'); git('status', '--short')
        if re.fullmatch(r'[a-f0-9]{40}', head) is None or expected is not None and head != expected: _fail()
        return head
    except (OSError, UnicodeError, subprocess.SubprocessError): _fail()


def _sources(head):
    result = {}
    for relative in SOURCE_PATHS:
        _guard(head)
        fd = _directory((LANE / relative).parent, private=False)
        try: raw = _read(fd, Path(relative).name, maximum=131072, private=False)
        finally: os.close(fd)
        try:
            committed = subprocess.run(['git', 'show', head + ':' + relative], cwd=LANE,
                capture_output=True, timeout=5, check=True).stdout
        except (OSError, subprocess.SubprocessError): _fail()
        if raw != committed: _fail()
        result[relative] = _sha(raw)
    _guard(head); return result


def make_plan(*, operation_id, stage, git_head, source_hashes, owner_instruction_sha256,
              created_utc, expires_utc, index_operation=None, inventory_sha256=None, mode='production'):
    _operation(operation_id, stage)
    if stage not in ('index', 'pages') or mode not in ('production', 'offline-fixture'): _fail()
    if type(git_head) is not str or re.fullmatch(r'[a-f0-9]{40}', git_head) is None: _fail()
    _closed(source_hashes, frozenset(SOURCE_PATHS))
    for value in source_hashes.values(): _hash(value)
    _hash(owner_instruction_sha256)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not timedelta(0) < expires - created <= timedelta(seconds=MAX_SECONDS): _fail()
    if stage == 'index':
        if index_operation is not None or inventory_sha256 is not None: _fail()
    else: _operation(index_operation, 'index'); _hash(inventory_sha256)
    return {'schema': 'tpr-ext26-sharadar-census-plan-v1', 'operation_id': operation_id, 'stage': stage,
        'mode': mode, 'git_head': git_head, 'source_hashes': dict(source_hashes),
        'owner_instruction_sha256': owner_instruction_sha256, 'created_utc': created.isoformat(),
        'expires_utc': expires.isoformat(), 'index_operation': index_operation, 'inventory_sha256': inventory_sha256,
        'input_root': str(INPUT_ROOT), 'output_root': str(OUTPUT_ROOT),
        'max_seconds': MAX_SECONDS, 'max_total_bytes': MAX_TOTAL}


def validate_plan(plan):
    _closed(plan, _PLAN_KEYS)
    keys = ('operation_id stage git_head source_hashes owner_instruction_sha256 created_utc expires_utc '
            'index_operation inventory_sha256 mode').split()
    expected = make_plan(**{key: plan[key] for key in keys})
    if _canonical(plan) != _canonical(expected): _fail()
    return expected


def _now():
    return datetime.now(timezone.utc)


def _lane_identity(path, lane):
    """True when `path` is the lane, one of its parents, or inside it, decided by
    real paths and directory identity rather than text, so case aliases and
    firmlinks cannot slip past the boundary."""
    candidate, lane_real = Path(path), Path(os.path.realpath(lane))
    real = Path(os.path.realpath(candidate))
    if (candidate == lane or candidate in lane.parents or candidate.is_relative_to(lane)
            or real == lane_real or real in lane_real.parents or real.is_relative_to(lane_real)):
        return True
    try:
        lane_info = os.stat(lane)
    except OSError:
        return False
    current = candidate
    while True:
        try:
            info = os.stat(current)
        except OSError:
            info = None
        if info is not None and (info.st_dev, info.st_ino) == (lane_info.st_dev, lane_info.st_ino):
            return True
        if current.parent == current:
            return False
        current = current.parent


def execute(plan, *, input_root=INPUT_ROOT, output_root=OUTPUT_ROOT,
            guard=_guard, source_identity=_sources, clock=_now,
            monotonic=time.monotonic):
    """Explicit processing entrypoint; fixtures must use separate temporary roots."""
    plan = validate_plan(plan)
    if plan['mode'] == 'production' and (guard is not _guard or source_identity is not _sources
            or clock is not _now or monotonic is not time.monotonic): _fail()
    input_root, output_root = Path(input_root), Path(output_root)
    if (plan['mode'] == 'production' and (input_root != INPUT_ROOT or output_root != OUTPUT_ROOT)
            or plan['mode'] == 'offline-fixture' and (_lane_identity(input_root, LANE) or _lane_identity(output_root, LANE))): _fail()
    operation, stage = plan['operation_id'], plan['stage']
    frozen = _canonical(plan)
    start = last_tick = monotonic(); last_now = None
    def check():
        nonlocal last_tick, last_now
        guard(plan['git_head'])
        if source_identity(plan['git_head']) != plan['source_hashes']: _fail()
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or type(tick) not in (int, float) or not math.isfinite(tick)
                or not _clock(plan['created_utc']) <= now < _clock(plan['expires_utc'])
                or type(start) not in (int, float) or not math.isfinite(start)
                or not 0 <= tick - start < MAX_SECONDS or tick < last_tick
                or last_now is not None and now < last_now): _fail()
        last_tick, last_now = tick, now
    check()
    out = _directory(output_root)
    source = lock = None
    receipt = {'schema': 'tpr-ext26-sharadar-census-receipt-v1', 'operation_id': operation,
        'stage': stage, 'plan_sha256': _sha(frozen), 'status': 'FAILED_OR_UNCERTAIN',
        'claim_attempted': False, 'scope_spent': False, 'input_read_attempts': 0,
        'completed_input_reads': 0, 'completed_input_bytes': 0, 'reserved_input_bytes': 0,
        'failed_input_read_bytes_unknown': False, 'output_sha256': None, 'output_bytes': None,
        'failure_stage': 'lock', 'lock_cleanup_complete': False, 'qc_access': False,
        'provider_access': False, 'outcome_reads': 0, 'new_looks': 0, 'quantconnect_attempts': 0,
        'inputs_changed': False, **_FALSE_FLAGS}
    nonce, cancelled = uuid.uuid4().hex, False
    def read(fd, name, maximum, *, size=None, sha256=None):
        check(); receipt['input_read_attempts'] += 1
        receipt['reserved_input_bytes'] += size if size is not None else maximum
        if receipt['reserved_input_bytes'] > MAX_TOTAL + MAX_METADATA: _fail()
        receipt['failed_input_read_bytes_unknown'] = True
        raw = _read(fd, name, size=size, maximum=maximum, sha256=sha256, check=check)
        receipt['completed_input_reads'] += 1; receipt['completed_input_bytes'] += len(raw)
        receipt['failed_input_read_bytes_unknown'] = False
        return raw
    try:
        try:
            lock = os.open(operation + '.lock', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=out)
            os.fsync(lock); os.fsync(out); check()
            receipt['failure_stage'] = 'claim'
            receipt['claim_attempted'] = receipt['scope_spent'] = True
            _publish(out, operation + '.claim.spent.json', frozen)
            check(); receipt['failure_stage'] = 'read'
            if stage == 'index':
                source = _directory(input_root)
                raw = read(source, INDEX_NAME, INDEX_BYTES, size=INDEX_BYTES, sha256=INDEX_SHA256)
                result = index_inventory(raw)
            else:
                raw = read(out, plan['index_operation'] + '.inventory.json', MAX_METADATA, sha256=plan['inventory_sha256'])
                inventory = validate_inventory(_object(raw, MAX_METADATA))
                source = _directory(input_root)
                pages = [read(source, descriptor['name'], descriptor['bytes'], size=descriptor['bytes'],
                    sha256=descriptor['sha256']) for descriptor in inventory['projections']]
                check(); result = project_pages(pages, inventory)
            check(); receipt['failure_stage'] = 'publish'
            payload = _canonical(result)
            _publish(out, operation + ('.inventory.json' if stage == 'index' else '.census.json'), payload)
            receipt['output_sha256'], receipt['output_bytes'] = _sha(payload), len(payload)
            check(); receipt['status'], receipt['failure_stage'] = 'COMPLETED_DIAGNOSTIC_ONLY', 'complete'
        except KeyboardInterrupt:
            cancelled = True; receipt['status'] = 'CANCELLED'
        except Exception:
            receipt['status'] = 'FAILED_OR_UNCERTAIN'
        finally:
            if source is not None:
                try: os.close(source)
                except KeyboardInterrupt:
                    cancelled = True; receipt['status'] = 'CANCELLED'; receipt['failure_stage'] = 'cleanup'
                except Exception:
                    receipt['status'] = 'CANCELLED' if cancelled else 'FAILED_OR_UNCERTAIN'; receipt['failure_stage'] = 'cleanup'
            if lock is not None:
                try:
                    named, owned = os.stat(operation + '.lock', dir_fd=out, follow_symlinks=False), os.fstat(lock)
                    if (named.st_dev, named.st_ino) != (owned.st_dev, owned.st_ino): _fail()
                    os.unlink(operation + '.lock', dir_fd=out); os.fsync(out)
                    receipt['lock_cleanup_complete'] = True
                except KeyboardInterrupt:
                    cancelled = True; receipt['status'] = 'CANCELLED'; receipt['failure_stage'] = 'cleanup'
                except Exception:
                    receipt['status'] = 'CANCELLED' if cancelled else 'FAILED_OR_UNCERTAIN'; receipt['failure_stage'] = 'cleanup'
                finally:
                    try: os.close(lock)
                    except KeyboardInterrupt:
                        cancelled = True; receipt['status'] = 'CANCELLED'; receipt['failure_stage'] = 'cleanup'
                    except Exception:
                        receipt['status'] = 'CANCELLED' if cancelled else 'FAILED_OR_UNCERTAIN'; receipt['failure_stage'] = 'cleanup'
        _publish(out, operation + '.attempt-' + nonce + '.result.json', _canonical(receipt))
        if cancelled: raise KeyboardInterrupt('local census cancelled; preserve spent scope')
        return receipt
    finally: os.close(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('register-index', 'read-index', 'register-census', 'read-census'))
    parser.add_argument('--operation', required=True)
    parser.add_argument('--owner-instruction-sha256')
    parser.add_argument('--index-operation')
    parser.add_argument('--inventory-sha256')
    args = parser.parse_args(argv)
    try:
        stage = 'index' if args.action.endswith('index') else 'pages'
        _operation(args.operation, stage); head = _guard(); identities = _sources(head)
        if args.action.startswith('register'):
            now = datetime.now(timezone.utc)
            plan = make_plan(operation_id=args.operation, stage=stage, git_head=head,
                source_hashes=identities, owner_instruction_sha256=args.owner_instruction_sha256,
                created_utc=now.isoformat(), expires_utc=(now + timedelta(seconds=MAX_SECONDS)).isoformat(),
                index_operation=args.index_operation, inventory_sha256=args.inventory_sha256)
            fd = _directory(OUTPUT_ROOT, create=True)
            try: _publish(fd, args.operation + '.plan.json', _canonical(plan))
            finally: os.close(fd)
            result = {'status': 'REGISTERED', 'operation_id': args.operation, 'plan_sha256': _sha(_canonical(plan)),
                'expires_utc': plan['expires_utc'], 'licensed_input_reads': 0, 'qc_access': False}
        else:
            if any(value is not None for value in (args.owner_instruction_sha256, args.index_operation, args.inventory_sha256)): _fail()
            fd = _directory(OUTPUT_ROOT)
            try: plan = validate_plan(_object(_read(fd, args.operation + '.plan.json'), MAX_METADATA))
            finally: os.close(fd)
            if plan['operation_id'] != args.operation or plan['stage'] != stage or plan['mode'] != 'production': _fail()
            result = execute(plan)
        print(_canonical(result).decode(), end=''); return 0
    except KeyboardInterrupt:
        print('{"status":"CANCELLED","automatic_retry":false}'); return 130
    except Exception:
        print('{"status":"FAILED_OR_UNCERTAIN","automatic_retry":false}'); return 1


if __name__ == '__main__': raise SystemExit(main())
