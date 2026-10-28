"""Pure selected terminal boundary for the common-price aggregate result.

The operational caller must independently bind the exact project, source
readback, compile, launch, job and actual terminal to its frozen one-shot run.
This helper reads no files or services. An external selected-byte pin covers
only the closed projection below, never ignored QC charts, orders or trades.
"""
import hashlib
import json
import re

from research.analyst_revisions_v2_qc import newrule_common_price_comparison_runtime as runtime

SCHEMA = 'arv2-r298-common-price-selected-result-v1'
LAUNCH_SCHEMA = SCHEMA + '-launch-binding'
MAX_SELECTED_BYTES, MAX_STATISTIC_BYTES, MAX_LAUNCH_BYTES = 65536, 16384, 4096
BINDING_KEYS = frozenset(('project_id', 'backtest_id', 'name', 'compile_id',
    'source_manifest_sha256', 'common_profile_sha256', 'run_scope_tag'))
SELECTED_KEYS = frozenset(('schema', 'binding', 'terminal', 'response_compile_id',
    'compile_binding_source', 'launch_binding_pin', 'statistics', 'aggregate_sha256',
    'aggregate_schema_checks_passed', 'selection_pin_scope', *(
        'whole_response_authenticated', 'source_job_authenticated_by_pure_helper',
        'strategy_result_accepted', 'source_admission_granted', 'point_in_time_proven',
        'formal_identity_admitted', 'formal_forward_ready', 'paper_or_live_ready')))
FALSE_FLAGS = {'whole_response_authenticated': False, 'source_job_authenticated_by_pure_helper': False,
    'strategy_result_accepted': False, 'source_admission_granted': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('binding', 'profile', 'profile_binding', 'response', 'response_success',
    'response_errors', 'response_identity', 'response_terminal', 'response_compile',
    'launch_required', 'launch_bound', 'launch_pin', 'launch_shape', 'launch_binding',
    'statistics', 'aggregate', 'selected_bound', 'selected_pin', 'selected_shape',
    'selected_binding', 'actual_exit', 'json', 'unknown'))


class Refused(ValueError):
    """Finite protocol predicate; never response rows, identifiers or errors."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _identifier(value):
    return type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is not None


def _pin(value, maximum, code):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and _hash(value['sha256']), code)
    return {'byte_count': value['byte_count'], 'sha256': value['sha256']}


def _bytes_pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _loads(raw, maximum, code):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, code)
    def pairs(items):
        value = {}
        for name, child in items:
            require(name not in value, 'json')
            value[name] = child
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) == raw, 'json')
        return value
    except Refused:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise Refused('json') from None


def validate_run_binding(value, *, expected_profile):
    require(type(value) is dict and set(value) == BINDING_KEYS
        and type(value['project_id']) is int and 0 < value['project_id'] <= 2147483647
        and type(value['backtest_id']) is str and re.fullmatch('[0-9a-f]{32}', value['backtest_id']) is not None
        and _identifier(value['compile_id']) and _identifier(value['run_scope_tag'])
        and type(value['name']) is str and 0 < len(value['name']) <= 200
        and value['name'].isascii() and all(32 <= ord(char) < 127 for char in value['name'])
        and _hash(value['source_manifest_sha256']) and _hash(value['common_profile_sha256']), 'binding')
    try:
        profile = runtime.validate_profile(expected_profile)
    except Exception:
        raise Refused('profile') from None
    require(value['project_id'] == profile['runtime_project_id']
        and value['common_profile_sha256'] == profile['profile_sha256'], 'profile_binding')
    return dict(value)


def _launch(raw, expected_pin, binding):
    if raw is None and expected_pin is None:
        return None
    require(raw is not None and expected_pin is not None, 'launch_pin')
    pin = _pin(expected_pin, MAX_LAUNCH_BYTES, 'launch_pin')
    require(type(raw) is bytes and 0 < len(raw) <= MAX_LAUNCH_BYTES, 'launch_bound')
    require(_bytes_pin(raw) == pin, 'launch_pin')
    value = _loads(raw, MAX_LAUNCH_BYTES, 'launch_bound')
    require(type(value) is dict and set(value) == {'schema', 'binding'}
        and value['schema'] == LAUNCH_SCHEMA, 'launch_shape')
    require(type(value['binding']) is dict and set(value['binding']) == BINDING_KEYS
        and all(type(value['binding'][key]) is type(binding[key]) and value['binding'][key] == binding[key]
            for key in BINDING_KEYS), 'launch_binding')
    return pin


def _compile(response_compile_id, launch_binding_bytes, expected_launch_binding_pin, binding):
    require(response_compile_id is None or _identifier(response_compile_id)
        and response_compile_id == binding['compile_id'], 'response_compile')
    launch_pin = _launch(launch_binding_bytes, expected_launch_binding_pin, binding)
    require(response_compile_id is not None or launch_pin is not None, 'launch_required')
    source = ('response_and_launch' if launch_pin is not None else 'response_only') if response_compile_id is not None else 'launch_only'
    return source, launch_pin


def _statistics(value, expected_profile):
    require(type(value) is dict, 'statistics')
    selected = {}
    for name in (runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC):
        text = value.get(name)
        require(type(text) is str and 0 < len(text) <= MAX_STATISTIC_BYTES and text.isascii(), 'statistics')
        selected[name] = text
    try:
        aggregate = runtime.validate_result_statistics(selected, expected_profile=expected_profile)
    except Exception:
        raise Refused('aggregate') from None
    return selected, aggregate


def select_response(value, *, expected_run_binding, expected_profile,
                    launch_binding_bytes=None, expected_launch_binding_pin=None):
    """Select only two genuine aggregate statistics from an already decoded reply.

    A missing response compileId requires supplied closed launch-binding bytes
    and their separately frozen external pin. Neither a boolean nor a generated
    compile identifier is accepted. External authentication remains the caller's
    responsibility; this pure comparison grants no authority.
    """
    binding = validate_run_binding(expected_run_binding, expected_profile=expected_profile)
    require(type(value) is dict, 'response')
    require(value.get('success') is True, 'response_success')
    # Real QC success envelopes may omit `errors`; every reader that consumed
    # actual responses accepts absence, so only a present non-empty or
    # non-list value refuses (section 328).
    require('errors' not in value or (type(value['errors']) is list and not value['errors']), 'response_errors')
    row = value.get('backtest')
    require(type(row) is dict, 'response_identity')
    require(type(row.get('projectId')) is int and row['projectId'] == binding['project_id']
        and type(row.get('backtestId')) is str and row['backtestId'] == binding['backtest_id']
        and type(row.get('name')) is str and row['name'] == binding['name'], 'response_identity')
    require(type(row.get('status')) is str and row['status'] == 'Completed.', 'response_terminal')
    response_compile_id = row.get('compileId')
    if 'compileId' in row:
        require(_identifier(response_compile_id) and response_compile_id == binding['compile_id'], 'response_compile')
    compile_source, launch_pin = _compile(response_compile_id, launch_binding_bytes, expected_launch_binding_pin, binding)
    statistics, aggregate = _statistics(row.get('statistics'), expected_profile)
    selected = {'schema': SCHEMA, 'binding': binding, 'terminal': 'Completed.',
        'response_compile_id': response_compile_id, 'compile_binding_source': compile_source,
        'launch_binding_pin': launch_pin, 'statistics': statistics, 'aggregate_sha256': sha(canonical(aggregate)),
        'aggregate_schema_checks_passed': True, 'selection_pin_scope': 'selected_projection_only', **FALSE_FLAGS}
    raw = canonical(selected)
    require(0 < len(raw) <= MAX_SELECTED_BYTES, 'selected_bound')
    return selected, _bytes_pin(raw)


def validate_selected(raw, *, expected_selected_pin, expected_run_binding, expected_profile,
                      actual_reader_exit, launch_binding_bytes=None, expected_launch_binding_pin=None):
    """Accept exact pinned selected bytes only after an observed real reader exit0."""
    require(type(actual_reader_exit) is int and actual_reader_exit == 0, 'actual_exit')
    binding = validate_run_binding(expected_run_binding, expected_profile=expected_profile)
    pin = _pin(expected_selected_pin, MAX_SELECTED_BYTES, 'selected_pin')
    require(type(raw) is bytes and 0 < len(raw) <= MAX_SELECTED_BYTES, 'selected_bound')
    require(_bytes_pin(raw) == pin, 'selected_pin')
    value = _loads(raw, MAX_SELECTED_BYTES, 'selected_bound')
    require(type(value) is dict and set(value) == SELECTED_KEYS and value['schema'] == SCHEMA
        and value['terminal'] == 'Completed.' and value['aggregate_schema_checks_passed'] is True
        and value['selection_pin_scope'] == 'selected_projection_only'
        and all(value[key] is False for key in FALSE_FLAGS), 'selected_shape')
    require(type(value['binding']) is dict and set(value['binding']) == BINDING_KEYS
        and all(type(value['binding'][key]) is type(binding[key]) and value['binding'][key] == binding[key]
            for key in BINDING_KEYS), 'selected_binding')
    compile_source, launch_pin = _compile(value['response_compile_id'], launch_binding_bytes,
        expected_launch_binding_pin, binding)
    require(value['compile_binding_source'] == compile_source and value['launch_binding_pin'] == launch_pin,
        'selected_binding')
    require(type(value['statistics']) is dict and set(value['statistics']) == {
        runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC}, 'statistics')
    statistics, aggregate = _statistics(value['statistics'], expected_profile)
    require(value['aggregate_sha256'] == sha(canonical(aggregate)), 'aggregate')
    return {'selected': value, 'selected_pin': pin, 'aggregate': aggregate}


def profile_record():
    return {'schema': SCHEMA, 'binding_fields': sorted(BINDING_KEYS), 'launch_schema': LAUNCH_SCHEMA,
        'terminal': 'Completed.', 'maximum_selected_bytes': MAX_SELECTED_BYTES,
        'maximum_statistic_bytes_each': MAX_STATISTIC_BYTES, 'maximum_launch_bytes': MAX_LAUNCH_BYTES,
        'statistics': [runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC],
        'compile_absence': 'closed_supplied_launch_binding_bytes_and_separately_frozen_external_pin',
        'selected_authentication': 'observed_actual_reader_exit0_and_external_exact_selected_bytes_pin',
        'ignored_subtrees': 'never_traversed_canonicalized_hashed_or_retained',
        'external_prerequisites': 'exact_project_source_readback_compile_launch_job_profile_terminal_and_one_shot_protocol',
        **FALSE_FLAGS}
