"""Public AE source-spec facts only; no spent inputs or QC operations."""
import ast
import builtins
import copy
import inspect
import os
from pathlib import Path

import pytest

from scripts import arv2_r298_ae_source_binding as m
from scripts import prepare_arv2_r298_native_price_specification as producer
from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native


def test_exact_native_spec_bytes_selection_and_prior_failure_metadata_join_without_operations(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('public source specification validation reached an operation')
    for module, name in ((producer, 'run'), (producer, 'observe'), (producer, 'prepare'),
            (producer, 'Store'), (producer.data_guard, 'FixedDataGuard'),
            (producer.previous, 'run'), (producer.previous, 'observe')):
        monkeypatch.setattr(module, name, deny)
    fact = m.observed_fact()
    specification = native.validate_specification(m.expected_specification())
    evidence = m.expected_selection_evidence()
    producer._evidence(evidence)
    assert specification == native.make_specification(evidence['selected_whole_binding_sha256s'])
    raw = native.canonical(specification)
    assert fact['specification_file'] == {'relative_path':
        'artifacts/analyst_revisions_v2/newrule_native_price_spec/R326-20261027-AE/native-price-specification.json',
        'byte_count': len(raw), 'sha256': producer.sha(raw)}
    assert len(raw) == 1791
    assert producer.sha(raw) == '9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66'
    assert specification['full_binding_count'] == 6151 and specification['full_axis_count'] == 3466
    assert specification['requested_session_count'] == 1452
    assert specification['first_session'] == '2020-12-31' and specification['last_session'] == '2026-10-13'
    assert evidence['selected_case_count'] == len(specification['selected_whole_binding_sha256s']) == 5
    assert evidence['original_binding_schema_and_semantic_row_hash_checked_count'] == 5
    assert evidence['original_class_and_identity_evidence_checked_count'] == 5
    assert evidence['original_native_QC_SIDs_available'] is False
    assert evidence['vendor_source_blockers_remaining'] == 5
    prior = producer.source_binding()
    assert prior['case_count'] == 5 and prior['planned_job_count'] == 9
    assert prior['source_refusal_counts'] == {'identity_missing': 4, 'global_collision': 1}
    assert m.profile_record()['specification_sha256'] == producer.sha(raw)
    changed = copy.deepcopy(specification); changed['maximum_history_calls'] = 6
    with pytest.raises(native.Refused): native.validate_specification(changed)
    changed = copy.deepcopy(evidence); changed['original_native_QC_SIDs_available'] = True
    with pytest.raises(producer.Refused): producer._evidence(changed)


def test_actual_offline_zeroes_are_scoped_facts_and_do_not_turn_old_AD_failure_into_success(monkeypatch):
    fact = m.observed_fact()
    assert fact['schema'] == producer.SCHEMA
    assert fact['expected_head'] == 'd49e54152f4d2bba50161850c82d692af1c7fc3c'
    assert fact['caller_sha256'] == '501371b38ab01fd23262b13da9432b6356dfa65a93ef27132992947307884673'
    assert fact['report'] == {'byte_count': 4797,
        'sha256': 'dc9d728d3dcb61f6393d82b22c7c9a05b06b1995ea0922fa965eb151fe59b010'}
    for name in ('producer', 'validator'):
        actual = fact[name]
        assert type(actual['actual_exit']) is int and actual['actual_exit'] == 0
        assert actual['bound'] is None and actual['spawn_observed'] is True
        assert actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == producer.sha(b'')
        assert actual['dispatched_at'] < actual['completion_observed_at']
    assert fact['producer']['completion_observed_at'] <= fact['validator']['dispatched_at']
    assert fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes'] == 4926
    assert fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256']
    profile = m.profile_record()
    assert profile['new_QC_source_project_rights_and_run_freeze_required'] is True
    assert all(profile[key] is False for key in ('old_control_or_operation_read',
        'operational_authority_granted', 'paid_rights_granted', 'native_identity_admitted',
        'strategy_price_admitted', 'strategy_nav_admitted', 'point_in_time_proven',
        'formal_forward_ready', 'paper_or_live_ready'))
    assert producer.anchor.observed_fact()['producer']['actual_exit'] == 2
    assert producer.anchor.expected_failure()['state']['mapping_complete'] is False
    changed = producer.anchor.observed_fact(); changed['producer']['actual_exit'] = 0
    with monkeypatch.context() as patch:
        patch.setattr(producer.anchor, 'observed_fact', lambda: changed)
        with pytest.raises(producer.Refused) as caught:
            producer.source_binding()
        assert producer.finite(caught.value) == 'source_binding'
    changed_failure = producer.anchor.expected_failure()
    changed_failure['state']['mapping_complete'] = True
    with monkeypatch.context() as patch:
        patch.setattr(producer.anchor, 'expected_failure', lambda: changed_failure)
        with pytest.raises(producer.Refused) as caught:
            producer.source_binding()
        assert producer.finite(caught.value) == 'source_binding'


def test_all_public_accessors_return_independent_nested_copies():
    baseline = (m.observed_fact(), m.expected_specification(), m.expected_selection_evidence(), m.profile_record())
    fact, spec, evidence, profile = (m.observed_fact(), m.expected_specification(),
        m.expected_selection_evidence(), m.profile_record())
    fact['producer']['actual_exit'] = 2
    fact['specification_file']['relative_path'] = 'synthetic/other-file'
    spec['selected_whole_binding_sha256s'][-1] = 'f' * 64
    spec['own_universe_tickers'].clear()
    evidence['selected_whole_binding_sha256s'].clear()
    evidence['vendor_source_blockers_remaining'] = 0
    profile['new_QC_source_project_rights_and_run_freeze_required'] = False
    assert (m.observed_fact(), m.expected_specification(), m.expected_selection_evidence(), m.profile_record()) == baseline
    assert m.observed_fact()['producer'] is not m.observed_fact()['producer']
    assert m.expected_specification()['selected_whole_binding_sha256s'] is not m.expected_selection_evidence()['selected_whole_binding_sha256s']


def test_anchor_is_literal_metadata_only_and_accessors_cannot_read_files_or_operate(monkeypatch):
    tree = ast.parse(inspect.getsource(m))
    assert {node.names[0].name for node in tree.body if isinstance(node, ast.Import)} == {'hashlib', 'json'}
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        'observed_fact', 'expected_specification', 'expected_selection_evidence', 'profile_record'}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assert isinstance(node.value, ast.Constant) and type(node.value.value) in (str, bytes)
        assert not isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
    forbidden = {'open', 'print', 'exec', 'eval', '__import__', 'read_bytes', 'read_text',
        'observe', 'run', 'prepare', 'load_key', 'request', 'get', 'post', 'connect'}
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls & forbidden
    def deny(*args, **kwargs):
        raise AssertionError('public metadata accessor attempted file access')
    with monkeypatch.context() as patch:
        for module, name in ((builtins, 'open'), (os, 'open'), (os, 'read'),
                (Path, 'read_bytes'), (Path, 'read_text')):
            patch.setattr(module, name, deny)
        assert m.observed_fact()['specification_file']['byte_count'] == 1791
        assert len(m.expected_specification()['selected_whole_binding_sha256s']) == 5
        assert m.expected_selection_evidence()['vendor_source_blockers_remaining'] == 5
        assert m.profile_record()['paid_rights_granted'] is False
