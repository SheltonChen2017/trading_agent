"""Synthetic selected coverage metadata only; no retained DATA, service or job."""
import ast
import copy
import inspect
import json

import pytest

from scripts import arv2_r329_native_coverage_result as m


def fixture(*, gaps=True, refused=False):
    profile = m.coverage.profile_record(m.PROJECT_ID)
    rows = []
    for index, (demand, geometry) in enumerate(zip(m.coverage.EXPECTED_DEMAND, m.coverage.EXPECTED_GEOMETRY, strict=True)):
        missing = 2 if index == 0 and gaps else 0
        rows.append({'ordinal': index, 'whole_binding_sha256': demand[0],
            'eligible_decision_count': demand[2], 'eligible_decisions_sha256': geometry[2],
            'required_session_count': geometry[0], 'required_sessions_sha256': geometry[1],
            'valid_cell_count': geometry[0] - missing, 'absent': missing,
            'invalid_or_duplicate': 0, 'failure_unknown': 0,
            'missing_before_first_valid': 1 if missing else 0,
            'missing_between_first_and_last_valid': 0,
            'missing_after_last_valid': 1 if missing else 0,
            'missing_without_any_valid': 0, 'potential_reference_count': demand[2],
            'potential_reference_missing_count': 1 if missing else 0})
    summary = {'schema': m.coverage.SCHEMA, 'profile_sha256': m.coverage.digest(profile),
        'runtime_project_id': m.PROJECT_ID, 'attempt_consumed': True,
        'terminal': 'complete', 'phase': 'complete', 'failure_code': None,
        'source_fingerprint_sha256': 'a' * 64, 'reader_receipt_sha256': 'b' * 64,
        'fresh_resolution_sha256': 'c' * 64, 'dense_envelopes_complete': not gaps,
        'required_cell_count': sum(row['required_session_count'] for row in rows),
        'valid_cell_count': sum(row['valid_cell_count'] for row in rows),
        'missing_cell_count': sum(row['absent'] for row in rows), 'per_selected': rows,
        **m.coverage.FALSE_FLAGS}
    if refused:
        summary.update(terminal='refused', phase='postcheck', failure_code='source_changed',
            dense_envelopes_complete=False)
    binding = {'project_id': m.PROJECT_ID, 'compile_id': 'synthetic_compile_1',
        'backtest_id': 'd' * 32, 'name': 'R329 synthetic metadata',
        'source_projection_pin': dict(m.PROJECTION_PIN), 'source_profile_pin': dict(m.SOURCE_PROFILE_PIN),
        'source_readback_pin': {'byte_count': 2000, 'sha256': 'e' * 64},
        'coverage_profile_sha256': m.coverage.digest(profile)}
    actual = {key: binding[key] for key in m.RUN_KEYS}
    actual['terminal'] = 'Runtime Error.' if refused else 'Completed.'
    return {'statistic_name': m.STATISTIC, 'statistic_bytes': m.canonical(summary),
        'expected_profile': profile, 'expected_run': binding, 'actual_run': actual}


def parse(case):
    return m.validate_selected(**case)


def refusal(code, case):
    with pytest.raises(m.Refused) as caught:
        parse(case)
    assert m.finite(caught.value) == code
    assert str(caught.value) == code


def test_completed_diagnostic_with_dense_gaps_is_not_strategy_success_or_launch_gate():
    case = fixture()
    result = parse(case)
    assert result['classification'] == 'diagnostic_complete_with_gaps'
    assert result['diagnostic_complete'] is True
    assert result['summary']['required_cell_count'] == 2286
    assert result['summary']['missing_cell_count'] == 2
    assert result['summary']['dense_envelopes_complete'] is False
    assert result['selected_statistic_pin'] == m.pin(case['statistic_bytes'])
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert len(m.canonical(result)) <= m.MAX_RECORD_BYTES
    assert b'raw_prices' not in case['statistic_bytes'].replace(b'raw_prices_exported', b'')


def test_complete_dense_envelopes_also_do_not_prove_actual_holdings_or_performance():
    result = parse(fixture(gaps=False))
    assert result['classification'] == 'diagnostic_complete_dense_envelopes_only'
    assert result['summary']['dense_envelopes_complete'] is True
    assert result['actual_target_or_holdings_path_proven'] is False
    assert result['complete_strategy_price_coverage_proven'] is False
    assert result['strategy_performance_observed'] is False


@pytest.mark.parametrize('terminal', sorted(m.FAILED_TERMINALS))
def test_actual_failed_terminal_overrides_even_completed_observation(terminal):
    case = fixture(gaps=False); case['actual_run']['terminal'] = terminal
    result = parse(case)
    assert result['diagnostic_complete'] is False
    assert result['classification'] == 'diagnostic_failed_terminal'
    assert result['summary']['terminal'] == 'complete'
    assert result['strategy_result_accepted'] is False


def test_refused_summary_is_finite_failure_evidence_only():
    result = parse(fixture(refused=True))
    assert result['summary']['failure_code'] == 'source_changed'
    assert result['diagnostic_complete'] is False
    assert result['summary_schema_checks_passed'] is True


def test_completed_terminal_cannot_clear_refused_summary():
    case = fixture(refused=True); case['actual_run']['terminal'] = 'Completed.'
    refusal('terminal', case)


@pytest.mark.parametrize('value', ('', 'Running', 'Completed', 'completed.', None, True, 0, {}, 'secret provider error'))
def test_unknown_missing_or_ambiguous_terminal_refuses_without_echo(value):
    case = fixture(); case['actual_run']['terminal'] = value
    refusal('terminal', case)


@pytest.mark.parametrize('value', ('OTHER', '', None, True, 'ARV2_W5_NATIVE_COVERAGE ', {'secret': 1}))
def test_only_exact_selected_statistic_name(value):
    case = fixture(); case['statistic_name'] = value
    refusal('statistic_name', case)


@pytest.mark.parametrize('value', (None, '', bytearray(b'{}'), b'', b' ' * 8003))
def test_raw_statistic_type_and_byte_bound_precede_json(value):
    case = fixture(); case['statistic_bytes'] = value
    refusal('statistic_bound', case)


@pytest.mark.parametrize('change', ('invalid_utf8', 'bom', 'trailing', 'space', 'nonfinite', 'duplicate_top',
    'duplicate_nested', 'noncanonical_unicode', 'deep', 'huge_integer'))
def test_json_boundary_rejects_duplicate_nonfinite_trailing_and_noncanonical_forms(change):
    case = fixture(); raw = case['statistic_bytes']
    if change == 'invalid_utf8': raw = b'\xff'
    elif change == 'bom': raw = b'\xef\xbb\xbf' + raw
    elif change == 'trailing': raw += b'{}'
    elif change == 'space': raw += b' '
    elif change == 'nonfinite': raw = b'{"number":NaN}'
    elif change == 'duplicate_top': raw = b'{"schema":"secret","schema":"secret"}'
    elif change == 'duplicate_nested': raw = b'{"nested":{"secret":1,"secret":2}}'
    elif change == 'noncanonical_unicode': raw = '{"secret":"é"}'.encode('utf-8')
    elif change == 'deep': raw = b'[' * 1200 + b']' * 1200
    elif change == 'huge_integer': raw = b'1' * 5000
    case['statistic_bytes'] = raw
    refusal('summary' if change == 'deep' else 'json', case)


@pytest.mark.parametrize('key', sorted(m.RUN_KEYS))
def test_actual_project_compile_job_and_name_are_each_exactly_bound(key):
    case = fixture(); case['actual_run'][key] = 1 if key == 'project_id' else 'mismatch'
    refusal('run_identity', case)


@pytest.mark.parametrize('change', ('extra', 'missing', 'project_bool', 'compile_none', 'job_uppercase', 'name_control'))
def test_expected_run_has_closed_strict_types(change):
    case = fixture(); binding = case['expected_run']
    if change == 'extra': binding['grant'] = True
    elif change == 'missing': del binding['compile_id']
    elif change == 'project_bool': binding['project_id'] = True
    elif change == 'compile_none': binding['compile_id'] = None
    elif change == 'job_uppercase': binding['backtest_id'] = 'A' * 32
    elif change == 'name_control': binding['name'] = 'name\nsecret'
    refusal('binding', case)


@pytest.mark.parametrize('change', ('projection', 'profile', 'readback_empty', 'readback_bool', 'readback_extra', 'readback_big', 'readback_hash'))
def test_source_bindings_are_fixed_or_externally_pinned_closed_records(change):
    case = fixture(); binding = case['expected_run']
    if change == 'projection': binding['source_projection_pin']['sha256'] = 'f' * 64
    elif change == 'profile': binding['source_profile_pin']['byte_count'] += 1
    elif change == 'readback_empty': binding['source_readback_pin']['byte_count'] = 0
    elif change == 'readback_bool': binding['source_readback_pin']['byte_count'] = True
    elif change == 'readback_extra': binding['source_readback_pin']['granted'] = True
    elif change == 'readback_big': binding['source_readback_pin']['byte_count'] = 65537
    elif change == 'readback_hash': binding['source_readback_pin']['sha256'] = 'unknown'
    refusal('source_binding', case)


@pytest.mark.parametrize('change', ('project', 'digest', 'bool_coercion', 'extra', 'source_context'))
def test_profile_is_exact_current_fixed_source_and_strict_nested_types(change):
    case = fixture()
    if change == 'project': case['expected_profile']['runtime_project_id'] = 40000001
    elif change == 'digest': case['expected_run']['coverage_profile_sha256'] = 'f' * 64
    elif change == 'bool_coercion': case['expected_profile']['orders_submitted'] = 0
    elif change == 'extra': case['expected_profile']['secret'] = 'unknown'
    elif change == 'source_context': case['expected_profile']['source_context_sha256'] = 'f' * 64
    refusal('profile', case)


@pytest.mark.parametrize('change', ('extra', 'schema', 'project', 'profile', 'attempt', 'flag', 'ordinal_bool',
    'count_float', 'count_bool', 'geometry', 'decision_digest', 'sum', 'gap_sum', 'reference', 'no_valid',
    'one_valid_interior', 'dense', 'missing_rows', 'row_extra', 'failure', 'fingerprint', 'phase'))
def test_summary_schema_geometry_categories_and_arithmetic_are_revalidated(change):
    case = fixture(); value = json.loads(case['statistic_bytes']); row = value['per_selected'][0]
    if change == 'extra': value['licensed_rows'] = []
    elif change == 'schema': value['schema'] = 'wrong'
    elif change == 'project': value['runtime_project_id'] += 1
    elif change == 'profile': value['profile_sha256'] = 'f' * 64
    elif change == 'attempt': value['attempt_consumed'] = 1
    elif change == 'flag': value['price_input_admitted'] = True
    elif change == 'ordinal_bool': row['ordinal'] = False
    elif change == 'count_float': row['absent'] = 2.0
    elif change == 'count_bool': row['invalid_or_duplicate'] = False
    elif change == 'geometry': row['required_session_count'] += 1
    elif change == 'decision_digest': row['eligible_decisions_sha256'] = 'f' * 64
    elif change == 'sum': value['required_cell_count'] += 1
    elif change == 'gap_sum': row['missing_before_first_valid'] += 1
    elif change == 'reference': row['potential_reference_missing_count'] = row['potential_reference_count'] + 1
    elif change == 'no_valid': row['missing_without_any_valid'] = row['required_session_count']
    elif change == 'one_valid_interior':
        total = row['required_session_count']; row.update(valid_cell_count=1, absent=total-1,
            missing_before_first_valid=0, missing_after_last_valid=total-2,
            missing_between_first_and_last_valid=1, potential_reference_missing_count=row['potential_reference_count']-1)
        value['valid_cell_count'] -= total-3; value['missing_cell_count'] += total-3
    elif change == 'dense': value['dense_envelopes_complete'] = True
    elif change == 'missing_rows': value['per_selected'].pop()
    elif change == 'row_extra': row['price'] = 'secret'
    elif change == 'failure': value['failure_code'] = 'secret'
    elif change == 'fingerprint': value['source_fingerprint_sha256'] = None
    elif change == 'phase': value['phase'] = 'coverage'
    case['statistic_bytes'] = m.canonical(value)
    refusal('summary', case)


def test_returned_metadata_does_not_alias_supplied_bindings_or_profiles():
    case = fixture(); before = copy.deepcopy(case); result = parse(case)
    result['binding']['source_readback_pin']['sha256'] = '0' * 64
    result['summary']['per_selected'][0]['absent'] = 123
    assert case == before


def test_finite_classifier_never_renders_hostile_or_raw_error():
    class Hostile(Exception):
        def __str__(self): raise AssertionError('must not render')
        def __repr__(self): raise AssertionError('must not render')
    assert m.finite(Hostile('secret')) == 'unknown'
    assert m.finite(m.Refused('secret')) == 'unknown'
    assert m.finite(m.Refused('summary', 'secret')) == 'unknown'
    assert m.finite(m.Refused('summary')) == 'summary'


def test_profile_declares_external_authentication_and_no_operational_capabilities():
    record = m.profile_record()
    assert record['coverage_profile_sha256'] == '97cc27c116037213dc6243164480336f98056f85abd7364185a684ae8d8194ad'
    assert all(record[name] is False for name in m.FALSE_FLAGS)
    tree = ast.parse(inspect.getsource(m))
    forbidden = {'open', 'exec', 'eval', '__import__', 'print', 'read_bytes', 'write_bytes',
        'request', 'send', 'getenv', 'mkdir', 'unlink', 'create_backtest', 'create_project'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
            assert name not in forbidden
        if isinstance(node, ast.Import):
            assert all(alias.name not in {'os', 'pathlib', 'socket', 'requests', 'subprocess'} for alias in node.names)


@pytest.mark.parametrize('where,code', (('actual', 'run_identity'), ('binding', 'binding'), ('profile', 'profile'), ('pin', 'source_binding')))
def test_string_subclass_metadata_keys_refuse_before_comparison(where, code):
    class Key(str): pass
    case = fixture()
    mapping = case['actual_run'] if where == 'actual' else case['expected_run'] if where == 'binding' else case['expected_profile'] if where == 'profile' else case['expected_run']['source_readback_pin']
    key = next(iter(mapping)); value = mapping.pop(key); mapping[Key(key)] = value
    refusal(code, case)


@pytest.mark.parametrize('change', ('extra', 'missing', 'bool', 'subclass'))
def test_actual_run_closed_keyset_and_exact_types(change):
    case = fixture()
    if change == 'extra': case['actual_run']['errors'] = 'not consumed'
    elif change == 'missing': del case['actual_run']['compile_id']
    elif change == 'bool': case['actual_run']['project_id'] = True
    else:
        class Row(dict): pass
        case['actual_run'] = Row(case['actual_run'])
    refusal('run_identity', case)
