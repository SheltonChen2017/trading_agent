"""Synthetic membership/time boundaries, never operational source reads."""
import copy
import hashlib
import sys
import time
import types

import pytest

from scripts import arv2_r298_membership_price_demand as m
from scripts import arv2_r298_route_disposition_evidence as REAL_EVIDENCE
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes as supplied

REAL_AUTHENTICATED, REAL_STREAMS = m._authenticated, m._streams


AXIS = ('2013-01-02', '2020-12-31', '2021-01-04', '2021-01-05',
    '2021-01-11', '2021-01-12', '2026-10-12', '2026-10-13')


def members(ids):
    rows = [m.evaluator.build_membership_record(security_id=ids[0], first_session_index=2,
        last_session_index_exclusive=3, sector_id='synthetic-sector'),
        m.evaluator.build_membership_record(security_id=ids[1], first_session_index=6,
        last_session_index_exclusive=8, sector_id='synthetic-sector'),
        m.evaluator.build_membership_record(security_id=ids[2], first_session_index=3,
        last_session_index_exclusive=4, sector_id='synthetic-sector')]
    return tuple(sorted(rows, key=lambda row: (row['security_id'], row['first_session_index'],
        row['last_session_index_exclusive'], row['sector_id'])))


def refuse(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


@pytest.fixture
def env(monkeypatch):
    raw = supplied.case(4)
    bindings = raw[0]
    stocks = [{'binding_ordinal': i, 'binding': row, 'disposition': ('refused' if i == 1
        else 'outside_window' if i == 2 else 'routed'),
        'reason': ('current_interval' if i == 1 else 'original_candidate_interval_disjoint' if i == 2 else None)}
        for i, row in enumerate(bindings)]
    funds = [{'fund_ordinal': i, 'ticker': ticker, 'disposition': 'routed', 'reason': None}
        for i, ticker in enumerate(m.runtime.targets.UNIVERSES)]
    route = {'schema': 'synthetic-route-private', 'frame_pin': {'byte_count': 100, 'sha256': 'a' * 64},
        'binding_contract': supplied.contract(bindings), 'stocks': stocks, 'funds': funds}
    evidence_summary = {'schema': 'synthetic-evidence-summary', 'frame_pin': dict(route['frame_pin'])}
    evidence = types.ModuleType('scripts.arv2_r298_route_disposition_evidence')
    def validate_summary(value):
        assert value == evidence_summary and set(value) == set(evidence_summary)
        return copy.deepcopy(value)
    def validate_private(value, *, expected_summary):
        assert expected_summary == evidence_summary
        assert set(value) == set(route) and value['frame_pin'] == evidence_summary['frame_pin']
        return copy.deepcopy(value)
    evidence.validate_summary, evidence.validate_private_record = validate_summary, validate_private
    monkeypatch.setitem(sys.modules, evidence.__name__, evidence)
    import scripts
    monkeypatch.setattr(scripts, 'arv2_r298_route_disposition_evidence', evidence, raising=False)
    monkeypatch.setattr(m, 'EXPECTED_BINDINGS', 4)
    monkeypatch.setattr(m.loader.previous.october, '_sessions', lambda: AXIS)
    input_binding = {'binding_contract': dict(route['binding_contract']), 'synthetic_pin': 'b' * 64}
    def validate_input(value):
        assert value == input_binding
    monkeypatch.setattr(m.loader.previous, '_validate_input', validate_input)
    membership_rows = members([row['security_id'] for row in bindings])
    selected = {'evaluator_manifest': [{'membership_row_count': len(membership_rows),
        'membership_rows_sha256': m.evaluator._stream_sha256(membership_rows)}],
        'session_axis': [{'schema': m.evaluator.SESSION_SCHEMA, 'session_index': i, 'session': session}
            for i, session in enumerate(AXIS)],
        'memberships': list(membership_rows), 'runtime_symbol_bindings': copy.deepcopy(bindings)}
    class Plain:
        changed = False
        def to_record(self): return {'synthetic': True}
    plain = Plain()
    parsed = m.evaluator._parse_memberships(membership_rows, len(AXIS))
    authenticated = lambda value, deadline: ('initial', plain.to_record(), copy.deepcopy(selected),
        copy.deepcopy(bindings), copy.deepcopy(input_binding), AXIS, parsed)
    monkeypatch.setattr(m, '_authenticated', authenticated)
    monkeypatch.setattr(m, '_streams', lambda value, record, deadline: copy.deepcopy(selected))
    monkeypatch.setattr(m.loader, '_load_plain', lambda deadline: plain)
    monkeypatch.setattr(m.transport, 'require_plain_transport', lambda value: value)
    monkeypatch.setattr(m.transport, '_fingerprint', lambda value: 'changed' if value.changed else 'initial')
    return types.SimpleNamespace(route=route, evidence=evidence_summary, evidence_module=evidence,
        bindings=bindings, selected=selected, members=parsed, membership_rows=membership_rows,
        input_binding=input_binding, plain=plain, authenticated=authenticated,
        run=lambda: m.prepare(route, evidence_summary=evidence_summary, deadline=time.monotonic() + 60))


def test_all_bindings_retained_and_membership_controls_potential_not_route_disposition(env):
    summary, private = env.run()
    rows = private['stocks']
    assert [row['security_id'] for row in rows] == [row['security_id'] for row in env.bindings]
    assert [row['potential_for_both_cohorts_all_AR_arms'] for row in rows] == [True, True, False, False]
    assert rows[0]['eligible_decision_count'] == 1
    assert rows[0]['first_eligible_decision'] == rows[0]['last_eligible_decision'] == '2021-01-04'
    assert rows[0]['required_price_start'] == '2020-12-31'
    assert rows[0]['required_price_end'] == '2026-10-13'
    assert rows[1]['route_disposition'] == 'refused' and rows[1]['required_price_end'] == '2026-10-13'
    assert rows[2]['membership_interval_count'] == 1 and rows[2]['eligible_decision_count'] == 0
    assert rows[3]['membership_interval_count'] == 0 and rows[3]['required_price_start'] is None
    assert rows[2]['zero_initial_runtime_condition_required_for_never_potential'] is True
    assert summary['cohorts']['6']['potential_stock_count'] == summary['cohorts']['8']['potential_stock_count'] == 2
    assert summary['cohorts']['6']['disposition_relevance'] == {'outside_window': {
        'potential': 0, 'never_potential': 1, 'total': 1}, 'refused': {
        'potential': 1, 'never_potential': 0, 'total': 1}, 'routed': {'potential': 1, 'never_potential': 1, 'total': 2}}
    assert summary['cohorts']['6']['refusal_reason_relevance'] == {'current_interval': {
        'potential': 1, 'never_potential': 0, 'total': 1}}
    assert len(private['funds']) == 8 and sum(row['six_universe'] for row in private['funds']) == 6
    assert all(row['required_price_start'] == '2020-12-31' and row['required_price_end'] == '2026-10-13'
        for row in private['funds'])
    assert summary['private_frame_sha256'] == m.sha(m.canonical(private))
    assert summary['private_frame_byte_count'] == len(m.canonical(private))
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    encoded = m.canonical(summary)
    for secret in ('SYN1', 'sharadar-composite-figi-', 'BBG000000001', 'QQQ', 'synthetic-sector'):
        assert secret.encode() not in encoded


def test_price_window_never_clipped_to_binding_or_membership_last_session(env):
    env.route['stocks'][0]['binding']['candidate_last_session'] = '2021-01-04'
    env.bindings[0]['candidate_last_session'] = '2021-01-04'
    # Synthetic substitution above authenticates both identical full rows;
    # no claim is made that this changed binding was loaded from production.
    summary, private = env.run()
    assert private['stocks'][0]['required_price_end'] == m.runtime.END_SESSION
    assert summary['membership_end_is_price_end'] is summary['binding_end_is_price_end'] is False


def test_first_inclusive_and_last_exclusive_membership_boundary():
    ids = ['synthetic-a', 'synthetic-b', 'synthetic-c']
    parsed = m.evaluator._parse_memberships(members(ids), len(AXIS))
    stocks = [{'binding_ordinal': i, 'binding': {'security_id': sid, 'row_sha256': str(i) * 64},
        'disposition': 'routed', 'reason': None} for i, sid in enumerate(ids)]
    rows, _, _, _ = m._derive(AXIS, parsed, stocks, [], time.monotonic() + 60)
    assert rows[0]['eligible_decision_count'] == 1
    assert rows[2]['eligible_decision_count'] == 0  # Jan11 is exclusive last.
    assert rows[1]['last_eligible_decision'] == '2026-10-12'


def test_weekly_axis_uses_first_actual_session_and_not_a_monday_guess():
    axis = ('2013-01-02', '2020-12-31', '2021-01-04', '2021-01-12', '2021-01-13',
        '2026-10-12', '2026-10-13')
    decisions, _ = m._decisions(axis)
    assert decisions == ('2021-01-04', '2021-01-12', '2026-10-12')


def test_final_capability_and_selected_stream_changes_refuse(env, monkeypatch):
    old = m._derive
    def derive(*args, **kwargs):
        result = old(*args, **kwargs); env.plain.changed = True
        return result
    monkeypatch.setattr(m, '_derive', derive)
    refuse('plain_changed', env.run)


def test_full_catalog_join_cannot_drop_or_change_a_last_binding(env):
    env.route['stocks'][-1]['binding'] = dict(env.route['stocks'][-1]['binding'], row_sha256='0' * 64)
    refuse('catalog_binding', env.run)


@pytest.mark.parametrize('fault', [None, 'count', 'hash', 'unknown_id', 'overlap', 'last_bound'])
def test_genuine_four_role_authentication_checks_membership_hash_count_and_all_ids(env, monkeypatch, fault):
    monkeypatch.setattr(m.loader, '_catalog', lambda plain, deadline: ('initial', env.plain.to_record(),
        {key: copy.deepcopy(env.selected[key]) for key in ('evaluator_manifest', 'session_axis', 'runtime_symbol_bindings')},
        copy.deepcopy(env.bindings), copy.deepcopy(env.input_binding)))
    monkeypatch.setattr(m.evaluator, '_parse_sessions', lambda rows: tuple(row['session'] for row in rows))
    if fault == 'count': env.selected['evaluator_manifest'][0]['membership_row_count'] += 1
    elif fault == 'hash': env.selected['evaluator_manifest'][0]['membership_rows_sha256'] = '0' * 64
    elif fault in ('unknown_id', 'overlap', 'last_bound'):
        rows = env.selected['memberships']
        if fault == 'unknown_id':
            rows[-1] = m.evaluator.build_membership_record(security_id='unknown-genuine-membership-identity',
                first_session_index=2, last_session_index_exclusive=3, sector_id='synthetic-sector')
        elif fault == 'overlap': rows.append(dict(rows[-1]))
        else:
            row = rows[-1]
            row['last_session_index_exclusive'] = len(AXIS) + 1
            seed = dict(row); seed.pop('row_sha256')
            row['row_sha256'] = m.evaluator._sha256(seed)
        env.selected['evaluator_manifest'][0].update(membership_row_count=len(rows),
            membership_rows_sha256=m.evaluator._stream_sha256(tuple(rows)))
    if fault is None:
        result = REAL_AUTHENTICATED(env.plain, time.monotonic() + 60)
        assert result[-2] == AXIS and len(result[-1]) == 3
    else:
        with pytest.raises(ValueError): REAL_AUTHENTICATED(env.plain, time.monotonic() + 60)


@pytest.mark.parametrize('fault', [None, 'missing_membership', 'order', 'hash', 'count', 'trailing_activation'])
def test_four_role_descriptor_iteration_is_complete_and_exact(monkeypatch, fault):
    rows = {
        'evaluator_manifest': [{'synthetic': True}],
        'session_axis': [{'synthetic': 'session'}],
        'memberships': [{'synthetic': 'membership'}],
        'contributions': [{'synthetic': 'contribution'}],
        'runtime_symbol_bindings': [{'synthetic': 'binding'}]}
    pairs = []
    for role in m.transport.ROLES:
        raw = b''.join(m.canonical(row) + b'\n' for row in rows[role])
        descriptor = types.SimpleNamespace(role=role, ordinal=0, record_count=1,
            activation_manifest=False, byte_count=len(raw), content_sha256=m.sha(raw))
        pairs.append((descriptor, raw))
    activation = b'{}\n'
    pairs.append((types.SimpleNamespace(role='activation_manifest', ordinal=0, record_count=1,
        activation_manifest=True, byte_count=len(activation), content_sha256=m.sha(activation)), activation))
    if fault == 'missing_membership': pairs = [pair for pair in pairs if pair[0].role != 'memberships']
    elif fault == 'order': pairs[1], pairs[2] = pairs[2], pairs[1]
    elif fault == 'hash': pairs[2][0].content_sha256 = '0' * 64
    elif fault == 'count': pairs[2][0].record_count = 2
    elif fault == 'trailing_activation': pairs.append(pairs[-1])
    monkeypatch.setattr(m.transport, 'iter_plain_upload_objects', lambda plain: iter(pairs))
    if fault is None:
        selected = REAL_STREAMS(object(), {}, time.monotonic() + 60)
        assert tuple(selected) == m.SELECTED_ROLES
        assert 'contributions' not in selected and selected['memberships'] == rows['memberships']
    else:
        refuse('stream_inventory', lambda: REAL_STREAMS(object(), {}, time.monotonic() + 60))


@pytest.mark.parametrize('path,value', [
    (('schema',), 'other'), (('provider_contact',), True),
    (('membership_row_count',), 0), (('decision_count',), True),
    (('decision_sessions_sha256',), '0' * 64),
    (('cohorts', '6', 'potential_stock_count'), 3),
    (('cohorts', '6', 'stock_required_last'), '2021-01-04'),
    (('cohorts', '6', 'own_etf_count'), 8),
    (('cohorts', '6', 'disposition_relevance', 'routed', 'total'), 0),
    (('cohorts', '8', 'refusal_reason_relevance'), {'credential-like-unknown': {'potential': 1, 'never_potential': 0, 'total': 1}}),
    (('source_frame_pin', 'byte_count'), True), (('private_frame_byte_count',), 0),
])
def test_closed_summary_rejects_forgery_without_new_reads(env, path, value):
    summary, _ = env.run()
    target = summary
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(m.Refused): m.validate_summary(summary)


@pytest.mark.parametrize('path', [(), ('input_binding',), ('cohorts', '6'),
    ('cohorts', '8', 'disposition_relevance', 'routed'), ('source_frame_pin',)])
def test_closed_summary_does_not_expose_extra_names_or_raw_rows(env, path):
    summary, _ = env.run()
    target = summary
    for key in path: target = target[key]
    target['raw-identity-do-not-disclose'] = 'SYNTHETIC'
    with pytest.raises((m.Refused, AssertionError)): m.validate_summary(summary)


def test_finite_diagnostic_never_formats_arbitrary_error():
    class Error(ValueError):
        def __str__(self): raise AssertionError('formatted error')
    assert m._failure_code(Error('private-value')) == 'unknown'
    assert m.finite(m.Refused('private-value')) == 'unknown'


def test_real_route_evidence_composes_without_reparsing_frame_or_weakening_full_binding(env, monkeypatch):
    monkeypatch.setattr(REAL_EVIDENCE, 'EXPECTED_STOCKS', 4)
    source = supplied.case(4)
    routing, private = m.loader.routes.join(*source, binding_contract=supplied.contract(source[0]))
    evidence_summary, facts = REAL_EVIDENCE.inspect(m.canonical(private.private_record()), expected_summary=routing)
    monkeypatch.setitem(sys.modules, 'scripts.arv2_r298_route_disposition_evidence', REAL_EVIDENCE)
    import scripts
    monkeypatch.setattr(scripts, 'arv2_r298_route_disposition_evidence', REAL_EVIDENCE)
    env.route.clear(); env.route.update(facts.private_record())
    env.evidence.clear(); env.evidence.update(evidence_summary)
    env.bindings[:] = source[0]
    summary, demand = env.run()
    assert summary['evidence_summary_sha256'] == m.sha(m.canonical(evidence_summary))
    assert summary['source_frame_pin'] == evidence_summary['frame_pin']
    assert summary['cohorts']['6']['potential_stock_count'] == 2
    assert len(demand['stocks']) == 4
    assert env.route['stocks'][0]['original_predicates']['source_row_hash'] == 'pass'
    env.route['stocks'][-1]['binding']['row_sha256'] = '0' * 64
    refuse('route_evidence', env.run)
