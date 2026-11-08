"""Synthetic QC-local coverage; no retained DATA, network or operational use."""
import ast
import copy
from datetime import datetime
from decimal import Decimal
import inspect
import json
import pickle
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_available_history_native_coverage as m
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from scripts import arv2_r327_i_source_binding as i_anchor
from tests.analyst_revisions_v2 import test_r298_native_price_book_runtime as reader_fixture
from tests.analyst_revisions_v2 import test_r298_native_price_source_diagnostic as native_fixture

PRODUCTION_DEMAND, PRODUCTION_GEOMETRY = m.EXPECTED_DEMAND, m.EXPECTED_GEOMETRY


def fail(code, action):
    with pytest.raises(m.Refused) as caught:
        action()
    assert m.finite(caught.value) == code


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    reader_fixture.no_old_operations.__wrapped__(monkeypatch)


@pytest.fixture
def case(monkeypatch):
    old = reader_fixture.case.__wrapped__(monkeypatch)
    source = old.source
    evaluator = m.reader.native.inputs.evaluator
    axis = tuple(row['session'] for row in source.grid)
    raw = tuple(evaluator.build_membership_record(security_id=row['security_id'],
        first_session_index=1, last_session_index_exclusive=2, sector_id='synthetic-sector')
        for row in sorted(source.rows, key=lambda row: row['security_id']))
    memberships = evaluator._parse_memberships(raw, len(axis))
    parsed = evaluator.PreliminaryRatingInput('synthetic-manifest', 'a' * 64, 'synthetic-benchmark',
        axis, memberships, (), (('security_master_admission_sha256', m.reader.native.ADMISSION_SHA256),), 1, 1, 1)
    package = m.reader.native.inputs.LoadedAcceptedRiskPreliminaryPackage('synthetic-package',
        m.reader.native.PACKAGE_SHA256, m.reader.native.ACTIVATION_SHA256, parsed, tuple(source.rows))
    def load(algorithm, **kwargs):
        source.loads.append(kwargs)
        return package
    monkeypatch.setattr(m.reader.native.inputs, 'load_accepted_risk_preliminary_package', load)
    monkeypatch.setattr(m, 'MEMBERSHIP_STREAM_SHA256', evaluator._stream_sha256(raw))
    monkeypatch.setattr(m.period, 'FULL_AXIS_COUNT', len(axis))
    wanted = tuple(m.digest(row) for row in old.selected)
    monkeypatch.setattr(m.period, 'NATIVE_WHOLE_BINDING_SHA256S', wanted)
    monkeypatch.setattr(m, 'EXPECTED_DEMAND', tuple((pin, axis[0], 1) for pin in wanted))
    monkeypatch.setattr(m, 'EXPECTED_GEOMETRY', tuple((len(axis), m.digest(list(axis)),
        m.digest([axis[1]])) for _ in wanted))
    view = {'period_sha256': m.PERIOD_SHA256, 'decision_sessions': [axis[1]],
        'evaluation_sessions': list(axis[1:])}
    def make_period(values):
        assert values == axis
        return copy.deepcopy(view)
    monkeypatch.setattr(m.period, 'make_period', make_period)
    source.algorithm.transactions.get_open_orders = lambda: ()
    def driver():
        return m.AvailableHistoryNativeCoverage(source.algorithm, runtime_project_id=40000001,
            benchmark_symbol=source.etfs['SPY'], etf_symbols=source.etfs,
            trade_bar_type=native_fixture.Bar, daily_resolution='Daily', raw_normalization='RAW')
    return NS(old=old, source=source, package=package, memberships=memberships, raw=raw,
        axis=axis, driver=driver)


def test_inert_then_fresh_package_identity_book_and_dense_remaining_lifetime(case):
    before_loads = len(case.source.loads)
    driver = case.driver()
    assert case.old.store.calls == []
    value = driver.observe_once()
    assert value['terminal'] == value['phase'] == 'complete'
    assert value['failure_code'] is None
    assert value['required_cell_count'] == 20
    assert value['valid_cell_count'] == 19 and value['missing_cell_count'] == 1
    assert value['dense_envelopes_complete'] is False
    assert sum(row['missing_between_first_and_last_valid'] for row in value['per_selected']) == 1
    assert sum(row['potential_reference_missing_count'] for row in value['per_selected']) == 0
    # Membership ends after the first decision; coverage still extends to LAST.
    assert all(row['required_session_count'] == 4 for row in value['per_selected'])
    assert len(case.source.loads) == before_loads + 2
    assert case.old.store.calls == [case.old.key]
    assert case.source.history.calls == []
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    raw = m.canonical(value)
    assert len(raw) <= m.MAX_STATISTIC_BYTES and b'123.45' not in raw and b'SYNTH' not in raw
    assert m.validate_summary(value, expected_profile=m.profile_record(40000001)) == value


def test_no_price_getter_serializer_or_replay(case):
    driver = case.driver()
    assert not any(word in repr(driver) for word in ('SYNTH', '123.45'))
    with pytest.raises(TypeError):
        pickle.dumps(driver)
    driver.observe_once()
    fail('once', driver.observe_once)
    assert case.old.store.calls == [case.old.key]


def test_failure_consumes_once_before_source_or_book(case):
    driver = case.driver()
    case.source.algorithm.transactions.get_open_orders = lambda: ('synthetic',)
    value = driver.observe_once()
    assert value['failure_code'] == 'orders' and value['terminal'] == 'refused'
    assert value['per_selected'] == [] and case.old.store.calls == []
    fail('once', driver.observe_once)


@pytest.mark.parametrize('change', ('date', 'live', 'position', 'orders', 'project', 'zone', 'seed'))
def test_initial_account_and_clock_scope_refuse_before_book(case, change):
    driver = case.driver(); algo = case.source.algorithm
    if change == 'date': algo.time = datetime(2026, 10, 13, 16)
    elif change == 'live': algo.live_mode = True
    elif change == 'position': algo.portfolio['synthetic'] = NS(quantity=1)
    elif change == 'orders': algo.transactions.get_orders = lambda: ('order',)
    elif change == 'project': algo.project_id += 1
    elif change == 'zone': algo.time_zone = 'UTC'
    else: algo.settings.seed_initial_prices = True
    value = driver.observe_once()
    assert value['terminal'] == 'refused' and case.old.store.calls == []
    assert value['failure_code'] in ('clock', 'orders', 'project', 'settings')


@pytest.mark.parametrize('change', ('package', 'activation', 'binding', 'membership', 'lineage', 'axis'))
def test_genuine_source_refuses_before_native_book(case, change):
    package = case.package
    if change == 'package': object.__setattr__(package, 'package_sha256', '0' * 64)
    elif change == 'activation': object.__setattr__(package, 'activation_manifest_sha256', '0' * 64)
    elif change == 'binding': package.runtime_symbol_bindings[0]['row_sha256'] = '0' * 64
    elif change == 'membership': object.__setattr__(package.evaluator_input.memberships[0], 'last_session_index_exclusive', 3)
    elif change == 'lineage': object.__setattr__(package.evaluator_input, 'source_lineage_sha256s', ())
    else: object.__setattr__(package.evaluator_input, 'session_axis', tuple(reversed(case.axis)))
    value = case.driver().observe_once()
    assert value['terminal'] == 'refused' and case.old.store.calls == []


@pytest.mark.parametrize('change', ('first', 'count', 'selected', 'member_end'))
def test_fresh_demand_must_match_exact_prior_I_observations(case, change, monkeypatch):
    if change in ('first', 'count'):
        rows = list(m.EXPECTED_DEMAND); pin, first, count = rows[0]
        rows[0] = (pin, case.axis[1] if change == 'first' else first, 2 if change == 'count' else count)
        monkeypatch.setattr(m, 'EXPECTED_DEMAND', tuple(rows))
    elif change == 'selected':
        monkeypatch.setattr(m.period, 'NATIVE_WHOLE_BINDING_SHA256S', tuple(reversed(m.period.NATIVE_WHOLE_BINDING_SHA256S)))
    else:
        object.__setattr__(case.memberships[0], 'last_session_index_exclusive', 1)
    value = case.driver().observe_once()
    assert value['terminal'] == 'refused' and case.old.store.calls == []


def test_complete_missing_is_not_a_source_fallback_or_strategy_acceptance(case, monkeypatch):
    original = m.reader.SpecificNativePriceBook.price
    def missing(self, binding, session):
        if session == case.axis[-1]:
            raise m.reader.Refused('failure_unknown')
        return original(self, binding, session)
    monkeypatch.setattr(m.reader.SpecificNativePriceBook, 'price', missing)
    value = case.driver().observe_once()
    assert value['terminal'] == 'complete'
    assert sum(row['failure_unknown'] for row in value['per_selected']) == 5
    assert value['missing_cell_count'] == 6 and value['dense_envelopes_complete'] is False
    assert value['complete_strategy_price_coverage_proven'] is False


@pytest.mark.parametrize('mode,region,count,prior_missing', (
    ('before', 'missing_before_first_valid', 1, 1),
    ('between', 'missing_between_first_and_last_valid', 1, 0),
    ('after', 'missing_after_last_valid', 1, 0),
    ('all', 'missing_without_any_valid', 4, 1),
))
def test_gap_regions_and_potential_prior_references_share_same_read_without_price_export(
        case, monkeypatch, mode, region, count, prior_missing):
    calls = []
    def price(self, binding, session):
        calls.append((m.digest(binding), session))
        index = case.axis.index(session)
        if mode == 'all' or index == {'before': 0, 'between': 1, 'after': 3}[mode]:
            raise m.reader.Refused('absent')
        return Decimal('123.45')
    monkeypatch.setattr(m.reader.SpecificNativePriceBook, 'price', price)
    value = case.driver().observe_once()
    assert value['terminal'] == 'complete' and len(calls) == len(set(calls)) == 20
    assert all(row[region] == count and row['potential_reference_missing_count'] == prior_missing
        and row['potential_reference_count'] == 1 for row in value['per_selected'])
    assert all(sum(row[key] for key in m.GAP_REGIONS) == count for row in value['per_selected'])
    assert b'123.45' not in m.canonical(value)


@pytest.mark.parametrize('code', ('selected_identity', 'future_session', 'deadline', 'source_changed', 'unknown'))
def test_nonmissing_refusal_does_not_become_a_missing_price_count(case, monkeypatch, code):
    def error(*_): raise m.reader.Refused(code)
    monkeypatch.setattr(m.reader.SpecificNativePriceBook, 'price', error)
    value = case.driver().observe_once()
    assert value['terminal'] == 'refused' and value['phase'] == 'coverage'
    assert value['failure_code'] == code and value['per_selected'] == []


@pytest.mark.parametrize('price', (Decimal('0'), Decimal('-1'), Decimal('NaN'), Decimal('Infinity'), 2.3, True))
def test_nonpositive_nonfinite_or_non_decimal_quote_never_counts_as_price(case, monkeypatch, price):
    monkeypatch.setattr(m.reader.SpecificNativePriceBook, 'price', lambda *_: price)
    value = case.driver().observe_once()
    assert value['terminal'] == 'refused' and value['failure_code'] == 'price'


def test_current_identity_and_full_book_pin_are_required(case):
    case.old.store.raw = case.old.raw[:-1] + b'!'
    value = case.driver().observe_once()
    assert value['terminal'] == 'refused' and value['failure_code'] == 'source_bytes'


def test_postcheck_detects_input_mutation_without_clearing_finished_failure(case, monkeypatch):
    original = m.reader.SpecificNativePriceBook.price
    def changing(self, binding, session):
        result = original(self, binding, session)
        if session == case.axis[-1]:
            object.__setattr__(case.package.evaluator_input, 'manifest_sha256', 'f' * 64)
        return result
    monkeypatch.setattr(m.reader.SpecificNativePriceBook, 'price', changing)
    value = case.driver().observe_once()
    assert value['terminal'] == 'refused' and value['phase'] == 'postcheck'
    assert value['failure_code'] == 'source_changed' and value['required_cell_count'] == 20
    assert value['dense_envelopes_complete'] is False


def test_postcompletion_guard_still_checks_no_orders(case):
    driver = case.driver(); driver.observe_once()
    driver._deadline = 0
    driver.assert_no_orders()
    case.source.algorithm.transactions.get_open_orders = lambda: (1,)
    fail('orders', driver.assert_no_orders)


def test_arbitrary_lookalike_reader_cannot_supply_an_observation(case):
    driver = case.driver()
    driver._reader = NS()
    value = driver.observe_once()
    assert value['terminal'] == 'refused' and value['failure_code'] == 'reader'
    assert case.old.store.calls == []


def test_cooperative_deadline_refuses_before_source_or_lookup(case, monkeypatch):
    driver = case.driver()
    ticks = iter((0, m.MAX_SECONDS + 1))
    monkeypatch.setattr(m.clock, 'monotonic', lambda: next(ticks))
    value = driver.observe_once()
    assert value['terminal'] == 'refused' and value['failure_code'] == 'deadline'
    assert case.old.store.calls == []


def test_no_valid_cells_cannot_claim_valid_potential_references(case, monkeypatch):
    def missing(*_): raise m.reader.Refused('absent')
    monkeypatch.setattr(m.reader.SpecificNativePriceBook, 'price', missing)
    value = case.driver().observe_once()
    value['per_selected'][0]['potential_reference_missing_count'] = 0
    fail('summary', lambda: m.validate_summary(value, expected_profile=m.profile_record(40000001)))


@pytest.mark.parametrize('change', ('field', 'flag', 'project', 'count_bool', 'count', 'ordinal',
    'hash', 'row_count', 'complete', 'failure', 'profile', 'geometry_hash', 'geometry_count',
    'gap_count', 'empty_valid', 'reference_count', 'reference_missing_bool'))
def test_summary_is_closed_and_bound(case, change):
    value = case.driver().observe_once(); profile = m.profile_record(40000001)
    if change == 'field': value['prices'] = []
    elif change == 'flag': value['price_input_admitted'] = True
    elif change == 'project': value['runtime_project_id'] += 1
    elif change == 'count_bool': value['required_cell_count'] = True
    elif change == 'count': value['valid_cell_count'] += 1
    elif change == 'ordinal': value['per_selected'][0]['ordinal'] = True
    elif change == 'hash': value['reader_receipt_sha256'] = None
    elif change == 'row_count': value['per_selected'].pop()
    elif change == 'complete': value['dense_envelopes_complete'] = True
    elif change == 'failure': value['failure_code'] = 'unbounded private text'
    elif change == 'profile': profile['maximum_seconds'] += 1
    elif change == 'geometry_hash': value['per_selected'][0]['required_sessions_sha256'] = 'f' * 64
    elif change == 'geometry_count':
        value['per_selected'][0]['required_session_count'] += 1
        value['per_selected'][0]['absent'] += 1
        value['required_cell_count'] += 1
        value['missing_cell_count'] += 1
    elif change == 'gap_count': value['per_selected'][0]['missing_before_first_valid'] += 1
    elif change == 'empty_valid':
        row = value['per_selected'][0]
        row['missing_without_any_valid'] = 1
        row['missing_between_first_and_last_valid'] = 0
    elif change == 'reference_count': value['per_selected'][0]['potential_reference_count'] += 1
    else: value['per_selected'][0]['potential_reference_missing_count'] = True
    with pytest.raises(m.Refused): m.validate_summary(value, expected_profile=profile)


def test_worst_case_finite_summary_fits_proven_statistic_boundary(case, monkeypatch):
    value = case.driver().observe_once()
    monkeypatch.setattr(m, 'EXPECTED_DEMAND', PRODUCTION_DEMAND)
    monkeypatch.setattr(m, 'EXPECTED_GEOMETRY', PRODUCTION_GEOMETRY)
    value['profile_sha256'] = m.digest(m.profile_record(40000001))
    for row, (pin, first, eligible), (count, sessions, decisions) in zip(
            value['per_selected'], PRODUCTION_DEMAND, PRODUCTION_GEOMETRY, strict=True):
        row.update(whole_binding_sha256=pin, eligible_decision_count=eligible,
            required_session_count=count, required_sessions_sha256=sessions,
            eligible_decisions_sha256=decisions, valid_cell_count=count - 300,
            absent=100, invalid_or_duplicate=100, failure_unknown=100,
            missing_before_first_valid=100, missing_between_first_and_last_valid=100,
            missing_after_last_valid=100, missing_without_any_valid=0,
            potential_reference_count=eligible, potential_reference_missing_count=eligible)
    value.update(required_cell_count=sum(row[0] for row in PRODUCTION_GEOMETRY),
        valid_cell_count=sum(row[0] for row in PRODUCTION_GEOMETRY) - 1500, missing_cell_count=1500)
    assert m.validate_summary(value, expected_profile=m.profile_record(40000001)) == value
    assert len(m.canonical(value)) <= 8002


def test_prior_I_demand_is_reused_exactly_by_whole_binding_not_display_or_hash_guess():
    fact = i_anchor.observed_fact()
    summary = fact['result']['identity_summary']
    actual = sorted((row['whole_binding_sha256'], row['required_price_first'], row['eligible_decision_count'])
        for row in summary['cases'])
    assert actual == list(m.EXPECTED_DEMAND)
    assert summary['source_pins']['membership_stream_sha256'] == m.MEMBERSHIP_STREAM_SHA256


def test_public_full_calendar_derives_prior_and_retains_last_after_membership_end(monkeypatch):
    axis = october._sessions(); view = m.period.make_period(axis)
    evaluator = m.reader.native.inputs.evaluator
    positions = {value: index for index, value in enumerate(axis)}
    by_pin, memberships = {}, []
    for index, (pin, prior, count) in enumerate(m.EXPECTED_DEMAND):
        security_id = 'synthetic-' + str(index); by_pin[pin] = {'security_id': security_id}
        first = positions[prior] + 1
        # Last index remains the final axis; eligible counts are exact I counts.
        row = evaluator.build_membership_record(security_id=security_id,
            first_session_index=first, last_session_index_exclusive=len(axis), sector_id='synthetic-sector')
        memberships.extend(evaluator._parse_memberships((row,), len(axis)))
    rows, dates, references = m._derive_demand(axis, view, by_pin, memberships)
    assert all(dates[pin][0] == first and dates[pin][-1] == '2026-10-13'
        for pin, first, _ in m.EXPECTED_DEMAND)
    assert [row['eligible_decision_count'] for row in rows] == [90, 87, 63, 87, 150]
    assert [(row['required_session_count'], row['required_sessions_sha256'], row['eligible_decisions_sha256'])
        for row in rows] == list(m.EXPECTED_GEOMETRY)
    assert all(len(references[pin]) == count and references[pin][0] == first
        for pin, first, count in m.EXPECTED_DEMAND)


def test_no_new_History_write_orders_host_transport_or_raw_serializer_interface():
    tree = ast.parse(inspect.getsource(m))
    forbidden = {'history', 'History', 'prepare', 'publish', 'save_bytes', 'save', 'read_bytes',
        'get_file_path', 'market_order', 'set_holdings', 'liquidate', 'open', 'print', 'exec', 'eval', '__import__'}
    calls = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))}
    assert not calls & forbidden
    imports = {node.names[0].name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
    assert not imports & {'os', 'requests', 'socket', 'subprocess', 'pathlib', 'pickle', 'urllib', 'http'}
