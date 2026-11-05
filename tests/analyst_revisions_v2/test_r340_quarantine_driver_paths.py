"""Real quarantine-driver paths a first QC launch would otherwise run first.

Claude review section 340 (ARV2R340-001, -002, -003). The R337 tests stub the
constructor, the genuine initializer and result emission. These tests execute
those real bodies. Only the data-loading seams are synthetic: the package load,
FIGI resolution, score runtime and the full 6151-row census check, which needs
licensed rows. This is not LEAN or cloud evidence.

Two tests are strict expected failures. They hold the open defects in place:
the sources are pinned by spent preparation E, so they are corrected by a new
freeze, and each marker must then be removed.
"""
import ast
from datetime import datetime
from decimal import Decimal as D
import json
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_comparison_projection as frozen_projection
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_common_price as price
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_runtime as m
from scripts import arv2_r337_quarantine_projection as projection
from tests.analyst_revisions_v2 import test_newrule_runtime_projection as base_fixtures
from tests.analyst_revisions_v2 import test_r337_quarantine_projection as projection_fixtures
from tests.analyst_revisions_v2 import test_r337_quarantine_runtime as runtime_fixtures

PROJECT = projection_fixtures.PROJECT
Symbol = base_fixtures.Symbol
DENIED = 'SYNTHETIC-QUARANTINE-0'
KNOWN_FORBIDDEN = {('newrule_five_case_quarantine_common_price.py', 'subprocess')}


def code(operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    return caught.value.args[0]


@pytest.fixture
def case(monkeypatch):
    axis = runtime_fixtures.october._sessions()
    rows = [{'security_id': f'SYNTHETIC-QUARANTINE-{i}', 'synthetic_only': i} for i in range(5)]
    wholes = tuple(m.digest(row) for row in rows)
    for module in (m.quarantine, m.quarantine.policy):
        monkeypatch.setattr(module, 'QUARANTINED_WHOLE_BINDING_SHA256S', wholes)
    catalog = m.quarantine.make_quarantine_catalog_from_bindings(rows)
    catalog_sha = m.digest(catalog)
    context = projection_fixtures.vendor_context(PROJECT)
    pins = {'source.py': 'a' * 64}
    strategy = m.make_strategy_profile(axis, package_sha256=price.native.PACKAGE_SHA256,
        lineage_sha256=m.LINEAGE_SHA256, universe_count=6, ar_percent=0, source_pins=pins,
        quarantine_catalog_sha256=catalog_sha)
    common = m.make_profile(strategy, runtime_project_id=PROJECT,
        vendor_source_context_sha256=m.digest(context), quarantine_catalog_sha256=catalog_sha,
        source_pins=pins)
    symbols = {name: Symbol('SID-' + name, name) for name in ('A', 'DENIED') + m.targets.UNIVERSES}
    configured = []

    def security(symbol):
        return NS(symbol=symbol, set_data_normalization_mode=lambda value: None,
            set_fee_model=lambda value: None, set_slippage_model=lambda value: None,
            set_leverage=lambda value: None)
    algorithm = NS(project_id=PROJECT, live_mode=False, portfolio=base_fixtures.Portfolio(),
        time=datetime(2026, 10, 14, 16, 0), composite_figi=object(), summaries={},
        securities={symbol: security(symbol) for symbol in symbols.values()},
        transactions=NS(get_open_orders=lambda *args: ()))
    algorithm.set_summary_statistic = algorithm.summaries.__setitem__
    resolution = NS(resolution_sha256='e' * 64, symbol_for_security={'A': symbols['A'], DENIED: symbols['DENIED']}.__getitem__,
        resolved=[{'qc_security_id': 'SID-A', 'security_id': 'A', 'qc_display_ticker': 'A'},
            {'qc_security_id': 'SID-DENIED', 'security_id': DENIED, 'qc_display_ticker': 'DENIED'}])
    package = NS(package_sha256=price.native.PACKAGE_SHA256, activation_manifest_sha256='d' * 64,
        runtime_symbol_bindings=tuple(rows), evaluator_input=NS(session_axis=axis,
            source_lineage_sha256s={'security_master_admission_sha256': 'e' * 64}))
    monkeypatch.setattr(m.inputs, 'load_accepted_risk_preliminary_package', lambda *a, **k: package)
    monkeypatch.setattr(m.figi, 'resolve_preliminary_qc_figis', lambda *a, **k: resolution)
    monkeypatch.setattr(m.preopen, 'PreopenRatingScoreRuntime', lambda *a, **k: object())
    monkeypatch.setattr(m.quarantine, 'make_quarantine_catalog', lambda rows: catalog)
    monkeypatch.setattr(m.base.NewruleComparisonDriver, 'configure_security',
        lambda self, value: configured.append(value.symbol))
    monkeypatch.setattr(m.legacy, '_symbol_sid', lambda symbol, label: symbol.id)
    kwargs = dict(common_profile=common, vendor_source_context=context, quarantine_catalog=catalog,
        profile=common['strategy_profile'], activation_manifest_key='synthetic/activation.json',
        activation_manifest_sha256='d' * 64, activation_manifest_byte_count=100,
        benchmark_symbol=symbols['SPY'], etf_symbols={name: symbols[name] for name in m.targets.UNIVERSES},
        fundamental_universe=object(), constituent_universes={name: object() for name in m.targets.UNIVERSES},
        trade_bar_type=object(), quote_bar_type=object(), minute_resolution='minute', daily_resolution='daily',
        raw_normalization='raw', fee_model_factory=lambda: object(), slippage_model_factory=lambda: object(),
        order_status_enum=base_fixtures.Status, order_status_to_int=int, split_occurred_type='occurred',
        split_warning_type='warning', split_data_type='Split')
    return NS(algorithm=algorithm, kwargs=kwargs, common=common, symbols=symbols, package=package,
        catalog=catalog, configured=configured, resolution=resolution, monkeypatch=monkeypatch)


def build(c):
    return m.FiveCaseQuarantineComparisonDriver(c.algorithm, **c.kwargs)


def test_real_constructor_and_genuine_initializer_complete_on_real_shaped_inputs(case):
    driver = build(case)
    assert driver._initialize_genuine_strategy() is True
    assert driver._denied_ids == {f'SYNTHETIC-QUARANTINE-{i}' for i in range(5)}
    assert len(driver._evaluation_sessions) == 1242 and len(driver._decision_sessions) == 259
    assert driver._security_by_sid == {'SID-A': 'A', 'SID-DENIED': DENIED}
    assert case.configured == [case.symbols[name] for name in m.targets.UNIVERSES]


@pytest.mark.parametrize('change,expected', [
    ('live', 'project'), ('project', 'project'), ('context', 'context'), ('strategy', 'profile')])
def test_real_constructor_refuses_a_wrong_binding(case, change, expected):
    if change == 'live':
        case.algorithm.live_mode = True
    elif change == 'project':
        case.algorithm.project_id = PROJECT + 1
    elif change == 'context':
        case.kwargs['vendor_source_context'] = projection_fixtures.vendor_context(PROJECT + 1)
    else:
        case.kwargs['profile'] = {**case.kwargs['profile'], 'universe_count': 8}
    assert code(lambda: build(case)) == expected


def test_valued_denied_holding_stops_at_the_earlier_cash_guard(case):
    driver = build(case)
    case.algorithm.portfolio[case.symbols['DENIED']] = NS(quantity=D(1))
    assert code(driver._initialize_genuine_strategy) == 'starting_cash'


def test_unpriced_denied_holding_stops_at_the_quarantine_guard(case):
    class Unpriced(base_fixtures.Portfolio):
        total_holdings_value = D(0)
    driver = build(case)
    case.algorithm.portfolio = Unpriced({case.symbols['DENIED']: NS(quantity=D(1))})
    assert code(driver._initialize_genuine_strategy) == 'quarantine'


def test_open_order_stops_the_genuine_initializer(case):
    driver = build(case)
    case.algorithm.transactions = NS(get_open_orders=lambda *args: (object(),))
    assert code(driver._initialize_genuine_strategy) == 'initial_open_orders'


def test_changed_catalog_stops_the_genuine_initializer(case):
    driver = build(case)
    case.monkeypatch.setattr(m.quarantine, 'make_quarantine_catalog', lambda rows: {'changed': True})
    assert code(driver._initialize_genuine_strategy) == 'catalog'


def test_nonstarting_cash_stops_the_genuine_initializer(case):
    driver = build(case)
    case.algorithm.portfolio.cash = D('999999')
    assert code(driver._initialize_genuine_strategy) == 'starting_cash'


def ready(case):
    driver = build(case)
    driver._initialize_genuine_strategy()
    driver._freeze_fund_translation()
    required = []
    driver._common_source = NS(require_identity=required.append, receipt=lambda: {})
    driver._common_ledger = NS(summary=lambda: runtime_fixtures.common_result(case.common)['ledger'])
    driver._bridge = NS(receipt=lambda: {'fresh_resolution_sha256': 'e' * 64})
    driver._common_ready = True
    case.monkeypatch.setattr(m.figi, 'require_preliminary_qc_figi_resolution', lambda value: None)
    return driver, required


def test_real_price_identity_binds_stock_fund_and_denied_paths(case):
    driver, required = ready(case)
    assert driver._price_identity('A') == 'A' and required == ['A']
    assert driver._price_identity('SID-SPY') == 'own-etf-SPY'
    assert code(lambda: driver._price_identity(DENIED)) == 'quarantine'
    assert code(lambda: driver._price_identity('UNKNOWN')) == 'identity'


@pytest.mark.parametrize('change,expected', [('not_ready', 'not_ready'), ('live', 'project'),
    ('project', 'project'), ('resolution', 'resolution'), ('catalog', 'catalog')])
def test_real_common_guard_refuses_each_changed_binding(case, change, expected):
    driver, _ = ready(case)
    driver._common_guard()
    if change == 'not_ready':
        driver._common_ready = False
    elif change == 'live':
        case.algorithm.live_mode = True
    elif change == 'project':
        case.algorithm.project_id = PROJECT + 1
    elif change == 'resolution':
        driver._bridge = NS(receipt=lambda: {'fresh_resolution_sha256': 'f' * 64})
    else:
        driver._quarantine_catalog = {'changed': True}
    assert code(driver._common_guard) == expected


def complete(driver):
    """Fill the state a finished run leaves; shapes match the real writers."""
    nav = D('1010000')
    driver._account_observations = {session: nav for session in driver._evaluation_sessions}
    driver._account_safety = {session: 'a' * 64 for session in driver._evaluation_sessions}
    driver._plans = {session: {'binding': {'context_sha256': 'b' * 64}, 'sha256': 'c' * 64}
        for session in driver._decision_sessions}
    driver._executed = set(driver._decision_sessions)
    driver._preopen_clock_confirmations = {session: 'd' * 64 for session in driver._decision_sessions}
    driver._order_ids = {1}
    driver._fills = [{'fee': '1'}]
    driver._split_history_count = len(driver._decision_sessions)
    driver._quarantine_ledgers = {session: {'transferred_to_own_etf_weight': '0.01',
        'selected_sleeve_occurrence_count': 2, 'positive_sleeve_occurrence_count': 1}
        for session in driver._decision_sessions}


def test_real_result_emission_passes_the_real_validators(case):
    driver, _ = ready(case)
    complete(driver)
    meta, monthly = driver.on_end_of_algorithm()
    assert set(case.algorithm.summaries) == {m.META_STATISTIC, m.MONTHLY_STATISTIC}
    checked = m.validate_result_statistics(dict(case.algorithm.summaries), expected_profile=case.common)
    assert checked['meta'] == json.loads(m.canonical(meta))
    assert checked['monthly']['months'] == monthly['months'] and len(monthly['months']) == 60
    quarantine = checked['meta']['quarantine']
    assert quarantine['decision_count'] == 259 and quarantine['decisions_with_positive_transfer'] == 259
    assert D(quarantine['total_transferred_to_own_etf_weight']) == D('0.01') * 259
    assert quarantine['total_selected_sleeve_occurrence_count'] == 518
    assert driver._emitted is True
    with pytest.raises(Exception, match='not active'):
        driver.on_end_of_algorithm()


@pytest.mark.parametrize('change', ['plan', 'executed', 'close', 'open_order'])
def test_real_result_emission_refuses_an_incomplete_run(case, change):
    driver, _ = ready(case)
    complete(driver)
    if change == 'plan':
        driver._plans.pop(driver._decision_sessions[0])
    elif change == 'executed':
        driver._executed.discard(driver._decision_sessions[-1])
    elif change == 'close':
        driver._account_observations.pop(driver._evaluation_sessions[-1])
    else:
        case.algorithm.transactions = NS(get_open_orders=lambda *args: (object(),))
    assert code(driver.on_end_of_algorithm) == 'incomplete_terminal_geometry'
    assert not case.algorithm.summaries


def test_real_result_rejects_a_missing_decision_ledger(case):
    driver, _ = ready(case)
    complete(driver)
    driver._quarantine_ledgers.pop(driver._decision_sessions[0])
    assert code(driver.on_end_of_algorithm) == 'quarantine_ledger'
    assert not case.algorithm.summaries


def buy_without_quote(monkeypatch):
    c = runtime_fixtures._quote_case(monkeypatch)
    d, session = c.driver, c.now.date().isoformat()
    d._require_initialized = lambda: None
    d._decision_set, d._executed = {session}, set()
    d._preopen_clock_confirmations, d._split_records_by_session = {session}, {}
    d._plans = {session: {'holdings': {}, 'split_records': {}, 'quantities': {'ID': 2}, 'sha256': 'a' * 64}}
    d._algorithm.transactions = NS(get_open_orders=lambda: ())
    d._current_holding_census = lambda: {}
    d._current_quantity = lambda identity: 0
    d._ensure_security = lambda identity: (c.symbol, c.security)
    d._portfolio_cash = lambda: D(230)
    d._cash_underfill_count = 0
    orders = []
    d._submit_market = lambda *args: orders.append(args)

    class NoBars:
        def __contains__(self, key):
            return False
    d._algorithm.current_slice = NS(quote_bars=NoBars())
    return d, orders


def test_buy_without_a_quote_fails_closed_before_any_order(monkeypatch):
    d, orders = buy_without_quote(monkeypatch)
    with pytest.raises(Exception):
        d.on_after_open()
    assert orders == [] and not d._executed


@pytest.mark.xfail(strict=True, raises=AssertionError,
    reason='ARV2R340-001: require raises contract.Refused, so the cash-bound clause relabels quote refusals')
def test_buy_without_a_quote_keeps_its_own_refusal_code(monkeypatch):
    d, _ = buy_without_quote(monkeypatch)
    with pytest.raises(Exception) as caught:
        d.on_after_open()
    assert caught.value.args == ('quote_execution_slice',)


def forbidden_cloud_imports():
    found = set()
    hosts = tuple((name, (projection_fixtures.PUBLIC / name).read_bytes()) for name in sorted(projection.HOST_SOURCE_PINS))
    cloud = projection._cloud_sources(hosts, dict(projection.HOST_SOURCE_PINS))
    assert len(cloud) == 19
    for name, raw in cloud:
        for node in ast.walk(ast.parse(raw)):
            modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
            found.update((name, module.split('.')[0]) for module in modules
                if module.split('.')[0] in frozen_projection.FORBIDDEN_IMPORTS)
    return found


def test_no_cloud_source_adds_a_forbidden_import_beyond_the_named_defect():
    assert forbidden_cloud_imports() <= KNOWN_FORBIDDEN


@pytest.mark.xfail(strict=True, raises=AssertionError,
    reason='ARV2R340-002: the quarantine common-price module imports subprocess; correct by a new freeze')
def test_cloud_sources_have_no_forbidden_import():
    assert not forbidden_cloud_imports()
