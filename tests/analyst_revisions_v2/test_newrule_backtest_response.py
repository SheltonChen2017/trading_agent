"""Pure synthetic response projection; no provider, QC or private artifact use."""
import copy
import hashlib
import json

import pytest

from scripts import arv2_newrule_backtest_response as m


EXPECTED = {'project_id': 38364439, 'backtest_id': 'synthetic-job',
    'backtest_name': 'ARV2 SYNTHETIC SELECTED RESPONSE', 'compile_id': 'synthetic-compile'}


def response(mode='error', **changes):
    row = {'projectId': EXPECTED['project_id'], 'backtestId': EXPECTED['backtest_id'],
        'name': EXPECTED['backtest_name'], 'compileId': EXPECTED['compile_id'],
        'status': 'Runtime Error' if mode == 'error' else 'Completed.'}
    if mode == 'error': row['error'] = 'RuntimeError: quote_execution_clock'
    else: row['statistics'] = {m.META_STATISTIC: '{}', m.MONTHLY_STATISTIC: '{"synthetic":true}'}
    row.update(changes)
    return {'success': True, 'backtest': row}


def select(value, mode='error', **changes):
    return m.select_response(value, **{**EXPECTED, **changes}, mode=mode)


def validate(value, mode='error', **changes):
    return m.validate_selected(value, **{**EXPECTED, **changes}, mode=mode)


class Hostile:
    def __repr__(self): raise AssertionError('repr forbidden')
    def __str__(self): raise AssertionError('str forbidden')
    def __iter__(self): raise AssertionError('iteration forbidden')
    def __len__(self): raise AssertionError('len forbidden')
    def __bool__(self): raise AssertionError('bool forbidden')
    def __eq__(self, other): raise AssertionError('equality forbidden')


class StrangeDict(dict):
    def get(self, *args): raise AssertionError('subclass lookup forbidden')


class StrangeString(str): pass


def test_error_selection_is_finite_bound_and_pin_covers_only_selected_projection():
    raw = response()
    result = select(raw)
    assert result['schema'] == m.SCHEMA and result['mode'] == 'error'
    assert result['whole_response_authenticated'] is False
    assert result['backtest']['finite_projected_error']['known_runtime_code'] == 'quote_execution_clock'
    assert result['backtest']['finite_projected_error']['raw_error_retained'] is False
    assert result['backtest']['finite_projected_error']['cause_authenticated'] is False
    assert 'error' not in result['backtest']
    seed = {key: value for key, value in result.items() if key != 'selection_pin'}
    encoded = m.canonical(seed)
    assert result['selection_pin'] == {'scope': 'selected_projection_only',
        'byte_count': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest()}
    assert validate(result) == result
    assert validate(result) is not result
    assert validate(result)['backtest'] is not result['backtest']
    assert len(m.canonical(result)) <= 64 * 1024


@pytest.mark.parametrize('mode', ['error', 'completed'])
def test_irrelevant_large_and_hostile_subtrees_are_not_traversed_or_canonicalized(mode):
    raw = response(mode)
    raw['unknown'] = Hostile()
    for field in ('charts', 'orders', 'trades', 'rollingWindow', 'totalPerformance'):
        raw['backtest'][field] = {'hostile': Hostile(), 'large': 'x' * (2 * 1024 * 1024)}
    if mode == 'completed': raw['backtest']['statistics']['unselected'] = Hostile()
    result = select(raw, mode)
    assert len(m.canonical(result)) < 20000
    assert not {'charts', 'orders', 'trades', 'rollingWindow', 'totalPerformance'} & set(result['backtest'])
    assert validate(result, mode) == result


def test_completed_selection_does_not_claim_financial_result_validation():
    raw = response('completed')
    result = select(raw, 'completed')
    assert result['backtest']['statistics'] == raw['backtest']['statistics']
    assert set(result['backtest']['statistics']) == {m.META_STATISTIC, m.MONTHLY_STATISTIC}
    assert 'finite_projected_error' not in result['backtest']
    assert m.profile_record()['financial_result_validated'] is False
    raw['backtest']['statistics'][m.META_STATISTIC] = 'changed'
    assert result['backtest']['statistics'][m.META_STATISTIC] == '{}'


@pytest.mark.parametrize('field,value', [
    ('projectId', True), ('projectId', '38364439'), ('projectId', 1),
    ('backtestId', False), ('backtestId', 'other'), ('backtestId', StrangeString('synthetic-job')),
    ('name', 'other'), ('name', StrangeString(EXPECTED['backtest_name'])),
    ('status', 'Completed'), ('status', 'Completed.'), ('status', False),
    ('compileId', True), ('compileId', None), ('compileId', 'other'),
])
def test_received_identity_types_and_exact_terminal_bindings_refuse(field, value):
    raw = response(); raw['backtest'][field] = value
    with pytest.raises(m.Refused): select(raw)


@pytest.mark.parametrize('field,value', [
    ('project_id', True), ('project_id', 0), ('project_id', 2**63),
    ('backtest_id', ''), ('backtest_id', 'x' * 129), ('backtest_id', Hostile()),
    ('backtest_name', '\n'), ('backtest_name', '\x00'), ('backtest_name', 'é'),
    ('compile_id', False), ('compile_id', 'with space'),
])
def test_expected_launch_bindings_reject_unsafe_types_before_response_lookup(field, value):
    with pytest.raises(m.Refused, match='^binding$'):
        select(Hostile(), **{field: value})


@pytest.mark.parametrize('mode', [None, True, 'Completed.', 'runtime_error', Hostile()])
def test_modes_closed(mode):
    with pytest.raises(m.Refused, match='^binding$'): select(response(), mode)


def test_returned_compile_is_optional_but_not_fabricated_or_accepted_unbound():
    raw = response(); del raw['backtest']['compileId']
    result = select(raw)
    assert 'compileId' not in result['backtest']
    assert result['expected_binding']['compile_id'] == EXPECTED['compile_id']
    assert validate(result) == result
    assert select(raw, compile_id=None)['expected_binding']['compile_id'] is None
    with pytest.raises(m.Refused): select(response(), compile_id=None)


@pytest.mark.parametrize('change', ['false', 'truthy', 'errors', 'errors_dict', 'errors_none', 'errors_hostile'])
def test_top_level_success_and_errors_are_checked_without_rendering_provider_message(change):
    raw = response()
    if change == 'false': raw['success'] = False
    elif change == 'truthy': raw['success'] = 1
    elif change == 'errors': raw['errors'] = ['secret-provider-message']
    elif change == 'errors_dict': raw['errors'] = {}
    elif change == 'errors_none': raw['errors'] = None
    else: raw['errors'] = Hostile()
    with pytest.raises(m.Refused) as error: select(raw)
    assert m.finite(error.value) in ('response_success', 'response_errors')
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('where', ['top', 'row', 'stats'])
def test_mapping_subclasses_are_not_accepted_or_executed(where):
    raw = response('completed')
    if where == 'top': raw = StrangeDict(raw)
    elif where == 'row': raw['backtest'] = StrangeDict(raw['backtest'])
    else: raw['backtest']['statistics'] = StrangeDict(raw['backtest']['statistics'])
    with pytest.raises(m.Refused): select(raw, 'completed')


@pytest.mark.parametrize('value', ['', 'é', 'x' * 8193, True, None, Hostile(), StrangeString('{}')])
def test_selected_statistic_string_bounds_ascii_and_type(value):
    raw = response('completed'); raw['backtest']['statistics'][m.META_STATISTIC] = value
    with pytest.raises(m.Refused, match='^statistics$'): select(raw, 'completed')


def test_exact_statistic_bound_accepted_without_parsing_financial_content():
    raw = response('completed'); raw['backtest']['statistics'][m.META_STATISTIC] = 'x' * 8192
    result = select(raw, 'completed')
    assert len(result['backtest']['statistics'][m.META_STATISTIC]) == 8192
    assert validate(result, 'completed') == result


@pytest.mark.parametrize('field,value', [
    ('error', Hostile()), ('error', StrangeString('quote_execution_clock')),
    ('error', 'x' * 32769), ('error', 'é' * 16385), ('error', '\ud800'),
    ('error', '\n' * 513), ('errors', ['x'] * 9), ('errors', {'x': 'y'}),
    ('errors', [Hostile()]), ('stacktrace', True),
])
def test_selected_error_inputs_have_finite_shape_and_byte_line_bounds(field, value):
    raw = response(); raw['backtest'][field] = value
    with pytest.raises(m.Refused) as error: select(raw)
    assert m.finite(error.value) in ('error_bound', 'error_shape')


@pytest.mark.parametrize('field', ['error', 'errorMessage', 'stacktrace', 'errors'])
def test_each_bounded_error_field_can_supply_the_fixed_literal_but_no_secret_is_retained(field):
    raw = response(); raw['backtest'].pop('error')
    value = 'private-secret-row\nAcceptedRiskSixUniverseOrderQcRuntimeError: ' + m.RAW_REFERENCE_LITERAL
    raw['backtest'][field] = [value] if field == 'errors' else value
    result = select(raw)
    evidence = result['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] == m.RAW_REFERENCE_CODE
    assert evidence['diagnostic_context'] is None
    assert b'private-secret-row' not in m.canonical(result)
    assert b'RAW reference price' not in m.canonical(result)


@pytest.mark.parametrize('text', [
    'prefix ' + m.RAW_REFERENCE_LITERAL,
    m.RAW_REFERENCE_LITERAL + ' trailing',
    m.RAW_REFERENCE_LITERAL + '; context={"secret":1}',
    'raise ValueError(' + repr(m.RAW_REFERENCE_LITERAL) + ')',
    'RuntimeError: not_quote_execution_clock',
    'unknown-secret-error',
])
def test_unsupported_or_partial_messages_remain_unknown_without_cause_claim(text):
    result = select(response(error=text))
    evidence = result['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] is None and evidence['known_runtime_code_sha256'] is None
    assert evidence['cause_authenticated'] is False and evidence['raw_error_retained'] is False
    assert text.encode('ascii') not in m.canonical(result)


@pytest.mark.parametrize('messages', [
    ['quote_execution_clock\nquote_execution_type', 'quote_execution_clock'],
    ['RuntimeError: quote_execution_clock RuntimeError: quote_execution_type', 'quote_execution_clock'],
    [m.RAW_REFERENCE_LITERAL, 'quote_execution_clock'],
])
def test_conflicting_known_categories_within_or_across_messages_remain_unknown(messages):
    raw = response(error=messages[0], errorMessage=messages[1])
    evidence = select(raw)['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] is None


def context_message(context):
    return m.RAW_REFERENCE_CODE + '|context=' + json.dumps(context,
        sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def test_new_closed_raw_context_is_selected_without_historical_raw_context_or_prices():
    context = m.raw_diagnostic.context_record(3, 2)
    raw = response(error=m.RAW_REFERENCE_LITERAL + '\n' + context_message(context))
    result = select(raw)
    evidence = result['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] == m.RAW_REFERENCE_CODE
    assert evidence['diagnostic_context'] == context
    assert evidence['diagnostic_context'] is not context
    assert evidence['diagnostic_context']['cause_authenticated'] is False
    assert evidence['diagnostic_context']['probe_prices_used'] is False
    assert evidence['diagnostic_context']['sizing_repaired'] is False
    assert validate(result) == result
    assert validate(result)['backtest']['finite_projected_error']['diagnostic_context'] is not evidence['diagnostic_context']


def test_distinct_valid_contexts_are_ambiguous_not_overwritten_by_last_or_first():
    first = m.raw_diagnostic.context_record(3, 2)
    second = m.raw_diagnostic.context_record(4, 3)
    result = select(response(error=context_message(first), errorMessage=context_message(second)))
    evidence = result['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] is None and evidence['diagnostic_context'] is None


def test_repeat_identical_valid_context_and_code_do_not_create_ambiguity():
    context = m.raw_diagnostic.context_record(3, 2)
    text = context_message(context)
    evidence = select(response(error=text, errorMessage=text))['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] == m.RAW_REFERENCE_CODE
    assert evidence['diagnostic_context'] == context


def test_valid_raw_context_with_other_known_failure_does_not_erase_conflict():
    text = context_message(m.raw_diagnostic.context_record(3, 2))
    evidence = select(response(error=text, errorMessage='quote_execution_clock'))['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] is None and evidence['diagnostic_context'] is None


@pytest.mark.parametrize('change', ['extra', 'huge', 'subclass', 'group_extra', 'group_value',
    'probe_extra', 'probe_items', 'offset_extra', 'offset_value', 'unknown_code',
    'false_cause', 'prices', 'repair', 'requested_bool', 'predicate_subclass'])
def test_received_context_shape_and_semantics_refuse_before_unselected_hostile_values(change):
    context = m.raw_diagnostic.context_record(3, 2)
    value = select(response(error=context_message(context)))
    evidence = value['backtest']['finite_projected_error']
    context = evidence['diagnostic_context']
    if change == 'extra': context['unselected'] = Hostile()
    elif change == 'huge': context['schema'] = 'x' * (2 * 1024 * 1024)
    elif change == 'subclass': evidence['diagnostic_context'] = StrangeDict(context)
    elif change == 'group_extra': context['missing_holdings']['unselected'] = Hostile()
    elif change == 'group_value': context['missing_holdings']['unknown'] = Hostile()
    elif change == 'probe_extra': context['probe']['unselected'] = Hostile()
    elif change == 'probe_items': context['probe']['items'] = 2**1000
    elif change == 'offset_extra': context['probe']['rows_by_offset']['unselected'] = Hostile()
    elif change == 'offset_value': context['probe']['rows_by_offset']['exact_reference'] = Hostile()
    elif change == 'unknown_code': evidence['known_runtime_code'] = 'quote_execution_clock'
    elif change == 'false_cause': context['cause_authenticated'] = True
    elif change == 'prices': context['probe_prices_used'] = True
    elif change == 'repair': context['sizing_repaired'] = True
    elif change == 'requested_bool': context['requested'] = True
    else: context['predicate'] = StrangeString(m.RAW_REFERENCE_CODE)
    with pytest.raises(m.Refused, match='^failure_evidence$'): validate(value)


def test_context_token_with_malformed_or_duplicate_json_remains_unknown():
    text = m.RAW_REFERENCE_CODE + '|context={"schema":"one","schema":"two"}'
    evidence = select(response(error=text))['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] is None and evidence['diagnostic_context'] is None


@pytest.mark.parametrize('code', sorted(m.frozen.KNOWN_CODES))
def test_frozen_complete_inventory_remains_finite_diagnostic_only(code):
    result = select(response(error='NewruleError: ' + code))
    evidence = result['backtest']['finite_projected_error']
    assert evidence['known_runtime_code'] == code
    assert evidence['known_runtime_code_sha256'] == m.sha(code.encode('ascii'))
    assert evidence['cause_authenticated'] is False
    assert validate(result) == result


@pytest.mark.parametrize('category', sorted(m.PYTHON_CATEGORIES))
def test_frozen_python_categories_retained_without_raw_message(category):
    result = select(response(error=category + ': secret body'))
    evidence = result['backtest']['finite_projected_error']
    assert evidence['python_error_category'] == category
    assert b'secret body' not in m.canonical(result)


@pytest.mark.parametrize('change', ['hash', 'count', 'bool_count', 'scope', 'extra',
    'schema', 'mode', 'whole', 'binding', 'row_extra', 'evidence_code', 'evidence_pin',
    'evidence_raw', 'evidence_cause', 'evidence_context'])
def test_received_selection_is_closed_and_pinned(change):
    value = select(response())
    if change == 'hash': value['selection_pin']['sha256'] = '0' * 64
    elif change == 'count': value['selection_pin']['byte_count'] += 1
    elif change == 'bool_count': value['selection_pin']['byte_count'] = True
    elif change == 'scope': value['selection_pin']['scope'] = 'complete_http_body'
    elif change == 'extra': value['extra'] = 'unbound'
    elif change == 'schema': value['schema'] = 'other'
    elif change == 'mode': value['mode'] = 'completed'
    elif change == 'whole': value['whole_response_authenticated'] = True
    elif change == 'binding': value['expected_binding']['project_id'] = True
    elif change == 'row_extra': value['backtest']['error'] = 'secret'
    else:
        evidence = value['backtest']['finite_projected_error']
        key, item = {'evidence_code': ('known_runtime_code', 'invented'),
            'evidence_pin': ('known_runtime_code_sha256', None),
            'evidence_raw': ('raw_error_retained', True),
            'evidence_cause': ('cause_authenticated', True),
            'evidence_context': ('diagnostic_context', {'secret': 'row'})}[change]
        evidence[key] = item
    with pytest.raises(m.Refused): validate(value)


def test_unknown_failure_with_nonnull_hash_refuses_finitely_without_none_encode():
    value = select(response(error='unknown'))
    value['backtest']['finite_projected_error']['known_runtime_code_sha256'] = '0' * 64
    with pytest.raises(m.Refused, match='^failure_evidence$'): validate(value)


def test_received_statistics_extra_cannot_hide_under_an_old_pin():
    value = select(response('completed'), 'completed')
    value['backtest']['statistics']['unselected'] = Hostile()
    with pytest.raises(m.Refused, match='^statistics$'): validate(value, 'completed')


def test_selected_output_bound_includes_pin_envelope(monkeypatch):
    value = select(response())
    monkeypatch.setattr(m, 'MAX_SELECTED_BYTES', len(m.canonical(value)) - 1)
    with pytest.raises(m.Refused, match='^selected_bound$'): select(response())


def test_finite_classifier_uses_only_exact_own_exception_without_rendering_subclasses():
    class HostileRefused(m.Refused):
        def __str__(self): raise AssertionError('render forbidden')
    assert all(m.finite(m.Refused(code)) == code for code in m.FINITE)
    assert m.finite(HostileRefused('response')) == 'unknown'
    assert m.finite(m.Refused(Hostile())) == 'unknown'
    assert m.finite(ValueError('secret')) == 'unknown'


def test_profile_is_public_finite_and_does_not_claim_whole_body_or_financial_admission():
    profile = m.profile_record()
    assert profile['selection_pin_scope'] == 'selected_projection_only'
    assert profile['complete_body_pin'] is False and profile['whole_response_authenticated'] is False
    assert profile['financial_result_validated'] is False and profile['cause_authenticated'] is False
    assert profile['maximum_selected_bytes'] == 65536
    assert json.loads(m.canonical(profile)) == profile
