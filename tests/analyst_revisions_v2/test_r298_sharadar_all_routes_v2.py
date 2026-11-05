"""Prospective supplied-column shape, full evidence and bounded route tests."""
import ast
import copy
import inspect
from pathlib import Path

import pytest

from scripts import arv2_r298_sharadar_all_routes_v2 as m
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes as supplied
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as metadata


@pytest.fixture(autouse=True)
def no_old_entrypoint_or_operation(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('frozen entrypoint or operation used')
    monkeypatch.setattr(supplied.m, 'join', deny)
    for module in (m.current.previous, m.current.previous.previous):
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, '_fetch', deny)
    monkeypatch.setattr(m.original, 'verify', deny)
    monkeypatch.setattr(m.original.identity_join, 'join', deny)


def case(count=2, *, rename=True):
    data = supplied.case(count)
    if rename:
        for row in data[1]:
            row['unused_fixture_column'] = row.pop('famaindustry')
        data[0][:] = [supplied.binding(row, count) for row in data[1]]
    return data


def join(data):
    return m.join(*data, binding_contract=supplied.contract(data[0]))


def refused(code, callback):
    with pytest.raises(m.Refused) as error:
        callback()
    assert m.finite(error.value) == code


def test_required_fields_are_derived_from_frozen_reconstruction_plus_existing_currency_guard():
    tree = ast.parse(inspect.getsource(m.original._metadata))
    names = {node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == 'get'
        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'row'
        and node.args and isinstance(node.args[0], ast.Constant) and type(node.args[0].value) is str}
    assert names | {'currency'} == m.REQUIRED_ORIGINAL_FIELDS
    assert len(names) == 11 and len(m.REQUIRED_ORIGINAL_FIELDS) == 12
    assert not hasattr(m, 'ORIGINAL_FIELDS')


def test_nominal_old_header_size_differs_from_pin_without_claiming_unknown_column_names():
    # This arithmetic concerns an UNQUOTED LF serialization only. It neither
    # reads the real header nor rules out quoting/CRLF from length alone.
    nominal = ','.join(sorted(supplied.m.ORIGINAL_FIELDS)).encode('ascii') + b'\n'
    assert len(nominal) == 289 != m.ORIGINAL_HEADER_BYTES == 291
    assert m.ORIGINAL_HEADER_SHA256 == 'c9186ed191f4e51d5142287016dc99e3f80ecebed49aa63c3fa1ecf09e5d26f7'
    assert m.sha(nominal) != m.ORIGINAL_HEADER_SHA256
    assert m.valid_original_columns(list(supplied.m.ORIGINAL_FIELDS)) is True
    assert m.valid_original_columns(list(case()[1][0])) is True


def test_different_unused_names_and_values_are_preserved_in_every_source_and_evidence_hash():
    old = case(rename=False)
    changed = case()
    for row in changed[1]: row['unused_fixture_column'] = 'synthetic-unused-\u00e9'
    changed[0][:] = [supplied.binding(row, 2) for row in changed[1]]
    summary, private = join(changed)
    payload = private.private_record()
    assert summary['schema'] == m.SCHEMA and payload['schema'] == m.PRIVATE_SCHEMA
    assert summary['disposition_counts'] == {'stocks': {'routed': 2}, 'funds': {'routed': 8}}
    assert len(private.price_routes()) == 10
    assert [item['original_row'] for item in payload['stocks']] == changed[1]
    for index, item in enumerate(payload['stocks']):
        assert len(item['original_row']) == 28 and 'famaindustry' not in item['original_row']
        assert item['original_row']['unused_fixture_column'] == 'synthetic-unused-\u00e9'
        assert item['binding']['source_row_sha256'] == m.original.source_row_digest(changed[1][index])
        assert item['binding']['source_row_sha256'] != old[0][index]['source_row_sha256']
        assert item['binding']['identity_evidence_sha256'] != old[0][index]['identity_evidence_sha256']
    assert b'synthetic-unused' not in m.canonical(summary)


def test_renamed_unused_column_with_stale_original_hash_cannot_be_normalized_back_or_discarded():
    data = case(rename=False)
    for row in data[1]: row['unused_fixture_column'] = row.pop('famaindustry')
    summary, private = join(data)
    assert summary['refusal_counts']['stocks'] == {'original_row_missing': 2}
    assert len(private.private_record()['stocks']) == 2
    refused('routes_incomplete', private.price_routes)


@pytest.mark.parametrize('field', sorted(m.REQUIRED_ORIGINAL_FIELDS))
def test_replacing_any_actual_identity_field_with_an_unused_name_refuses_shape(field):
    data = case()
    data[1][0]['another_unused_fixture_column'] = data[1][0].pop(field)
    assert len(data[1][0]) == 28
    assert m.valid_original_columns(tuple(data[1][0])) is False
    refused('original_rows', lambda: join(data))


@pytest.mark.parametrize('change', ['short', 'long', 'duplicate', 'non_ascii', 'control',
    'empty', 'oversize', 'subclass', 'generator', 'set'])
def test_column_predicate_is_bounded_primitive_and_preserves_exact_names(change):
    class Text(str): pass
    columns = list(case()[1][0])
    position = columns.index('unused_fixture_column')
    if change == 'short': columns.pop(position)
    elif change == 'long': columns.append('one_more_unused')
    elif change == 'duplicate': columns[position] = 'table'
    elif change == 'non_ascii': columns[position] = 'unused_\u00e9'
    elif change == 'control': columns[position] = 'unused\tcolumn'
    elif change == 'empty': columns[position] = ''
    elif change == 'oversize': columns[position] = 'A' * 129
    elif change == 'subclass': columns[position] = Text('unused_fixture_column')
    elif change == 'generator': columns = iter(columns)
    else: columns = set(columns)
    assert m.valid_original_columns(columns) is False


def test_same_original_header_shape_must_apply_to_every_supplied_row():
    data = case()
    data[1][1]['different_unused_fixture_column'] = data[1][1].pop('unused_fixture_column')
    assert all(m.valid_original_columns(tuple(row)) for row in data[1])
    refused('original_rows', lambda: join(data))


def test_shape_is_explicitly_not_the_caller_exact_header_manifest_or_source_authentication():
    columns = tuple(case()[1][0])
    arbitrary = ','.join(columns).encode('ascii') + b'\n'
    assert m.valid_original_columns(columns) is True
    assert m.sha(arbitrary) != m.ORIGINAL_HEADER_SHA256
    profile = m.profile_record()
    assert profile['caller_original_header_byte_count'] == 291
    assert profile['caller_original_header_sha256'] == m.ORIGINAL_HEADER_SHA256
    assert 'before_helper' in profile['caller_header_manifest_gate']
    assert profile['frozen_v1_source_sha256'] == m.FROZEN_V1_SHA256


@pytest.mark.parametrize('kind', ['original_evidence', 'current_interval', 'later_token', 'cross_table', 'missing_route'])
def test_original_evidence_interval_and_all_token_collision_refusals_are_preserved(kind):
    data = case()
    if kind == 'original_evidence':
        data[0][0]['identity_evidence_sha256'] = 'c' * 64
        seed = dict(data[0][0]); seed.pop('row_sha256')
        data[0][0]['row_sha256'] = m.sha(m.original.identity_join.figi._canonical(seed))
    elif kind == 'current_interval': data[2][0]['firstpricedate'] = '2021-01-04'
    elif kind == 'missing_route': data[2].pop(0)
    else:
        data[2][0]['cusips'] += ' ABCDEF123'
        extra = metadata.metadata('OTHER', 99, fund=kind == 'cross_table')
        extra['cusips'] += ' ABCDEF123'
        (data[3] if kind == 'cross_table' else data[2]).append(extra)
    summary, private = join(data)
    expected = {'original_evidence': 'original_identity', 'current_interval': 'current_interval',
        'later_token': 'current_collision', 'cross_table': 'current_collision',
        'missing_route': 'current_identity_missing'}[kind]
    assert summary['refusal_counts']['stocks'] == {expected: 1}
    assert len(private.private_record()['stocks']) == 2
    refused('routes_incomplete', private.price_routes)


@pytest.mark.parametrize('field,limit,code', [('MAX_CANDIDATE_ROWS_PER_ITEM', 1, 'candidate_bound'),
    ('MAX_CANDIDATE_ROWS', 5, 'candidate_bound'), ('MAX_CANDIDATE_BYTES', 64, 'candidate_bound'),
    ('MAX_PRIVATE_BYTES', 5000, 'private_payload')])
def test_existing_candidate_and_full_private_graph_budgets_are_unchanged(monkeypatch, field, limit, code):
    data = case()
    if field == 'MAX_CANDIDATE_ROWS_PER_ITEM': data[2].append(metadata.metadata(data[2][0]['ticker'], 99))
    monkeypatch.setattr(m, field, limit)
    refused(code, lambda: join(data))


def test_frozen_v1_is_unchanged_and_new_helper_never_invokes_a_reader_or_original_entrypoint():
    frozen = Path(m.__file__).with_name('arv2_r298_sharadar_all_routes.py').read_bytes()
    assert m.sha(frozen) == m.FROZEN_V1_SHA256
    assert m.SCHEMA != supplied.m.SCHEMA and m.PRIVATE_SCHEMA != supplied.m.PRIVATE_SCHEMA
    source = inspect.getsource(m)
    for forbidden in ('.read_bytes(', 'open(', '.observe(', '._fetch(', 'identity_join.join(', 'require_probe_routes('):
        assert forbidden not in source
    assert 'ORIGINAL_FIELDS =' not in source.replace('REQUIRED_ORIGINAL_FIELDS =', '')
