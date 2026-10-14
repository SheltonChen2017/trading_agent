"""Bounded prospective private QC operations for the extended paired study.

Imports do no I/O. This new producer does not open any historical operation,
capture, project or result. All actual operations require freshly committed
source-bound access and exclusive persistent claims. Cooperative POSIX custody
is not hostile-parent/Windows canonical custody or strategy acceptance.
"""
from __future__ import annotations

import ast
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import threading
import time
from zoneinfo import ZoneInfo

from . import extended_evidence as evidence

LANE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions')
BRANCH = 'codex/strategy-target-price-revisions'
BASELINE = '5cd1a7bed6e27c121cbdf0c60d4e61a44536018a'
PRIVATE_PARENT = LANE / 'artifacts/target_price_extended'
PRIVATE_ROOT = PRIVATE_PARENT / evidence.STUDY_ID / 'operations'
INPUT_ROOT = PRIVATE_PARENT / evidence.STUDY_ID / 'inputs'
ENDPOINTS = frozenset({'authenticate', 'projects/create', 'files/read', 'files/create', 'files/update',
    'compile/create', 'compile/read', 'backtests/create', 'backtests/read', 'backtests/orders/read', 'backtests/read/log', 'backtests/chart/read', 'object/set'})
MUTATIONS = frozenset({'projects/create', 'files/create', 'files/update', 'compile/create', 'backtests/create', 'object/set'})
MAX_REQUESTS, MAX_ORDERS, MAX_COLLECTIONS = 4096, 50000, 3
MAX_INPUT_BYTES, MAX_INPUT_TOTAL = 32 * 1024 * 1024, 512 * 1024 * 1024
CALENDAR_SHA256 = '3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d'
# End is exclusive UTC midnight after the owner-authorized Oct9 session. It
# includes that NY close, not a new trading session or extra-day fallback.
CHART_START, CHART_END, CHART_COUNT = 1609718400, 1791590400, 2000
CHARTS = {'Strategy Equity': 'strategy-equity', 'EXT26 Account NAV': 'account-nav'}
NY = ZoneInfo('America/New_York')
SUMMARY_KEYS = frozenset(('study_id candidate_id arm config_sha256 freeze_sha256 calendar_sha256 attempt project_id job_id '
    'input_hashes decisions refused_decisions valuation_days last_valuation_session engine_end_utc submitted_orders fill_events '
    'requested_shares submitted_shares filled_shares fees max_cash_ledger_residual max_nav_ledger_residual '
    'position_ledger_mismatches risk_breaches name_soft_cap_breaches max_name_exposure reason_counts delisting_audit '
    'coverage_complete internally_meaningful_execution full_evidence_retrieval_verified strategy_accepted canonical_admission '
    'independent_sleeve_pnl_observed clock_assertions per_sleeve_coverage cap_snapshot_coverage cash_exposure_aggregate matched_input_chains').split())
INDEX_KEYS = frozenset(('index_key index_sha256 chunks records bytes candidate_id attempt config_sha256 freeze_sha256 '
    'project_id job_id record_kind_counts internally_meaningful_execution strategy_accepted canonical_admission').split())
Refusal = evidence.EvidenceError
canonical, digest = evidence.canonical, evidence.digest


def _input_digest(raw, *, multipart=False):
    maximum = MAX_INPUT_BYTES + (4096 if multipart else 0)
    if type(raw) is not bytes or not 0 < len(raw) <= maximum: raise Refusal('bounded private input wire required')
    return hashlib.sha256(raw).hexdigest()


def _request_digest(raw, endpoint):
    return _input_digest(raw, multipart=True) if endpoint == 'object/set' else digest(raw)


def now():
    return datetime.now(timezone.utc).isoformat()


def _name(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,220}', value) is None:
        raise Refusal('bounded immutable basename required')
    return value


def _clock(value):
    try:
        result = datetime.fromisoformat(value)
        if type(value) is not str or result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise Refusal('aware access clock required') from None


def _int(value, maximum=2**63 - 1):
    return evidence._integer(value, maximum)


def _count(value):
    if type(value) is not evidence.JsonNumber or value.fraction().denominator != 1 or not 0 <= value.fraction() <= 2**63 - 1:
        raise Refusal('exact nonnegative aggregate count required')
    return int(value.fraction())


def _rational(value, *, nonnegative=True):
    evidence._closed(value, {'numerator', 'denominator'})
    numerator, denominator = value['numerator'], value['denominator']
    if (type(numerator) is not str or re.fullmatch(r'-?(0|[1-9][0-9]{0,1000})', numerator) is None
            or type(denominator) is not str or re.fullmatch(r'[1-9][0-9]{0,1000}', denominator) is None):
        raise Refusal('exact bounded rational aggregate required')
    from fractions import Fraction
    result = Fraction(int(numerator), int(denominator))
    if nonnegative and result < 0: raise Refusal('negative cost/exposure/residual refused')
    return result


def _returned_identity(response, project, job):
    """Reject explicitly foreign IDs; never invent identifiers absent from API.

    Counts describe returned identifiers that were actually observed. The own
    request envelope provides scope when IDs are absent; that is not a returned
    provider identity statement or independent provider-authenticity evidence.
    Only known response/row identity fields are inspected, not symbol IDs.
    """
    if type(response) is not dict: raise Refusal('typed native response required')
    objects = [response]
    for key in ('backtest', 'chart'):
        if type(response.get(key)) is dict: objects.append(response[key])
    if type(response.get('orders')) is list:
        objects.extend(row for row in response['orders'] if type(row) is dict)
    observed_project, observed_job = 0, 0
    for row in objects:
        if 'projectId' in row:
            if _int(row['projectId']) != _int(project): raise Refusal('returned native project identity differs')
            observed_project += 1
        if 'backtestId' in row:
            if evidence._id(row['backtestId']) != evidence._id(job): raise Refusal('returned native job identity differs')
            observed_job += 1
    return {'observed_project_id_fields': observed_project, 'observed_backtest_id_fields': observed_job,
        'absent_identifiers_inferred': False, 'provider_authenticity_independently_verified': False}


def _bundle_calendar(specification):
    """Extract a hash-frozen literal without executing cloud source or I/O."""
    text = specification['files'].get('extended_loader.py')
    if type(text) is not str or specification['input_hashes'].get('calendar.json') != CALENDAR_SHA256:
        raise Refusal('exact frozen rendered calendar source required')
    try:
        tree = ast.parse(text)
        rows = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'CALENDAR_JSON' for target in node.targets)]
        if (len(rows) != 1 or len(rows[0].targets) != 1 or not isinstance(rows[0].value, ast.Constant)
                or type(rows[0].value.value) is not str): raise ValueError
        raw = rows[0].value.value.encode('utf-8')
    except (SyntaxError, TypeError, ValueError, UnicodeError):
        raise Refusal('one exact literal rendered calendar required') from None
    if digest(raw) != CALENDAR_SHA256: raise Refusal('rendered calendar bytes differ')
    body = evidence.parse_json(raw)
    sessions = body.get('valuation_sessions')
    if (body.get('schema') != 'tpr-extended-calendar-v1' or body.get('study_id') != evidence.STUDY_ID
            or body.get('study_freeze_sha256') != evidence.FREEZE_SHA256 or type(sessions) is not list
            or len(sessions) != 1449 or sessions != sorted(set(sessions))
            or sessions[0] != '2021-01-04' or sessions[-1] != '2026-10-09'):
        raise Refusal('whole frozen valuation calendar required')
    return tuple(sessions)


def _account_nav_chart(response, sessions):
    """Normalize only explicit own daily account observations, never gap-fill.

    LEAN Plot uses UTC ChartPoint time. Modern native line points are [x,y];
    legacy {x,y} is also explicit. The custom frozen source plots once per
    valuation session at16:01 NY. Strategy Equity is independently sampled and
    cannot substitute for this daily series. Native chart smart-rounding is
    retained verbatim, not claimed as replay of the exact private journal.
    """
    result = {'complete_daily_account_nav': False, 'expected_observations': len(sessions),
        'observations': None, 'classification': 'diagnostic_missing_chart',
        'calendar_sha256': CALENDAR_SHA256, 'observation_clock': '16:01:00 America/New_York',
        'native_numeric_tokens_preserved': True, 'private_journal_replay_verified': False}
    if response.get('status') in {'loading', 'Loading'}:
        result['classification'] = 'diagnostic_loading_chart'; return result, None
    chart = response.get('chart')
    if type(chart) is not dict or chart.get('name') != 'EXT26 Account NAV': return result, None
    series = chart.get('series')
    row = series.get('NAV') if type(series) is dict else None
    if (type(row) is not dict or row.get('name') != 'NAV' or row.get('unit') != '$'
            or type(row.get('seriesType')) is not evidence.JsonNumber or row['seriesType'].fraction() != 0):
        result['classification'] = 'diagnostic_unknown_account_series'; return result, None
    values = row.get('values')
    if type(values) is not list:
        result['classification'] = 'diagnostic_unobserved_chart_values'; return result, None
    result['observations'] = len(values)
    if len(values) != len(sessions) or len(values) > CHART_COUNT:
        result['classification'] = 'diagnostic_incomplete_daily_census'; return result, None
    normalized, prior_time = [], None
    for point, session in zip(values, sessions):
        if type(point) is list and len(point) == 2:
            stamp, nav = point
        elif type(point) is dict and set(point) == {'x', 'y'}:
            stamp, nav = point['x'], point['y']
        else:
            result['classification'] = 'diagnostic_unknown_point_shape'; return result, None
        if (type(stamp) is not evidence.JsonNumber or stamp.fraction().denominator != 1
                or not CHART_START <= stamp.fraction() < CHART_END or type(nav) is not evidence.JsonNumber
                or nav.fraction() <= 0):
            result['classification'] = 'diagnostic_invalid_chart_observation'; return result, None
        instant = datetime.fromtimestamp(int(stamp.fraction()), timezone.utc)
        local = instant.astimezone(NY)
        if (local.date().isoformat() != session or (local.hour, local.minute, local.second) != (16, 1, 0)
                or prior_time is not None and instant <= prior_time):
            result['classification'] = 'diagnostic_wrong_session_or_audit_clock'; return result, None
        prior_time = instant
        normalized.append({'session': session, 'nav': nav})
    raw = canonical(normalized)
    result.update(complete_daily_account_nav=True, classification='complete_native_daily_account_nav',
        normalized_series_sha256=digest(raw), first_session=sessions[0], last_session=sessions[-1])
    return result, raw


def _coverage(summary):
    """Exact aggregate shape/coherence only; absent observations stay null."""
    _count(summary['clock_assertions'])
    caps = summary['cap_snapshot_coverage']
    evidence._closed(caps, {'available_decisions', 'missing_decisions', 'unobserved_decisions'})
    if sum(_count(value) for value in caps.values()) != 301: raise Refusal('cap snapshot decision census mismatch')
    sleeves = summary['per_sleeve_coverage']
    evidence._closed(sleeves, {'SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE'})
    counts = {'membership_available_decisions', 'membership_missing_decisions', 'membership_unobserved_decisions',
        'construction_observed_decisions', 'construction_unobserved_decisions', 'selected_any_decisions', 'selected_zero_decisions'}
    for sleeve in sleeves.values():
        evidence._closed(sleeve, counts | {'cap_state_counts', 'tpr_state_counts', 'cap_ranked_slots', 'executable_slots', 'selected_slots'})
        numeric = {key: _count(sleeve[key]) for key in counts}
        if (any(value > 301 for value in numeric.values())
                or sum(numeric[key] for key in ('membership_available_decisions', 'membership_missing_decisions', 'membership_unobserved_decisions')) != 301
                or numeric['construction_observed_decisions'] + numeric['construction_unobserved_decisions'] != 301
                or numeric['selected_any_decisions'] + numeric['selected_zero_decisions'] != numeric['construction_observed_decisions']):
            raise Refusal('complete sleeve decision census mismatch')
        for key, states in (('cap_state_counts', {'available', 'missing', 'unknown', 'invalid', 'nonpositive'}),
                ('tpr_state_counts', {'nonzero', 'zero', 'missing', 'unknown', 'invalid', 'not_used'})):
            evidence._closed(sleeve[key], states)
            for value in sleeve[key].values(): _count(value)
        for key in ('cap_ranked_slots', 'executable_slots', 'selected_slots'):
            stats = sleeve[key]; evidence._closed(stats, {'observed_decisions', 'sum', 'min', 'max'})
            observed, total = _count(stats['observed_decisions']), _count(stats['sum'])
            if observed > 301 or total > observed * 10: raise Refusal('bounded slot aggregate required')
            if not observed:
                if total or stats['min'] is not None or stats['max'] is not None: raise Refusal('unobserved slots cannot be imputed')
            elif (stats['min'] is None or stats['max'] is None or not 0 <= _count(stats['min']) <= _count(stats['max']) <= 10
                    or not _count(stats['min']) * observed <= total <= _count(stats['max']) * observed):
                raise Refusal('coherent observed slot range required')
    cash = summary['cash_exposure_aggregate']
    evidence._closed(cash, {'nav_observations', 'expected_nav_observations', 'missing_nav_observations', 'cash_usd', 'cash_fraction', 'gross_exposure',
        'dimensionless_mean_precision_digits', 'dimensionless_mean_rounding', 'dimensionless_means_are_rounded'})
    if (_count(cash['dimensionless_mean_precision_digits']) != 50 or cash['dimensionless_mean_rounding'] != 'ROUND_HALF_EVEN'
            or cash['dimensionless_means_are_rounded'] is not True): raise Refusal('explicit statistical mean precision required')
    observations, missing = _count(cash['nav_observations']), _count(cash['missing_nav_observations'])
    if _count(cash['expected_nav_observations']) != 1449 or observations + missing != 1449:
        raise Refusal('full NAV observation census required')
    for key in ('cash_usd', 'cash_fraction', 'gross_exposure'):
        stats = cash[key]; evidence._closed(stats, {'observations', 'min', 'max', 'mean'})
        if _count(stats['observations']) != observations: raise Refusal('cash/exposure observation census differs')
        if not observations:
            if any(stats[name] is not None for name in ('min', 'max', 'mean')): raise Refusal('missing exposure cannot be zero')
        else:
            low, high = (_rational(stats[name], nonnegative=key == 'gross_exposure') for name in ('min', 'max'))
            if key == 'cash_usd':
                mean, allowance = _rational(stats['mean'], nonnegative=False), 0
            else:
                from decimal import Decimal
                from fractions import Fraction
                if type(stats['mean']) is not str: raise Refusal('explicit bounded rounded dimensionless mean required')
                token = evidence.JsonNumber(stats['mean']); decimal = Decimal(token.lexeme)
                if len(decimal.as_tuple().digits) > 50: raise Refusal('dimensionless statistical precision exceeded')
                mean = token.fraction()
                if key == 'gross_exposure' and mean < 0: raise Refusal('negative gross exposure refused')
                allowance = Fraction(10) ** decimal.as_tuple().exponent / 2
            if low > high or not low - allowance <= mean <= high + allowance:
                raise Refusal('coherent exact cash/exposure range required')
    _matched_chains(summary['matched_input_chains'])


def _matched_chains(chains):
    evidence._closed(chains, {'SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE'})
    for sleeve in chains.values():
        evidence._closed(sleeve, {'membership', 'caps', 'selection', 'prior_marks'})
        for chain in sleeve.values():
            evidence._closed(chain, {'sha256', 'observed_decisions', 'unavailable_decisions', 'expected_decisions'})
            evidence._hash(chain['sha256'])
            if (_count(chain['expected_decisions']) != 301
                    or _count(chain['observed_decisions']) + _count(chain['unavailable_decisions']) != 301):
                raise Refusal('whole-run matched input chain census required')
    return chains


def compare_matched_chain_receipts(on_chains, off_chains):
    """Equality of bounded hash receipts, not independent row/PIT replay."""
    _matched_chains(on_chains); _matched_chains(off_chains)
    from .extended_metrics import compare_matched_input_chains
    return compare_matched_input_chains(on_chains, off_chains)


def compact_aggregate(line, marker, manifest, attempt, job):
    """Closed own runtime aggregate binding, not cloud-chunk replay evidence."""
    if type(line) is not str or line.count(marker + ' ') != 1:
        raise Refusal('exact compact marker required')
    raw = line.split(marker + ' ', 1)[1].encode()
    if len(raw) > (24576 if marker == 'EXT26_SUMMARY' else 8192): raise Refusal('compact JSON byte bound exceeded')
    body = evidence.parse_json(raw)
    evidence._closed(body, SUMMARY_KEYS if marker == 'EXT26_SUMMARY' else INDEX_KEYS)
    if (body['candidate_id'] != manifest['candidate_id'] or _int(body['attempt'], 3) != attempt
            or body['config_sha256'] != manifest['config_sha256'] or body['freeze_sha256'] != evidence.FREEZE_SHA256
            or _int(body['project_id']) != _int(manifest['project_id']) or body['job_id'] != job
            or body['strategy_accepted'] is not False or body['canonical_admission'] is not False
            or type(body['internally_meaningful_execution']) is not bool):
        raise Refusal('own exact compact runtime identity required')
    if marker == 'EXT26_SUMMARY':
        if (body['study_id'] != evidence.STUDY_ID or body['arm'] != manifest['arm'] or body['input_hashes'] != manifest['input_hashes']
                or body['calendar_sha256'] != manifest['input_hashes'].get('calendar.json')
                or body['full_evidence_retrieval_verified'] is not False or body['independent_sleeve_pnl_observed'] is not False
                or type(body['coverage_complete']) is not bool or type(body['reason_counts']) is not dict
                or type(body['delisting_audit']) is not dict):
            raise Refusal('exact summary scope/custody required')
        for key in ('decisions', 'refused_decisions', 'valuation_days', 'submitted_orders', 'fill_events', 'requested_shares',
                'submitted_shares', 'filled_shares', 'position_ledger_mismatches', 'risk_breaches', 'name_soft_cap_breaches'):
            _count(body[key])
        for key in ('fees', 'max_cash_ledger_residual', 'max_nav_ledger_residual', 'max_name_exposure'): _rational(body[key])
        for key, value in body['reason_counts'].items(): evidence._id(key); _count(value)
        if body['last_valuation_session'] is not None and (type(body['last_valuation_session']) is not str
                or re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', body['last_valuation_session']) is None):
            raise Refusal('exact last valuation date required')
        _clock(body['engine_end_utc'])
        _coverage(body)
    else:
        expected = ('tpr-ext26/evidence/' + manifest['candidate_id'] + '/' + manifest['config_sha256'] + '/attempt-' + str(attempt)
            + '/' + str(_int(manifest['project_id'])) + '/' + job + '/index.json')
        if body['index_key'] != expected or type(body['record_kind_counts']) is not dict: raise Refusal('exact own evidence index pointer required')
        evidence._hash(body['index_sha256'])
        for key in ('chunks', 'records', 'bytes'): _int(body[key])
        counts = body['record_kind_counts']
        if any(type(key) is not str or re.fullmatch(r'[A-Z_]{1,64}', key) is None for key in counts):
            raise Refusal('bounded own evidence record kinds required')
        if sum(_count(value) for value in counts.values()) != _int(body['records']) or _count(counts.get('SUMMARY')) != 1:
            raise Refusal('coherent cloud index record counts required')
    return body


def _custody(info, directory=False):
    if (info.st_uid != os.getuid() or stat.S_ISLNK(info.st_mode)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or not directory and info.st_nlink != 1):
        raise Refusal('owner-only cooperative private custody required')


def read_private(root, name, maximum=evidence.MAX_BYTES):
    _name(name)
    directory = file = None
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        _custody(os.fstat(directory), True)
        file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        before = os.fstat(file)
        _custody(before)
        with os.fdopen(file, 'rb') as stream:
            file = None
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        _custody(after)
        if (len(raw) > maximum or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise Refusal('private bytes changed or exceeded bound')
        return raw
    except OSError:
        raise Refusal('private read refused') from None
    finally:
        if file is not None: os.close(file)
        if directory is not None: os.close(directory)


@contextmanager
def wall_deadline(seconds):
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0, 0):
        raise Refusal('exclusive POSIX deadline unavailable')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_): raise Refusal('bounded request timed out; outcome unknown')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def credential():
    user, token = os.environ.get('QC_USER_ID', '').strip(), os.environ.get('QC_API_TOKEN', '').strip()
    if (re.fullmatch(r'[0-9]{1,30}', user) is None
            or re.fullmatch(r'[A-Za-z0-9._~-]{8,256}', token) is None):
        raise Refusal('existing QC credentials unavailable')
    return user, token


def validate_manifest(body):
    evidence._closed(body, {'schema', 'study_id', 'operation_id', 'created_utc', 'expires_utc', 'git_head',
        'freeze_sha256', 'preparation_sha256', 'repository_source_hashes', 'candidates', 'inputs', 'max_requests', 'max_response_bytes',
        'request_seconds', 'max_orders', 'max_collections'})
    if (body['schema'] != 'tpr-ext26-operations-manifest-v1' or body['study_id'] != evidence.STUDY_ID
            or body['freeze_sha256'] != evidence.FREEZE_SHA256):
        raise Refusal('exact extended study manifest required')
    _name(body['operation_id'])
    if len(body['operation_id']) > 80: raise Refusal('bounded operation identifier required')
    evidence._hash(body['preparation_sha256'])
    evidence._hash(body['git_head'], 40)
    if not 0 < (_clock(body['expires_utc']) - _clock(body['created_utc'])).total_seconds() <= 172800:
        raise Refusal('bounded fresh access lifetime required')
    for key, maximum in (('max_requests', MAX_REQUESTS), ('max_response_bytes', evidence.MAX_BYTES),
            ('request_seconds', 30), ('max_orders', MAX_ORDERS), ('max_collections', MAX_COLLECTIONS)):
        _int(body[key], maximum)
    sources = body['repository_source_hashes']
    if type(sources) is not dict or not 3 <= len(sources) <= 32:
        raise Refusal('committed source closure required')
    for relative, identity in sources.items():
        if (type(relative) is not str or re.fullmatch(r'research/target_price_revisions_qc/[A-Za-z0-9_.-]+\.(py|json)', relative) is None):
            raise Refusal('lane-owned source allowlist required')
        evidence._hash(identity)
    required = {'research/target_price_revisions_qc/extended_operations.py',
                'research/target_price_revisions_qc/extended_driver.py',
                'research/target_price_revisions_qc/extended_evidence.py'}
    if not required <= set(sources):
        raise Refusal('complete committed producer identities required')
    rows = body['candidates']
    if type(rows) is not list or len(rows) != 2:
        raise Refusal('both frozen candidates required')
    candidates = {}
    for row in rows:
        evidence._closed(row, {'candidate_id', 'planned_attempt', 'project_name', 'config_raw', 'files', 'input_hashes'})
        candidate = row['candidate_id']
        if (type(candidate) is not str or candidate not in evidence.CANDIDATES or candidate in candidates
                or row['project_name'] != candidate + '-private'):
            raise Refusal('exact fresh private candidates required')
        _int(row['planned_attempt'], 3)
        if type(row['config_raw']) is not str or type(row['files']) is not dict:
            raise Refusal('source bundle bytes required')
        hashes = {}
        for name, content in row['files'].items():
            if type(name) is not str or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}\.py', name) is None or type(content) is not str:
                raise Refusal('readable source inventory refused')
            encoded = content.encode('utf-8')
            if not 0 < len(encoded) <= 60000:
                raise Refusal('conservative per-file quota exceeded')
            try: compile(ast.parse(content), name, 'exec')
            except (SyntaxError, ValueError, TypeError): raise Refusal('readable source compilation refused') from None
            hashes[name] = digest(encoded)
        if not 2 <= len(hashes) <= 32 or not {'main.py', 'extended_config.py'} <= set(hashes):
            raise Refusal('complete new source inventory required')
        config = evidence.parse_json(row['config_raw'].encode())
        evidence._closed(config, {'schema', 'study_id', 'candidate_id', 'arm', 'freeze_sha256', 'input_hashes'})
        if (config['schema'] != 'tpr-ext26-config-v1' or config['study_id'] != evidence.STUDY_ID
                or config['candidate_id'] != candidate or config['arm'] != evidence.CANDIDATES[candidate]
                or config['freeze_sha256'] != evidence.FREEZE_SHA256 or config['input_hashes'] != row['input_hashes']):
            raise Refusal('source/config/input identities differ')
        if type(row['input_hashes']) is not dict or row['input_hashes'].get('preparation.json') != body['preparation_sha256']:
            raise Refusal('closed public prepared-input receipt must bind both arms')
        for name, identity in row['input_hashes'].items():
            evidence._id(name); evidence._hash(identity)
        candidates[candidate] = {**row, 'source_hashes': hashes, 'config_sha256': digest(row['config_raw'].encode())}
    inputs = body['inputs']
    if type(inputs) is not list or not 1 <= len(inputs) <= 256:
        raise Refusal('bounded fresh private input inventory required')
    names, keys, input_total = set(), set(), 0
    for row in inputs:
        evidence._closed(row, {'name', 'sha256', 'bytes', 'key'})
        _name(row['name']); evidence._hash(row['sha256']); input_total += _int(row['bytes'], MAX_INPUT_BYTES)
        if (type(row['key']) is not str or row['name'] in names or row['key'] in keys
                or row['key'] != 'tpr-ext26/inputs/' + evidence.STUDY_ID + '/' + body['preparation_sha256'] + '/' + row['sha256'] + '.json'):
            raise Refusal('content-addressed new private input keys required')
        names.add(row['name']); keys.add(row['key'])
    if input_total > MAX_INPUT_TOTAL: raise Refusal('bounded prepared-input total exceeded')
    return candidates


class Operations:
    def __init__(self, manifest, *, manifest_sha256, fixture_root=None, fixture_transport=None):
        raw = canonical(manifest)
        if digest(raw) != evidence._hash(manifest_sha256): raise Refusal('operations manifest hash mismatch')
        self.manifest = evidence.parse_json(raw)
        self.candidates = validate_manifest(self.manifest)
        if (fixture_root is None) != (fixture_transport is None): raise Refusal('complete synthetic fixture seam required')
        self.fixture = fixture_root is not None
        self.root = Path(fixture_root) if self.fixture else PRIVATE_ROOT
        self.transport = fixture_transport
        self.manifest_hash, self.operation = manifest_sha256, self.manifest['operation_id']

    def guard(self):
        if not _clock(self.manifest['created_utc']) <= datetime.now(timezone.utc) <= _clock(self.manifest['expires_utc']):
            raise Refusal('fresh access scope inactive')
        if self.fixture: return
        if Path.cwd() != LANE or Path.cwd().resolve() != LANE: raise Refusal('wrong physical lane')
        def git(*args): return subprocess.run(['git', *args], cwd=LANE, capture_output=True, text=True, check=True).stdout.strip()
        if (git('rev-parse', '--show-toplevel') != str(LANE) or git('branch', '--show-current') != BRANCH
                or git('rev-parse', 'HEAD') != self.manifest['git_head']): raise Refusal('root/branch/HEAD invariant moved')
        git('status', '--short')
        if subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE, self.manifest['git_head']], cwd=LANE, capture_output=True).returncode:
            raise Refusal('authorized lineage diverged')
        if subprocess.run(['git', 'check-ignore', '-q', str(PRIVATE_ROOT)], cwd=LANE, capture_output=True).returncode:
            raise Refusal('private resources must be Git ignored')
        for relative, identity in self.manifest['repository_source_hashes'].items():
            path = LANE / relative
            if path.resolve() != path or path.is_symlink() or not path.is_file() or path.stat().st_size > evidence.MAX_BYTES: raise Refusal('source custody refused')
            observed = path.read_bytes()
            committed = subprocess.run(['git', 'show', self.manifest['git_head'] + ':' + relative], cwd=LANE, capture_output=True, check=True).stdout
            if observed != committed or digest(observed) != identity: raise Refusal('source bytes not committed and exact')

    def _ensure_root(self):
        if self.fixture:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            _custody(self.root.lstat(), True)
        else:
            if self.root.resolve() != self.root: raise Refusal('private ancestor custody refused')
            for path in (PRIVATE_PARENT, PRIVATE_PARENT / evidence.STUDY_ID, self.root):
                path.mkdir(mode=0o700, exist_ok=True); _custody(path.lstat(), True)

    def write(self, name, value):
        self.guard(); _name(name); self._ensure_root()
        raw = value if type(value) is bytes else canonical(value)
        try: fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError: raise Refusal('immutable claim exists; no implicit retry') from None
        with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        return digest(raw)

    def read(self, name):
        self.guard(); return read_private(self.root, name)

    def value(self, name): return evidence.parse_json(self.read(name))

    def prepare(self):
        self.guard()
        self.write('access.' + self.operation + '.json', {'manifest_sha256': self.manifest_hash, 'at': now(), 'fixture': self.fixture})
        self.write('manifest.' + self.operation + '.json', self.manifest)
        return {'operation_id': self.operation, 'manifest_sha256': self.manifest_hash, 'fixture': self.fixture}

    def access(self):
        self.guard()
        if self.value('access.' + self.operation + '.json')['manifest_sha256'] != self.manifest_hash:
            raise Refusal('fresh access manifest differs')

    @contextmanager
    def locked(self):
        self.access(); self._ensure_root()
        try: fd = os.open(self.root / 'controller.lock', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError: raise Refusal('concurrent or crashed operation unresolved') from None
        try:
            os.write(fd, canonical({'at': now(), 'manifest_sha256': self.manifest_hash})); os.fsync(fd)
            yield
        finally:
            os.close(fd); (self.root / 'controller.lock').unlink()

    def candidate(self, candidate):
        if type(candidate) is not str or candidate not in self.candidates: raise Refusal('candidate outside frozen pair')
        return self.candidates[candidate]

    def project(self, candidate):
        row = self.value(candidate + '.project.json')
        if row['candidate_id'] != candidate or row['name'] != self.candidate(candidate)['project_name'] or row['owner'] is not True:
            raise Refusal('fresh own project receipt mismatch')
        _int(row['project_id']); return row

    def sequence(self, prefix, suffix):
        numbers = []
        for path in self.root.glob(prefix + '*' + suffix):
            middle = path.name[len(prefix):-len(suffix)]
            if not middle.isdigit(): raise Refusal('malformed persistent receipt census')
            numbers.append(int(middle))
        return max(numbers, default=0) + 1

    def request(self, endpoint, payload, *, candidate=None, stage=None, content_type='application/json'):
        self.access()
        if endpoint not in ENDPOINTS: raise Refusal('endpoint outside scoped workflow')
        if endpoint not in {'authenticate', 'projects/create', 'object/set'}:
            if candidate is None or _int(payload.get('projectId')) != _int(self.project(candidate)['project_id']):
                raise Refusal('request must target fresh registered project')
        if endpoint == 'backtests/chart/read':
            evidence._closed(payload, {'projectId', 'backtestId', 'name', 'count', 'start', 'end'})
            if (type(payload['name']) is not str or payload['name'] not in CHARTS or _int(payload['count']) != CHART_COUNT
                    or _int(payload['start']) != CHART_START or _int(payload['end']) != CHART_END):
                raise Refusal('exact frozen native chart request required')
            _name(stage)
            claim = self.value(stage + '.spent.json')
            if (claim.get('endpoint') != endpoint or claim.get('payload_sha256') != digest(canonical(payload))
                    or claim.get('manifest_sha256') != self.manifest_hash or claim.get('new_looks') != evidence.JsonNumber('0')):
                raise Refusal('fresh explicitly bounded chart read claim required')
        raw = payload if type(payload) is bytes else canonical(payload)
        if endpoint in MUTATIONS:
            _name(stage)
            self.admit_mutation(endpoint, payload, raw, candidate, stage)
            admitted = self.value(stage + '.spent.json')
            if admitted.get('manifest_sha256') != self.manifest_hash or admitted.get('payload_sha256') != _request_digest(raw, endpoint):
                raise Refusal('typed effectful stage payload not admitted')
            self.write(stage + '.transport.json', {'at': now(), 'endpoint': endpoint})
        sequence = self.sequence('request.', '.spent.json')
        if sequence > _int(self.manifest['max_requests'], MAX_REQUESTS): raise Refusal('persistent request budget exhausted')
        prefix = 'request.' + f'{sequence:04d}'
        self.write(prefix + '.spent.json', {'at': now(), 'endpoint': endpoint, 'payload_sha256': _request_digest(raw, endpoint), 'manifest_sha256': self.manifest_hash})
        connection = None
        try:
            if self.fixture:
                response_raw = self.transport(endpoint, raw, content_type)
                token, status = '', 200
            else:
                with wall_deadline(_int(self.manifest['request_seconds'], 30)):
                    user, token = credential()
                    stamp = str(int(time.time()))
                    signed = hashlib.sha256((token + ':' + stamp).encode()).hexdigest()
                    authorization = base64.b64encode((user + ':' + signed).encode()).decode()
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.keylog_filename = None
                    context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED
                    context.load_default_certs()
                    connection = http.client.HTTPSConnection('www.quantconnect.com',
                        timeout=_int(self.manifest['request_seconds'], 30), context=context)
                    connection.request('POST', '/api/v2/' + endpoint, body=raw,
                        headers={'Authorization': 'Basic ' + authorization, 'Timestamp': stamp, 'Content-Type': content_type})
                    response = connection.getresponse(); status = response.status
                    response_raw = response.read(_int(self.manifest['max_response_bytes'], evidence.MAX_BYTES) + 1)
            if type(response_raw) is not bytes or len(response_raw) > _int(self.manifest['max_response_bytes'], evidence.MAX_BYTES):
                raise Refusal('response bytes exceed bound')
            projected = evidence.project_wire(response_raw, credential=token)
            self.write(prefix + '.projection.json', projected)
            value = projected['projection']
            if status != 200 or type(value) is not dict or value.get('success') is not True:
                raise Refusal('API refused; original wire hash retained')
            if endpoint in {'backtests/read', 'backtests/orders/read', 'backtests/read/log', 'backtests/chart/read'}:
                _returned_identity(value, payload['projectId'], payload['backtestId'])
            self.write(prefix + '.terminal.json', {'at': now(), 'status': 'succeeded', 'original_wire_sha256': projected['original_wire_sha256'],
                'projection_sha256': projected['projection_sha256']})
            return value
        except Exception:
            if not (self.root / (prefix + '.terminal.json')).exists():
                self.write(prefix + '.terminal.json', {'at': now(), 'status': 'failed_or_unknown', 'automatic_retry': False})
            raise Refusal('request failed or uncertain; claim remains consumed') from None
        finally:
            if connection is not None: connection.close()

    def admit_mutation(self, endpoint, payload, raw, candidate, stage):
        """Effectful routes cannot bypass the specialized source/attempt gates."""
        if endpoint == 'projects/create':
            if candidate is None:
                matches = [name for name in self.candidates if stage == name + '.project-create']
                if len(matches) != 1: raise Refusal('typed project creation stage required')
                candidate = matches[0]
            if (stage != candidate + '.project-create' or payload != {'name': self.candidate(candidate)['project_name'], 'language': 'Py'}):
                raise Refusal('exact new project creation payload required')
            return
        if endpoint in {'files/create', 'files/update'}:
            specification = self.candidate(candidate)
            evidence._closed(payload, {'projectId', 'name', 'content'})
            name = payload['name']
            if (type(name) is not str or name not in specification['files']
                    or stage != candidate + '.source.' + self.operation + '.' + name
                    or payload['content'] != specification['files'][name]):
                raise Refusal('typed exact-source upload stage required')
            return
        if endpoint == 'object/set':
            matches = [row for row in self.manifest['inputs'] if stage == 'input.' + row['sha256'] + '.upload']
            if len(matches) != 1: raise Refusal('typed new input upload stage required')
            row = matches[0]
            organization = self.project(next(name for name, arm in evidence.CANDIDATES.items() if arm == 'tpr_on'))['organization_id']
            boundary = 'tpr-ext26-' + row['sha256']
            prefix = b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n').encode()
                for field, value in (('organizationId', organization), ('key', row['key'])))
            prefix += (f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="{row["sha256"]}.json"\r\nContent-Type: application/json\r\n\r\n').encode()
            suffix = f'\r\n--{boundary}--\r\n'.encode()
            if not raw.startswith(prefix) or not raw.endswith(suffix): raise Refusal('input multipart target mismatch')
            data = raw[len(prefix):-len(suffix)]
            if _input_digest(data) != row['sha256'] or len(data) != _int(row['bytes'], MAX_INPUT_BYTES):
                raise Refusal('input multipart content mismatch')
            return
        match = re.fullmatch(re.escape(candidate or '') + r'[.]attempt[.]([1-3])[.](compile|backtest)', stage)
        if match is None: raise Refusal('typed persistent attempt stage required')
        attempt = int(match.group(1)); prefix, manifest = self.attempt(candidate, attempt)
        if endpoint == 'compile/create':
            if match.group(2) != 'compile' or payload != {'projectId': _int(manifest['project_id'])}:
                raise Refusal('typed compile payload required')
            readback = self.read(prefix + '.precompile-readback.json')
            evidence._readback(readback, self.candidate(candidate)['config_raw'].encode(), manifest)
        elif endpoint == 'backtests/create':
            compile_id, state = evidence._compile(self.read(prefix + '.compile-response.json'), manifest)
            if (match.group(2) != 'backtest' or state != 'BuildSuccess' or payload != {
                    'projectId': _int(manifest['project_id']), 'compileId': compile_id,
                    'backtestName': candidate + '-attempt-' + str(attempt)}):
                raise Refusal('typed source-bound successful compile launch required')
            evidence._readback(self.read(prefix + '.launch-readback.json'), self.candidate(candidate)['config_raw'].encode(), manifest)
            if not (self.root / (prefix + '.look.json')).exists(): raise Refusal('prelaunch look claim required')
            if evidence.CANDIDATES[candidate] == 'tpr_on':
                for row in self.manifest['inputs']:
                    receipt = self.value('input.' + row['sha256'] + '.completed.json')
                    if receipt.get('sha256') != row['sha256'] or receipt.get('key') != row['key'] or receipt.get('bytes') != row['bytes']:
                        raise Refusal('exact private input upload receipts required')
        else:
            raise Refusal('unrecognized effectful route')

    def effect(self, endpoint, payload, stage, candidate=None, content_type='application/json'):
        self.write(stage + '.spent.json', {'at': now(), 'manifest_sha256': self.manifest_hash,
            'payload_sha256': _request_digest(payload if type(payload) is bytes else canonical(payload), endpoint)})
        return self.request(endpoint, payload, stage=stage, candidate=candidate, content_type=content_type)

    def create_project(self, candidate):
        specification = self.candidate(candidate)
        with self.locked():
            result = self.effect('projects/create', {'name': specification['project_name'], 'language': 'Py'}, candidate + '.project-create')
            rows = result.get('projects')
            if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict: raise Refusal('ambiguous new project response')
            row = rows[0]
            collaborators = row.get('collaborators', [])
            if (row.get('name') != specification['project_name'] or row.get('owner') is not True or row.get('isPublic') is not False
                    or type(collaborators) is not list or any(type(item) is not dict or item.get('owner') is not True for item in collaborators)
                    or _int(row.get('maxFileSize')) < max(60000, max(len(value.encode()) for value in specification['files'].values()))): raise Refusal('private ownership/quota not proved')
            project = {'candidate_id': candidate, 'project_id': _int(row.get('projectId')), 'name': specification['project_name'],
                'organization_id': evidence._id(row.get('organizationId')), 'owner': True, 'lean_version_id': row.get('leanVersionId'),
                'max_file_size': _int(row.get('maxFileSize')), 'at': now()}
            for path in self.root.glob('*.project.json'):
                existing = self.value(path.name)
                if existing['project_id'] == row['projectId'] or existing['organization_id'] != project['organization_id']:
                    raise Refusal('distinct private projects in same organization required')
            self.write(candidate + '.project.json', project); return project

    def envelope(self, endpoint, payload, response):
        return canonical({'schema': 'tpr-ext26-request-response-v1', 'endpoint': endpoint,
            'stage': evidence._STAGES[endpoint], 'request': payload, 'response': response})

    def readback(self, candidate):
        specification, project = self.candidate(candidate), self.project(candidate)
        payload = {'projectId': _int(project['project_id'])}
        response = self.request('files/read', payload, candidate=candidate)
        if 'projectId' in response and _int(response['projectId']) != _int(project['project_id']):
            raise Refusal('returned source project identity differs')
        rows = response.get('files')
        if type(rows) is not list or len(rows) > 33: raise Refusal('cloud source inventory refused')
        files = {}
        for row in rows:
            if type(row) is not dict or type(row.get('name')) is not str or type(row.get('content')) is not str or row['name'] in files:
                raise Refusal('cloud source identity refused')
            files[row['name']] = row['content']
        if set(files) - set(specification['files']) - {'research.ipynb'}: raise Refusal('unrelated cloud code refused')
        if 'research.ipynb' in files:
            identity = digest(files['research.ipynb'].encode())
            name = candidate + '.notebook.json'
            if (self.root / name).exists():
                if self.value(name)['sha256'] != identity: raise Refusal('unrelated notebook changed')
            else: self.write(name, {'sha256': identity})
        clean = {'success': True, 'files': [{'name': name, 'content': files[name]} for name in sorted(specification['files']) if name in files]}
        return self.envelope('files/read', payload, clean), files

    def execution_manifest(self, candidate):
        specification, project = self.candidate(candidate), self.project(candidate)
        return canonical({'schema': 'tpr-ext26-execution-manifest-v1', 'study_id': evidence.STUDY_ID,
            'freeze_sha256': evidence.FREEZE_SHA256, 'candidate_id': candidate, 'arm': evidence.CANDIDATES[candidate],
            'project_id': _int(project['project_id']), 'baseline_git_head': self.manifest['git_head'],
            'config_sha256': specification['config_sha256'], 'source_hashes': specification['source_hashes'],
            'input_hashes': specification['input_hashes'], 'max_attempts': 3})

    def upload_sources(self, candidate):
        with self.locked():
            specification = self.candidate(candidate)
            _, existing = self.readback(candidate)
            for name, content in sorted(specification['files'].items()):
                endpoint = 'files/update' if name in existing else 'files/create'
                payload = {'projectId': _int(self.project(candidate)['project_id']), 'name': name, 'content': content}
                self.effect(endpoint, payload, candidate + '.source.' + self.operation + '.' + name, candidate)
            readback, _ = self.readback(candidate)
            manifest = evidence._manifest(self.execution_manifest(candidate), digest(self.execution_manifest(candidate)))
            evidence._readback(readback, specification['config_raw'].encode(), manifest)
            self.write(candidate + '.readback.' + self.operation + '.json', readback)
            return {'candidate_id': candidate, 'source_hashes': specification['source_hashes'], 'readback_envelope_sha256': digest(readback)}

    def history(self, candidate):
        count = self.sequence(candidate + '.attempt.', '.reservation.json') - 1
        rows = []
        for attempt in range(1, count + 1):
            prefix = candidate + '.attempt.' + str(attempt)
            row = {key: self.read(prefix + '.' + suffix) if (self.root / (prefix + '.' + suffix)).exists() else None
                for key, suffix in (('manifest', 'manifest.json'), ('reservation', 'reservation.json'), ('closure', 'closure.json'),
                    ('compile_response', 'compile-response.json'), ('launch', 'launch.json'), ('backtest_response', 'terminal.json'))}
            rows.append(row)
        return count, rows

    def reserve(self, candidate):
        with self.locked():
            count, prior = self.history(candidate)
            state = {'candidate_id': candidate, 'consumed_count': count, 'ledger_sha256': evidence.ledger_identity(prior), 'at': now()}
            self.write(candidate + '.ledger.' + self.operation + '.json', state)
            retained = self.value(candidate + '.ledger.' + self.operation + '.json')
            attempt = evidence.next_attempt(prior, candidate_id=candidate, consumed_count=count, expected_ledger_sha256=retained['ledger_sha256'])
            if attempt != _int(self.candidate(candidate)['planned_attempt'], 3): raise Refusal('planned source attempt differs from persistent counter')
            readback, _ = self.readback(candidate)
            manifest_raw = self.execution_manifest(candidate); manifest = evidence.parse_json(manifest_raw)
            evidence._readback(readback, self.candidate(candidate)['config_raw'].encode(), manifest)
            reservation = {'schema': 'tpr-ext26-attempt-reservation-v1', 'study_id': evidence.STUDY_ID,
                'candidate_id': candidate, 'attempt': attempt, 'manifest_sha256': digest(manifest_raw), 'project_id': manifest['project_id'],
                'config_sha256': manifest['config_sha256'], 'freeze_sha256': evidence.FREEZE_SHA256,
                'source_hashes': manifest['source_hashes'], 'input_hashes': manifest['input_hashes'], 'state': 'reserved'}
            prefix = candidate + '.attempt.' + str(attempt)
            self.write(prefix + '.manifest.json', manifest_raw)
            self.write(prefix + '.reservation.json', reservation)
            return {'candidate_id': candidate, 'attempt': attempt, 'compile_counts_as_attempt': True}

    def attempt(self, candidate, attempt):
        self.candidate(candidate); _int(attempt, 3)
        prefix = candidate + '.attempt.' + str(attempt)
        manifest_raw = self.read(prefix + '.manifest.json')
        manifest = evidence._manifest(manifest_raw, digest(manifest_raw))
        current = evidence.parse_json(self.execution_manifest(candidate))
        if any(manifest[key] != current[key] for key in current if key != 'baseline_git_head'):
            raise Refusal('active operation source/input manifest changed')
        evidence._reservation(self.read(prefix + '.reservation.json'), manifest, digest(manifest_raw))
        return prefix, manifest

    def compile(self, candidate, attempt):
        with self.locked():
            prefix, manifest = self.attempt(candidate, attempt)
            readback, _ = self.readback(candidate)
            evidence._readback(readback, self.candidate(candidate)['config_raw'].encode(), manifest)
            payload = {'projectId': _int(manifest['project_id'])}
            self.write(prefix + '.precompile-readback.json', readback)
            response = self.effect('compile/create', payload, prefix + '.compile', candidate)
            compile_id = evidence._id(response.get('compileId'))
            self.write(prefix + '.compile-id.json', {'compile_id': compile_id})
            return {'candidate_id': candidate, 'attempt': attempt, 'compile_id': compile_id, 'state': response.get('state')}

    def compile_status(self, candidate, attempt):
        with self.locked():
            prefix, manifest = self.attempt(candidate, attempt)
            compile_id = self.value(prefix + '.compile-id.json')['compile_id']
            if (self.root / (prefix + '.compile-response.json')).exists():
                _, state = evidence._compile(self.read(prefix + '.compile-response.json'), manifest)
                return {'compile_id': compile_id, 'state': state}
            payload = {'projectId': _int(manifest['project_id']), 'compileId': compile_id}
            response = self.request('compile/read', payload, candidate=candidate)
            encoded = self.envelope('compile/read', payload, response)
            _, state = evidence._compile(encoded, manifest)
            if state in {'BuildSuccess', 'BuildError', 'Error', 'Failed'}:
                if not (self.root / (prefix + '.compile-response.json')).exists(): self.write(prefix + '.compile-response.json', encoded)
                elif self.read(prefix + '.compile-response.json') != encoded: raise Refusal('terminal compile bytes changed')
                if state != 'BuildSuccess': self.close(prefix, candidate, attempt, 'compile_failure')
            return {'compile_id': compile_id, 'state': state}

    def close(self, prefix, candidate, attempt, outcome):
        raw = {'schema': 'tpr-ext26-closed-attempt-v1', 'candidate_id': candidate, 'attempt': attempt,
            'manifest_sha256': digest(self.read(prefix + '.manifest.json')), 'reservation_sha256': digest(self.read(prefix + '.reservation.json')),
            'outcome': outcome, 'compile_response_sha256': digest(self.read(prefix + '.compile-response.json')),
            'launch_sha256': digest(self.read(prefix + '.launch.json')) if outcome == 'backtest_terminal' else None,
            'backtest_response_sha256': digest(self.read(prefix + '.terminal.json')) if outcome == 'backtest_terminal' else None}
        if outcome == 'compile_failure' and (self.root / (prefix + '.backtest.spent.json')).exists(): raise Refusal('contradictory launch claim blocks compile closure')
        if outcome == 'backtest_terminal':
            count, prior = self.history(candidate)
            item = prior[attempt - 1]
            item['closure'] = canonical(raw)
            self.validate_terminal(candidate, attempt, item)
        if not (self.root / (prefix + '.closure.json')).exists(): self.write(prefix + '.closure.json', raw)

    def launch(self, candidate, attempt):
        with self.locked():
            prefix, manifest = self.attempt(candidate, attempt)
            compile_raw = self.read(prefix + '.compile-response.json')
            compile_id, state = evidence._compile(compile_raw, manifest)
            if state != 'BuildSuccess': raise Refusal('known BuildSuccess required before launch')
            if evidence.CANDIDATES[candidate] == 'tpr_on':
                for row in self.manifest['inputs']:
                    receipt = self.value('input.' + row['sha256'] + '.completed.json')
                    if receipt.get('sha256') != row['sha256'] or receipt.get('key') != row['key'] or receipt.get('bytes') != row['bytes']:
                        raise Refusal('fresh private ON inputs not uploaded')
            readback, _ = self.readback(candidate)
            evidence._readback(readback, self.candidate(candidate)['config_raw'].encode(), manifest)
            receipt = {'schema': 'tpr-ext26-verified-compile-v1', 'manifest_sha256': digest(self.read(prefix + '.manifest.json')),
                'reservation_sha256': digest(self.read(prefix + '.reservation.json')), 'compile_response_sha256': digest(compile_raw),
                'source_readback_sha256': digest(readback), 'project_id': manifest['project_id'], 'compile_id': compile_id}
            self.write(prefix + '.launch-readback.json', readback); self.write(prefix + '.compile-verified.json', receipt)
            payload = {'projectId': _int(manifest['project_id']), 'compileId': compile_id, 'backtestName': candidate + '-attempt-' + str(attempt)}
            self.write(prefix + '.look.json', {'at': now(), 'candidate_id': candidate, 'attempt': attempt,
                'manifest_sha256': self.manifest_hash, 'execution_manifest_sha256': digest(self.read(prefix + '.manifest.json')),
                'config_sha256': manifest['config_sha256'], 'source_hashes': manifest['source_hashes'], 'input_hashes': manifest['input_hashes'],
                'consumed': not self.fixture, 'fixture': self.fixture, 'old_looks': 16})
            response = self.effect('backtests/create', payload, prefix + '.backtest', candidate)
            launch_raw = self.envelope('backtests/create', payload, response)
            self.write(prefix + '.launch.json', launch_raw)
            binding = evidence.validate_execution_binding(self.read(prefix + '.manifest.json'),
                expected_manifest_sha256=digest(self.read(prefix + '.manifest.json')), config_raw=self.candidate(candidate)['config_raw'].encode(),
                reservation_raw=self.read(prefix + '.reservation.json'), compile_response_raw=compile_raw,
                compile_receipt_raw=canonical(receipt), readback_raw=readback, launch_raw=launch_raw)
            self.write(prefix + '.binding.json', binding)
            return {key: binding[key] for key in ('candidate_id', 'attempt', 'project_id', 'compile_id', 'backtest_id')}

    def status(self, candidate, attempt):
        with self.locked():
            prefix, manifest = self.attempt(candidate, attempt)
            launch = evidence.parse_json(self.read(prefix + '.launch.json'))
            job = evidence._id(launch['response']['backtest']['backtestId'])
            payload = {'projectId': _int(manifest['project_id']), 'backtestId': job}
            response = self.request('backtests/read', payload, candidate=candidate)
            backtest = response.get('backtest')
            if type(backtest) is not dict or backtest.get('backtestId') != job: raise Refusal('returned backtest identity differs')
            if 'projectId' in backtest and _int(backtest['projectId']) != _int(manifest['project_id']): raise Refusal('returned backtest project differs')
            encoded = self.envelope('backtests/read', payload, response)
            seq = self.sequence(prefix + '.poll.', '.json'); self.write(prefix + '.poll.' + f'{seq:04d}' + '.json', encoded)
            terminal = backtest.get('completed') is True and type(backtest.get('status')) is str and backtest['status'] in {'Completed', 'Completed.', 'Runtime Error', 'Error', 'Stopped', 'Cancelled'}
            if terminal:
                if not (self.root / (prefix + '.terminal.json')).exists(): self.write(prefix + '.terminal.json', encoded)
                self.close(prefix, candidate, attempt, 'backtest_terminal')
            return {'backtest_id': job, 'completed': backtest.get('completed') is True, 'terminal': terminal,
                'status': backtest.get('status'), 'error': type(backtest.get('error')) is str and bool(backtest['error'])}

    def collect_orders(self, candidate, attempt):
        with self.locked():
            prefix, manifest = self.attempt(candidate, attempt)
            count, prior = self.history(candidate)
            # Terminal proof includes exact returned identity; no Completed-only shortcut.
            self.validate_terminal(candidate, attempt, prior[attempt - 1])
            if not (self.root / (prefix + '.closure.json')).exists(): raise Refusal('known terminal attempt required')
            launch = evidence.parse_json(self.read(prefix + '.launch.json')); job = launch['response']['backtest']['backtestId']
            sequence = self.sequence(prefix + '.collection.', '.spent.json')
            if sequence > _int(self.manifest['max_collections'], MAX_COLLECTIONS): raise Refusal('bounded read-only collection cap consumed')
            name = prefix + '.collection.' + f'{sequence:04d}'
            self.write(name + '.spent.json', {'at': now(), 'new_looks': 0, 'read_only': True, 'backtest_id': job})
            start, total, pages, ids = 0, None, [], set()
            while total is None or start < total:
                payload = {'projectId': _int(manifest['project_id']), 'backtestId': job, 'start': start, 'end': start + 99}
                response = self.request('backtests/orders/read', payload, candidate=candidate)
                self.write(name + '.orders.' + f'{start:05d}' + '.json', response)
                returned_checks = _returned_identity(response, manifest['project_id'], job)
                envelope = canonical({'schema': 'tpr-ext26-native-read-envelope-v1', 'endpoint': 'backtests/orders/read',
                    'request': payload, 'response': response, 'returned_identity_checks': returned_checks})
                self.write(name + '.orders.' + f'{start:05d}' + '.envelope.json', envelope)
                rows = response.get('orders'); reported = response.get('length')
                total_now = 0 if type(reported) is evidence.JsonNumber and reported.lexeme == '0' else _int(reported, _int(self.manifest['max_orders'], MAX_ORDERS))
                if (type(rows) is not list or len(rows) > 99 or total is not None and total != total_now
                        or not rows and start < total_now): raise Refusal('complete order pagination refused')
                total = total_now
                for row in rows:
                    identity = _int(row.get('id')) if type(row) is dict else None
                    if identity in ids: raise Refusal('duplicate native order identity')
                    ids.add(identity)
                pages.append({'start': start, 'end': start + 99, 'response_projection_sha256': digest(canonical(response)),
                    'request_response_envelope_sha256': digest(envelope), 'returned_identity_checks': returned_checks}); start += 99
            if len(ids) != total: raise Refusal('native order census incomplete')
            result = {'schema': 'tpr-ext26-order-collection-v1', 'candidate_id': candidate, 'attempt': attempt,
                'backtest_id': job, 'order_count': len(ids), 'pages': pages, 'strategy_accepted': False, 'new_looks': 0}
            self.write(name + '.completed.json', result); return result

    def validate_terminal(self, candidate, attempt, row):
        """Validate the selected terminal even when all three slots are spent."""
        closure = evidence.parse_json(row['closure'])
        evidence._closed(closure, {'schema', 'candidate_id', 'attempt', 'manifest_sha256', 'reservation_sha256',
            'outcome', 'compile_response_sha256', 'launch_sha256', 'backtest_response_sha256'})
        if (closure['schema'] != 'tpr-ext26-closed-attempt-v1' or closure['candidate_id'] != candidate
                or _int(closure['attempt'], 3) != attempt or closure['manifest_sha256'] != digest(row['manifest'])
                or closure['reservation_sha256'] != digest(row['reservation'])
                or closure['compile_response_sha256'] != digest(row['compile_response'])
                or closure.get('outcome') != 'backtest_terminal' or closure.get('launch_sha256') != digest(row['launch'])
                or closure.get('backtest_response_sha256') != digest(row['backtest_response'])):
            raise Refusal('concrete terminal closure required')
        manifest = evidence._manifest(row['manifest'], digest(row['manifest']))
        launch = evidence.parse_json(row['launch']); terminal_envelope = evidence.parse_json(row['backtest_response'])
        job = launch['response']['backtest']['backtestId']
        request, response = evidence._envelope(row['backtest_response'], {'projectId', 'backtestId'}, 'backtests/read')
        evidence._project(request, response, manifest)
        terminal = response.get('backtest')
        if (type(terminal) is not dict or request['backtestId'] != job or terminal.get('backtestId') != job
                or terminal.get('completed') is not True or type(terminal.get('status')) is not str
                or terminal['status'] not in {'Completed', 'Completed.', 'Runtime Error', 'Error', 'Stopped', 'Cancelled'}
                or 'error' not in terminal): raise Refusal('known exact terminal required')
        if terminal['error'] is not None and (type(terminal['error']) is not str or not terminal['error']):
            raise Refusal('typed known terminal error required')
        if terminal['status'] in {'Runtime Error', 'Error'} and terminal['error'] is None:
            raise Refusal('actual runtime error evidence required')
        if terminal['status'] in {'Completed', 'Completed.'}:
            progress = terminal.get('progress')
            if type(progress) is not evidence.JsonNumber or progress.fraction() != 1: raise Refusal('complete numeric progress required')
        if 'projectId' in terminal and _int(terminal['projectId']) != _int(manifest['project_id']): raise Refusal('terminal project mismatch')
        if _int(evidence.parse_json(row['reservation'])['attempt'], 3) != attempt or manifest['candidate_id'] != candidate:
            raise Refusal('terminal reservation identity mismatch')
        prefix = candidate + '.attempt.' + str(attempt)
        evidence.validate_execution_binding(row['manifest'], expected_manifest_sha256=digest(row['manifest']),
            config_raw=self.candidate(candidate)['config_raw'].encode(), reservation_raw=row['reservation'],
            compile_response_raw=row['compile_response'], compile_receipt_raw=self.read(prefix + '.compile-verified.json'),
            readback_raw=self.read(prefix + '.launch-readback.json'), launch_raw=row['launch'])
        return terminal_envelope

    def _collect_native_chart(self, candidate, manifest, job, name, chart_name, sessions):
        """One bounded own-job read; loading is retained, never auto-retried."""
        stage = name + '.chart.' + CHARTS[chart_name]
        payload = {'projectId': _int(manifest['project_id']), 'backtestId': job, 'name': chart_name,
            'count': CHART_COUNT, 'start': CHART_START, 'end': CHART_END}
        self.write(stage + '.spent.json', {'at': now(), 'endpoint': 'backtests/chart/read',
            'payload_sha256': digest(canonical(payload)), 'manifest_sha256': self.manifest_hash,
            'backtest_id': job, 'read_only': True, 'new_looks': 0, 'automatic_retry': False})
        response = self.request('backtests/chart/read', payload, candidate=candidate, stage=stage)
        identity = _returned_identity(response, manifest['project_id'], job)
        envelope = canonical({'schema': 'tpr-ext26-native-read-envelope-v1', 'endpoint': 'backtests/chart/read',
            'request': payload, 'response': response, 'returned_identity_checks': identity})
        self.write(stage + '.envelope.json', envelope)
        result = {'chart_name': chart_name, 'request_response_envelope_sha256': digest(envelope),
            'response_projection_sha256': digest(canonical(response)), 'returned_identity_checks': identity,
            'read_only': True, 'new_looks': 0, 'automatic_retry': False}
        if chart_name == 'EXT26 Account NAV':
            observation, raw = _account_nav_chart(response, sessions)
            result['daily_account_observations'] = observation
            if raw is not None: self.write(stage + '.normalized-nav.json', raw)
        else:
            chart = response.get('chart')
            result['classification'] = ('diagnostic_loading_chart' if response.get('status') in {'loading', 'Loading'}
                else 'diagnostic_default_equity_control' if type(chart) is dict and chart.get('name') == chart_name
                else 'diagnostic_missing_chart')
            result['complete_daily_account_nav'] = False
        self.write(stage + '.completed.json', result)
        return result

    def collect_native(self, candidate, attempt):
        """Permitted native account/aggregate evidence, not restricted Object export.

        Full private cloud chunks remain unexported. Compact aggregate logs and
        native API evidence must not be claimed as independently replayed rows.
        """
        with self.locked():
            prefix, manifest = self.attempt(candidate, attempt)
            sessions = _bundle_calendar(self.candidate(candidate))
            _, history = self.history(candidate)
            terminal = self.validate_terminal(candidate, attempt, history[attempt - 1])
            backtest = terminal['response']['backtest']; job = backtest['backtestId']
            name = prefix + '.native.' + self.operation
            self.write(name + '.spent.json', {'at': now(), 'backtest_id': job, 'new_looks': 0, 'object_export': False})
            payload = {'projectId': _int(manifest['project_id']), 'backtestId': job}
            response = self.request('backtests/read', payload, candidate=candidate)
            fresh_envelope = self.envelope('backtests/read', payload, response)
            self.write(name + '.backtest-envelope.json', fresh_envelope)
            row = dict(history[attempt - 1]); closure = evidence.parse_json(row['closure'])
            closure['backtest_response_sha256'] = digest(fresh_envelope)
            row['closure'], row['backtest_response'] = canonical(closure), fresh_envelope
            backtest = self.validate_terminal(candidate, attempt, row)['response']['backtest']
            selected = {key: value for key, value in backtest.items() if key != 'charts'}
            selected['charts'] = {key: value for key, value in backtest.get('charts', {}).items()
                if key in {'Strategy Equity', 'EXT26 Account NAV', 'Drawdown', 'Portfolio Turnover'}} if type(backtest.get('charts')) is dict else {}
            self.write(name + '.account.json', selected)
            charts = {chart_name: self._collect_native_chart(candidate, manifest, job, name, chart_name, sessions)
                for chart_name in CHARTS}
            inventories = {}
            for marker, maximum in (('EXT26_SUMMARY', 24576), ('EXT26_EVIDENCE_INDEX', 8192)):
                payload = {'projectId': _int(self.project(candidate)['project_id']), 'backtestId': job,
                           'start': 0, 'end': 100, 'query': marker}
                logs = self.request('backtests/read/log', payload, candidate=candidate)
                self.write(name + '.' + marker + '.projection.json', logs)
                identity = _returned_identity(logs, manifest['project_id'], job)
                envelope = canonical({'schema': 'tpr-ext26-native-read-envelope-v1', 'endpoint': 'backtests/read/log',
                    'request': payload, 'response': logs, 'returned_identity_checks': identity})
                self.write(name + '.' + marker + '.envelope.json', envelope)
                rows = logs.get('logs'); length = logs.get('length')
                count = 0 if type(length) is evidence.JsonNumber and length.lexeme == '0' else _int(length, 100)
                if (type(rows) is not list or len(rows) != count or any(type(line) is not str or len(line) > maximum + 100
                        or marker not in line for line in rows)):
                    raise Refusal('bounded complete compact aggregate census refused')
                inventories[marker] = {'count': count, 'projection_sha256': digest(canonical(logs)),
                    'request_response_envelope_sha256': digest(envelope), 'returned_identity_checks': identity}
                if count == 1:
                    aggregate = compact_aggregate(rows[0], marker, manifest, attempt, job)
                    self.write(name + '.' + marker + '.aggregate.json', aggregate)
                    inventories[marker]['aggregate_sha256'] = digest(canonical(aggregate))
            result = {'candidate_id': candidate, 'attempt': attempt, 'backtest_id': job, 'native_account_sha256': digest(canonical(selected)),
                'compact_aggregate_inventories': inventories, 'chart_inventories': charts,
                'native_backtest_envelope_sha256': digest(fresh_envelope),
                'returned_identity_checks': _returned_identity(response, manifest['project_id'], job),
                'has_account_chart': charts['EXT26 Account NAV']['daily_account_observations']['complete_daily_account_nav'],
                'classification': 'native_evidence_requires_accounting_audit' if all(item['count'] == 1 for item in inventories.values())
                    and charts['EXT26 Account NAV']['daily_account_observations']['complete_daily_account_nav']
                    else 'diagnostic_missing_evidence', 'full_object_chunks_downloaded': False,
                'independent_input_row_replay': False, 'strategy_accepted': False, 'new_looks': 0}
            self.write(name + '.completed.json', result); return result

    def upload_inputs(self, candidate):
        if evidence.CANDIDATES[self.candidate(candidate)['candidate_id']] != 'tpr_on': raise Refusal('OFF cannot read/upload signal inputs')
        with self.locked():
            organization = self.project(candidate)['organization_id']
            for row in self.manifest['inputs']:
                stage = 'input.' + row['sha256']
                self.write(stage + '.read.spent.json', {'at': now(), 'name': row['name'], 'sha256': row['sha256'], 'manifest_sha256': self.manifest_hash})
                input_root = self.root / 'fixture-inputs' if self.fixture else INPUT_ROOT
                data = read_private(input_root, row['name'], MAX_INPUT_BYTES)
                if _input_digest(data) != row['sha256'] or len(data) != _int(row['bytes'], MAX_INPUT_BYTES): raise Refusal('fresh input bytes changed')
                boundary = 'tpr-ext26-' + row['sha256']
                wire = b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n').encode()
                    for field, value in (('organizationId', organization), ('key', row['key'])))
                wire += (f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="{row["sha256"]}.json"\r\nContent-Type: application/json\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
                self.effect('object/set', wire, stage + '.upload', content_type='multipart/form-data; boundary=' + boundary)
                self.write(stage + '.completed.json', {'sha256': row['sha256'], 'key': row['key'], 'bytes': row['bytes']})
            return {'uploaded_count': len(self.manifest['inputs']), 'private_only': True}
