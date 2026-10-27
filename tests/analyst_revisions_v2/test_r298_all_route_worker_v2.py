"""New supplied-data worker integration; never reads old or private controls."""
import ast
import copy
import inspect
import time

import pytest

from scripts import arv2_r298_all_route_worker_v2 as m
from tests.analyst_revisions_v2 import test_r298_all_route_worker as previous_fixture
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes as supplied


def refused(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


@pytest.fixture
def environment(monkeypatch):
    # Explicit synthetic substitution of the internal integration seam. There
    # is no production authority bool, alternate package or alternate decoder.
    e = previous_fixture.environment.__wrapped__(monkeypatch)
    for name in ('_load_plain', '_catalog', '_catalog_unchanged', '_guard_fingerprint'):
        monkeypatch.setattr(m, name, getattr(m.previous, name))
    join = m.routes.join
    def route(bindings, originals, stocks, funds, *, binding_contract):
        assert stocks == e.stocks_raw and funds == e.funds_raw
        e.events.append('v2_join')
        return join(bindings, originals, e.data[2], e.data[3], binding_contract=binding_contract)
    monkeypatch.setattr(m.routes, 'join', route)
    def deny(*args, **kwargs):
        raise AssertionError('old worker preparation or guessed original-name gate invoked')
    monkeypatch.setattr(m.previous, 'prepare', deny)
    monkeypatch.setattr(m.previous, '_prepare_bound', deny)
    monkeypatch.setattr(m.previous.routes, 'join', deny)
    monkeypatch.setattr(m.previous.routes, '_originals', deny)
    e.run = lambda: m.prepare(e.stocks_raw, e.funds_raw, deadline=time.monotonic() + 60)
    return e


def alternate_unused_column(e):
    old, new = 'companysite', 'unused_authentic_column'
    assert old not in m.routes.REQUIRED_ORIGINAL_FIELDS
    e.catalog.columns = tuple(new if name == old else name for name in e.catalog.columns)
    for row in e.data[1]:
        row[new] = row.pop(old)
    e.data[0][:] = sorted([supplied.binding(row, 2) for row in e.data[1]], key=lambda row: row['security_id'])
    e.selected['runtime_symbol_bindings'] = e.data[0]
    e.record['runtime_symbol_bindings_sha256'] = supplied.contract(e.data[0])['binding_stream_sha256']
    e.receipts['ordered_source_row_digests_sha256'] = m.sha(e.decoder.canonical([
        m.routes.original.source_row_digest(row) for row in e.data[1]]))


@pytest.mark.parametrize('changed', [False, True])
def test_exact_decoder_output_all_28_names_and_values_are_preserved(environment, changed):
    e = environment
    if changed:
        alternate_unused_column(e)
    original_rows = copy.deepcopy(e.data[1])
    source_pins = [m.routes.original.source_row_digest(row) for row in original_rows]
    summary, private = e.run()
    assert summary == m.validate_summary(summary)
    assert [row['original_row'] for row in private['stocks']] == original_rows
    assert [row['binding']['source_row_sha256'] for row in private['stocks']] == source_pins
    observed = summary['original_schema']
    assert observed == {'schema': m.ORIGINAL_SCHEMA, 'column_count': 28,
        'ordered_column_names_sha256': m.sha(m.canonical(list(e.catalog.columns))),
        'legacy_known_name_set_equal': not changed, 'required_identity_fields_present': True}
    assert summary['original_shape_policy_sha256'] == m.sha(m.canonical(m.original_shape_policy()))
    assert summary['routing_summary']['schema'] == m.routes.SCHEMA
    assert private['schema'] == m.routes.PRIVATE_SCHEMA
    assert m.sha(m.canonical(private)) == summary['private_frame_sha256']
    assert e.events.index('decode_original') < e.events.index('v2_join') < e.events.index('guard_exit')
    assert e.guard.last.reads == list(m.source_guard.LEAVES)
    assert all(summary[field] is False for field in m.FALSE_FLAGS)
    assert b'unused_authentic_column' not in m.canonical(summary)


def test_normal_guard_close_failure_remains_spent_refusal(environment):
    environment.guard.fail_exit = True
    refused('source_guard_close', environment.run)


def test_unknown_name_observation_does_not_skip_exact_original_decoder(environment):
    def fail(*args, **kwargs):
        raise m.original_decoder.Refused('header_binding')
    environment.decoder.decode_original_catalog = fail
    refused('original_decoder_header_binding', environment.run)
    assert 'v2_join' not in environment.events


@pytest.mark.parametrize('mode,code', [
    ('type', 'original_catalog_type'), ('count', 'original_catalog_count'),
    ('columns', 'original_columns'), ('digest', 'original_catalog_digest')])
def test_original_catalog_failure_subpredicates_are_decisive(environment, mode, code):
    e = environment
    if mode == 'type':
        old = e.decoder.decode_original_catalog
        def decode(*args, **kwargs):
            receipt, catalog = old(*args, **kwargs)
            return receipt, object()
        e.decoder.decode_original_catalog = decode
    elif mode == 'count':
        e.catalog.mapping_rows = lambda self: ()
    elif mode == 'columns':
        e.catalog.columns = tuple('missing_identity' if value == 'figi' else value for value in e.catalog.columns)
    else:
        e.data[1][-1]['name'] = 'altered only after original receipt was bound'
    refused(code, e.run)
    assert 'v2_join' not in e.events


@pytest.mark.parametrize('field', sorted(m.routes.REQUIRED_ORIGINAL_FIELDS))
def test_missing_required_identity_column_is_never_an_unused_schema_variation(environment, field):
    e = environment
    e.catalog.columns = tuple('synthetic_replacement' if name == field else name for name in e.catalog.columns)
    refused('original_columns', e.run)


def test_original_identity_evidence_and_currency_remain_strict(environment):
    e = environment
    alternate_unused_column(e)
    e.data[1][0]['currency'] = 'EUR'
    # The changed row is authenticated supplied data for this synthetic test;
    # preserving its prior binding proves identity/source mismatch is refused.
    e.receipts['ordered_source_row_digests_sha256'] = m.sha(e.decoder.canonical([
        m.routes.original.source_row_digest(row) for row in e.data[1]]))
    summary, private = e.run()
    assert private['stocks'][0]['disposition'] == 'refused'
    assert summary['routing_summary']['refusal_counts']['stocks'] == {'original_row_missing': 1}
    assert summary['price_coverage_proven'] is False


def test_final_plain_and_original_guard_fingerprints_remain_required(environment):
    e = environment
    old = e.decoder.decode_original_catalog
    def decode(*args, **kwargs):
        e.plain.changed = True
        return old(*args, **kwargs)
    e.decoder.decode_original_catalog = decode
    refused('plain_changed', e.run)


@pytest.mark.parametrize('path,value', [
    (('schema',), m.previous.SCHEMA),
    (('original_shape_policy_sha256',), '0' * 64),
    (('original_schema', 'schema'), 'other'),
    (('original_schema', 'column_count'), True),
    (('original_schema', 'column_count'), 27),
    (('original_schema', 'ordered_column_names_sha256'), 'unbound-columns'),
    (('original_schema', 'legacy_known_name_set_equal'), 'true'),
    (('original_schema', 'required_identity_fields_present'), False),
    (('routing_summary', 'schema'), m.previous.routes.SCHEMA),
    (('routing_summary', 'private_payload_sha256'), '0' * 64),
    (('input_binding', 'source_package_sha256'), '0' * 64),
    (('source_guard_receipt', 'guard_normal_return'), False),
    (('provider_contact',), True),
])
def test_closed_summary_new_policy_and_old_metadata_checks_both_apply(environment, path, value):
    summary, _ = environment.run()
    target = summary
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(m.Refused): m.validate_summary(summary)


@pytest.mark.parametrize('path', [(), ('original_schema',), ('routing_summary',),
    ('input_binding',), ('current_metadata', 'stocks')])
def test_unknown_extra_fields_cannot_be_dropped_by_schema_projection(environment, path):
    summary, _ = environment.run()
    target = summary
    for key in path: target = target[key]
    target['arbitrary_column_or_secret'] = 'must not be projected away'
    with pytest.raises(m.Refused): m.validate_summary(summary)


def test_metadata_projection_never_mutates_supplied_summary_or_old_module_globals(environment):
    summary, _ = environment.run()
    before = copy.deepcopy(summary)
    old_schema, old_route_schema = m.previous.SCHEMA, m.previous.routes.SCHEMA
    assert m.validate_summary(summary) == before and summary == before
    assert m.previous.SCHEMA == old_schema and m.previous.routes.SCHEMA == old_route_schema
    assert m.previous.routes.ORIGINAL_FIELDS != set(m.routes.REQUIRED_ORIGINAL_FIELDS)


def test_no_old_operational_entry_or_global_rebinding_exists():
    source = inspect.getsource(m)
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'previous'
        and node.func.attr in ('prepare', '_prepare_bound') for node in ast.walk(tree))
    assert not any(isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and any(isinstance(target, ast.Attribute) for target in
            (node.targets if isinstance(node, ast.Assign) else [node.target])) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in ('open', 'print', 'eval', 'exec', '__import__') for node in ast.walk(tree))
    assert 'if __name__' not in source


def test_new_route_failure_code_is_finite_and_never_formats_arbitrary_values(environment, monkeypatch):
    def fail(*args, **kwargs):
        raise m.routes.Refused('original_rows')
    monkeypatch.setattr(m.routes, 'join', fail)
    refused('routes_v2_original_rows', environment.run)
    assert m._failure_code(m.routes.Refused('private-data')) == 'routes_v2_refused'
    assert m.finite(m.Refused('private-data')) == 'unknown'
