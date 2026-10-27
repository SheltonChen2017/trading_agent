"""Pure selected result-envelope tests; genuine common aggregate fixtures only."""
import ast
import copy
import json
from pathlib import Path

import pytest

from scripts import arv2_r298_common_price_result as m
from tests.analyst_revisions_v2 import test_common_price_comparison_runtime as aggregate_fixture


def refused(code, operation):
    with pytest.raises(m.Refused) as caught: operation()
    assert m.finite(caught.value) == code


@pytest.fixture
def case():
    statistics, profile = aggregate_fixture.result_fixture()
    binding = {'project_id': profile['runtime_project_id'], 'backtest_id': 'a' * 32,
        'name': 'R326-common-six-AR0-synthetic', 'compile_id': 'compile-fixed',
        'source_manifest_sha256': 'b' * 64, 'common_profile_sha256': profile['profile_sha256'],
        'run_scope_tag': 'R326-SYNTHETIC'}
    response = {'success': True, 'errors': [], 'backtest': {'projectId': binding['project_id'],
        'backtestId': binding['backtest_id'], 'name': binding['name'], 'compileId': binding['compile_id'],
        'status': 'Completed.', 'statistics': statistics}}
    launch = m.canonical({'schema': m.LAUNCH_SCHEMA, 'binding': binding})
    return {'profile': profile, 'binding': binding, 'response': response, 'launch': launch,
        'launch_pin': {'byte_count': len(launch), 'sha256': m.sha(launch)}}


def select(case, response=None, **extra):
    return m.select_response(response if response is not None else case['response'],
        expected_run_binding=case['binding'], expected_profile=case['profile'], **extra)


def validate(case, raw, pin, **extra):
    return m.validate_selected(raw, expected_selected_pin=pin, expected_run_binding=case['binding'],
        expected_profile=case['profile'], actual_reader_exit=0, **extra)


def test_exact_terminal_job_profile_and_genuine_common_aggregate_are_selected_and_pinned(case):
    selected, pin = select(case)
    raw = m.canonical(selected)
    result = validate(case, raw, pin)
    assert result['selected'] == selected and result['selected_pin'] == pin
    assert result['aggregate']['meta']['raw_reference_history_calls'] == 0
    assert result['aggregate']['meta']['split_unit_history_calls'] == 302
    assert selected['compile_binding_source'] == 'response_only' and selected['launch_binding_pin'] is None
    assert selected['aggregate_schema_checks_passed'] is True
    assert all(selected[key] is False for key in m.FALSE_FLAGS)
    result['selected']['binding']['name'] = 'changed'
    assert selected['binding']['name'] == case['binding']['name']


class Unreadable:
    def __iter__(self): raise AssertionError('ignored private subtree traversed')
    def __str__(self): raise AssertionError('ignored private subtree rendered')
    def __repr__(self): raise AssertionError('ignored private subtree rendered')


def test_unknown_charts_orders_trades_and_other_statistics_are_not_traversed_or_hashed(case):
    response = copy.deepcopy(case['response'])
    for name in ('charts', 'orders', 'trades', 'rollingWindow', 'totalPerformance', 'rawPrices'):
        response['backtest'][name] = Unreadable()
    response['privateUnknown'] = Unreadable()
    response['backtest']['statistics']['Unknown licensed rows'] = Unreadable()
    selected, pin = select(case, response)
    baseline, baseline_pin = select(case)
    assert selected == baseline and pin == baseline_pin
    assert set(selected['statistics']) == {m.runtime.META_STATISTIC, m.runtime.MONTHLY_STATISTIC}


@pytest.mark.parametrize('mutation,code', [('success', 'response_success'), ('errors', 'response_errors'),
    ('errors_type', 'response_errors'), ('project', 'response_identity'), ('project_bool', 'response_identity'),
    ('job', 'response_identity'), ('name', 'response_identity'), ('runtime', 'response_terminal'),
    ('completed_without_dot', 'response_terminal'), ('compile', 'response_compile'), ('compile_null', 'response_compile')])
def test_completed_or_foreign_job_alone_never_passes(case, mutation, code):
    response = copy.deepcopy(case['response']); row = response['backtest']
    if mutation == 'success': response['success'] = 1
    elif mutation == 'errors': response['errors'] = ['PRIVATE']
    elif mutation == 'errors_type': response['errors'] = {}
    elif mutation == 'project': row['projectId'] += 1
    elif mutation == 'project_bool': row['projectId'] = True
    elif mutation == 'job': row['backtestId'] = 'c' * 32
    elif mutation == 'name': row['name'] += '-other'
    elif mutation == 'runtime': row['status'] = 'Runtime Error'
    elif mutation == 'completed_without_dot': row['status'] = 'Completed'
    elif mutation == 'compile': row['compileId'] = 'other-compile'
    else: row['compileId'] = None
    refused(code, lambda: select(case, response))


def test_missing_response_compile_requires_external_exact_launch_bytes_not_a_boolean(case):
    response = copy.deepcopy(case['response']); del response['backtest']['compileId']
    refused('launch_required', lambda: select(case, response))
    refused('launch_pin', lambda: select(case, response, launch_binding_bytes=True))
    arguments = {'launch_binding_bytes': case['launch'], 'expected_launch_binding_pin': case['launch_pin']}
    selected, pin = select(case, response, **arguments)
    assert selected['compile_binding_source'] == 'launch_only'
    assert selected['response_compile_id'] is None and selected['launch_binding_pin'] == case['launch_pin']
    refused('launch_required', lambda: validate(case, m.canonical(selected), pin))
    assert validate(case, m.canonical(selected), pin, **arguments)['aggregate']['meta']['decision_count'] == 302
    selected_both, _ = select(case, **arguments)
    assert selected_both['compile_binding_source'] == 'response_and_launch'


@pytest.mark.parametrize('mutation', ['pin', 'binding', 'unknown', 'duplicate', 'trailing', 'bool_pin', 'missing_pin'])
def test_launch_proof_is_closed_bytes_exact_externally_pinned_and_same_run(case, mutation):
    response = copy.deepcopy(case['response']); del response['backtest']['compileId']
    raw, pin = case['launch'], dict(case['launch_pin'])
    if mutation == 'pin': pin['sha256'] = 'c' * 64
    elif mutation == 'binding':
        value = json.loads(raw); value['binding']['compile_id'] = 'other'; raw = m.canonical(value)
    elif mutation == 'unknown':
        value = json.loads(raw); value['credentials'] = 'PRIVATE'; raw = m.canonical(value)
    elif mutation == 'duplicate': raw = b'{"schema":"duplicate",' + raw[1:]
    elif mutation == 'trailing': raw += b'\n'
    elif mutation == 'bool_pin': pin['byte_count'] = True
    if mutation not in ('pin', 'bool_pin'):
        pin = {'byte_count': len(raw), 'sha256': m.sha(raw)}
    if mutation == 'missing_pin': pin = None
    with pytest.raises(m.Refused): select(case, response, launch_binding_bytes=raw, expected_launch_binding_pin=pin)


@pytest.mark.parametrize('exit_value', [2, -9, None, True, False, '0'])
def test_external_actual_exit_is_mandatory_and_precedes_even_supplied_byte_parsing(case, exit_value):
    refused('actual_exit', lambda: m.validate_selected(Unreadable(), expected_selected_pin=Unreadable(),
        expected_run_binding=Unreadable(), expected_profile=Unreadable(), actual_reader_exit=exit_value))


def test_authentic_matching_selected_output_cannot_override_actual_nonzero_reader_exit(case):
    selected, pin = select(case)
    refused('actual_exit', lambda: m.validate_selected(m.canonical(selected), expected_selected_pin=pin,
        expected_run_binding=case['binding'], expected_profile=case['profile'], actual_reader_exit=2))


@pytest.mark.parametrize('mutation,code', [('extra', 'selected_shape'), ('terminal', 'selected_shape'),
    ('flags', 'selected_shape'), ('binding', 'selected_binding'), ('compile_source', 'selected_binding'),
    ('aggregate_hash', 'aggregate'), ('statistics_extra', 'statistics'), ('statistic_bound', 'statistics'),
    ('source_failure', 'aggregate')])
def test_pinned_selected_bytes_do_not_bypass_closed_shape_context_or_aggregate_validation(case, mutation, code):
    selected, _ = select(case)
    if mutation == 'extra': selected['privateError'] = 'PRIVATE'
    elif mutation == 'terminal': selected['terminal'] = 'Completed'
    elif mutation == 'flags': selected['strategy_result_accepted'] = True
    elif mutation == 'binding': selected['binding']['source_manifest_sha256'] = 'c' * 64
    elif mutation == 'compile_source': selected['compile_binding_source'] = 'launch_only'
    elif mutation == 'aggregate_hash': selected['aggregate_sha256'] = 'c' * 64
    elif mutation == 'statistics_extra': selected['statistics']['other'] = 'PRIVATE'
    elif mutation == 'statistic_bound': selected['statistics'][m.runtime.META_STATISTIC] = 'x' * 16385
    else:
        meta = json.loads(selected['statistics'][m.runtime.META_STATISTIC])
        meta['common_price']['ledger']['source_observation']['lookup_counts']['vendor_price_lookup_completed'] -= 1
        selected['statistics'][m.runtime.META_STATISTIC] = m.canonical(meta).decode()
    raw = m.canonical(selected); pin = {'byte_count': len(raw), 'sha256': m.sha(raw)}
    refused(code, lambda: validate(case, raw, pin))


@pytest.mark.parametrize('mutation', ['mismatch', 'size_bool', 'missing', 'extra', 'trailing', 'duplicate'])
def test_selected_hash_length_canonical_single_frame_and_pin_are_all_required(case, mutation):
    selected, pin = select(case); raw = m.canonical(selected)
    if mutation == 'mismatch': pin['sha256'] = 'c' * 64
    elif mutation == 'size_bool': pin['byte_count'] = True
    elif mutation == 'missing': del pin['byte_count']
    elif mutation == 'extra': pin['raw'] = 'PRIVATE'
    elif mutation == 'trailing': raw += b'\n'
    else: raw = b'{"schema":"duplicate",' + raw[1:]
    if mutation in ('trailing', 'duplicate'): pin = {'byte_count': len(raw), 'sha256': m.sha(raw)}
    with pytest.raises(m.Refused): validate(case, raw, pin)


@pytest.mark.parametrize('mutation,code', [('extra', 'binding'), ('project', 'profile_binding'),
    ('profile', 'profile_binding'), ('compile_none', 'binding'), ('manifest', 'binding'),
    ('scope', 'binding'), ('name', 'binding')])
def test_expected_source_job_binding_is_closed_and_tied_to_genuine_profile(case, mutation, code):
    if mutation == 'extra': case['binding']['authorized'] = True
    elif mutation == 'project': case['binding']['project_id'] += 1
    elif mutation == 'profile': case['binding']['common_profile_sha256'] = 'c' * 64
    elif mutation == 'compile_none': case['binding']['compile_id'] = None
    elif mutation == 'manifest': case['binding']['source_manifest_sha256'] = 'not-a-hash'
    elif mutation == 'scope': case['binding']['run_scope_tag'] = '../not-a-scope'
    else: case['binding']['name'] = 'not-printable\n'
    refused(code, lambda: select(case))


def test_profile_flags_and_source_import_surface_do_not_create_operational_capabilities():
    profile = m.profile_record()
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    raw = Path(m.__file__).read_bytes(); tree = ast.parse(raw)
    imported = {node.names[0].name.split('.')[0] for node in tree.body if isinstance(node, ast.Import)}
    assert imported == {'hashlib', 'json', 're'}
    forbidden = {'open', 'eval', 'exec', '__import__', 'compile'}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden
        for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr in ('read_bytes', 'write_bytes', 'request',
        'get_file_path', 'save_bytes', 'getenv', 'system', 'Popen') for node in ast.walk(tree))
    assert not any(isinstance(node, ast.If) and any(isinstance(child, ast.Name) and child.id == '__name__'
        for child in ast.walk(node.test)) for node in tree.body)
