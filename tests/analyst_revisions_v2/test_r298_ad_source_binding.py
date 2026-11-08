"""Public AD failure joins only; no spent control or operational reads."""
import ast
import builtins
import copy
import inspect
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_ad_source_binding as m
from scripts import inspect_arv2_r298_public_figi_lineage as producer


def test_closed_failure_is_validated_as_consumed_failure_and_never_accepted_success(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('public metadata validation reached an operational function')
    for module, name in ((producer, 'run'), (producer, 'observe'), (producer, 'Store'),
            (producer, '_session'), (producer, 'capture'),
            (producer.data_guard, 'FixedDataGuard')):
        monkeypatch.setattr(module, name, deny)
    fact, failed = m.observed_fact(), m.expected_failure()
    args = SimpleNamespace(expected_head=fact['expected_head'], caller_sha256=fact['caller_sha256'])
    producer._state(failed['state'])
    value = {'binding': producer.binding(args), 'outcome': {'failure': failed}}
    raw = producer.canonical(value)
    assert producer.validate_output(raw, fact['producer']['actual_exit'], args) == value
    assert failed['failure_code'] == failed['state']['terminal_failure_code'] == 'transport_unknown'
    assert failed['claim_consumed'] is True and failed['provider_request_count'] is None
    assert failed['state']['mapping_complete'] is False
    assert all(failed[key] is False for key in producer.FALSE_FLAGS)
    # Authentication of this failure cannot be relabelled as a successful exit.
    with pytest.raises(producer.Refused):
        producer.validate_output(raw, 0, args)
    changed = copy.deepcopy(value)
    changed['outcome']['failure']['claim_consumed'] = False
    with pytest.raises(producer.Refused):
        producer.validate_output(producer.canonical(changed), 2, args)
    changed = copy.deepcopy(failed['state'])
    changed['unrecognized_authority'] = True
    with pytest.raises(producer.Refused):
        producer._state(changed)


def test_actual_failed_exit_private_pin_selection_and_source_receipt_join_without_contact_claims():
    fact, failed = m.observed_fact(), m.expected_failure()
    state = failed['state']
    assert set(fact) == {'schema', 'expected_head', 'caller_sha256', 'profile_sha256',
        'failure_code', 'producer', 'validator', 'private_file', 'source_guard_returned'}
    assert fact['schema'] == producer.SCHEMA
    assert fact['expected_head'] == '874b349d8b681b1fbca908502c40994869229b92'
    assert fact['caller_sha256'] == '0e1328c07fa82690625a49dbc043cc9facdf125516bfff8a411dd0eb5bfa2ab4'
    assert fact['producer']['actual_exit'] == 2 and type(fact['producer']['actual_exit']) is int
    assert fact['validator']['actual_exit'] == 0 and type(fact['validator']['actual_exit']) is int
    for role in ('producer', 'validator'):
        actual = fact[role]
        assert actual['bound'] is None and actual['spawn_observed'] is True
        assert actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == producer.sha(b'')
        assert actual['dispatched_at'] < actual['completion_observed_at']
    assert fact['producer']['completion_observed_at'] <= fact['validator']['dispatched_at']
    assert fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes'] == 4232
    assert fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256']
    assert fact['source_guard_returned'] is state['source_guard_returned'] is True
    assert fact['private_file'] == {'relative_path':
        'artifacts/analyst_revisions_v2/newrule_public_figi_lineage/R326-20261027-AD/public-figi-private.json',
        **state['private_pin']}
    assert state['private_pin'] == state['package_pin'] == {'byte_count': 26503,
        'sha256': 'babb09c92ccf109bede02e0e9d125dc650ad3d64fee99b64b08770f19a62961c'}
    producer.data_guard.validate_receipt(state['source_receipt'], producer.FILE_PLAN)
    assert {role: {key: row[key] for key in ('relative_path', 'byte_count', 'sha256')}
        for role, row in state['source_receipt']['files'].items()} == producer.FILE_PLAN
    selection = state['selection_summary']
    producer._selection_summary(selection)
    assert selection['case_count'] == 5 and selection['source_stock_count'] == 6151
    assert selection['source_fund_count'] == 8
    assert selection['source_refusal_counts'] == {'identity_missing': 4, 'global_collision': 1}
    assert [row['retained_candidate_row_count'] for row in selection['case_counts']] == [2, 1, 1, 1, 1]
    assert selection['unique_valid_figi_count'] == selection['planned_job_count'] == 9
    assert selection['planned_batch_count'] == len(state['dispatch_intents']) == 1
    assert state['dispatch_intents'][0]['dispatch_intent_count'] == 1
    assert state['dispatch_intents'][0]['job_count'] == 9
    assert state['http_statuses'] == state['batch_summaries'] == []
    assert state['response_pins'] == state['corroboration_counts'] == {} and state['response_bytes'] == 0
    # Empty retained status/body evidence does not measure zero provider contact.
    assert failed['provider_request_count'] is None
    changed = copy.deepcopy(state)
    changed['private_pin']['sha256'] = 'f' * 64
    with pytest.raises(producer.Refused):
        producer._state(changed)
    profile = m.profile_record()
    assert profile['actual_prior_producer_exit'] == 2 and profile['new_consumer_freeze_required'] is True
    assert all(profile[key] is False for key in ('mapping_accepted', 'source_admission_granted',
        'operational_authority_granted', 'old_control_or_operation_read', 'strategy_price_admitted',
        'strategy_nav_admitted', 'point_in_time_proven', 'formal_forward_ready', 'paper_or_live_ready'))


def test_metadata_accessors_return_independent_copies_of_deep_failure_state():
    baseline = (m.observed_fact(), m.expected_failure(), m.profile_record())
    fact, failed, profile = m.observed_fact(), m.expected_failure(), m.profile_record()
    fact['producer']['actual_exit'] = 0
    fact['private_file']['relative_path'] = 'synthetic/other-leaf'
    failed['state']['dispatch_intents'][0]['job_count'] = 1
    failed['state']['selection_summary']['case_counts'][-1]['retained_candidate_row_count'] = 0
    failed['state']['source_receipt']['files']['aa_frame']['sha256'] = 'f' * 64
    failed['state']['private_pin']['sha256'] = 'f' * 64
    failed['claim_consumed'] = False
    profile['actual_prior_producer_exit'] = 0
    profile['new_consumer_freeze_required'] = False
    assert (m.observed_fact(), m.expected_failure(), m.profile_record()) == baseline
    assert m.observed_fact()['producer'] is not m.observed_fact()['producer']
    assert m.expected_failure()['state']['dispatch_intents'] is not m.expected_failure()['state']['dispatch_intents']


def test_anchor_contains_literal_metadata_only_and_accessors_have_no_io_capability(monkeypatch):
    tree = ast.parse(inspect.getsource(m))
    assert {node.names[0].name for node in tree.body if isinstance(node, ast.Import)} == {'hashlib', 'json'}
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        'observed_fact', 'expected_failure', 'profile_record'}
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
        raise AssertionError('public metadata accessor attempted filesystem access')
    with monkeypatch.context() as patch:
        for module, name in ((builtins, 'open'), (os, 'open'), (os, 'read'),
                (Path, 'read_bytes'), (Path, 'read_text')):
            patch.setattr(module, name, deny)
        assert m.observed_fact()['private_file']['byte_count'] == 26503
        assert m.expected_failure()['state']['selection_summary']['case_count'] == 5
        assert m.profile_record()['operational_authority_granted'] is False
