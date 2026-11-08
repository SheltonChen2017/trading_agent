"""Pure selected metadata boundary for the one R329 native coverage diagnostic.

Only the caller can authenticate the UI selection, source readback, compile/job
linkage and actual terminal. This module contacts no service and reads no files.
A completed observation, including one with dense gaps, is no strategy result.
"""
import hashlib
import json
import re

from research.analyst_revisions_v2_qc import newrule_available_history_native_coverage as coverage

SCHEMA = 'arv2-r329-native-coverage-selected-result-v1'
PROJECT_ID = 38522505
STATISTIC = 'ARV2_W5_NATIVE_COVERAGE'
MAX_STATISTIC_BYTES, MAX_RECORD_BYTES, MAX_READBACK_BYTES = 8002, 16384, 65536
PROJECTION_PIN = {'byte_count': 2495, 'sha256': 'a3a3a4a1a46b2760bc56964a89088a83f23c1918f74f5998c3e73d995fe64dba'}
SOURCE_PROFILE_PIN = {'byte_count': 7635, 'sha256': 'bd22b98f02de9a81266e3768534aa5364a8c3d633220bd5b9d20794389a6ce5c'}
RUN_KEYS = frozenset(('project_id', 'compile_id', 'backtest_id', 'name'))
BINDING_KEYS = RUN_KEYS | {'source_projection_pin', 'source_profile_pin', 'source_readback_pin',
    'coverage_profile_sha256'}
FAILED_TERMINALS = frozenset(('Runtime Error.', 'Build Error.', 'Stopped.', 'Cancelled.', 'Invalid.'))
FALSE_FLAGS = {**coverage.FALSE_FLAGS, 'whole_response_authenticated': False,
    'source_job_authenticated_by_pure_helper': False, 'source_readback_authenticated_by_pure_helper': False,
    'QC_or_Safari_access_performed': False, 'strategy_performance_observed': False,
    'unconditional_launch_gate_satisfied': False}
FINITE = frozenset(('statistic_name', 'statistic_bound', 'json', 'binding', 'source_binding',
    'profile', 'run_identity', 'terminal', 'summary', 'record_bound', 'unknown'))


class Refused(ValueError):
    """Finite protocol predicate only; never raw selected content or QC errors."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def pin(raw):
    require(type(raw) is bytes, 'record_bound')
    return {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _identifier(value):
    return type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is not None


def _keys(value, expected):
    return type(value) is dict and all(type(key) is str for key in value) and set(value) == expected


def _exact(left, right):
    """Reject numeric/bool equivalence and subclasses before nested comparison."""
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        return _keys(left, set(right)) and all(_exact(left[key], right[key]) for key in right)
    if type(right) is list:
        return len(left) == len(right) and all(_exact(a, b) for a, b in zip(left, right))
    return type(right) in (str, int, bool, type(None)) and left == right


def _pin(value, maximum):
    require(_keys(value, {'byte_count', 'sha256'})
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and _hash(value['sha256']), 'source_binding')
    return dict(value)


def _binding(value, expected_profile):
    require(_keys(value, BINDING_KEYS)
        and type(value['project_id']) is int and value['project_id'] == PROJECT_ID
        and _identifier(value['compile_id']) and type(value['backtest_id']) is str
        and re.fullmatch('[0-9a-f]{32}', value['backtest_id']) is not None
        and type(value['name']) is str and 0 < len(value['name']) <= 200
        and value['name'].isascii() and all(32 <= ord(char) < 127 for char in value['name']), 'binding')
    require(_exact(expected_profile, coverage.profile_record(PROJECT_ID)), 'profile')
    require(_hash(value['coverage_profile_sha256'])
        and value['coverage_profile_sha256'] == coverage.digest(expected_profile), 'profile')
    for name in ('source_projection_pin', 'source_profile_pin', 'source_readback_pin'):
        _pin(value[name], MAX_READBACK_BYTES)
    require(_exact(value['source_projection_pin'], PROJECTION_PIN)
        and _exact(value['source_profile_pin'], SOURCE_PROFILE_PIN), 'source_binding')
    # A supplied readback pin is a comparison binding, never an authentication
    # performed by this pure helper. The external caller owns its provenance.
    return json.loads(canonical(value))


def _loads(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_STATISTIC_BYTES, 'statistic_bound')
    def pairs(items):
        result = {}
        for name, value in items:
            require(name not in result, 'json')
            result[name] = value
        return result
    try:
        text = raw.decode('utf-8', errors='strict')
        value = json.loads(text, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) == raw, 'json')
        return value
    except Refused:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refused('json') from None


def validate_selected(statistic_name, statistic_bytes, *, actual_run, expected_run, expected_profile):
    """Validate supplied selected metadata without authenticating its provenance.

    The actual compile/job linkage and source readback must already be bound by
    the caller's separately frozen run. Unknown or absent terminal/statistic
    evidence refuses; no status, compile ID, price cell or error is inferred.
    """
    require(type(statistic_name) is str and statistic_name == STATISTIC == coverage.STATISTIC,
        'statistic_name')
    binding = _binding(expected_run, expected_profile)
    require(_keys(actual_run, RUN_KEYS | {'terminal'})
        and all(_exact(actual_run[key], binding[key]) for key in RUN_KEYS), 'run_identity')
    terminal = actual_run['terminal']
    require(type(terminal) is str and terminal in FAILED_TERMINALS | {'Completed.'}, 'terminal')
    supplied = _loads(statistic_bytes)
    try:
        summary = coverage.validate_summary(supplied, expected_profile=expected_profile)
    except Exception:
        raise Refused('summary') from None
    # validate_summary binds genuine geometry/count/category arithmetic. Its
    # returned canonical copy additionally must preserve exact JSON types.
    require(_exact(supplied, summary), 'summary')
    complete = terminal == 'Completed.'
    require(not complete or summary['terminal'] == 'complete', 'terminal')
    if not complete:
        classification = 'diagnostic_failed_terminal'
    elif summary['dense_envelopes_complete']:
        classification = 'diagnostic_complete_dense_envelopes_only'
    else:
        classification = 'diagnostic_complete_with_gaps'
    result = {'schema': SCHEMA, 'binding': binding, 'actual_terminal': terminal,
        'statistic_name': STATISTIC, 'selected_statistic_pin': pin(statistic_bytes),
        'diagnostic_complete': complete, 'classification': classification,
        'summary_schema_checks_passed': True, 'summary': summary,
        'pin_scope': 'exact_selected_statistic_only_not_whole_response',
        'coverage_scope': 'conservative_potential_envelopes_not_actual_target_or_holdings_path',
        'compile_job_source_provenance': 'caller_supplied_external_run_and_readback_binding', **FALSE_FLAGS}
    require(len(canonical(result)) <= MAX_RECORD_BYTES, 'record_bound')
    return result


def profile_record():
    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'statistic_name': STATISTIC,
        'statistic_schema': coverage.SCHEMA, 'maximum_statistic_bytes': MAX_STATISTIC_BYTES,
        'maximum_record_bytes': MAX_RECORD_BYTES, 'run_binding_fields': sorted(BINDING_KEYS),
        'actual_run_fields': sorted(RUN_KEYS | {'terminal'}), 'completed_terminal': 'Completed.',
        'failed_terminals': sorted(FAILED_TERMINALS), 'source_projection_pin': dict(PROJECTION_PIN),
        'source_profile_pin': dict(SOURCE_PROFILE_PIN),
        'coverage_profile_sha256': coverage.digest(coverage.profile_record(PROJECT_ID)),
        'strict_canonical_UTF8_no_duplicates_nonfinite_or_trailing_content': True,
        'complete_with_gaps_is_valid_diagnostic_not_strategy_success': True,
        'late_failed_terminal_overrides_complete_summary': True,
        'no_effects': 'supplied_metadata_only_no_file_service_credential_artifact_or_output_claim',
        **FALSE_FLAGS}
