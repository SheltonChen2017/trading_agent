"""Public AC observation joins only; no retained data or operational calls."""
import ast
import builtins
import copy
import inspect
import os
from pathlib import Path

import pytest

from scripts import arv2_r298_ac_source_binding as m
from scripts import arv2_r298_price_lineage_routes as routes
from scripts import prepare_arv2_r298_price_lineage as producer


def test_exact_closed_price_summary_joins_observed_private_pin_and_prior_data_bindings(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('metadata validation attempted an operational entry or data read')
    monkeypatch.setattr(producer, 'run', deny)
    monkeypatch.setattr(producer, 'observe', deny)
    monkeypatch.setattr(producer, 'Store', deny)
    monkeypatch.setattr(producer.data_guard, 'FixedDataGuard', deny)
    summary = routes.validate_summary(m.expected_summary())
    assert producer._summary(summary) == summary  # Independent frozen input/source-policy joins.
    fact = m.observed_fact()
    assert fact['private_file'] == {
        'relative_path': 'artifacts/analyst_revisions_v2/newrule_price_lineage/R326-20261027-AC/price-lineage-private.json',
        'byte_count': summary['private_frame_byte_count'], 'sha256': summary['private_frame_sha256']}
    assert summary['binding_contract']['binding_count'] == 6151
    assert summary['potential_stock_count'] == 5641
    assert summary['conditional_never_potential_stock_count'] == 510
    assert summary['disposition_counts'] == {'stocks': {
        'routed': 5636, 'refused': 5, 'conditional_never_potential': 510}, 'funds': {'routed': 8}}
    assert summary['refusal_counts'] == {'stocks': {'identity_missing': 4, 'global_collision': 1}, 'funds': {}}
    assert summary['price_window'] == ['2020-12-31', '2026-10-13']
    assert summary['old_predicate_only_route_correction_count'] == 74
    for key in routes.FALSE_FLAGS:
        assert summary[key] is False
    changed = copy.deepcopy(summary)
    changed['price_coverage_proven'] = True
    with pytest.raises(routes.Refused): routes.validate_summary(changed)
    changed = copy.deepcopy(summary)
    changed['source_pins']['demand_frame']['sha256'] = 'f' * 64
    with pytest.raises(producer.Refused): producer._summary(changed)


def test_recorded_actual_zero_is_a_scoped_fact_not_a_future_permit():
    fact = m.observed_fact()
    assert fact['schema'] == producer.SCHEMA
    assert fact['expected_head'] == 'd25ab8eaaa4a3abea39c41b7e3d6470b429c4e16'
    assert fact['caller_sha256'] == '2b6de35e7115010573ba40221a85a29174db8004ff35faea5932799b963618d3'
    assert fact['report']['byte_count'] > 0
    assert fact['report']['sha256'] == '2eec05418cd5e61ba453c1ee8c900bb5776fd5c21d5e1c05348ca6a701ac4267'
    for role in ('producer', 'validator'):
        actual = fact[role]
        assert type(actual['actual_exit']) is int and actual['actual_exit'] == 0
        assert actual['bound'] is None and actual['spawn_observed'] is True
        assert actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == routes.sha(b'')
        assert actual['dispatched_at'] < actual['completion_observed_at']
    assert fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes'] == 6063
    assert fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256']
    assert fact['producer']['completion_observed_at'] <= fact['validator']['dispatched_at']
    profile = m.profile_record()
    assert profile['new_consumer_freeze_required'] is True
    assert all(profile[key] is False for key in ('old_control_or_operation_read',
        'source_admission_granted', 'operational_authority_granted', 'point_in_time_proven',
        'strategy_price_admitted', 'strategy_nav_admitted', 'formal_forward_ready', 'paper_or_live_ready'))


def test_accessors_return_independent_mutable_copies_including_deep_nested_metadata():
    original = (m.observed_fact(), m.expected_summary(), m.profile_record())
    fact, summary, profile = m.observed_fact(), m.expected_summary(), m.profile_record()
    fact['producer']['actual_exit'] = 2
    fact['validator']['stdout_sha256'] = 'f' * 64
    fact['private_file']['relative_path'] = 'synthetic/other-leaf'
    summary['binding_contract']['binding_count'] = 1
    summary['source_pins']['aa_frame']['sha256'] = 'f' * 64
    summary['disposition_counts']['stocks'].clear()
    summary['refusal_counts']['stocks']['global_collision'] = 0
    summary['price_window'][0] = '2026-10-13'
    profile['new_consumer_freeze_required'] = False
    assert (m.observed_fact(), m.expected_summary(), m.profile_record()) == original
    assert m.observed_fact()['producer'] is not m.observed_fact()['producer']
    assert m.expected_summary()['source_pins'] is not m.expected_summary()['source_pins']


def test_binding_module_contains_only_literal_metadata_and_nonoperational_accessors(monkeypatch):
    tree = ast.parse(inspect.getsource(m))
    assert {node.names[0].name for node in tree.body if isinstance(node, ast.Import)} == {'hashlib', 'json'}
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        'observed_fact', 'expected_summary', 'profile_record'}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assert isinstance(node.value, ast.Constant) and type(node.value.value) in (str, bytes)
        assert not isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
    forbidden = {'open', 'print', 'exec', 'eval', '__import__', 'read_bytes', 'read_text',
        'observe', 'run', 'load_key', 'request', 'get', 'post', 'connect'}
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls & forbidden
    def deny(*args, **kwargs):
        raise AssertionError('literal metadata accessor tried filesystem access')
    with monkeypatch.context() as patch:
        for module, name in ((builtins, 'open'), (os, 'open'), (os, 'read'),
            (Path, 'read_bytes'), (Path, 'read_text')):
            patch.setattr(module, name, deny)
        assert m.observed_fact()['private_file']['byte_count'] == 16344399
        assert m.expected_summary()['refusal_counts']['stocks']['identity_missing'] == 4
        assert m.profile_record()['operational_authority_granted'] is False
