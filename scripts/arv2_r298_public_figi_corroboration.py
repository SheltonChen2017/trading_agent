"""Pure bounded corroboration of supplied PUBLIC-FIGI mapping responses.

No CUSIP, vendor permaticker, issuer row, credential, file or HTTP interface is
accepted here. The caller authenticates the actual request, response/status,
public provenance and secret checks. An observation never clears a vendor
collision, replaces an old FIGI, or proves a historical mapping or event.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
import time

SCHEMA = 'arv2-r298-public-figi-batch-v1'
PRIVATE_SCHEMA = SCHEMA + '-private'
CORROBORATION_SCHEMA = 'arv2-r298-public-figi-corroboration-v1'
MAX_JOBS, MAX_BATCHES, MAX_BODY = 10, 3, 2 * 1024 * 1024
MAX_REQUEST, MAX_FIELD_BYTES, MAX_MESSAGE_BYTES = 4096, 2048, 4096
MAX_RESULTS_PER_JOB, MAX_JSON_DEPTH, MAX_JSON_NODES = 15000, 8, 250000
RESULT_FIELDS = frozenset(('figi', 'securityType', 'marketSector', 'ticker', 'name',
    'exchCode', 'shareClassFIGI', 'compositeFIGI', 'securityType2', 'securityDescription'))
JOB_STATES = frozenset(('not_parsed_http_status', 'no_match', 'job_error_unknown',
    'job_warning_unknown', 'metadata_unavailable', 'ambiguous_results', 'identity_mismatch',
    'instrument_scope_unknown', 'composite_or_share_class_missing', 'hierarchy_level_inconsistent',
    'unique_us_equity_composite'))
OBSERVATIONS = frozenset(('same_current_us_composite_observed', 'unresolved_mapping_missing',
    'unresolved_http_status', 'unresolved_no_match', 'unresolved_job_error',
    'unresolved_metadata', 'unresolved_ambiguity', 'unresolved_identity_binding',
    'unresolved_instrument_scope', 'unresolved_composite_or_share_class_missing', 'unresolved_hierarchy_level',
    'unresolved_share_class_only', 'unresolved_composite_disagreement', 'unresolved_share_class_disagreement'))
FALSE_FLAGS = {'provider_contact_performed_by_helper': False, 'route_acceptance_granted': False,
    'old_figi_replacement_authorized': False, 'historical_mapping_proven': False,
    'corporate_event_proven': False, 'permanent_master_proven': False,
    'point_in_time_proven': False, 'price_input_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('figi', 'claims', 'request', 'http_status', 'failed_body', 'body',
    'json', 'json_bound', 'job_count', 'job_shape', 'result_shape', 'result_bound',
    'text', 'summary', 'private_record', 'batch_bound', 'duplicate_claim', 'deadline', 'unknown'))


class Refused(ValueError):
    """Finite predicates only; no mapping fields or provider text."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None
def _figi(value):
    # Same literal canonical alphabet/checksum as frozen public FIGI capture;
    # no import of its capture, credential or filesystem interfaces.
    if type(value) is not str or re.fullmatch('[B-DF-HJ-NP-TV-Z]{2}G[B-DF-HJ-NP-TV-Z0-9]{8}[0-9]', value) is None:
        return False
    values = [int(character, 36) * (1 if index % 2 == 0 else 2)
        for index, character in enumerate(value[:11])]
    total = sum(number // 10 + number % 10 for number in values)
    return int(value[-1]) == (10 - total % 10) % 10
def _pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}


def _deadline(deadline):
    if deadline is not None:
        require(type(deadline) in (int, float) and math.isfinite(deadline) and time.monotonic() < deadline, 'deadline')


def _claims(values):
    require(type(values) in (list, tuple) and 0 < len(values) <= MAX_JOBS
        and all(_figi(value) for value in values) and len(set(values)) == len(values), 'claims')
    return list(values)


def mapping_jobs(figis):
    """Public identifiers only; exact instrument lookup, no alternate-id retry."""
    return [{'idType': 'ID_BB_GLOBAL', 'idValue': value,
        'includeUnlistedEquities': True} for value in _claims(figis)]


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'json'); result[key] = value
    return result


def _decode(raw, maximum, deadline):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'body')
    quoted, escaped, depth, separators = False, False, 0, 0
    for index, value in enumerate(raw):
        if index % 65536 == 0: _deadline(deadline)
        if quoted:
            if escaped: escaped = False
            elif value == 92: escaped = True
            elif value == 34: quoted = False
        elif value == 34: quoted = True
        elif value in (123, 91): depth += 1; require(depth <= MAX_JSON_DEPTH, 'json_bound')
        elif value in (125, 93): depth -= 1; require(depth >= 0, 'json')
        elif value in (44, 58): separators += 1; require(separators <= MAX_JSON_NODES * 2, 'json_bound')
    require(not quoted and not escaped and depth == 0, 'json')
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
    except (ValueError, UnicodeError, RecursionError): raise Refused('json') from None
    pending, count = [result], 0
    while pending:
        value = pending.pop(); count += 1
        require(count <= MAX_JSON_NODES and type(value) in (dict, list, str, bool, int, type(None)), 'json_bound')
        if type(value) is dict: pending.extend(value.values())
        elif type(value) is list: pending.extend(value)
    return result


def _text(value, maximum, *, nullable=False):
    if value is None: return nullable
    if type(value) is not str: return False
    try: raw = value.encode('utf-8', 'strict')
    except UnicodeError: return False
    return len(raw) <= maximum and not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _result(row):
    require(type(row) is dict and 'figi' in row and _figi(row['figi']), 'result_shape')
    if 'metadata' in row:
        require(set(row) == {'figi', 'metadata'} and row['metadata'] == 'Metadata N/A', 'result_shape')
        return
    require(set(row) <= RESULT_FIELDS
        and all(_text(value, MAX_FIELD_BYTES, nullable=True) for value in row.values()), 'result_shape')
    require(all(row.get(field) is None or _figi(row[field]) for field in ('compositeFIGI', 'shareClassFIGI')), 'result_shape')


def _job(job, claimed, ordinal, deadline):
    require(type(job) is dict and set(job) in ({'data'}, {'error'}, {'warning'}), 'job_shape')
    state, count, rows_pin = None, 0, None
    if 'error' in job or 'warning' in job:
        key = 'error' if 'error' in job else 'warning'
        require(_text(job[key], MAX_MESSAGE_BYTES) and bool(job[key]), 'job_shape')
        state = 'no_match' if job[key] == 'No identifier found.' else 'job_' + key + '_unknown'
    else:
        rows = job['data']
        require(type(rows) is list and len(rows) < MAX_RESULTS_PER_JOB, 'result_bound')
        for row in rows: _deadline(deadline); _result(row)
        count, rows_pin = len(rows), sha(canonical(rows))
        if not rows: state = 'no_match'
        elif len(rows) != 1: state = 'ambiguous_results'
        else:
            row = rows[0]
            if row['figi'] != claimed: state = 'identity_mismatch'
            elif 'metadata' in row: state = 'metadata_unavailable'
            elif row.get('marketSector') != 'Equity' or row.get('exchCode') != 'US': state = 'instrument_scope_unknown'
            elif row.get('compositeFIGI') is None or row.get('shareClassFIGI') is None: state = 'composite_or_share_class_missing'
            # A US composite container cannot support a different instrument
            # FIGI as that same composite. Keep contradictory levels unknown.
            elif row['figi'] != row['compositeFIGI']: state = 'hierarchy_level_inconsistent'
            else: state = 'unique_us_equity_composite'
    return {'job_ordinal': ordinal, 'claim_sha256': sha(canonical(claimed)), 'state': state,
        'result_count': count, 'result_rows_sha256': rows_pin}


class PrivateMappingResults:
    __slots__ = ('_raw',)
    def __init__(self, record): object.__setattr__(self, '_raw', canonical(record))
    def __setattr__(self, name, value): raise TypeError('private mapping results are immutable')
    def __repr__(self): return '<PrivateMappingResults redacted; current public FIGI observations only>'
    def __reduce_ex__(self, protocol): raise TypeError('mapping results need explicitly private export')
    def private_record(self): return json.loads(self._raw)


def analyze_batch(figis, *, request_raw, response_raw, http_status, deadline=None):
    """Validate every supplied job; no first-result or retry selection exists."""
    _deadline(deadline); claims = _claims(figis)
    require(type(request_raw) is bytes and 0 < len(request_raw) <= MAX_REQUEST
        and request_raw == canonical(mapping_jobs(claims)), 'request')
    require(type(http_status) is int and 100 <= http_status <= 599, 'http_status')
    if http_status != 200:
        require(response_raw is None, 'failed_body')
        response, pin = None, None
        jobs = [{'job_ordinal': index, 'claim_sha256': sha(canonical(value)), 'state': 'not_parsed_http_status',
            'result_count': 0, 'result_rows_sha256': None} for index, value in enumerate(claims)]
    else:
        response = _decode(response_raw, MAX_BODY, deadline)
        require(type(response) is list and len(response) == len(claims), 'job_count')
        jobs = [_job(job, value, index, deadline) for index, (job, value) in enumerate(zip(response, claims, strict=True))]
        pin = _pin(response_raw)
    record = {'schema': PRIVATE_SCHEMA, 'claims': claims, 'request_pin': _pin(request_raw),
        'http_status': http_status, 'response_pin': pin, 'response_jobs': response}
    private = PrivateMappingResults(record)
    summary = {'schema': SCHEMA, 'scope': 'supplied_current_public_FIGI_mapping_not_route_or_history_admission',
        'request_pin': _pin(request_raw), 'response_pin': pin, 'http_status': http_status,
        'job_count': len(claims), 'jobs': jobs, 'state_counts': dict(sorted(Counter(job['state'] for job in jobs).items())),
        'private_frame_byte_count': len(private._raw), 'private_frame_sha256': sha(private._raw), **FALSE_FLAGS}
    _deadline(deadline)
    return validate_summary(summary), private


def _valid_pin(value, maximum):
    return type(value) is dict and set(value) == {'byte_count', 'sha256'} and type(value['byte_count']) is int \
        and 0 < value['byte_count'] <= maximum and _hash(value['sha256'])


def validate_summary(value):
    keys = {'schema', 'scope', 'request_pin', 'response_pin', 'http_status', 'job_count', 'jobs',
        'state_counts', 'private_frame_byte_count', 'private_frame_sha256', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['scope'] == 'supplied_current_public_FIGI_mapping_not_route_or_history_admission'
        and all(value[key] is False for key in FALSE_FLAGS) and _valid_pin(value['request_pin'], MAX_REQUEST)
        and type(value['http_status']) is int and 100 <= value['http_status'] <= 599
        and type(value['job_count']) is int and 0 < value['job_count'] <= MAX_JOBS
        and type(value['jobs']) is list and len(value['jobs']) == value['job_count']
        and _valid_pin({'byte_count': value['private_frame_byte_count'], 'sha256': value['private_frame_sha256']}, MAX_BODY * 4), 'summary')
    require(_valid_pin(value['response_pin'], MAX_BODY) if value['http_status'] == 200 else value['response_pin'] is None, 'summary')
    for index, job in enumerate(value['jobs']):
        require(type(job) is dict and set(job) == {'job_ordinal', 'claim_sha256', 'state', 'result_count', 'result_rows_sha256'}
            and type(job['job_ordinal']) is int and job['job_ordinal'] == index and _hash(job['claim_sha256'])
            and type(job['state']) is str and job['state'] in JOB_STATES
            and type(job['result_count']) is int and 0 <= job['result_count'] < MAX_RESULTS_PER_JOB
            and (job['result_rows_sha256'] is None or _hash(job['result_rows_sha256'])), 'summary')
        require((value['http_status'] == 200) == (job['state'] != 'not_parsed_http_status'), 'summary')
        if job['state'] in ('metadata_unavailable', 'identity_mismatch', 'instrument_scope_unknown',
                'composite_or_share_class_missing', 'hierarchy_level_inconsistent', 'unique_us_equity_composite'):
            require(job['result_count'] == 1 and _hash(job['result_rows_sha256']), 'summary')
        if job['state'] == 'ambiguous_results': require(job['result_count'] > 1, 'summary')
        if job['state'] in ('not_parsed_http_status', 'no_match', 'job_error_unknown', 'job_warning_unknown'):
            require(job['result_count'] == 0, 'summary')
        if job['state'] in ('not_parsed_http_status', 'job_error_unknown', 'job_warning_unknown'):
            require(job['result_rows_sha256'] is None, 'summary')
    require(type(value['state_counts']) is dict and value['state_counts']
        == dict(sorted(Counter(job['state'] for job in value['jobs']).items()))
        and all(type(n) is int and n > 0 for n in value['state_counts'].values()), 'summary')
    return json.loads(canonical(value))


def validate_private_record(record, *, expected_summary, deadline=None):
    summary = validate_summary(expected_summary)
    require(type(record) is dict and set(record) == {'schema', 'claims', 'request_pin', 'http_status', 'response_pin', 'response_jobs'}
        and record['schema'] == PRIVATE_SCHEMA and record['request_pin'] == summary['request_pin']
        and record['response_pin'] == summary['response_pin'] and record['http_status'] == summary['http_status'], 'private_record')
    claims = _claims(record['claims']); raw = canonical(record)
    require(len(raw) == summary['private_frame_byte_count'] and sha(raw) == summary['private_frame_sha256']
        and _pin(canonical(mapping_jobs(claims))) == summary['request_pin'] and len(claims) == summary['job_count'], 'private_record')
    if summary['http_status'] == 200:
        require(type(record['response_jobs']) is list and len(record['response_jobs']) == len(claims), 'private_record')
        jobs = [_job(job, value, index, deadline) for index, (job, value) in enumerate(zip(record['response_jobs'], claims, strict=True))]
        require(jobs == summary['jobs'], 'private_record')
    else: require(record['response_jobs'] is None, 'private_record')
    require(all(job['claim_sha256'] == sha(canonical(claim)) for job, claim in zip(summary['jobs'], claims, strict=True)), 'private_record')
    return json.loads(raw)


def corroborate(original_figi, current_figi, *, batches, deadline=None):
    require(_figi(original_figi) and _figi(current_figi), 'figi')
    require(type(batches) in (list, tuple) and 0 < len(batches) <= MAX_BATCHES, 'batch_bound')
    indexed, batch_pins = {}, []
    for pair in batches:
        _deadline(deadline); require(type(pair) in (list, tuple) and len(pair) == 2, 'batch_bound')
        summary, record = pair
        checked = validate_private_record(record, expected_summary=summary, deadline=deadline)
        batch_pins.append(sha(canonical(summary)))
        for index, claim in enumerate(checked['claims']):
            require(claim not in indexed, 'duplicate_claim')
            indexed[claim] = (summary['jobs'][index], None if checked['response_jobs'] is None else checked['response_jobs'][index])
    status, same_composite, same_share, causes = None, None, None, []
    if original_figi not in indexed or current_figi not in indexed: status = 'unresolved_mapping_missing'
    else:
        values = [indexed[value] for value in (original_figi, current_figi)]
        state_status = {'not_parsed_http_status': 'unresolved_http_status', 'no_match': 'unresolved_no_match',
            'job_error_unknown': 'unresolved_job_error', 'job_warning_unknown': 'unresolved_job_error',
            'metadata_unavailable': 'unresolved_metadata', 'ambiguous_results': 'unresolved_ambiguity',
            'identity_mismatch': 'unresolved_identity_binding', 'instrument_scope_unknown': 'unresolved_instrument_scope',
            'composite_or_share_class_missing': 'unresolved_composite_or_share_class_missing',
            'hierarchy_level_inconsistent': 'unresolved_hierarchy_level'}
        statuses = {state_status[job['state']] for job, _ in values if job['state'] != 'unique_us_equity_composite'}
        if statuses: causes = sorted(statuses); status = causes[0]
        else:
            left, right = (job['data'][0] for _, job in values)
            same_composite = left['compositeFIGI'] == right['compositeFIGI']
            same_share = left['shareClassFIGI'] == right['shareClassFIGI']
            status = ('same_current_us_composite_observed' if same_composite and same_share
                else 'unresolved_share_class_only' if same_share
                else 'unresolved_share_class_disagreement' if same_composite else 'unresolved_composite_disagreement')
    require(status in OBSERVATIONS, 'summary')
    if status != 'same_current_us_composite_observed' and not causes: causes = [status]
    return validate_observation({'schema': CORROBORATION_SCHEMA, 'observation': status, 'unresolved_causes': causes,
        'original_claim_sha256': sha(canonical(original_figi)), 'current_claim_sha256': sha(canonical(current_figi)),
        'batch_summary_sha256s': batch_pins, 'same_nonnull_US_composite': same_composite,
        'same_nonnull_share_class': same_share,
        'interpretation': 'current_mapping_observation_never_historical_replacement_or_vendor_collision_clearance', **FALSE_FLAGS})


def validate_observation(value):
    keys = {'schema', 'observation', 'unresolved_causes', 'original_claim_sha256', 'current_claim_sha256',
        'batch_summary_sha256s', 'same_nonnull_US_composite', 'same_nonnull_share_class', 'interpretation', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == CORROBORATION_SCHEMA
        and type(value['observation']) is str and value['observation'] in OBSERVATIONS
        and all(value[key] is False for key in FALSE_FLAGS)
        and _hash(value['original_claim_sha256']) and _hash(value['current_claim_sha256'])
        and type(value['batch_summary_sha256s']) is list and 0 < len(value['batch_summary_sha256s']) <= MAX_BATCHES
        and all(_hash(pin) for pin in value['batch_summary_sha256s'])
        and type(value['unresolved_causes']) is list and value['unresolved_causes'] == sorted(set(value['unresolved_causes']))
        and all(type(cause) is str and cause in OBSERVATIONS - {'same_current_us_composite_observed'}
            for cause in value['unresolved_causes'])
        and all(state is None or type(state) is bool for state in
            (value['same_nonnull_US_composite'], value['same_nonnull_share_class']))
        and value['interpretation'] == 'current_mapping_observation_never_historical_replacement_or_vendor_collision_clearance', 'summary')
    shapes = {'same_current_us_composite_observed': (True, True), 'unresolved_share_class_only': (False, True),
        'unresolved_share_class_disagreement': (True, False), 'unresolved_composite_disagreement': (False, False)}
    expected = shapes.get(value['observation'], (None, None))
    require((value['same_nonnull_US_composite'], value['same_nonnull_share_class']) == expected
        and ((value['observation'] == 'same_current_us_composite_observed' and not value['unresolved_causes'])
            or (value['observation'] != 'same_current_us_composite_observed'
                and value['observation'] in value['unresolved_causes'])), 'summary')
    if value['same_nonnull_US_composite'] is True:
        require(value['original_claim_sha256'] == value['current_claim_sha256'], 'summary')
    return json.loads(canonical(value))


def profile_record():
    return {'schema': SCHEMA, 'private_schema': PRIVATE_SCHEMA, 'corroboration_schema': CORROBORATION_SCHEMA,
        'maximum_jobs_per_batch': MAX_JOBS, 'maximum_batches': MAX_BATCHES, 'maximum_body_bytes': MAX_BODY,
        'maximum_request_bytes': MAX_REQUEST, 'maximum_result_rows_per_job_exclusive': MAX_RESULTS_PER_JOB,
        'maximum_text_UTF8_bytes': MAX_FIELD_BYTES, 'maximum_JSON_depth': MAX_JSON_DEPTH, 'maximum_JSON_nodes': MAX_JSON_NODES,
        'request': 'ID_BB_GLOBAL_exact_claim_includeUnlistedEquities_true_no_exchange_or_market_filter_no_alternative_idtype_or_retry',
        'public_provenance': 'caller_pins_only_public_FIGIs_no_CUSIP_vendor_perma_ticker_name_or_rows',
        'FIGI_shape': 'canonical_consonant_alphabet_final_decimal_digit_and_base36_alternating_checksum_not_BBG_only',
        'request_order': 'canonical_fixed_jobs_complete_same_length_response_array_positional_binding',
        'positive_observation': 'exactly_one_exact_requested_FIGI_per_job_US_Equity_instrument_equals_composite_same_nonnull_composite_and_shareClass',
        'US_composite_hierarchy': 'conservative_US_container_instrument_must_equal_its_composite_FIGI_otherwise_unresolved_hierarchy_level',
        'multiple_results': 'unresolved_even_if_first_result_matches_no_selection',
        'shared_share_class_only': 'unresolved_when_claimed_US_composites_differ',
        'non200_body': 'None_only_never_parsed_or_retained_by_helper',
        'response_errors_and_warnings': 'finite_unknown_or_no_match_no_raw_text_in_public_summary',
        'raw_public_identity_fields': 'private_record_only', 'caller_authentication':
            'actual_request_HTTP_response_secret_check_and_complete_retention_are_external_requirements',
        'documentation': 'https://www.openfigi.com/api/documentation',
        'hierarchy_documentation': ['https://www.openfigi.com/about/exchange-codes',
            'https://www.openfigi.com/about/allocation-rules'], **FALSE_FLAGS}
