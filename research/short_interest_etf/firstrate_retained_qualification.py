"""Pure assessment of a retained aggregate, never historical/source authority.

Anyone may supply these bytes. Only the separate held loader authenticates a
historical observation. Counts, dates and dispositions returned here are PRIVATE;
the public projection contains hashes and closed authority only. No rows exist
in this interface and reported DTC is neither recomputed nor made an S1 gate.
"""
from datetime import date
import hashlib
import json
import re
import sys
from types import FrameType

SCHEMA = 'si-firstrate-retained-qualification-v1'
INSPECTION_SCHEMA = 'si-firstrate-supplied-byte-inspection-v1'
INSPECTION_POLICY_SHA256 = 'a403579c17c31010ae26eaddf1350a7f1d313cbf6bdae9b6d815f1ccd83121fe'
POLICY_SHA256 = '9408f0c4c4f2edca105c9f710670ed34d3fef507bdf0bb6b44bce0e266063230'
MAX_BYTES, MAX_ASSESSMENT_BYTES = 16384, 32768
MAX_ROWS, MAX_MEMBERS, MAX_INFLATED = 3000000, 50000, 128 * 1024**2
PINS = (('full', 34319601, '08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8'),
        ('year', 9660009, '3a8a07dec5c91f4e54cda396d9b1483895769d6ecac1a8d1a15a64e873fa191a'),
        ('manifest', 327907, 'c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8'),
        ('readme', 1051, 'bbcddf477ba3ffacb4b0116e9d3f6c2c2a864576ae748abc8daa825602a16ecf'))
GAPS = ('settlement_is_not_public_availability', 'revision_vintage_unverified',
        'filename_is_not_native_or_share_class_identity', 'same_date_own_class_denominator_missing',
        'DTC_volume_basis_and_rounding_contract_unverified', 'source_custody_and_upstream_authentication_unqualified',
        'processing_rights_and_actual_input_admission_unqualified')
REASONS = ('row_width', 'field_length', 'settlement_date', 'short_interest_numeric',
           'avg_daily_share_volume_numeric', 'days_to_cover_numeric', 'short_interest_nonintegral',
           'duplicate_settlement_all_peers')
OBSERVATIONS = ('fractional_average_volume', 'zero_average_volume', 'zero_average_volume_positive_SI',
                'zero_average_volume_positive_reported_DTC')
REPORT_KEYS = ('archive_sha256', 'archive_bytes', 'member_count', 'inflated_bytes', 'rows',
               'structurally_clear_rows', 'quarantined_rows', 'empty_members', 'row_reason_counts',
               'reported_field_observations', 'earliest_settlement_date', 'latest_settlement_date',
               'distinct_settlement_dates', 'member_origin_disposition_commitment_sha256',
               'all_member_tokens_commitment_sha256', 'year_2026_tokens_commitment_sha256',
               'year_2026_rows', 'year_2026_members', 'all_members_CRC_verified',
               'complete_byte_inspection', 'DTC_recalculated_or_substituted')
MODEL_AUTHORITY = {'inspection_only': True, **{key: False for key in
    ('source_admitted', 'custody_qualified', 'upstream_authentication_verified', 'historical_availability_verified',
     'point_in_time_data', 'native_identity_admitted', 'share_class_admitted', 'same_class_denominator_admitted',
     'actual_input_execution_admitted', 'ready_for_backtesting', 'outcome_access_authorized', 'qc_authorized', 'trading_authority')},
    **{key: 0 for key in ('provider_HTTP', 'credential_reads', 'new_claims', 'new_STARTs', 'new_charged_bytes',
                         'outcome_looks', 'allocated_alpha', 'qc_attempts')}}
_ISSUED, _FAILED = {}, set()
_ORIGINAL_ISSUED, _ORIGINAL_FAILED = _ISSUED, _FAILED
_CODES = frozenset('bytes JSON schema policy authority archive accounting dates pair factory changed'.split())


class RetainedQualificationRefusal(ValueError):
    pass


def _require(value, code):
    if not value:
        raise RetainedQualificationRefusal(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def authority():
    return {'structural_aggregate_only': True, **{key: False for key in
        ('source_authenticated', 'historical_process_reobserved', 'source_admitted', 'custody_qualified',
         'historical_availability_verified', 'point_in_time_data', 'native_identity_admitted', 'share_class_admitted',
         'CIK_admitted', 'USD_currency_admitted', 'same_class_denominator_admitted', 'actual_input_execution_admitted',
         'ready_for_backtest', 'outcome_access_authorized', 'qc_authorized', 'trading_authority')},
        **{key: 0 for key in ('provider_HTTP', 'credential_reads', 'new_claims', 'new_STARTs', 'new_charged_bytes',
                             'outcome_looks', 'allocated_alpha', 'qc_attempts')}}


def qualification_policy():
    return {'schema': SCHEMA + '-policy', 'input_schema': INSPECTION_SCHEMA,
            'inspection_policy_sha256': INSPECTION_POLICY_SHA256, 'original_pins': [list(row) for row in PINS],
            'maximum_aggregate_bytes': MAX_BYTES, 'maximum_rows_per_archive': MAX_ROWS,
            'maximum_assessment_bytes': MAX_ASSESSMENT_BYTES,
            'maximum_members_per_archive': MAX_MEMBERS, 'maximum_inflated_bytes_per_archive': MAX_INFLATED,
            'report_fields': list(REPORT_KEYS), 'reason_fields': list(REASONS), 'observation_fields': list(OBSERVATIONS),
            'inspection_authority': dict(MODEL_AUTHORITY),
            'reason_counts': 'overlapping_issues_positive_per_reason_never_sum_equal_quarantined',
            'pair': 'retain_match_or_discordance_zero_mismatch_requires_reported_commitment_and_count_concordance',
            'dispositions': 'quarantines_and_reported_attributes_retained_no_drop_no_DTC_recalculation_or_S1_gate',
            'dates': 'canonical_ISO_settlement_dates_only_not_publication_revision_or_availability',
            'consumer': 'private_aggregate_only_no_rows_cells_compiler_lease_or_historical_source_authentication',
            'seal': 'original_policy_authority_code_and_bytes_snapshots_factory_closed_public_projection_failure_latches',
            'semantic_gaps': list(GAPS), 'authority': authority()}


def _registered():
    _require(POLICY_SHA256 == _FROZEN_POLICY_SHA and type(POLICY_SHA256) is str
             and re.fullmatch('[0-9a-f]{64}', POLICY_SHA256)
             and authority is _AUTHORITY and _AUTHORITY.__code__ is _AUTHORITY_CODE
             and qualification_policy is _POLICY and _POLICY.__code__ is _POLICY_CODE
             and _canonical(_POLICY()) == _FROZEN_POLICY_BYTES
             and _sha(_FROZEN_POLICY_BYTES) == _FROZEN_POLICY_SHA
             and _AUTHORITY_BYTES is _ORIGINAL_AUTHORITY_BYTES
             and _AUTHORITY_BYTES == _canonical(_AUTHORITY())
             and _AUTHORITY_BYTES == _canonical(_json(_FROZEN_POLICY_BYTES)['authority']), 'policy')


def _exact(value, expected):
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return set(value) == set(expected) and all(_exact(value[key], item) for key, item in expected.items())
    if type(expected) is list:
        return len(value) == len(expected) and all(_exact(a, b) for a, b in zip(value, expected))
    return value == expected


def _integer(value, maximum, minimum=0):
    _require(type(value) is int and minimum <= value <= maximum, 'accounting')
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'JSON'); result[key] = value
    return result


def _json(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda unused: _require(False, 'JSON'))
        _require(_canonical(value) == raw, 'JSON')
        return value
    except (UnicodeError, ValueError, TypeError, OverflowError):
        raise RetainedQualificationRefusal('JSON') from None


def _report(value, role):
    _require(type(value) is dict and set(value) == set(REPORT_KEYS), 'schema')
    unused, length, digest = next(row for row in PINS if row[0] == role)
    _require(type(value['archive_bytes']) is int and value['archive_bytes'] == length
             and value['archive_sha256'] == digest, 'archive')
    members = _integer(value['member_count'], MAX_MEMBERS, 1)
    _integer(value['inflated_bytes'], min(MAX_INFLATED, members * 1024**2), 1)
    rows = _integer(value['rows'], MAX_ROWS)
    clear = _integer(value['structurally_clear_rows'], rows)
    quarantined = _integer(value['quarantined_rows'], rows)
    empty = _integer(value['empty_members'], members)
    _require(clear + quarantined == rows and members - empty <= rows, 'accounting')
    _require(value['all_members_CRC_verified'] is True and value['complete_byte_inspection'] is True
             and value['DTC_recalculated_or_substituted'] is False, 'schema')
    reasons, observations = value['row_reason_counts'], value['reported_field_observations']
    _require(type(reasons) is dict and set(reasons) <= set(REASONS)
             and type(observations) is dict and set(observations) <= set(OBSERVATIONS), 'schema')
    for count in reasons.values(): _integer(count, quarantined, 1)
    _require(quarantined <= sum(reasons.values()) <= len(REASONS) * quarantined, 'accounting')
    for count in observations.values(): _integer(count, rows, 1)
    _require(all(observations.get(key, 0) <= observations.get('zero_average_volume', 0) for key in
                 ('zero_average_volume_positive_SI', 'zero_average_volume_positive_reported_DTC')), 'accounting')
    valid_dates = rows - reasons.get('settlement_date', 0)
    distinct = _integer(value['distinct_settlement_dates'], valid_dates)
    earliest, latest = value['earliest_settlement_date'], value['latest_settlement_date']
    if distinct == 0:
        _require(earliest is None and latest is None and valid_dates == 0, 'dates')
    else:
        _require(all(type(item) is str and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', item)
                     for item in (earliest, latest)), 'dates')
        try: beginning, ending = date.fromisoformat(earliest), date.fromisoformat(latest)
        except ValueError: raise RetainedQualificationRefusal('dates') from None
        _require(beginning.isoformat() == earliest and ending.isoformat() == latest and beginning <= ending
                 and distinct <= (ending - beginning).days + 1 and (distinct == 1) == (earliest == latest), 'dates')
    year_rows = _integer(value['year_2026_rows'], valid_dates)
    year_members = _integer(value['year_2026_members'], min(members, year_rows))
    _require((year_rows == 0) == (year_members == 0), 'accounting')
    if year_rows:
        _require(earliest is not None and earliest <= '2026-12-31' and latest >= '2026-01-01', 'dates')
    for key in ('member_origin_disposition_commitment_sha256', 'all_member_tokens_commitment_sha256',
                'year_2026_tokens_commitment_sha256'):
        _require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]), 'schema')


def _validate(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'bytes'); payload = _json(raw)
    fields = {'schema', 'policy_sha256', 'scope', 'full', 'year', 'manifest_sha256', 'readme_sha256',
              'selected_manifest_observations_match', 'paired_member_mismatches',
              'year_is_exact_full_2026_token_multiset_subset', 'semantic_gaps', 'authority'}
    _require(type(payload) is dict and set(payload) == fields and payload['schema'] == INSPECTION_SCHEMA
             and payload['policy_sha256'] == INSPECTION_POLICY_SHA256 and payload['scope'] == 'registered_full_and_2026_pair', 'schema')
    _require(_exact(payload['authority'], MODEL_AUTHORITY), 'authority')
    _require(_exact(payload['semantic_gaps'], list(GAPS)) and payload['selected_manifest_observations_match'] is True, 'schema')
    for role in ('manifest', 'readme'):
        _require(payload[role + '_sha256'] == next(row[2] for row in PINS if row[0] == role), 'archive')
    for role in ('full', 'year'): _report(payload[role], role)
    full, year = payload['full'], payload['year']
    mismatches = _integer(payload['paired_member_mismatches'], full['year_2026_members'] + year['member_count'])
    matched = payload['year_is_exact_full_2026_token_multiset_subset']
    _require(type(matched) is bool and matched == (mismatches == 0), 'pair')
    if matched:
        _require(full['year_2026_tokens_commitment_sha256'] == year['all_member_tokens_commitment_sha256']
                 == year['year_2026_tokens_commitment_sha256'] and full['year_2026_rows'] == year['rows'] == year['year_2026_rows']
                 and full['year_2026_members'] == year['member_count'] == year['year_2026_members']
                 and year['empty_members'] == 0 and year['row_reason_counts'].get('settlement_date', 0) == 0, 'pair')
    return payload


class RetainedAggregateAssessment:
    __slots__ = ('_anchor',)
    def __init__(self): raise RetainedQualificationRefusal('factory')
    def __setattr__(self, name, value): raise RetainedQualificationRefusal('changed')
    def canonical_bytes(self): return _access(self)[1]
    def to_payload(self): return _json(_access(self)[1])
    @property
    def sha256(self): return _access(self)[2]
    def public_summary(self):
        return _json(_access(self)[6])


def _access(value):
    row = _ORIGINAL_ISSUED.get(id(value))
    try:
        _registered()
        _require(_ISSUED is _ORIGINAL_ISSUED and _FAILED is _ORIGINAL_FAILED and id(value) not in _ORIGINAL_FAILED
                 and type(value) is _ASSESSMENT_CLASS and RetainedAggregateAssessment is _ASSESSMENT_CLASS
                 and type(row) is tuple and len(row) == 7 and row[0] is value and value._anchor is row
                 and type(row[1]) is bytes and _sha(row[1]) == row[2] and type(row[3]) is bytes and _sha(row[3]) == row[4], 'changed')
        frame = row[5]
        _require(type(frame) is FrameType and frame.f_code is _EVALUATOR_CODE and frame.f_globals is globals()
                 and evaluate_retained_aggregate is _EVALUATOR and _EVALUATOR.__code__ is _EVALUATOR_CODE
                 and frame.f_locals.get('value') is value and frame.f_locals.get('row') is row
                 and frame.f_locals.get('canonical_bytes') is row[3]
                 and type(row[6]) is bytes and frame.f_locals.get('public_raw') is row[6], 'changed')
        _require(all(_ASSESSMENT_CLASS.__dict__.get(name) is original and function.__code__ is code
                     for name, original, function, code in _METHOD_PINS), 'changed')
        return row
    except BaseException:
        if type(row) is tuple and row and row[0] is value: _ORIGINAL_FAILED.add(id(value))
        raise


def evaluate_retained_aggregate(canonical_bytes):
    """Assess supplied aggregate structure; input authenticity stays false."""
    _registered(); aggregate = _validate(canonical_bytes)
    payload = {'schema': SCHEMA, 'policy_sha256': POLICY_SHA256, 'input_aggregate_sha256': _sha(canonical_bytes),
               'inspection_aggregate': aggregate, 'structural_dispositions': {
                   'pair': 'reported_match' if aggregate['year_is_exact_full_2026_token_multiset_subset'] else 'reported_discordance_retained',
                   'rows': 'quarantine_dispositions_retained' if any(aggregate[role]['quarantined_rows'] for role in ('full', 'year')) else 'no_row_quarantines_reported',
                   'reported_attributes': 'retained_without_DTC_recalculation_or_S1_gate',
                   'temporal': 'settlement_only_availability_unverified'}, 'authority': _json(_ORIGINAL_AUTHORITY_BYTES)}
    raw = _canonical(payload); _require(len(raw) <= MAX_ASSESSMENT_BYTES, 'bytes')
    value = object.__new__(_ASSESSMENT_CLASS)
    public_raw = _canonical({'schema': 'si-firstrate-retained-qualification-summary-v1', 'policy_sha256': _FROZEN_POLICY_SHA,
                             'input_aggregate_sha256': _sha(canonical_bytes), 'assessment_sha256': _sha(raw),
                             'authority': _json(_ORIGINAL_AUTHORITY_BYTES)})
    row = (value, raw, _sha(raw), canonical_bytes, _sha(canonical_bytes), sys._getframe(), public_raw)
    object.__setattr__(value, '_anchor', row); _ORIGINAL_ISSUED[id(value)] = row
    _access(value)
    return value


def _failure_projector(authority_raw, codes, decode):
    def failure_summary(error):
        args = BaseException.args.__get__(error, BaseException)
        code = args[0] if type(error) is RetainedQualificationRefusal and len(args) == 1 and type(args[0]) is str and args[0] in codes else None
        return {'category': 'structural_aggregate_refusal' if code is not None else 'unclassified',
                'code': code, 'authority': decode(authority_raw)}
    return failure_summary


_ASSESSMENT_CLASS = RetainedAggregateAssessment
_AUTHORITY, _AUTHORITY_CODE = authority, authority.__code__
_POLICY, _POLICY_CODE = qualification_policy, qualification_policy.__code__
_FROZEN_POLICY_SHA, _FROZEN_POLICY_BYTES = POLICY_SHA256, _canonical(qualification_policy())
_AUTHORITY_BYTES = _canonical(authority())
_ORIGINAL_AUTHORITY_BYTES = _AUTHORITY_BYTES
failure_summary = _failure_projector(_ORIGINAL_AUTHORITY_BYTES, _CODES, _json)
_EVALUATOR, _EVALUATOR_CODE = evaluate_retained_aggregate, evaluate_retained_aggregate.__code__
_METHOD_PINS = tuple((name, descriptor, descriptor.fget if type(descriptor) is property else descriptor,
                      (descriptor.fget if type(descriptor) is property else descriptor).__code__)
                     for name, descriptor in RetainedAggregateAssessment.__dict__.items()
                     if name in ('canonical_bytes', 'to_payload', 'sha256', 'public_summary'))
