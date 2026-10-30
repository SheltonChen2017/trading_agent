"""Synthetic clipped interval facts, with no private reads or operations."""
import builtins
import copy
from pathlib import Path

import pytest

from scripts import arv2_r298_reference_catalog_facts as m
from tests.analyst_revisions_v2 import test_r298_reference_identity_join as fixtures


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    fixtures.no_operations.__wrapped__(monkeypatch)


@pytest.fixture(scope='module')
def axis(): return fixtures.axis.__wrapped__()


@pytest.fixture
def case(monkeypatch, axis):
    return fixtures.make_case(monkeypatch, axis)


def expected(case): return m.identity_join.join(case.plain, case.context, case.packet)


def facts(case, receipt=None):
    return m.facts(case.plain, case.context, case.packet, receipt if receipt is not None else expected(case))


def repin(row):
    seed = dict(row); seed.pop('row_sha256')
    # Binding rows use their FIGI contract's canonical JSON WITH LF; the dated
    # witness and outer join-receipt domains deliberately do not use an LF.
    row['row_sha256'] = m.identity_join.sha(m.identity_join.figi._canonical(seed))


def test_facts_bind_fresh_join_and_never_disclose_dates_or_routes(case):
    receipt = expected(case)
    value = facts(case, receipt)
    assert value['context_sha256'] == m.identity_join.context_digest(case.context)
    assert value['join_receipt_sha256'] == m.join_receipt_digest(receipt)
    assert value['facts'][0]['reference_candidate_interval_relation'] == 'inside'
    assert value['facts'][0]['decision_candidate_interval_relation'] == 'inside'
    assert value['facts'][0]['source_snapshot_vs_decision'] == 'after'
    assert value['witness_count'] == 1
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    raw = m.canonical(value)
    for private in ('2022-10-21', '2022-10-24', '2026-10-13', 'SYNTH0',
            'BBG000000001', 'sharadar-composite-figi-', 'synthetic-listing-'):
        assert private.encode('ascii') not in raw


@pytest.mark.parametrize('first,last,reference,decision', [
    ('2023-01-03', '2026-10-13', 'before', 'before'),
    ('2021-01-04', '2022-10-20', 'after', 'after'),
    ('2022-10-21', '2022-10-21', 'inside', 'after'),
    ('2022-10-24', '2026-10-13', 'before', 'inside'),
    ('2022-10-21', '2022-10-24', 'inside', 'inside')])
def test_closed_interval_boundary_relations(monkeypatch, axis, first, last, reference, decision):
    bindings = fixtures.rows(3)
    bindings[0].update(candidate_first_session=first, candidate_last_session=last)
    repin(bindings[0])
    case = fixtures.make_case(monkeypatch, axis, binding_rows=bindings)
    row = facts(case)['facts'][0]
    assert row['reference_candidate_interval_relation'] == reference
    assert row['decision_candidate_interval_relation'] == decision


@pytest.mark.parametrize('timestamp,relation', [
    ('2022-10-24T13:19:59.000000Z', 'before'),
    ('2022-10-24T13:20:00.000000Z', 'at'),
    ('2022-10-24T13:20:00.000001Z', 'after'),
    ('2026-10-13T00:00:00.000000Z', 'after')])
def test_snapshot_compares_actual_ny0920_not_naive_utc(monkeypatch, axis, timestamp, relation):
    bindings = fixtures.rows(3)
    bindings[0]['source_snapshot_available_at'] = timestamp
    repin(bindings[0])
    case = fixtures.make_case(monkeypatch, axis, binding_rows=bindings)
    assert facts(case)['facts'][0]['source_snapshot_vs_decision'] == relation


def test_complete_multiple_witness_facts_sorted_and_counted(monkeypatch, axis):
    case = fixtures.make_case(monkeypatch, axis, context_count=3)
    value = facts(case)
    assert value['witness_count'] == 3
    assert value['reference_relations'] == {'before': 0, 'inside': 3, 'after': 0}
    assert value['snapshot_relations'] == {'before': 0, 'at': 0, 'after': 3}
    assert [row['identity_sha256'] for row in value['facts']] == sorted(
        row['identity_sha256'] for row in value['facts'])


@pytest.mark.parametrize('change', ['join_hash', 'binding_hash', 'count', 'formal_flag'])
def test_expected_join_receipt_cannot_be_asserted_or_changed(case, change):
    receipt = expected(case)
    if change == 'join_hash': receipt['context_sha256'] = '0' * 64
    elif change == 'binding_hash': receipt['matches'][0]['whole_binding_row_sha256'] = '0' * 64
    elif change == 'count': receipt['matched_count'] = False
    else: receipt['formal_identity_admitted'] = True
    with pytest.raises(m.Refused): facts(case, receipt)


def test_actual_genuine_join_is_mandatory_before_selection(case, monkeypatch):
    receipt = expected(case)
    monkeypatch.setattr(m.identity_join, '_streams', lambda *_: pytest.fail('selected before genuine join'))
    monkeypatch.setattr(m.identity_join, 'join', lambda *_: (_ for _ in ()).throw(
        m.identity_join.Refused('plain_authority')))
    with pytest.raises(m.Refused, match='^join_refused$'): facts(case, receipt)


@pytest.mark.parametrize('change', ['copy', 'capability', 'packet', 'context', 'expected'])
def test_late_change_refuses_instead_of_returning_plausible_facts(case, monkeypatch, change):
    receipt = expected(case)
    if change == 'copy':
        with pytest.raises(m.Refused, match='^join_refused$'):
            m.facts(copy.copy(case.plain), case.context, case.packet, receipt)
        return
    original = m.identity_join._streams
    calls = []
    def selected(*args):
        result = original(*args)
        calls.append(True)
        if len(calls) == 2:
            if change == 'capability': object.__setattr__(case.plain, 'source_lineage_sha256', '0' * 64)
            elif change == 'packet': case.packet['synthetic-public-packet'] = False
            elif change == 'context': case.context['diagnostic_only'] = False
            else: receipt['context_sha256'] = '0' * 64
        return result
    monkeypatch.setattr(m.identity_join, '_streams', selected)
    with pytest.raises(m.Refused, match='^plain_changed$'): facts(case, receipt)


def test_missing_or_duplicate_whole_row_match_refuses(case, monkeypatch):
    receipt = expected(case)
    original = m.identity_join._streams
    calls = []
    def selected(*args):
        result = original(*args)
        calls.append(True)
        if len(calls) == 2:
            result['runtime_symbol_bindings'].append(copy.deepcopy(result['runtime_symbol_bindings'][0]))
        return result
    monkeypatch.setattr(m.identity_join, '_streams', selected)
    with pytest.raises(m.Refused, match='^catalog_match$'): facts(case, receipt)


def test_no_new_file_archive_or_provider_read(case, monkeypatch):
    receipt = expected(case)
    def denied(*args, **kwargs): raise AssertionError('pure facts performed an external read')
    monkeypatch.setattr(builtins, 'open', denied)
    monkeypatch.setattr(Path, 'read_bytes', denied)
    assert facts(case, receipt)['witness_count'] == 1


def test_receipt_is_detached(case):
    value = facts(case)
    second = m.validate_receipt(value)
    value['facts'][0]['source_snapshot_vs_decision'] = 'before'
    value['snapshot_relations']['after'] = 0
    assert second['facts'][0]['source_snapshot_vs_decision'] == 'after'
    assert second['snapshot_relations']['after'] == 1


@pytest.mark.parametrize('change', ['extra', 'bool_count', 'raw_date', 'invalid_relation',
    'count', 'authority', 'duplicate', 'bad_hash', 'nested', 'false_qualification'])
def test_closed_receipt_cannot_gain_false_readiness_or_raw_fields(case, change):
    value = facts(case)
    if change == 'extra': value['private'] = 'hidden'
    elif change == 'bool_count': value['witness_count'] = True
    elif change == 'raw_date': value['facts'][0]['actual_date'] = '2022-10-21'
    elif change == 'invalid_relation': value['facts'][0]['source_snapshot_vs_decision'] = 'historical-proof'
    elif change == 'count': value['reference_relations']['inside'] = 0
    elif change == 'authority': value['formal_forward_ready'] = True
    elif change == 'duplicate': value['facts'] *= 2
    elif change == 'bad_hash': value['join_receipt_sha256'] = 'A' * 64
    elif change == 'nested': value['facts'][0]['identity_sha256'] = {'private': 'data'}
    else: value['candidate_intervals_are_clipped_input_geometry'] = False
    with pytest.raises(m.Refused, match='^receipt$'): m.validate_receipt(value)


@pytest.mark.parametrize('code', sorted(m.FINITE))
def test_finite_failures(code): assert m.finite(m.Refused(code)) == code


def test_unknown_error_details_are_never_returned():
    class Foreign(m.Refused): pass
    for error in (ValueError('PRIVATE'), Foreign('catalog'), m.Refused('PRIVATE'),
            m.Refused(), m.Refused('catalog', 'PRIVATE')):
        assert m.finite(error) == 'unknown'


def test_profile_is_qualified_and_has_no_operational_entry():
    profile = m.profile_record()
    assert profile['candidate_intervals_are_clipped_input_geometry'] is True
    assert profile['same_admitted_plain_payloads_only'] is True
    assert profile['no_new_archive_or_provider_read'] is True
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert not any(hasattr(m, key) for key in ('main', 'run', 'request', 'Store', 'claim', 'launch'))
