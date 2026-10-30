"""Pure exact OFF mark-witness validation and safe relative-clock projection.

This module opens nothing and performs no native/API effect. A caller must
establish fresh source/HEAD/access claims and real project/job custody BEFORE
supplying private bytes, including when using these definitions inside QC.
Supplied binding hashes authenticate neither that caller nor its custody.

Official /object/get creates an export job and signed download URL, not a
bounded raw JSON read. Official export permission and download-host custody
are unproved here; no downloader or fabricated production adapter is offered.
Existing own-job readback pointers may suffice without retrieving this body.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import re
from zoneinfo import ZoneInfo

STUDY = 'TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1'
PROJECT = 37650980
MAX_BYTES = 4096
MODULE = 'research/target_price_revisions_qc/comparison_20261028_mark_read.py'
PRODUCER = 'research/target_price_revisions_qc/comparison_20261028_algorithm.py'
GET_DOCUMENTATION = 'https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/object-store-management/get-object-store-file'
EXPORT_DOCUMENTATION = 'https://www.quantconnect.com/docs/v2/cloud-platform/object-store'
NY = ZoneInfo('America/New_York')
PREDICATE_KEYS = frozenset(('observed_equals_expected', 'expected_date_equals_algorithm',
    'observed_date_equals_session', 'observed_relation'))
BODY_KEYS = frozenset(('schema', 'study_id', 'candidate_id', 'arm', 'operation_id', 'attempt',
    'config_sha256', 'source_template_closure_sha256', 'policy_sha256', 'calendar_sha256',
    'project_id', 'job_id', 'security_id', 'data_type', 'algorithm_utc', 'algorithm_local',
    'expected_close_utc', 'expected_close_local', 'observed_end_utc', 'observed_end_local',
    'predicates', 'guard_unchanged', 'source_inputs_admitted', 'strategy_accepted', 'canonical_admission'))
POINTER_KEYS = frozenset(('schema', 'status', 'key', 'bytes', 'expected_sha256', 'verified_sha256',
    'readback_verified', 'data_type', 'predicates'))
BINDING_ARGUMENTS = ('operation_id', 'git_head', 'source_hashes', 'off_operation_id', 'attempt',
    'job_id', 'config_sha256', 'source_template_closure_sha256', 'policy_sha256', 'calendar_sha256',
    'expected_sha256', 'expected_bytes')
V2_MODE = 'strict_minute_or_raw_daily_equal_close_v1'
V2_REASONS = frozenset(('valuation_clock', 'not_real_minute_trade_bar',
    'minute_or_native_close_wrong_day_or_future', 'ineligible_minute_or_precise_daily_clock',
    'native_job_custody', 'native_raw_config_unproven', 'native_cache_reference_changed',
    'captured_price_or_clock_mismatch', 'native_snapshot_changed', 'daily_scope_already_attempted',
    'daily_count_not_exactly_one', 'daily_identity_type_or_clock', 'daily_price_or_volume_mismatch',
    'daily_native_request_or_representation_failed', 'mark_native_or_representation_failed',
    'daily_access_claim_key_exists_or_unknown', 'daily_access_claim_publication_failed',
    'daily_access_claim_readback_mismatch', 'daily_access_claim_budget_exhausted'))
V2_BODY_KEYS = (BODY_KEYS-{'guard_unchanged'}) | {'valuation_verification_mode', 'verification_policy_extended'}
V2_POINTER_KEYS = POINTER_KEYS | {'reason_code', 'valuation_verification_mode'}


class MarkReadRefusal(ValueError):
    """Fixed body-free refusal; never copy supplied values into an exception."""


def _fail():
    raise MarkReadRefusal('exact private OFF mark witness refused') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        _fail()


def _hash(value, length=64):
    if type(value) is not str or re.fullmatch('[a-f0-9]{'+str(length)+'}', value) is None or set(value) == {'0'}:
        _fail()
    return value


def _identity(value, prefix=''):
    if (type(value) is not str or not 0 < len(value) <= 160
            or re.fullmatch(r'[A-Za-z0-9_.-]+', value) is None or not value.startswith(prefix)):
        _fail()
    return value


def _integer(value, maximum, minimum=1):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _predicates(value):
    _closed(value, PREDICATE_KEYS)
    if (any(type(value[name]) is not bool for name in PREDICATE_KEYS-{'observed_relation'})
            or value['observed_relation'] not in ('before', 'after', 'equal')):
        _fail()
    return dict(value)


def prepare_binding(*, operation_id, git_head, source_hashes, off_operation_id, attempt, job_id,
        config_sha256, source_template_closure_sha256, policy_sha256, calendar_sha256,
        expected_sha256, expected_bytes):
    """Freeze supplied identities without allocating a scope, read or native right."""
    _identity(operation_id, 'TPR-CMP28-MARK-')
    _hash(git_head, 40)
    _identity(off_operation_id, 'TPR-CMP28-OFF-')
    _integer(attempt, 2**31-1)
    _hash(job_id, 32)
    _integer(expected_bytes, MAX_BYTES)
    for digest in (config_sha256, source_template_closure_sha256, policy_sha256, calendar_sha256, expected_sha256):
        _hash(digest)
    if type(source_hashes) is not dict or set(source_hashes) != {MODULE, PRODUCER}:
        _fail()
    for digest in source_hashes.values():
        _hash(digest)
    key = ('tpr-cmp28/evidence/' + STUDY + '/' + off_operation_id + '/' + config_sha256
        + '/attempt-' + str(attempt) + '/' + str(PROJECT) + '/' + job_id + '/mark-refusal.json')
    return {'schema': 'tpr-cmp28-mark-read-binding-v1', 'operation_id': operation_id, 'git_head': git_head,
        'source_hashes': dict(source_hashes), 'study_id': STUDY, 'candidate_id': STUDY+'-OFF', 'arm': 'cap_off',
        'project_id': PROJECT, 'off_operation_id': off_operation_id, 'attempt': attempt, 'job_id': job_id,
        'config_sha256': config_sha256, 'source_template_closure_sha256': source_template_closure_sha256,
        'policy_sha256': policy_sha256, 'calendar_sha256': calendar_sha256, 'expected_sha256': expected_sha256,
        'expected_bytes': expected_bytes, 'max_bytes': MAX_BYTES, 'key': key,
        'native_effects_authorized': False, 'source_binding_authenticated': False,
        'object_download_authorized': False, 'strategy_accepted': False, 'canonical_admission': False}


def _binding(binding):
    if type(binding) is not dict or not set(BINDING_ARGUMENTS) <= set(binding):
        _fail()
    expected = prepare_binding(**{name: binding[name] for name in BINDING_ARGUMENTS})
    try:
        if binding != expected or _canonical(binding) != _canonical(expected):
            _fail()
    except (ValueError, TypeError, RecursionError):
        _fail()
    return expected


def validate_pointer(pointer, *, binding):
    """Accept the exact source producer's readback-verified pointer only."""
    scope = _binding(binding)
    _closed(pointer, POINTER_KEYS)
    if (pointer['schema'] != 'tpr-cmp28-mark-refusal-pointer-v1' or pointer['status'] != 'verified'
            or pointer['key'] != scope['key'] or type(pointer['bytes']) is not int
            or pointer['bytes'] != scope['expected_bytes'] or pointer['expected_sha256'] != scope['expected_sha256']
            or pointer['verified_sha256'] != scope['expected_sha256'] or pointer['readback_verified'] is not True
            or pointer['data_type'] != 'trade_bar'):
        _fail()
    return {'schema': 'tpr-cmp28-safe-mark-pointer-v1', 'prefix_sha256': _sha((scope['key'].rsplit('/', 1)[0]+'/').encode()),
        'witness_sha256': scope['expected_sha256'], 'witness_bytes': scope['expected_bytes'],
        'predicates': _predicates(pointer['predicates']), 'native_custody_independently_proven': False,
        'strategy_accepted': False, 'canonical_admission': False}


def _parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail()
            result[key] = value
        return result
    def forbidden(_):
        _fail()
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=forbidden, parse_constant=forbidden)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        _fail()


def _clock(utc_text, local_text):
    try:
        if type(utc_text) is not str or type(local_text) is not str or max(len(utc_text), len(local_text)) > 40:
            _fail()
        clock = datetime.fromisoformat(utc_text)
        if (clock.utcoffset() != timedelta(0) or clock.isoformat() != utc_text
                or clock.astimezone(NY).isoformat() != local_text):
            _fail()
        return clock
    except (ValueError, TypeError, OverflowError):
        _fail()


def project_witness(raw, *, binding, pointer):
    """Pure supplied-byte processing; output no raw SID, date, price or clock."""
    scope = _binding(binding)
    safe_pointer = validate_pointer(pointer, binding=scope)
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES or len(raw) != scope['expected_bytes']
            or _sha(raw) != scope['expected_sha256']):
        _fail()
    body = _parse(raw)
    _closed(body, BODY_KEYS)
    if (body['schema'] != 'tpr-cmp28-private-mark-refusal-v1' or body['operation_id'] != scope['off_operation_id']
            or type(body['attempt']) is not int or body['attempt'] != scope['attempt']
            or type(body['project_id']) is not int or body['project_id'] != PROJECT
            or any(body[name] != scope[name] for name in ('study_id', 'candidate_id', 'arm', 'job_id',
                'config_sha256', 'source_template_closure_sha256', 'policy_sha256', 'calendar_sha256'))
            or body['data_type'] != 'trade_bar' or body['guard_unchanged'] is not True
            or any(body[name] is not False for name in ('source_inputs_admitted', 'strategy_accepted', 'canonical_admission'))):
        _fail()
    sid = body['security_id']
    if (type(sid) is not str or not 0 < len(sid) <= 256 or sid.strip() != sid
            or any(ord(char) < 32 or ord(char) == 127 for char in sid)):
        _fail()
    try:
        sid_hash = _sha(sid.encode('utf-8'))
    except UnicodeError:
        _fail()
    algorithm = _clock(body['algorithm_utc'], body['algorithm_local'])
    expected = _clock(body['expected_close_utc'], body['expected_close_local'])
    observed = _clock(body['observed_end_utc'], body['observed_end_local'])
    predicates = {'observed_equals_expected': observed == expected,
        'expected_date_equals_algorithm': expected.date() == algorithm.date(),
        'observed_date_equals_session': observed.astimezone(NY).date() == algorithm.astimezone(NY).date(),
        'observed_relation': 'before' if observed < expected else 'after' if observed > expected else 'equal'}
    if (_predicates(body['predicates']) != predicates or safe_pointer['predicates'] != predicates):
        _fail()
    return {'schema': 'tpr-cmp28-safe-mark-witness-v1', 'witness_sha256': scope['expected_sha256'],
        'witness_bytes': len(raw), 'prefix_sha256': safe_pointer['prefix_sha256'], 'security_id_sha256': sid_hash,
        'data_type': 'trade_bar', 'predicates': predicates,
        'observed_minus_expected_microseconds': (observed-expected)//timedelta(microseconds=1),
        'algorithm_minus_expected_microseconds': (algorithm-expected)//timedelta(microseconds=1),
        'observed_minus_algorithm_microseconds': (observed-algorithm)//timedelta(microseconds=1),
        'private_reads_performed': 0, 'native_effects_performed': 0, 'diagnostic_only': True,
        'source_binding_authenticated': False, 'native_custody_independently_proven': False,
        'source_inputs_admitted': False, 'strategy_accepted': False, 'canonical_admission': False}


def prepare_binding_v2(**arguments):
    """Explicit future v2 binding; historical v1 is never upgraded in place."""
    binding = prepare_binding(**arguments)
    binding.update(schema='tpr-cmp28-mark-read-binding-v2',
        witness_schema='tpr-cmp28-private-mark-refusal-v2',
        pointer_schema='tpr-cmp28-mark-refusal-pointer-v2', valuation_verification_mode=V2_MODE)
    return binding


def _binding_v2(binding):
    if type(binding) is not dict or not set(BINDING_ARGUMENTS) <= set(binding):
        _fail()
    expected = prepare_binding_v2(**{name: binding[name] for name in BINDING_ARGUMENTS})
    try:
        if binding != expected or _canonical(binding) != _canonical(expected):
            _fail()
    except (ValueError, TypeError, RecursionError):
        _fail()
    return expected


def validate_pointer_v2(pointer, *, binding):
    """Exact D010 verified pointer; a mode/reason marker grants no admission."""
    scope = _binding_v2(binding)
    _closed(pointer, V2_POINTER_KEYS)
    if (pointer['schema'] != scope['pointer_schema'] or pointer['status'] != 'verified'
            or pointer['key'] != scope['key'] or type(pointer['bytes']) is not int
            or pointer['bytes'] != scope['expected_bytes'] or pointer['expected_sha256'] != scope['expected_sha256']
            or pointer['verified_sha256'] != scope['expected_sha256'] or pointer['readback_verified'] is not True
            or pointer['data_type'] != 'trade_bar' or pointer['valuation_verification_mode'] != V2_MODE
            or type(pointer['reason_code']) is not str or pointer['reason_code'] not in V2_REASONS):
        _fail()
    return {'schema': 'tpr-cmp28-safe-mark-pointer-v2', 'prefix_sha256': _sha((scope['key'].rsplit('/', 1)[0]+'/').encode()),
        'witness_sha256': scope['expected_sha256'], 'witness_bytes': scope['expected_bytes'],
        'predicates': _predicates(pointer['predicates']), 'reason_code': pointer['reason_code'],
        'valuation_verification_mode': V2_MODE, 'verification_policy_authenticated': False,
        'native_custody_independently_proven': False, 'strategy_accepted': False, 'canonical_admission': False}


def project_witness_v2(raw, *, binding, pointer):
    """Validate v2 directly; never manufacture the historical v1 guard marker."""
    scope = _binding_v2(binding)
    safe_pointer = validate_pointer_v2(pointer, binding=scope)
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES or len(raw) != scope['expected_bytes']
            or _sha(raw) != scope['expected_sha256']):
        _fail()
    body = _parse(raw)
    _closed(body, V2_BODY_KEYS)
    if (body['schema'] != scope['witness_schema'] or body['operation_id'] != scope['off_operation_id']
            or type(body['attempt']) is not int or body['attempt'] != scope['attempt']
            or type(body['project_id']) is not int or body['project_id'] != PROJECT
            or any(body[name] != scope[name] for name in ('study_id', 'candidate_id', 'arm', 'job_id',
                'config_sha256', 'source_template_closure_sha256', 'policy_sha256', 'calendar_sha256'))
            or body['data_type'] != 'trade_bar' or body['valuation_verification_mode'] != V2_MODE
            or body['verification_policy_extended'] is not True
            or any(body[name] is not False for name in ('source_inputs_admitted', 'strategy_accepted', 'canonical_admission'))):
        _fail()
    sid = body['security_id']
    if (type(sid) is not str or not 0 < len(sid) <= 256 or sid.strip() != sid
            or any(ord(char) < 32 or ord(char) == 127 for char in sid)):
        _fail()
    try:
        sid_hash = _sha(sid.encode('utf-8'))
    except UnicodeError:
        _fail()
    algorithm = _clock(body['algorithm_utc'], body['algorithm_local'])
    expected = _clock(body['expected_close_utc'], body['expected_close_local'])
    observed = _clock(body['observed_end_utc'], body['observed_end_local'])
    predicates = {'observed_equals_expected': observed == expected,
        'expected_date_equals_algorithm': expected.date() == algorithm.date(),
        'observed_date_equals_session': observed.astimezone(NY).date() == algorithm.astimezone(NY).date(),
        'observed_relation': 'before' if observed < expected else 'after' if observed > expected else 'equal'}
    if (_predicates(body['predicates']) != predicates or safe_pointer['predicates'] != predicates):
        _fail()
    return {'schema': 'tpr-cmp28-safe-mark-witness-v2', 'witness_sha256': scope['expected_sha256'],
        'witness_bytes': len(raw), 'prefix_sha256': safe_pointer['prefix_sha256'], 'security_id_sha256': sid_hash,
        'data_type': 'trade_bar', 'predicates': predicates, 'reason_code': safe_pointer['reason_code'],
        'valuation_verification_mode': V2_MODE, 'verification_policy_extended': True,
        'verification_policy_authenticated': False,
        'observed_minus_expected_microseconds': (observed-expected)//timedelta(microseconds=1),
        'algorithm_minus_expected_microseconds': (algorithm-expected)//timedelta(microseconds=1),
        'observed_minus_algorithm_microseconds': (observed-algorithm)//timedelta(microseconds=1),
        'private_reads_performed': 0, 'native_effects_performed': 0, 'diagnostic_only': True,
        'source_binding_authenticated': False, 'native_custody_independently_proven': False,
        'source_inputs_admitted': False, 'strategy_accepted': False, 'canonical_admission': False}
