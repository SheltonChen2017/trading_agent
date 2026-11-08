"""Identity-v2 selected response; no operation or private input reads."""
import ast
import copy
from pathlib import Path

import pytest

from scripts import arv2_newrule_reference_identity_response as m
from tests.analyst_revisions_v2 import test_newrule_backtest_response as old
from tests.analyst_revisions_v2 import test_reference_identity_projection as witness


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(autouse=True)
def select_module(monkeypatch):
    monkeypatch.setattr(old, 'm', m)


def message(context):
    return m.raw_diagnostic.MARKER + m.raw_diagnostic.canonical(context).decode('ascii')


def test_full_boundary_ast_equal_except_identity_import_and_context_validator():
    old_raw = (ROOT / 'scripts/arv2_newrule_backtest_response.py').read_bytes()
    assert m.sha(old_raw) == '24f77bfc8764137ae387ab01d546a9a6a13fe5799ba6697068e0cd6e2d314a08'
    new = ast.parse((ROOT / 'scripts/arv2_newrule_reference_identity_response.py').read_bytes())
    previous = ast.parse(old_raw)
    def normalize(tree):
        for index, node in enumerate(tree.body):
            if index == 0:
                assert isinstance(node, ast.Expr)
                node.value = ast.Constant('permitted documentation')
            elif isinstance(node, ast.ImportFrom) and node.module == 'scripts':
                for alias in node.names:
                    if alias.asname == 'raw_diagnostic': alias.name = 'permitted_context_validator'
            elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                    and target.id == 'SCHEMA' for target in node.targets):
                node.value = ast.Constant('permitted_schema')
            elif isinstance(node, ast.FunctionDef) and node.name == '_context':
                node.body = [ast.Pass()]
        return ast.dump(tree, include_attributes=False)
    assert normalize(new) == normalize(previous)


def test_finite_error_selected_pin_and_flags_unchanged():
    old.test_error_selection_is_finite_bound_and_pin_covers_only_selected_projection()


@pytest.mark.parametrize('mode', ['error', 'completed'])
def test_large_ignored_and_hostile_subtrees_never_traversed(mode):
    old.test_irrelevant_large_and_hostile_subtrees_are_not_traversed_or_canonicalized(mode)


@pytest.mark.parametrize('field,value', [('projectId', True), ('projectId', 1),
    ('backtestId', 'wrong'), ('name', 'wrong'), ('status', 'Completed.'), ('compileId', 'wrong')])
def test_exact_received_identity_remains_required(field, value):
    old.test_received_identity_types_and_exact_terminal_bindings_refuse(field, value)


def test_completed_statistics_are_not_financial_admission():
    old.test_completed_selection_does_not_claim_financial_result_validation()


def test_complete_new_witness_and_dates_retained_not_raw_identity_or_message():
    context = witness.complete_context()
    result = old.select(old.response(error=m.RAW_REFERENCE_LITERAL + '\n' + message(context)))
    checked = result['backtest']['finite_projected_error']
    assert checked['known_runtime_code'] == 'raw_reference_census_incomplete'
    assert checked['diagnostic_context'] == context
    assert checked['diagnostic_context'] is not context
    assert m.raw_diagnostic.validate_complete_witness(checked['diagnostic_context']) == context
    assert checked['cause_authenticated'] is False and checked['raw_error_retained'] is False
    assert m.RAW_REFERENCE_LITERAL.encode('ascii') not in m.canonical(result)
    assert old.validate(result) == result


def test_old_v1_context_is_not_new_witness_or_join_acceptance():
    parent = m.raw_diagnostic.parent
    text = parent.FAILURE_CODES[0] + '|context=' + parent.canonical(parent.context_record(2, 1)).decode('ascii')
    result = old.select(old.response(error=m.RAW_REFERENCE_LITERAL + '\n' + text))
    checked = result['backtest']['finite_projected_error']
    assert checked['known_runtime_code'] == 'raw_reference_census_incomplete'
    assert checked['diagnostic_context'] is None


def test_duplicate_new_contexts_and_other_known_code_remain_ambiguous():
    first = witness.complete_context()
    second = copy.deepcopy(first)
    second['witnesses'][0]['identity_sha256'] = '2' * 64
    for other in (message(second), 'quote_execution_clock'):
        checked = old.select(old.response(error=message(first), errorMessage=other))['backtest']['finite_projected_error']
        assert checked['known_runtime_code'] is None and checked['diagnostic_context'] is None


@pytest.mark.parametrize('change', ['raw_id', 'extra', 'hostile', 'too_many', 'hash', 'calendar',
    'history', 'partial', 'schema', 'unknown_type'])
def test_received_context_refuses_new_shape_drift_before_canonicalization(change):
    context = witness.complete_context()
    result = old.select(old.response(error=message(context)))
    context = result['backtest']['finite_projected_error']['diagnostic_context']
    if change == 'raw_id': context['witnesses'][0]['security_id'] = 'private'
    elif change == 'extra': context['unselected'] = old.Hostile()
    elif change == 'hostile': context['witnesses'][0]['unselected'] = old.Hostile()
    elif change == 'too_many': context['witnesses'] = [old.Hostile()] * 100000
    elif change == 'hash': context['witnesses'][0]['identity_sha256'] = 'g' * 64
    elif change == 'calendar': context['reference_session'] = '2022-10-20'
    elif change == 'history': context['extra_history_call'] = True
    elif change == 'partial': context['witnesses'] = []
    elif change == 'schema': context['schema'] = 'old-v1'
    else: context['decision_session'] = old.Hostile()
    with pytest.raises(m.Refused, match='^failure_evidence$'): old.validate(result)


@pytest.mark.parametrize('change', ['hash', 'count', 'bool_count', 'scope', 'extra',
    'schema', 'mode', 'whole', 'binding', 'row_extra', 'evidence_code', 'evidence_pin',
    'evidence_raw', 'evidence_cause', 'evidence_context'])
def test_selected_packet_pin_and_closed_flags_remain_required(change):
    old.test_received_selection_is_closed_and_pinned(change)


def test_selected_bound_includes_pin_envelope(monkeypatch):
    old.test_selected_output_bound_includes_pin_envelope(monkeypatch)
