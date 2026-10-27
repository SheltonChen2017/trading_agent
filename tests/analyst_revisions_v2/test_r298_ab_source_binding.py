"""Public observed metadata joins; no private artifact or operational calls."""
import ast
import inspect

from scripts import arv2_r298_ab_source_binding as m
from scripts import inspect_arv2_r298_route_dispositions as producer


def test_closed_summaries_join_the_exact_observed_private_products():
    fact = m.observed_fact()
    evidence = m.expected_evidence_summary()
    demand = m.expected_demand_summary()
    producer._summaries(evidence, demand)
    for name, summary, prefix in (
        ('evidence-private.json', evidence, 'private_evidence'),
        ('membership-demand-private.json', demand, 'private_frame'),
    ):
        pin = fact['private_files'][name]
        assert pin['byte_count'] == summary[prefix + '_byte_count']
        assert pin['sha256'] == summary[prefix + '_sha256']
    assert demand['cohorts']['6']['potential_stock_count'] == 5641
    assert demand['cohorts']['8']['potential_stock_count'] == 5641
    assert demand['cohorts']['6']['disposition_relevance']['refused']['potential'] == 79


def test_actual_process_records_are_facts_and_never_new_readiness_authority():
    fact = m.observed_fact()
    for name in ('producer', 'validator'):
        actual = fact[name]
        assert type(actual['actual_exit']) is int and actual['actual_exit'] == 0
        assert actual['bound'] is None and actual['spawn_observed'] is True
        assert actual['stderr_bytes'] == 0
    assert fact['producer']['stdout_bytes'] == fact['validator']['stdout_bytes']
    assert fact['producer']['stdout_sha256'] == fact['validator']['stdout_sha256']
    profile = m.profile_record()
    assert profile['new_consumer_freeze_required'] is True
    assert all(profile[key] is False for key in (
        'old_control_or_operation_read', 'source_admission_granted', 'operational_authority_granted',
        'point_in_time_proven', 'strategy_price_admitted', 'strategy_nav_admitted',
        'formal_forward_ready', 'paper_or_live_ready'))


def test_all_accessors_return_independent_mutable_copies():
    originals = [m.observed_fact(), m.expected_evidence_summary(), m.expected_demand_summary()]
    m.observed_fact()['private_files']['evidence-private.json']['sha256'] = 'f' * 64
    m.expected_evidence_summary()['disposition_counts']['stocks'].clear()
    m.expected_demand_summary()['cohorts']['6']['potential_stock_count'] = 0
    assert [m.observed_fact(), m.expected_evidence_summary(), m.expected_demand_summary()] == originals


def test_public_binding_module_has_no_reader_provider_or_credential_capability():
    source = inspect.getsource(m)
    tree = ast.parse(source)
    assert {node.names[0].name for node in tree.body if isinstance(node, ast.Import)} == {'hashlib', 'json'}
    forbidden = {'open', 'print', 'exec', 'eval', '__import__', 'read_bytes', 'read_text', 'observe', 'run', 'load_key'}
    calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))}
    assert not calls & forbidden
