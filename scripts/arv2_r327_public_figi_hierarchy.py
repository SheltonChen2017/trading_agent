"""Pure two-phase public-FIGI hierarchy observations; no alias or route authority.

The operational caller binds the exact original nine claims, request bytes,
status and response provenance. This helper performs no I/O or request. One
derived composite-witness phase is permitted; it is never a retry or a walk
through further returned identifiers. Original/vendor identities stay intact.
"""
from collections import Counter
import json

from scripts import arv2_r298_public_figi_corroboration as old

SCHEMA = 'arv2-r327-public-FIGI-hierarchy-v1'
PRIVATE_SCHEMA, PAIR_SCHEMA = SCHEMA + '-private', SCHEMA + '-pair'
INITIAL_COUNT, MAX_DERIVED, MAX_JOBS = 9, 9, 10
MAX_BODY, MAX_REQUEST, MAX_PRIVATE = 2 * 1024 * 1024, 4096, 8 * 1024 * 1024
MAX_RESULTS, MAX_DEPTH, MAX_NODES = 15000, 8, 250000
GOOD = frozenset(('unique_equity_hierarchy', 'unique_US_equity_composite'))
STATES = GOOD | frozenset(('not_parsed_http_status', 'no_match', 'job_error_unknown',
    'job_warning_unknown', 'job_schema_invalid', 'result_schema_invalid', 'ambiguous_results',
    'metadata_unavailable', 'identity_mismatch', 'instrument_scope_unknown',
    'composite_or_share_class_missing', 'US_hierarchy_inconsistent'))
OBSERVATIONS = frozenset(('same_validated_US_composite_and_share_class_observed',
    'unresolved_input_jobs', 'unresolved_phase2_missing', 'unresolved_composite_disagreement',
    'unresolved_share_class_only', 'unresolved_share_class_disagreement',
    'unresolved_US_composite_witness_missing', 'unresolved_witness_share_class_disagreement'))
FALSE_FLAGS = {**old.FALSE_FLAGS, 'vendor_collision_cleared': False,
    'original_identifier_rewritten': False, 'alias_or_route_created': False,
    'source_admission_granted': False, 'new_operation_or_read_granted': False}
FINITE = frozenset(('claims', 'request', 'http_status', 'failed_body', 'body', 'json', 'json_bound',
    'job_count', 'result_bound', 'phase_binding', 'phase2_not_required', 'summary',
    'private_record', 'private_bound', 'pair', 'deadline', 'unknown'))
canonical, sha, _figi, _hash, _deadline = old.canonical, old.sha, old._figi, old._hash, old._deadline


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is old.Refused and old.finite(error) == 'deadline': return 'deadline'
    return 'unknown'


def digest(value): return sha(canonical(value))
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}


def _budget(deadline):
    try: _deadline(deadline)
    except old.Refused: raise Refused('deadline') from None


def _claims(figis, *, initial):
    require(type(figis) in (tuple, list) and all(_figi(value) for value in figis)
        and len(figis) == len(set(figis)) and (len(figis) == INITIAL_COUNT if initial else 0 < len(figis) <= MAX_DERIVED), 'claims')
    return list(figis)


def _jobs(figis):
    return [{'idType': 'ID_BB_GLOBAL', 'idValue': value, 'includeUnlistedEquities': True} for value in figis]


def mapping_jobs(figis): return _jobs(_claims(figis, initial=True))


def _decode(raw, maximum, deadline):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'body')
    quoted, escaped, depth, separators = False, False, 0, 0
    for ordinal, byte in enumerate(raw):
        if ordinal % 65536 == 0: _budget(deadline)
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
        elif byte == 34: quoted = True
        elif byte in (91, 123): depth += 1; require(depth <= MAX_DEPTH, 'json_bound')
        elif byte in (93, 125): depth -= 1; require(depth >= 0, 'json')
        elif byte in (44, 58): separators += 1; require(separators <= MAX_NODES * 2, 'json_bound')
    require(not quoted and not escaped and depth == 0, 'json')
    def pairs(items):
        value = {}
        for key, child in items: require(key not in value, 'json'); value[key] = child
        return value
    def no_float(_): raise Refused('json')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_float=no_float, parse_constant=no_float)
    except Refused: raise
    except (ValueError, UnicodeError, RecursionError, OverflowError): raise Refused('json') from None
    pending, nodes = [value], 0
    while pending:
        item = pending.pop(); nodes += 1
        require(nodes <= MAX_NODES and type(item) in (dict, list, str, bool, int, type(None)), 'json_bound')
        if type(item) is dict: pending.extend(item.values())
        elif type(item) is list: pending.extend(item)
    return value


def _job(job, claimed, ordinal, deadline):
    row = {'job_ordinal': ordinal, 'claim_sha256': digest(claimed), 'state': 'job_schema_invalid',
        'result_count': 0, 'invalid_result_count': 0, 'result_rows_sha256': None,
        'job_sha256': digest(job)}
    if type(job) is not dict or set(job) not in ({'data'}, {'error'}, {'warning'}): return row
    if 'error' in job or 'warning' in job:
        key = 'error' if 'error' in job else 'warning'
        if old._text(job[key], old.MAX_MESSAGE_BYTES) and bool(job[key]):
            row['state'] = 'no_match' if job[key] == 'No identifier found.' else 'job_' + key + '_unknown'
        return row
    rows = job['data']
    if type(rows) is not list: return row
    require(len(rows) <= MAX_RESULTS, 'result_bound')
    row.update(result_count=len(rows), result_rows_sha256=digest(rows))
    for result in rows:
        _budget(deadline)
        try: old._result(result)
        except old.Refused: row['invalid_result_count'] += 1
    if row['invalid_result_count']: row['state'] = 'result_schema_invalid'
    elif not rows: row['state'] = 'no_match'
    elif len(rows) != 1: row['state'] = 'ambiguous_results'
    else:
        result = rows[0]
        if result['figi'] != claimed: row['state'] = 'identity_mismatch'
        elif 'metadata' in result: row['state'] = 'metadata_unavailable'
        elif result.get('marketSector') != 'Equity': row['state'] = 'instrument_scope_unknown'
        elif result.get('compositeFIGI') is None or result.get('shareClassFIGI') is None:
            row['state'] = 'composite_or_share_class_missing'
        elif result.get('exchCode') == 'US' and result['figi'] != result['compositeFIGI']:
            row['state'] = 'US_hierarchy_inconsistent'
        else:
            row['state'] = 'unique_US_equity_composite' if result.get('exchCode') == 'US' \
                and result['figi'] == result['compositeFIGI'] else 'unique_equity_hierarchy'
    return row


def _derived(claims, jobs, response):
    if response is None: return []
    return sorted({response[index]['data'][0]['compositeFIGI'] for index, job in enumerate(jobs)
        if job['state'] in GOOD} - set(claims))


class PrivateHierarchyResults:
    __slots__ = ('_raw',)
    def __init__(self, record): object.__setattr__(self, '_raw', canonical(record))
    def __setattr__(self, name, value): raise TypeError('hierarchy results are immutable')
    def __repr__(self): return '<PrivateHierarchyResults redacted; diagnostic evidence; no route authority>'
    def __reduce_ex__(self, protocol): raise TypeError('hierarchy evidence cannot be pickled')
    def private_record(self): return json.loads(self._raw)


def _analyze(claims, *, phase, predecessor, request_raw, response_raw, http_status, deadline):
    _budget(deadline)
    require(type(request_raw) is bytes and 0 < len(request_raw) <= MAX_REQUEST
        and request_raw == canonical(_jobs(claims)), 'request')
    require(type(http_status) is int and 100 <= http_status <= 599, 'http_status')
    if http_status != 200:
        require(response_raw is None, 'failed_body'); response, response_pin = None, None
        jobs = [{'job_ordinal': index, 'claim_sha256': digest(value), 'state': 'not_parsed_http_status',
            'result_count': 0, 'invalid_result_count': 0, 'result_rows_sha256': None, 'job_sha256': None}
            for index, value in enumerate(claims)]
    else:
        response = _decode(response_raw, MAX_BODY, deadline)
        require(type(response) is list and len(response) == len(claims), 'job_count')
        jobs = [_job(job, value, index, deadline) for index, (job, value)
            in enumerate(zip(response, claims, strict=True))]
        response_pin = pin(response_raw)
    derived = _derived(claims, jobs, response) if phase == 1 else []
    require(len(derived) <= MAX_DERIVED, 'claims')
    record = {'schema': PRIVATE_SCHEMA, 'phase': phase, 'claims': claims, 'request_pin': pin(request_raw),
        'http_status': http_status, 'response_pin': response_pin, 'response_jobs': response,
        'phase1_summary_sha256': predecessor}
    private = PrivateHierarchyResults(record)
    require(len(private._raw) <= MAX_PRIVATE, 'private_bound')
    summary = {'schema': SCHEMA, 'scope': 'supplied_current_hierarchy_observation_not_alias_route_or_history_admission',
        'phase': phase, 'phase1_summary_sha256': predecessor, 'request_pin': pin(request_raw),
        'response_pin': response_pin, 'http_status': http_status, 'job_count': len(claims), 'jobs': jobs,
        'state_counts': dict(sorted(Counter(job['state'] for job in jobs).items())),
        'all_jobs_unambiguous': all(job['state'] in GOOD for job in jobs),
        'derived_composite_count': len(derived), 'derived_composite_claims_sha256': digest(derived),
        'private_frame_pin': pin(private._raw), **FALSE_FLAGS}
    return validate_summary(summary), private


def analyze_phase1(figis, *, request_raw, response_raw, http_status, deadline=None):
    return _analyze(_claims(figis, initial=True), phase=1, predecessor=None, request_raw=request_raw,
        response_raw=response_raw, http_status=http_status, deadline=deadline)


def _phase1(pair, deadline):
    require(type(pair) in (tuple, list) and len(pair) == 2, 'phase_binding')
    summary = validate_summary(pair[0]); require(summary['phase'] == 1, 'phase_binding')
    record = validate_private_record(pair[1], expected_summary=summary, deadline=deadline)
    return summary, record, _derived(record['claims'], summary['jobs'], record['response_jobs'])


def phase2_jobs(phase1, deadline=None):
    _, _, values = _phase1(phase1, deadline)
    return _jobs(values)


def analyze_phase2(phase1, *, request_raw, response_raw, http_status, deadline=None):
    summary, _, values = _phase1(phase1, deadline)
    require(values, 'phase2_not_required')
    return _analyze(_claims(values, initial=False), phase=2, predecessor=digest(summary),
        request_raw=request_raw, response_raw=response_raw, http_status=http_status, deadline=deadline)


def validate_summary(value):
    keys = {'schema', 'scope', 'phase', 'phase1_summary_sha256', 'request_pin', 'response_pin',
        'http_status', 'job_count', 'jobs', 'state_counts', 'all_jobs_unambiguous',
        'derived_composite_count', 'derived_composite_claims_sha256', 'private_frame_pin', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['scope'] == 'supplied_current_hierarchy_observation_not_alias_route_or_history_admission'
        and type(value['phase']) is int and value['phase'] in (1, 2)
        and (value['phase1_summary_sha256'] is None if value['phase'] == 1 else _hash(value['phase1_summary_sha256']))
        and old._valid_pin(value['request_pin'], MAX_REQUEST)
        and type(value['http_status']) is int and 100 <= value['http_status'] <= 599
        and type(value['job_count']) is int and (value['job_count'] == INITIAL_COUNT if value['phase'] == 1
            else 0 < value['job_count'] <= MAX_DERIVED)
        and type(value['jobs']) is list and len(value['jobs']) == value['job_count']
        and old._valid_pin(value['private_frame_pin'], MAX_PRIVATE)
        and all(value[key] is False for key in FALSE_FLAGS), 'summary')
    require(old._valid_pin(value['response_pin'], MAX_BODY) if value['http_status'] == 200
        else value['response_pin'] is None, 'summary')
    for index, row in enumerate(value['jobs']):
        require(type(row) is dict and set(row) == {'job_ordinal', 'claim_sha256', 'state', 'result_count',
            'invalid_result_count', 'result_rows_sha256', 'job_sha256'}
            and type(row['job_ordinal']) is int and row['job_ordinal'] == index and _hash(row['claim_sha256'])
            and type(row['state']) is str and row['state'] in STATES
            and type(row['result_count']) is type(row['invalid_result_count']) is int
            and 0 <= row['invalid_result_count'] <= row['result_count'] <= MAX_RESULTS
            and (row['result_rows_sha256'] is None or _hash(row['result_rows_sha256']))
            and (row['job_sha256'] is None or _hash(row['job_sha256'])), 'summary')
        require((row['state'] == 'not_parsed_http_status') is (value['http_status'] != 200), 'summary')
        if row['state'] == 'not_parsed_http_status':
            require(row['result_count'] == 0 and row['job_sha256'] is row['result_rows_sha256'] is None, 'summary')
        else: require(_hash(row['job_sha256']), 'summary')
        if row['state'] in GOOD | {'identity_mismatch', 'metadata_unavailable', 'instrument_scope_unknown',
                'composite_or_share_class_missing', 'US_hierarchy_inconsistent'}:
            require(row['result_count'] == 1 and row['invalid_result_count'] == 0
                and _hash(row['result_rows_sha256']), 'summary')
        if row['state'] == 'ambiguous_results': require(row['result_count'] > 1 and row['invalid_result_count'] == 0
            and _hash(row['result_rows_sha256']), 'summary')
        if row['state'] == 'result_schema_invalid': require(row['invalid_result_count'] > 0
            and _hash(row['result_rows_sha256']), 'summary')
        if row['state'] in ('job_schema_invalid', 'job_error_unknown', 'job_warning_unknown'):
            require(row['result_count'] == row['invalid_result_count'] == 0
                and row['result_rows_sha256'] is None, 'summary')
        if row['state'] == 'no_match': require(row['result_count'] == row['invalid_result_count'] == 0
            and row['result_rows_sha256'] in (None, digest([])), 'summary')
    require(type(value['state_counts']) is dict and value['state_counts']
        == dict(sorted(Counter(row['state'] for row in value['jobs']).items()))
        and all(type(number) is int and number > 0 for number in value['state_counts'].values())
        and type(value['all_jobs_unambiguous']) is bool
        and value['all_jobs_unambiguous'] is all(row['state'] in GOOD for row in value['jobs'])
        and type(value['derived_composite_count']) is int and 0 <= value['derived_composite_count'] <= MAX_DERIVED
        and value['derived_composite_count'] <= sum(row['state'] in GOOD for row in value['jobs'])
        and _hash(value['derived_composite_claims_sha256']), 'summary')
    if value['phase'] == 2 or value['derived_composite_count'] == 0:
        require(value['derived_composite_count'] == 0 and value['derived_composite_claims_sha256'] == digest([]), 'summary')
    return json.loads(canonical(value))


def validate_private_record(record, *, expected_summary, deadline=None):
    summary = validate_summary(expected_summary)
    require(type(record) is dict and set(record) == {'schema', 'phase', 'claims', 'request_pin',
        'http_status', 'response_pin', 'response_jobs', 'phase1_summary_sha256'}
        and record['schema'] == PRIVATE_SCHEMA and all(record[name] == summary[name]
            for name in ('phase', 'request_pin', 'http_status', 'response_pin', 'phase1_summary_sha256')), 'private_record')
    claims = _claims(record['claims'], initial=summary['phase'] == 1)
    try: raw = canonical(record)
    except (ValueError, TypeError, UnicodeError, RecursionError): raise Refused('private_record') from None
    require(pin(raw) == summary['private_frame_pin'] and len(raw) <= MAX_PRIVATE
        and pin(canonical(_jobs(claims))) == summary['request_pin'] and len(claims) == summary['job_count'], 'private_record')
    _decode(raw, MAX_PRIVATE, deadline)
    response = record['response_jobs']
    if summary['http_status'] == 200:
        require(type(response) is list and len(response) == len(claims), 'private_record')
        jobs = [_job(job, value, index, deadline) for index, (job, value) in enumerate(zip(response, claims, strict=True))]
        require(jobs == summary['jobs'], 'private_record')
    else: require(response is None, 'private_record')
    require(all(row['claim_sha256'] == digest(claim) for row, claim in zip(summary['jobs'], claims, strict=True)), 'private_record')
    derived = _derived(claims, summary['jobs'], response) if summary['phase'] == 1 else []
    require(len(derived) == summary['derived_composite_count']
        and digest(derived) == summary['derived_composite_claims_sha256'], 'private_record')
    return json.loads(raw)


def corroborate(original, current, *, phase1, phase2=None, deadline=None):
    first, record, wanted = _phase1(phase1, deadline)
    require(_figi(original) and _figi(current) and original in record['claims'] and current in record['claims'], 'pair')
    summaries, records = [first], [record]
    if phase2 is not None:
        require(wanted and type(phase2) in (tuple, list) and len(phase2) == 2, 'phase_binding')
        second = validate_summary(phase2[0]); other = validate_private_record(phase2[1], expected_summary=second, deadline=deadline)
        require(second['phase'] == 2 and second['phase1_summary_sha256'] == digest(first)
            and other['claims'] == wanted, 'phase_binding')
        summaries.append(second); records.append(other)
    indexed = {}
    for summary, source in zip(summaries, records, strict=True):
        for index, claim in enumerate(source['claims']):
            require(claim not in indexed, 'phase_binding')
            indexed[claim] = (summary['phase'], summary['jobs'][index],
                None if source['response_jobs'] is None else source['response_jobs'][index])
    bad = sorted({row['state'] for summary in summaries for row in summary['jobs'] if row['state'] not in GOOD})
    complete = not bad and (not wanted or phase2 is not None)
    same_composite, same_share, witness_phase = None, None, None
    if bad: status = 'unresolved_input_jobs'
    elif wanted and phase2 is None: status = 'unresolved_phase2_missing'
    else:
        left, right = (indexed[value][2]['data'][0] for value in (original, current))
        same_composite = left['compositeFIGI'] == right['compositeFIGI']
        same_share = left['shareClassFIGI'] == right['shareClassFIGI']
        if not same_composite: status = 'unresolved_share_class_only' if same_share else 'unresolved_composite_disagreement'
        elif not same_share: status = 'unresolved_share_class_disagreement'
        else:
            witness = indexed.get(left['compositeFIGI'])
            if witness is None or witness[1]['state'] != 'unique_US_equity_composite':
                status = 'unresolved_US_composite_witness_missing'
            elif witness[2]['data'][0]['shareClassFIGI'] != left['shareClassFIGI']:
                status = 'unresolved_witness_share_class_disagreement'
            else:
                witness_phase = witness[0]; status = 'same_validated_US_composite_and_share_class_observed'
    result = {'schema': PAIR_SCHEMA, 'observation': status, 'original_claim_sha256': digest(original),
        'current_claim_sha256': digest(current), 'phase_summary_sha256s': [digest(value) for value in summaries],
        'same_nonnull_composite': same_composite, 'same_nonnull_share_class': same_share,
        'validated_US_witness': witness_phase is not None, 'witness_phase': witness_phase,
        'all_input_jobs_unambiguous': complete, 'unresolved_job_states': bad, **FALSE_FLAGS}
    return validate_observation(result)


def validate_observation(value):
    keys = {'schema', 'observation', 'original_claim_sha256', 'current_claim_sha256',
        'phase_summary_sha256s', 'same_nonnull_composite', 'same_nonnull_share_class',
        'validated_US_witness', 'witness_phase', 'all_input_jobs_unambiguous', 'unresolved_job_states', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == PAIR_SCHEMA
        and type(value['observation']) is str and value['observation'] in OBSERVATIONS
        and _hash(value['original_claim_sha256']) and _hash(value['current_claim_sha256'])
        and type(value['phase_summary_sha256s']) is list and 1 <= len(value['phase_summary_sha256s']) <= 2
        and all(_hash(item) for item in value['phase_summary_sha256s'])
        and all(value[key] is None or type(value[key]) is bool for key in ('same_nonnull_composite', 'same_nonnull_share_class'))
        and type(value['validated_US_witness']) is type(value['all_input_jobs_unambiguous']) is bool
        and (value['witness_phase'] is None or type(value['witness_phase']) is int and value['witness_phase'] in (1, 2))
        and (value['witness_phase'] is not None) is value['validated_US_witness']
        and type(value['unresolved_job_states']) is list
        and all(type(item) is str and item in STATES - GOOD for item in value['unresolved_job_states'])
        and value['unresolved_job_states'] == sorted(set(value['unresolved_job_states']))
        and all(value[key] is False for key in FALSE_FLAGS), 'summary')
    positive = value['observation'] == 'same_validated_US_composite_and_share_class_observed'
    require(value['validated_US_witness'] is positive, 'summary')
    if positive:
        require(value['same_nonnull_composite'] is value['same_nonnull_share_class'] is True
            and value['all_input_jobs_unambiguous'] is True and not value['unresolved_job_states'], 'summary')
    if value['observation'] == 'unresolved_input_jobs':
        require(value['unresolved_job_states'] and value['all_input_jobs_unambiguous'] is False
            and value['same_nonnull_composite'] is value['same_nonnull_share_class'] is None, 'summary')
    elif value['observation'] == 'unresolved_phase2_missing':
        require(not value['unresolved_job_states'] and value['all_input_jobs_unambiguous'] is False
            and len(value['phase_summary_sha256s']) == 1
            and value['same_nonnull_composite'] is value['same_nonnull_share_class'] is None, 'summary')
    else: require(value['all_input_jobs_unambiguous'] is True and not value['unresolved_job_states'], 'summary')
    if value['observation'] == 'unresolved_share_class_only':
        require(value['same_nonnull_composite'] is False and value['same_nonnull_share_class'] is True, 'summary')
    if value['observation'] == 'unresolved_composite_disagreement':
        require(value['same_nonnull_composite'] is value['same_nonnull_share_class'] is False, 'summary')
    if value['observation'] == 'unresolved_share_class_disagreement':
        require(value['same_nonnull_composite'] is True and value['same_nonnull_share_class'] is False, 'summary')
    if value['observation'] in ('unresolved_US_composite_witness_missing', 'unresolved_witness_share_class_disagreement'):
        require(value['same_nonnull_composite'] is value['same_nonnull_share_class'] is True, 'summary')
    if value['witness_phase'] == 2: require(len(value['phase_summary_sha256s']) == 2, 'summary')
    return json.loads(canonical(value))


def profile_record():
    return {'schema': SCHEMA, 'primary_source': 'https://www.openfigi.com/api/documentation',
        'initial_jobs': INITIAL_COUNT, 'maximum_jobs_per_batch': MAX_JOBS, 'maximum_phases': 2,
        'maximum_derived_jobs': MAX_DERIVED, 'maximum_response_bytes': MAX_BODY,
        'maximum_results_per_job_inclusive': MAX_RESULTS, 'maximum_JSON_nodes': MAX_NODES,
        'request': 'ID_BB_GLOBAL_exact_claim_includeUnlistedEquities_true_no_market_exchange_alternate_ID_filter',
        'phase2': 'sorted_unique_complete_unambiguous_phase1_equity_composites_excluding_initial_claims_no_recursive_derivation',
        'phase1': 'exact_returned_claim_valid_nonnull_composite_shareClass_Equity_venue_label_observational',
        'witness': 'unique_exact_requested_figi_equals_compositeFIGI_exchCode_US_marketSector_Equity_valid_shareClass',
        'pair': 'same_composite_and_shareClass_plus_US_witness_all_input_jobs_unambiguous_no_favorable_subset',
        'failed_status': 'body_must_be_None_never_parsed', 'private_results': 'all_jobs_rows_retained_redacted_repr_no_pickle',
        'old_pure_validation_source_sha256': '1b7c3151266023286b4170b0b2412acc08c7bbb011d86a2ec012cfc3db4eb54e',
        'scope': 'current_public_hierarchy_observation_not_historical_identity_replacement_or_vendor_collision_clearance', **FALSE_FLAGS}
