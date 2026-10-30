"""W5 cash-limited buys fit LEAN's market-order buying-power check (section 330).

Owner-directed ARV2R328-004 revision: a cash-limited buy is sized on the larger
of the authenticated ask and the engine's security.Price, because LEAN values a
market buy at security.Price plus its fee. Generated public W5 code with the
synthetic quote harness only; the inequality is the documented market-order
check, not cloud evidence of LEAN's behavior.
"""
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from tests.analyst_revisions_v2 import test_quote_execution_projection as quote_fixtures
from tests.analyst_revisions_v2 import test_r327_available_history_projection as projection_fixtures

ASK, CASH = D(110), D('220.22')  # Ask-based sizing alone buys exactly two shares.


@pytest.fixture(scope='module')
def w5():
    batch = projection_fixtures.public_batch()
    raw = dict(batch.specs[0].source_pairs)[projection_fixtures.m.BASE_NAME]
    return NS(files={quote_fixtures.m.RUNTIME_NAME: raw})


def buy(w5, engine_price):
    c = quote_fixtures.case(w5)
    assert c.security.ask_price == ASK
    c.security.price = engine_price
    d, session = c.driver, quote_fixtures.NOW.date().isoformat()
    d._require_initialized = lambda: None
    d._decision_set = d._preopen_clock_confirmations = {session}
    d._executed, d._split_records_by_session = set(), {}
    d._plans = {session: {'holdings': {}, 'split_records': {}, 'quantities': {'ID': 2}, 'sha256': 'a' * 64}}
    d._algorithm.live_mode = False
    d._algorithm.transactions = NS(get_open_orders=lambda: ())
    holdings, orders = {}, []
    d._current_holding_census = lambda: dict(holdings)
    d._current_quantity = lambda identity: holdings.get(identity, 0)
    d._ensure_security = lambda identity: (c.symbol, c.security)
    d._portfolio_cash = lambda: CASH
    d._cash_underfill_count = 0

    def submit(identity, quantity, _session):
        orders.append((identity, quantity))
        holdings[identity] = quantity
    d._submit_market = submit
    return d, orders


@pytest.mark.parametrize('engine_price', ['90', '110', '110.2', '120', '150.5'])
def test_cash_limited_buy_passes_lean_security_price_buying_power_check(w5, engine_price):
    d, orders = buy(w5, D(engine_price))
    assert d.on_after_open() == 'a' * 64
    [(identity, quantity)] = orders
    fee = quantity * ASK * D('0.001')  # The W5 fee model charges on the frozen ask.
    assert identity == 'ID' and quantity * D(engine_price) + fee <= CASH
    assert quantity * ASK + fee <= CASH  # The actual ask fill also fits.


@pytest.mark.parametrize('engine_price', ['90', '110'])
def test_engine_price_at_or_below_ask_keeps_exact_ask_sizing(w5, engine_price):
    d, orders = buy(w5, D(engine_price))
    d.on_after_open()
    assert orders == [('ID', 2)] and d._cash_underfill_count == 0


def test_stale_engine_price_above_ask_sizes_on_engine_price(w5):
    d, orders = buy(w5, D(120))
    d.on_after_open()
    assert orders == [('ID', 1)] and d._cash_underfill_count == 1


@pytest.mark.parametrize('engine_price', [D(0), D(-1), None, D('NaN'), D('Infinity'), D('-Infinity'), True, False])
def test_invalid_engine_price_refuses_before_any_order(w5, engine_price):
    d, orders = buy(w5, engine_price)
    with pytest.raises(quote_fixtures.NewruleError, match='^quote_execution_engine_price$'):
        d.on_after_open()
    assert orders == [] and not d._executed


def test_absent_engine_price_refuses_before_any_order(w5):
    d, orders = buy(w5, D(120))
    del d._ensure_security('ID')[1].price
    with pytest.raises(quote_fixtures.NewruleError, match='^quote_execution_engine_price$'):
        d.on_after_open()
    assert orders == [] and not d._executed


def test_sell_only_dispatch_does_not_enter_buy_engine_price_check(w5):
    d, orders = buy(w5, None)
    session = quote_fixtures.NOW.date().isoformat()
    holdings = {'ID': 2}
    d._plans[session].update(holdings=dict(holdings), quantities={'ID': 0})
    d._current_holding_census = lambda: dict(holdings)
    d._current_quantity = lambda identity: holdings.get(identity, 0)
    d._ensure_security = lambda identity: pytest.fail('sell-only loop entered buy price check')

    def sell(identity, quantity, _session):
        orders.append((identity, quantity))
        holdings[identity] += quantity
    d._submit_market = sell
    assert d.on_after_open() == 'a' * 64
    assert orders == [('ID', -2)] and d._executed == {session}
    assert d._cash_underfill_count == 0


def test_source_profile_declares_cash_bound_change_and_preserved_inverse():
    m = projection_fixtures.m
    profile = m.profile_record()
    assert profile['source_delta'] == ('explicit_W5_base_and_common_modules_Main_import_profile_start_date'
        '_and_declared_buy_cash_bound')
    assert profile['buy_cash_bound'] == m.CASH_BOUND_FIELD[1]
    assert profile['W5_cloud_inverse'].endswith('_and_declared_cash_bound')
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
