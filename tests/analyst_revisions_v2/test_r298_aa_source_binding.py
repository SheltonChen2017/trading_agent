"""Public externally observed metadata only; no retained artifact reads."""
import ast
import inspect

from scripts import arv2_r298_aa_source_binding as m
from scripts import arv2_r298_all_route_worker_v2 as worker


def test_closed_summary_matches_recorded_data_pin_and_frozen_worker_contract():
    summary = worker.validate_summary(m.expected_summary())
    fact = m.observed_fact()
    assert fact['private_file']['byte_count'] == summary['private_frame_byte_count']
    assert fact['private_file']['sha256'] == summary['private_frame_sha256']
    assert summary['routing_summary']['binding_contract']['binding_count'] == 6151
    assert sum(summary['routing_summary']['disposition_counts']['stocks'].values()) == 6151
    assert summary['routing_summary']['disposition_counts']['funds'] == {'routed': 8}
    assert all(summary[key] is False for key in worker.FALSE_FLAGS)


def test_recorded_process_success_is_exact_external_fact_not_a_readiness_permit():
    fact = m.observed_fact()
    for role in ('producer', 'validator'):
        actual = fact[role]
        assert type(actual['actual_exit']) is int and actual['actual_exit'] == 0
        assert actual['bound'] is None and actual['spawn_observed'] is True
        assert actual['stderr_bytes'] == 0 and actual['stderr_sha256'] == worker.sha(b'')
    assert fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes']
    assert fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256']
    profile = m.profile_record()
    assert profile['new_consumer_freeze_required'] is True
    assert profile['operational_authority_granted'] is False
    assert profile['source_admission_granted'] is False
    assert profile['strategy_price_admitted'] is False
    assert profile['strategy_nav_admitted'] is False


def test_observed_and_summary_accessors_return_independent_private_mutable_copies():
    before, original = m.expected_summary(), m.observed_fact()
    changed = m.expected_summary()
    changed['routing_summary']['disposition_counts']['stocks'].clear()
    changed['input_binding']['binding_contract']['binding_count'] = 1
    facts = m.observed_fact()
    facts['producer']['actual_exit'] = 2
    facts['private_file']['sha256'] = 'f' * 64
    assert m.expected_summary() == before and m.observed_fact() == original


def test_module_has_no_source_control_reader_or_provider_credential_capability():
    tree = ast.parse(inspect.getsource(m))
    imports = {node.names[0].name for node in tree.body if isinstance(node, ast.Import)}
    assert imports == {'hashlib', 'json'}
    forbidden = {'open', 'print', 'eval', 'exec', '__import__', 'load_key', 'read_bytes', 'read_text', 'observe', 'run'}
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls & forbidden
    assert all(name not in inspect.getsource(m) for name in ('api_key', 'QC_API_TOKEN', 'raw_route', 'raw_price'))
