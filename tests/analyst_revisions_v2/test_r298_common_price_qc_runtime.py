"""Synthetic monetary/reference tests; no provider, QC or licensed input reads."""
import copy
import json
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from types import MethodType, SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_common_price_qc_runtime as m
from tests.analyst_revisions_v2 import test_r298_native_price_source_diagnostic as original


class Provider:
    def __init__(self, rows, symbols, grid, *, funds=None):
        self.rows = {row['security_id']: row for row in rows}
        self.symbols, self.grid, self.funds = symbols, {row['session']: row for row in grid}, funds or {}
        self.prices = {(identity, session): Decimal('100')
            for identity in [*self.rows, *('own-etf-' + ticker for ticker in self.funds)] for session in self.grid}
        self.calls, self.auths, self.ready, self.fail_auth = [], 0, False, False

    def authenticate_once(self):
        assert not self.ready
        self.auths += 1
        if self.fail_auth: raise RuntimeError('SYNTHETIC PRIVATE AUTH FAILURE')
        self.ready = True

    def receipt(self):
        assert self.ready
        return {'schema': 'synthetic-provider-receipt', 'source_pin': 'a' * 64}

    def symbol_for_binding(self, row):
        assert self.ready and row == self.rows[row['security_id']]
        return self.symbols[row['composite_figi']]

    def price(self, contract, session):
        assert self.ready
        identity = contract['security_id'] if 'security_id' in contract else 'own-etf-' + contract['ticker']
        self.calls.append((identity, session))
        return self.prices[(identity, session)]


class Native(Provider):
    def session_close(self, session):
        assert self.ready
        return datetime.fromisoformat(self.grid[session]['close_utc']).astimezone(m.NY)


class Vendor(Provider):
    def symbol_for_fund(self, contract):
        assert self.ready and contract == {'schema': m.FUND_SCHEMA, 'ticker': contract['ticker']}
        return self.funds[contract['ticker']]


@pytest.fixture
def case(monkeypatch):
    base = original.scenario.__wrapped__(monkeypatch)
    native = Native(base.rows[:5], base.symbols, base.grid)
    vendor = Vendor(base.rows[5:], base.symbols, base.grid, funds=base.etfs)
    monkeypatch.setattr(m, '_provider_types', lambda: (Native, Vendor))
    monkeypatch.setattr(m, 'NATIVE_SPECIFICATION_SHA256', m.digest(base.spec))
    args = {'stock_bindings': tuple(base.rows), 'own_fund_contracts': m.fund_contracts(),
        'session_axis': base.loaded.evaluator_input.session_axis, 'native_specification': base.spec}
    source = m.SpecificCommonPriceBook(native, vendor, **args)
    source.authenticate_once()
    ids = [row['security_id'] for row in base.rows]
    symbols = {row['security_id']: base.symbols[row['composite_figi']] for row in base.rows}
    symbols.update({'own-etf-' + ticker: symbol for ticker, symbol in base.etfs.items()})
    return NS(base=base, native=native, vendor=vendor, source=source, ids=ids, symbols=symbols, args=args)


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code
    assert 'PRIVATE' not in str(caught.value)


def after_close(case, session='2021-01-04'):
    return case.source.session_close(session) + timedelta(minutes=1)


def test_same_fixed_book_routes_exact_five_and_vendor_rest_without_callbacks_or_fallback(case):
    assert case.native.auths == case.vendor.auths == 1
    native_id, vendor_id, fund_id = case.ids[0], case.ids[-1], 'own-etf-SPY'
    for identity in (native_id, vendor_id, fund_id):
        assert case.source.price(identity, '2021-01-04', runtime_symbol=case.symbols[identity]) == Decimal(100)
    assert case.native.calls == [(native_id, '2021-01-04')]
    assert case.vendor.calls == [(vendor_id, '2021-01-04'), (fund_id, '2021-01-04')]
    counts = case.source.receipt()['lookup_counts']
    assert counts['native_price_lookup_attempts'] == counts['native_price_lookup_completed'] == 1
    assert counts['vendor_price_lookup_attempts'] == counts['vendor_price_lookup_completed'] == 2
    assert counts['native_identity_check_attempts'] == counts['native_identity_check_completed'] == 1
    assert all(case.source.receipt()[key] is False for key in m.FALSE_FLAGS)
    refused('once', case.source.authenticate_once)


@pytest.mark.parametrize('mode', ['callable', 'subclass', 'instance_method', 'bound_callback', 'class_method'])
def test_concrete_provider_and_original_bound_method_guards_reject_callback_substitutes(case, monkeypatch, mode):
    if mode == 'callable':
        refused('provider_type', lambda: m.SpecificCommonPriceBook(lambda: 100, case.vendor, **case.args))
    elif mode == 'subclass':
        class Alternate(Native): pass
        other = Alternate(case.base.rows[:5], case.base.symbols, case.base.grid)
        refused('provider_type', lambda: m.SpecificCommonPriceBook(other, case.vendor, **case.args))
    elif mode == 'instance_method':
        case.native.price = lambda *args: Decimal(100)
        refused('provider_method', lambda: case.source.price(case.ids[0], '2021-01-04', runtime_symbol=case.symbols[case.ids[0]]))
    elif mode == 'bound_callback':
        case.native.price = MethodType(lambda self, *args: Decimal(100), case.native)
        refused('provider_method', lambda: case.source.price(case.ids[0], '2021-01-04', runtime_symbol=case.symbols[case.ids[0]]))
    else:
        monkeypatch.setattr(Native, 'price', lambda self, *args: Decimal(100))
        refused('provider_changed', lambda: case.source.price(case.ids[0], '2021-01-04', runtime_symbol=case.symbols[case.ids[0]]))


@pytest.mark.parametrize('mode,code', [('rows', 'catalog'), ('funds', 'fund'), ('axis', 'axis'), ('spec', 'specification')])
def test_full_original_inventory_fund_roles_axis_and_native_five_are_not_relaxed(case, mode, code):
    args = copy.deepcopy(case.args)
    if mode == 'rows': args['stock_bindings'] = args['stock_bindings'][:-1]
    elif mode == 'funds': args['own_fund_contracts'] = tuple(reversed(args['own_fund_contracts']))
    elif mode == 'axis': args['session_axis'] = tuple(reversed(args['session_axis']))
    else: args['native_specification']['selected_whole_binding_sha256s'][-1] = 'f' * 64
    refused(code, lambda: m.SpecificCommonPriceBook(case.native, case.vendor, **args))


def test_failed_provider_authentication_is_consumed_without_partial_ready_or_price_access(case):
    native = Native(case.base.rows[:5], case.base.symbols, case.base.grid)
    vendor = Vendor(case.base.rows[5:], case.base.symbols, case.base.grid, funds=case.base.etfs)
    vendor.fail_auth = True
    source = m.SpecificCommonPriceBook(native, vendor, **case.args)
    refused('provider_authentication', source.authenticate_once)
    assert native.auths == vendor.auths == 1
    refused('not_authenticated', source.receipt)
    refused('once', source.authenticate_once)
    assert native.calls == vendor.calls == []


def test_prior_close_references_include_target_and_all_positive_holdings_with_honest_counters(case):
    ledger = m.CommonPriceLedger(case.source)
    target, held = case.ids[0], case.ids[-1]
    case.native.prices[(target, '2020-12-31')] = Decimal('12.25')
    case.vendor.prices[(held, '2020-12-31')] = Decimal('7.50')
    symbols = {identity: case.symbols[identity] for identity in (target, held)}
    result = ledger.reference_prices('2020-12-31', (target,), {held: 3}, symbols,
        now=datetime(2021, 1, 4, 9, 20))
    assert result == {target: Decimal('12.25'), held: Decimal('7.50')}
    summary = ledger.summary()
    assert summary['counts']['reference_batch_attempts'] == summary['counts']['reference_batch_completed'] == 1
    assert summary['reference_QC_History_calls_by_component'] == summary['split_QC_History_calls_by_component'] == 0
    assert summary['source_observation']['lookup_counts']['native_price_lookup_attempts'] == 1
    assert summary['source_observation']['lookup_counts']['vendor_price_lookup_attempts'] == 1


@pytest.mark.parametrize('mode,code', [('same_day', 'clock'), ('wrong_prior', 'clock'), ('wrong_time', 'clock'),
    ('missing_held_symbol', 'runtime_identity'), ('unknown_holding', 'identity'), ('wrong_sid', 'runtime_identity')])
def test_reference_clock_and_complete_holding_identity_precede_any_price_fallback(case, mode, code):
    ledger = m.CommonPriceLedger(case.source)
    target, held = case.ids[0], case.ids[-1]
    previous, now = '2020-12-31', datetime(2021, 1, 4, 9, 20)
    holdings = {held: 1}; symbols = {target: case.symbols[target], held: case.symbols[held]}
    if mode == 'same_day': previous = '2021-01-04'
    elif mode == 'wrong_prior': previous = '2021-11-26'
    elif mode == 'wrong_time': now = now.replace(minute=19)
    elif mode == 'missing_held_symbol': symbols.pop(held)
    elif mode == 'unknown_holding': holdings = {'unexpected-positive': 1}
    else: symbols[target] = case.symbols['own-etf-SPY']
    refused(code, lambda: ledger.reference_prices(previous, (target,), holdings, symbols, now=now))
    assert case.native.calls == case.vendor.calls == []


def test_authoritative_close_nav_gross_uses_cash_and_same_session_RAW_under_Decimal96(case):
    ledger = m.CommonPriceLedger(case.source)
    stock, fund = case.ids[0], 'own-etf-SPY'
    case.native.prices[(stock, '2021-01-04')] = Decimal('12.125')
    case.vendor.prices[(fund, '2021-01-04')] = Decimal('7.01')
    nav, gross = ledger.observe_close('2021-01-04', cash=Decimal('900.123'), holdings={stock: 3, fund: 2},
        runtime_symbols={stock: case.symbols[stock], fund: case.symbols[fund]}, now=after_close(case), engine_nav=Decimal('999999'))
    with localcontext() as arithmetic:
        arithmetic.prec = 96
        expected_holdings = Decimal(3) * Decimal('12.125') + Decimal(2) * Decimal('7.01')
        assert nav == Decimal('900.123') + expected_holdings
        assert gross == expected_holdings / nav
    assert nav != Decimal('999999')
    assert ledger.summary()['unique_close_count'] == 1
    assert b'12.125' not in m.canonical(ledger.summary())


def test_actual_cash_already_contains_dividend_fee_and_action_credits_without_second_adjustment(case):
    ledger = m.CommonPriceLedger(case.source)
    identity = case.ids[0]
    case.native.prices[(identity, '2021-01-04')] = Decimal(10)
    # The input cash is the actual post-fee/post-dividend engine balance.
    nav, gross = ledger.observe_close('2021-01-04', cash=Decimal('101.25'), holdings={identity: 5},
        runtime_symbols={identity: case.symbols[identity]}, now=after_close(case))
    assert nav == Decimal('151.25')
    with localcontext() as arithmetic:
        arithmetic.prec = 96
        assert gross == Decimal(50) / Decimal('151.25')


def test_same_day_split_bridge_is_left_to_frozen_driver_and_not_double_applied_to_RAW(case):
    ledger = m.CommonPriceLedger(case.source)
    identity = case.ids[0]
    case.native.prices[(identity, '2020-12-31')] = Decimal(100)
    reference = ledger.reference_prices('2020-12-31', (identity,), {identity: 10},
        {identity: case.symbols[identity]}, now=datetime(2021, 1, 4, 9, 20))[identity]
    assert reference == Decimal(100)
    # Existing exact same-day split factor1/2 changes sizing units once.
    split_unit_reference = reference * Decimal('0.5')
    case.native.prices[(identity, '2021-01-04')] = Decimal(50)
    nav, _ = ledger.observe_close('2021-01-04', cash=0, holdings={identity: 20},
        runtime_symbols={identity: case.symbols[identity]}, now=after_close(case))
    assert split_unit_reference == 50 and nav == 1000
    assert ledger.summary()['split_QC_History_calls_by_component'] == 0


@pytest.mark.parametrize('mode,code', [('negative_cash', 'cash'), ('zero_NAV', 'valuation'),
    ('short', 'quantity'), ('fractional', 'quantity'), ('unknown_positive', 'identity'),
    ('before_close', 'clock'), ('wrong_day', 'clock')])
def test_invalid_account_or_early_close_never_uses_engine_NAV_as_fallback(case, mode, code):
    ledger = m.CommonPriceLedger(case.source)
    identity = case.ids[0]
    cash, holdings, symbols, now = 1, {identity: 1}, {identity: case.symbols[identity]}, after_close(case)
    if mode == 'negative_cash': cash = -1
    elif mode == 'zero_NAV': cash, holdings, symbols = 0, {}, {}
    elif mode == 'short': holdings[identity] = -1
    elif mode == 'fractional': holdings[identity] = Decimal('0.5')
    elif mode == 'unknown_positive': holdings, symbols = {'unexpected': 1}, {'unexpected': case.symbols[identity]}
    elif mode == 'before_close': now = datetime(2021, 1, 4, 13)
    else: now = datetime(2021, 1, 5, 17)
    refused(code, lambda: ledger.observe_close('2021-01-04', cash=cash, holdings=holdings,
        runtime_symbols=symbols, now=now, engine_nav=Decimal(1000000)))


@pytest.mark.parametrize('value', [None, Decimal(0), Decimal(-1), Decimal('NaN'), Decimal('Infinity'), 100, '100'])
def test_missing_or_unknown_or_nonDecimal_prices_stop_without_vendor_scalar_or_engine_fallback(case, value):
    ledger = m.CommonPriceLedger(case.source)
    identity = case.ids[0]
    if value is None: del case.native.prices[(identity, '2021-01-04')]
    else: case.native.prices[(identity, '2021-01-04')] = value
    refused('price_missing_or_unknown' if value is None else 'price', lambda: ledger.observe_close('2021-01-04',
        cash=1, holdings={identity: 1}, runtime_symbols={identity: case.symbols[identity]}, now=after_close(case), engine_nav=999))
    assert case.vendor.calls == []
    counts = case.source.receipt()['lookup_counts']
    assert counts['native_price_lookup_attempts'] == 1 and counts['native_price_lookup_completed'] == 0


def test_holding_past_membership_or_binding_end_still_requires_current_mark_and_actual_zero_controls_exit(case):
    ledger = m.CommonPriceLedger(case.source)
    identity = case.ids[0]
    assert case.base.rows[0]['candidate_last_session'] == '2021-01-04'
    case.native.prices[(identity, '2021-11-26')] = Decimal(20)
    nav, _ = ledger.observe_close('2021-11-26', cash=10, holdings={identity: 2},
        runtime_symbols={identity: case.symbols[identity]}, now=after_close(case, '2021-11-26'))
    assert nav == 50 and case.native.calls[-1] == (identity, '2021-11-26')
    # A zero quantity comes only from a future driver's actual engine census,
    # never from this component's membership/date or price logic.
    count = len(case.native.calls)
    nav, gross = ledger.observe_close('2026-10-13', cash=Decimal('49.99'), holdings={identity: 0, 'unknown-zero': 0},
        runtime_symbols={}, now=after_close(case, '2026-10-13'))
    assert nav == Decimal('49.99') and gross == 0 and len(case.native.calls) == count


@pytest.mark.parametrize('drift', ['cash', 'quantity', 'mark'])
def test_repeated_authoritative_close_conflict_refuses_but_engine_only_diagnostic_change_does_not(case, drift):
    ledger = m.CommonPriceLedger(case.source)
    identity = case.ids[0]
    args = {'cash': 100, 'holdings': {identity: 1}, 'runtime_symbols': {identity: case.symbols[identity]}, 'now': after_close(case)}
    first = ledger.observe_close('2021-01-04', **args, engine_nav=1000)
    assert ledger.observe_close('2021-01-04', **args, engine_nav=1) == first
    assert ledger.summary()['unique_close_count'] == 1
    if drift == 'cash': args['cash'] = 101
    elif drift == 'quantity': args['holdings'][identity] = 2
    else: case.native.prices[(identity, '2021-01-04')] = Decimal(101)
    refused('repeated_close', lambda: ledger.observe_close('2021-01-04', **args))
    assert ledger.summary()['counts']['close_batch_attempts'] == 3
    assert ledger.summary()['counts']['close_batch_completed'] == 2


def test_component_interface_has_no_callbacks_history_quotes_prices_cache_or_trading_methods(case):
    import ast, inspect
    tree = ast.parse(inspect.getsource(m))
    names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & {'history', 'market_order', 'limit_order', 'set_holdings', 'set_market_price',
        'total_portfolio_value', 'total_holdings_value', 'bid_price', 'ask_price', 'cache', 'save_bytes'}
    assert m.profile_record()['integration'].startswith('future_exact_quote_aware_BaseDriver_alias')
    assert all(m.profile_record()[key] is False for key in m.FALSE_FLAGS)


def test_missing_concrete_vendor_reader_is_an_explicit_barrier_not_a_callback_or_data_fallback(monkeypatch):
    import builtins
    original_import = builtins.__import__
    def bounded_import(name, *args, **kwargs):
        if 'newrule_raw_vendor_price_book_runtime' in name:
            raise ImportError('synthetic missing reviewed vendor reader')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', bounded_import)
    refused('provider_unavailable', m._provider_types)
