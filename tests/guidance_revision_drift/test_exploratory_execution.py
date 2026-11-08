"""Invented observations only: local order/cash execution, never market outcomes."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
import json
import re
import unittest
from zoneinfo import ZoneInfo

from research.guidance_revision_drift.execution_contract import default_contract
from research.guidance_revision_drift.exploratory_execution import (
    ExploratoryExecutionError, LiquidityReference, LocalExecutionAdapter, MatchedSpyBudgetLedger,
)
from research.guidance_revision_drift.exploratory_market import (
    attach_first_rate_minutes, decode_alpaca_quote_pages,
)
from research.guidance_revision_drift.firstrate import parse_line, reconcile_records
from research.guidance_revision_drift.historical_market import instant_ns
from research.guidance_revision_drift.input_contracts import InputError
from research.guidance_revision_drift.research_reference import CalendarInput

NY = ZoneInfo('America/New_York')
D = Decimal
DAYS = (date(2024, 5, 24), date(2024, 5, 28), date(2024, 5, 29), date(2024, 5, 30))
SEC = 'INVENTED-SEC'
SOURCE = 'a' * 64


def at(day=DAYS[0], hour=10, minute=0, second=0):
    return datetime.combine(day, time(hour, minute, second), NY).astimezone(timezone.utc)


def stamp(value):
    return value.isoformat().replace('+00:00', 'Z')


def calendar(days=DAYS):
    return CalendarInput.from_dict({'schema': 'gdr.research-calendar.v1', 'calendar_id': 'INVENTED-EXECUTION-CALENDAR',
        'source_sha256': SOURCE, 'covered_from': days[0].isoformat(), 'covered_through': days[-1].isoformat(),
        'sessions': [{'date': day.isoformat(), 'open_utc': stamp(at(day, 9, 30)),
                      'close_utc': stamp(at(day, 16))} for day in days]})


def liquidity(day=DAYS[0], security=SEC, adv='10000000', known=None):
    return LiquidityReference(security, day, known or at(day, 9, 59), D(adv), SOURCE)


def book(*, day=DAYS[0], cash='10000', mode='base', sleeve='strategy', positions=None, settlement_days=DAYS):
    return LocalExecutionAdapter(calendar=calendar(),
        contract=default_contract(settlement_days, calendar_source_sha256=SOURCE),
        settled_cash=D(cash), at=at(day, 9, 30), mode=mode, sleeve=sleeve, positions=positions)


def market(*, day=DAYS[0], price='10', volume=10000, security=SEC, symbol='INVENTED',
           role='stock', minutes=(0, 1, 2), conditions=('R',), allow_unknown=False,
           quotes=None, calendar_input=None, capture_bounds=None):
    session = next(row for row in (calendar_input or calendar()).sessions if row.session_date == day)
    if quotes is None:
        quotes = [{'t': stamp(at(day, minute=minute, second=59)), 'bx': 'N', 'bp': price,
                   'bs': 100, 'ap': price, 'as': 100, 'ax': 'N', 'c': list(conditions), 'z': 'A'}
                  for minute in minutes]
    text = json.dumps({'symbol': symbol, 'quotes': quotes, 'next_page_token': None})
    # Invented exact provider number lexemes; never introduce binary floats.
    text = re.sub(r'"(bp|ap)": "(-?[0-9]+(?:\.[0-9]+)?)"', r'"\1": \2', text)
    raw = text.encode()
    paired = decode_alpaca_quote_pages((raw,), security_id=security, symbol=symbol, role=role,
        session=session, allow_unknown_conditions=allow_unknown,
        assumption_sha256='b' * 64 if allow_unknown else None,
        capture_start_ns=capture_bounds[0] if capture_bounds else instant_ns(session.open_utc),
        capture_end_ns=capture_bounds[1] if capture_bounds else instant_ns(session.close_utc))
    rows = [parse_line(f'{day.isoformat()} 10:{minute:02d}:00,{price},{price},{price},{price},{volume}'.encode(),
        source_id='INVENTED-RAW-MINUTES', member=f'{symbol}_full_1min_UNADJUSTED.txt',
        line_number=index + 1, symbol=symbol, kind='minute') for index, minute in enumerate(minutes)]
    return attach_first_rate_minutes(paired, reconcile_records(rows).accepted)


def submit(adapter, *, identity='ORDER1', side='buy', quantity=250, limit='11', day=DAYS[0],
           security=SEC, symbol='INVENTED', adv='10000000', when=None):
    return adapter.submit(order_id=identity, security_id=security, symbol=symbol, side=side,
        quantity=quantity, submitted_at=when or at(day), liquidity=liquidity(day, security, adv),
        limit=D(limit) if limit is not None else None)


class ExploratoryExecutionTests(unittest.TestCase):
    def test_no_submission_quote_or_unclosed_minute_fill(self):
        adapter = book()
        submit(adapter)
        before = adapter.snapshot()
        for callback in (at(), at(second=30)):
            with self.subTest(callback=callback), self.assertRaises(InputError):
                adapter.process('ORDER1', market(), callback_at=callback)
            self.assertEqual(adapter.snapshot(), before)
        old_quote = [{'t': stamp(at()), 'bx': 'N', 'bp': '10', 'bs': 100,
                      'ap': '10', 'as': 100, 'ax': 'N', 'c': ['R'], 'z': 'A'}]
        with self.assertRaises(InputError):
            adapter.process('ORDER1', market(quotes=old_quote), callback_at=at(minute=1))
        self.assertEqual(adapter.snapshot(), before)

    def test_fresh_quote_cannot_fill_beyond_actual_capture_interval(self):
        adapter = book()
        submit(adapter, quantity=200)
        quote = {'t': stamp(at(minute=1)), 'bx': 'N', 'bp': '10', 'bs': 100,
                 'ap': '10', 'as': 100, 'ax': 'N', 'c': ['R'], 'z': 'A'}
        # A later FirstRate minute cannot extend the Alpaca capture interval.
        # The documented request end is inclusive; exact-end selection is
        # allowed, but a later minute/age-60s quote cannot extend coverage.
        observed = market(quotes=[quote], minutes=(0, 1),
            capture_bounds=(instant_ns(at(DAYS[0], 9, 59)), instant_ns(at(minute=1))))
        self.assertEqual(adapter.process('ORDER1', observed, callback_at=at(minute=1)).quantity, 100)
        before = adapter.snapshot()
        with self.assertRaisesRegex(InputError, 'capture'):
            adapter.process('ORDER1', observed, callback_at=at(minute=2))
        self.assertEqual(adapter.snapshot(), before)
        self.assertEqual(before['orders'][0]['remaining'], 100)

    def test_exact_base_stress_quote_side_impact_and_buy_limit(self):
        base, stress = book(), book(mode='stress')
        for adapter in (base, stress):
            submit(adapter, quantity=10, limit='10.01')
        fill = base.process('ORDER1', market(), callback_at=at(minute=1))
        self.assertEqual(fill.price, D('10.0050'))
        self.assertEqual(fill.fee, D('1'))
        self.assertIsNone(stress.process('ORDER1', market(), callback_at=at(minute=1)))
        self.assertEqual(stress.snapshot()['orders'][0]['remaining'], 10)
        selling = book(mode='stress', positions={SEC: 10})
        submit(selling, side='sell', quantity=10, limit=None)
        sale = selling.process('ORDER1', market(), callback_at=at(minute=1))
        self.assertEqual(sale.price, D('9.9850'))
        self.assertEqual(sale.fee, D('2'))

    def test_dollar_ADV_daily_cap_shared_between_orders_exact_whole_shares(self):
        adapter = book()
        submit(adapter, identity='A', quantity=50, adv='1000000')
        submit(adapter, identity='B', quantity=60, adv='1000000')
        first = adapter.process('A', market(), callback_at=at(minute=1))
        second = adapter.process('B', market(), callback_at=at(minute=1))
        self.assertEqual((first.quantity, second.quantity), (50, 49))
        self.assertEqual(first.notional + second.notional, D('990.495'))
        self.assertIsNone(adapter.process('B', market(), callback_at=at(minute=2)))
        self.assertEqual(adapter.snapshot()['positions'][SEC], 99)

    def test_one_percent_minute_cap_is_shared_not_reused_per_order(self):
        adapter = book()
        submit(adapter, identity='A', quantity=70)
        submit(adapter, identity='B', quantity=70)
        first = adapter.process('A', market(), callback_at=at(minute=1))
        second = adapter.process('B', market(), callback_at=at(minute=1))
        self.assertEqual((first.quantity, second.quantity), (70, 30))
        self.assertEqual(adapter.snapshot()['positions'][SEC], 100)

    def test_cumulative_fee_minimum_once_across_partials_and_callback_replay(self):
        adapter = book()
        submit(adapter, quantity=250)
        fills = [adapter.process('ORDER1', market(), callback_at=at(minute=i)) for i in (1, 2, 3)]
        self.assertEqual([fill.quantity for fill in fills], [100, 100, 50])
        self.assertEqual([fill.fee for fill in fills], [D('1'), D('0'), D('0.25')])
        state = adapter.snapshot()
        self.assertEqual(state['settled_cash'], '7497.5')
        self.assertEqual(state['reserved_cash'], '0')
        self.assertEqual(state['orders'][0]['status'], 'filled')
        self.assertIsNone(adapter.process('ORDER1', market(), callback_at=at(minute=1)))
        self.assertEqual(adapter.snapshot(), state)
        with self.assertRaisesRegex(ExploratoryExecutionError, 'conflicting_market_callback_replay'):
            adapter.process('ORDER1', market(price='11'), callback_at=at(minute=1))
        self.assertEqual(adapter.snapshot(), state)
        stress = book(mode='stress')
        submit(stress, quantity=500)
        observations = market(minutes=(0, 1, 2, 3, 4))
        stress_fees = [stress.process('ORDER1', observations, callback_at=at(minute=i)).fee for i in range(1, 6)]
        self.assertEqual(stress_fees, [D('2'), D('0'), D('0'), D('0'), D('0.5')])

    def test_cancel_request_can_race_fill_until_ack_partial_history_retained(self):
        adapter = book()
        submit(adapter)
        adapter.request_cancel('ORDER1', at(second=30))
        self.assertEqual(adapter.process('ORDER1', market(), callback_at=at(minute=1)).quantity, 100)
        adapter.acknowledge_cancel('ORDER1', at(minute=1))
        self.assertIsNone(adapter.process('ORDER1', market(), callback_at=at(minute=2)))
        state = adapter.snapshot()
        self.assertEqual(state['orders'][0]['status'], 'cancelled')
        self.assertEqual(state['orders'][0]['remaining'], 150)
        self.assertEqual(state['orders'][0]['filled_quantity'], 100)
        self.assertEqual(state['orders'][0]['fees_paid'], '1')
        self.assertEqual(state['reserved_cash'], '0')
        self.assertEqual(len(state['fills']), 1)
        adapter.request_cancel('ORDER1', at(second=30))
        adapter.acknowledge_cancel('ORDER1', at(minute=1))
        self.assertEqual(adapter.snapshot(), state)

    def test_pending_buy_reservations_and_sell_reservations_cannot_be_reused(self):
        adapter = book(cash='101', positions={SEC: 10})
        submit(adapter, identity='BUY', quantity=10, limit='10')
        with self.assertRaisesRegex(ExploratoryExecutionError, 'settled_cash'):
            submit(adapter, identity='BUY2', quantity=1, limit='10')
        submit(adapter, identity='SELL', side='sell', quantity=10, limit=None)
        with self.assertRaisesRegex(ExploratoryExecutionError, 'unreserved_position'):
            submit(adapter, identity='SELL2', side='sell', quantity=1, limit=None)
        adapter.request_cancel('SELL', at(second=1))
        with self.assertRaisesRegex(ExploratoryExecutionError, 'unreserved_position'):
            submit(adapter, identity='SELL2', side='sell', quantity=1, limit=None, when=at(second=1))
        adapter.acknowledge_cancel('SELL', at(second=2))
        submit(adapter, identity='SELL2', side='sell', quantity=1, limit=None, when=at(second=2))

    def test_t2_sale_proceeds_unspendable_until_supplied_settlement_observation(self):
        adapter = book(cash='0', positions={SEC: 50})
        submit(adapter, side='sell', quantity=50, limit=None)
        fill = adapter.process('ORDER1', market(), callback_at=at(minute=1))
        self.assertEqual(fill.settlement_on, DAYS[2])
        self.assertEqual(adapter.snapshot()['settled_cash'], '0')
        self.assertEqual(adapter.snapshot()['receivables'][0]['amount'], '498.75')
        adapter.advance_to(at(DAYS[1], 9, 30))
        self.assertEqual(adapter.snapshot()['settled_cash'], '0')
        before = adapter.snapshot()
        with self.assertRaisesRegex(ExploratoryExecutionError, 'settled_cash'):
            submit(adapter, identity='REUSE', day=DAYS[1], quantity=1, limit='10')
        self.assertEqual(adapter.snapshot(), before)
        adapter.advance_to(at(DAYS[2], 9, 30))
        self.assertEqual(adapter.snapshot()['settled_cash'], '498.75')
        self.assertTrue(adapter.snapshot()['receivables'][0]['released'])
        adapter.advance_to(at(DAYS[2], 10))
        self.assertEqual(adapter.snapshot()['settled_cash'], '498.75')

    def test_t1_cutover_and_missing_settlement_tail_refuse_without_partial_state(self):
        later = book(day=DAYS[1], positions={SEC: 10})
        submit(later, day=DAYS[1], side='sell', quantity=10, limit=None)
        fill = later.process('ORDER1', market(day=DAYS[1]), callback_at=at(DAYS[1], minute=1))
        self.assertEqual(fill.settlement_on, DAYS[2])
        short = book(settlement_days=DAYS[:2])
        submit(short, quantity=10)
        before = short.snapshot()
        with self.assertRaisesRegex(InputError, 'settlement_date_not_supplied'):
            short.process('ORDER1', market(), callback_at=at(minute=1))
        self.assertEqual(short.snapshot(), before)

    def test_tiny_sale_fee_shortfall_uses_cash_never_negative_receivable(self):
        empty = book(cash='0', positions={SEC: 1})
        submit(empty, side='sell', quantity=1, limit=None)
        before = empty.snapshot()
        with self.assertRaisesRegex(ExploratoryExecutionError, 'fee_shortfall'):
            empty.process('ORDER1', market(price='0.001'), callback_at=at(minute=1))
        self.assertEqual(empty.snapshot(), before)
        funded = book(cash='2', positions={SEC: 1})
        submit(funded, side='sell', quantity=1, limit=None)
        funded.process('ORDER1', market(price='0.001'), callback_at=at(minute=1))
        self.assertEqual(funded.snapshot()['settled_cash'], '1.0009995')
        self.assertEqual(funded.snapshot()['receivables'][0]['amount'], '0')

    def test_dividend_receivable_survives_flat_position_and_unknown_payment_date(self):
        adapter = book(cash='0')
        fields = dict(receivable_id='DIVIDEND1', security_id=SEC, kind='dividend',
            quantity=10, cash_per_share=D('0.5'), entitlement_date=DAYS[0],
            payment_on=None, known_at=at(DAYS[0], 9), observed_at=at(), source_sha256=SOURCE)
        adapter.register_cash_entitlement(**fields)
        adapter.advance_to(at(DAYS[3], 16))
        state = adapter.snapshot()
        self.assertEqual(state['positions'], {})
        self.assertEqual(state['settled_cash'], '0')
        self.assertEqual(state['receivables'][0]['amount'], '5')
        self.assertEqual(state['unknown_payment_date_receivables'], 1)
        self.assertEqual(state['unresolved_receivables'], 1)
        adapter.register_cash_entitlement(**fields)
        self.assertEqual(adapter.snapshot(), state)
        with self.assertRaisesRegex(ExploratoryExecutionError, 'conflicting_cash_entitlement_replay'):
            adapter.register_cash_entitlement(**(fields | {'payment_on': DAYS[3]}))
        self.assertEqual(adapter.snapshot(), state)

    def test_explicit_dividend_payment_not_ex_date_and_no_preknowledge_credit(self):
        adapter = book(cash='0')
        fields = dict(receivable_id='DIVIDEND1', security_id=SEC, kind='dividend',
            quantity=10, cash_per_share=D('0.5'), entitlement_date=DAYS[0],
            payment_on=DAYS[2], known_at=at(DAYS[0], 9), observed_at=at(), source_sha256=SOURCE)
        adapter.register_cash_entitlement(**fields)
        adapter.advance_to(at(DAYS[1], 16))
        self.assertEqual(adapter.snapshot()['settled_cash'], '0')
        adapter.advance_to(at(DAYS[2], 9, 30))
        self.assertEqual(adapter.snapshot()['settled_cash'], '5')
        before = adapter.snapshot()
        with self.assertRaisesRegex(ExploratoryExecutionError, 'known_clock_mismatch'):
            adapter.register_cash_entitlement(**(fields | {'receivable_id': 'FUTURE',
                'observed_at': at(DAYS[2], 10), 'known_at': at(DAYS[3], 10)}))
        self.assertEqual(adapter.snapshot(), before)

    def test_fill_and_external_cash_reference_namespace_cannot_alias_in_either_order(self):
        for side in ('buy', 'sell'):
            with self.subTest(direction='external_before_fill', side=side):
                adapter = book(positions={SEC: 10} if side == 'sell' else None)
                identity = 'BUY1' if side == 'buy' else 'SELL1'
                fields = dict(receivable_id=identity + '_F10', security_id=SEC, kind='dividend',
                    quantity=10, cash_per_share=D('0.5'), entitlement_date=DAYS[0], payment_on=None,
                    known_at=at(DAYS[0], 9), observed_at=at(), source_sha256=SOURCE)
                adapter.register_cash_entitlement(**fields)
                submit(adapter, identity=identity, side=side, quantity=10,
                       limit='11' if side == 'buy' else None)
                before = adapter.snapshot()
                with self.assertRaisesRegex(ExploratoryExecutionError, 'identity_already_used'):
                    adapter.process(identity, market(), callback_at=at(minute=1))
                self.assertEqual(adapter.snapshot(), before)
                # A failed transition must not leave callback/minute replay
                # markers or consume invisible participation capacity.
                with self.assertRaisesRegex(ExploratoryExecutionError, 'identity_already_used'):
                    adapter.process(identity, market(), callback_at=at(minute=1))
                self.assertEqual(adapter.snapshot(), before)
                adapter.request_cancel(identity, at())
                adapter.acknowledge_cancel(identity, at())
                submit(adapter, identity='ALTERNATE', side=side, quantity=10,
                       limit='11' if side == 'buy' else None)
                self.assertEqual(adapter.process('ALTERNATE', market(), callback_at=at(minute=1)).quantity, 10)
            with self.subTest(direction='fill_before_external', side=side):
                adapter = book(positions={SEC: 10} if side == 'sell' else None)
                submit(adapter, identity=identity, side=side, quantity=10,
                       limit='11' if side == 'buy' else None)
                fill = adapter.process(identity, market(), callback_at=at(minute=1))
                before = adapter.snapshot()
                with self.assertRaisesRegex(ExploratoryExecutionError, 'identity_already_used'):
                    adapter.register_cash_entitlement(**(fields | {'receivable_id': fill.fill_id,
                        'observed_at': at(minute=1)}))
                self.assertEqual(adapter.snapshot(), before)

    def test_market_open_settlement_holiday_uses_contract_service_dates_not_NYSE_dates(self):
        days = (date(2025, 11, 10), date(2025, 11, 11), date(2025, 11, 12))
        trading = calendar(days)
        contract = default_contract((days[0], days[2]), calendar_source_sha256=SOURCE)
        for trade_day in days[:2]:
            with self.subTest(trade_day=trade_day):
                adapter = LocalExecutionAdapter(calendar=trading, contract=contract,
                    settled_cash=D('0'), at=at(trade_day, 9, 30), positions={SEC: 10})
                submit(adapter, day=trade_day, side='sell', quantity=10, limit=None)
                fill = adapter.process('ORDER1', market(day=trade_day, calendar_input=trading),
                                       callback_at=at(trade_day, minute=1))
                self.assertEqual(fill.settlement_on, days[2])
                if trade_day == days[0]:
                    adapter.advance_to(at(days[1], 9, 30))
                    self.assertEqual(adapter.snapshot()['settled_cash'], '0')
                adapter.advance_to(at(days[2], 9, 30))
                self.assertEqual(adapter.snapshot()['settled_cash'], '98.95')

    def test_sell_after_entry_cutoff_and_absent_future_quotes_remain_unresolved(self):
        adapter = book(positions={SEC: 200})
        submit(adapter, side='sell', quantity=200, limit=None)
        observed = market(minutes=(5,))
        fill = adapter.process('ORDER1', observed, callback_at=at(minute=6))
        self.assertEqual(fill.quantity, 100)
        state = adapter.snapshot()
        self.assertEqual(state['orders'][0]['status'], 'open')
        self.assertEqual(state['positions'][SEC], 100)
        self.assertEqual(state['open_order_ids'], ['ORDER1'])
        with self.assertRaises(InputError):
            adapter.process('ORDER1', observed, callback_at=at(minute=7))
        self.assertEqual(adapter.snapshot(), state)

    def test_future_or_changed_ADV_clock_and_invalid_amounts_refuse(self):
        adapter = book()
        with self.assertRaises(InputError):
            adapter.submit(order_id='BAD', security_id=SEC, symbol='INVENTED', side='buy',
                quantity=10, submitted_at=at(), liquidity=liquidity(known=at(minute=1)), limit=D('11'))
        submit(adapter, identity='A', quantity=10)
        with self.assertRaisesRegex(ExploratoryExecutionError, 'daily_liquidity_reference_changed'):
            submit(adapter, identity='B', quantity=10, adv='20000000')
        for value in (True, 1.5, -1):
            with self.subTest(value=value), self.assertRaises(InputError):
                submit(adapter, identity='INVALID', quantity=value)
        with self.assertRaises(InputError):
            LocalExecutionAdapter(calendar=calendar(), contract=default_contract(DAYS, calendar_source_sha256=SOURCE),
                settled_cash=10000.0, at=at())

    def test_latest_bad_quote_identity_and_market_role_never_fall_back(self):
        adapter = book()
        submit(adapter, quantity=10)
        quotes = [{'t': stamp(at(second=30)), 'bx': 'N', 'bp': '10', 'bs': 100,
                   'ap': '10', 'as': 100, 'ax': 'N', 'c': ['R'], 'z': 'A'},
                  {'t': stamp(at(second=59)), 'bx': 'N', 'bp': '11', 'bs': 100,
                   'ap': '10', 'as': 100, 'ax': 'N', 'c': ['R'], 'z': 'A'}]
        before = adapter.snapshot()
        with self.assertRaises(InputError):
            adapter.process('ORDER1', market(quotes=quotes), callback_at=at(minute=1))
        self.assertEqual(adapter.snapshot(), before)
        with self.assertRaisesRegex(ExploratoryExecutionError, 'identity_mismatch'):
            adapter.process('ORDER1', market(security='OTHER'), callback_at=at(minute=1))
        with self.assertRaisesRegex(ExploratoryExecutionError, 'sleeve_role_mismatch'):
            adapter.process('ORDER1', market(security='SPY-SEC', symbol='SPY', role='benchmark'), callback_at=at(minute=1))
        self.assertEqual(adapter.snapshot(), before)

    def test_unknown_condition_assumption_retained_and_gates_never_promoted(self):
        adapter = book()
        submit(adapter, quantity=10)
        fill = adapter.process('ORDER1', market(conditions=('?',), allow_unknown=True), callback_at=at(minute=1))
        self.assertTrue(fill.unknown_quote_condition_assumed)
        self.assertEqual(fill.condition_assumption_sha256, 'b' * 64)
        self.assertEqual(len(fill.quote_source_sha256), 64)
        for name in ('source_execution_qualified', 'point_in_time_data', 'native_execution_verified',
                     'complete_strategy_runner', 'matched_SPY_parity_verified', 'outcomes_evaluated',
                     'backtest_ready', 'qc_access_allowed', 'broker_orders_allowed'):
            self.assertIs(adapter.snapshot()[name], False)

    def test_decimal_context_cannot_round_share_cap_price_fee_or_cash(self):
        expected = book()
        submit(expected, quantity=250)
        expected.process('ORDER1', market(), callback_at=at(minute=1))
        with localcontext() as context:
            context.prec = 3
            actual = book()
            submit(actual, quantity=250)
            actual.process('ORDER1', market(), callback_at=at(minute=1))
        self.assertEqual(actual.snapshot(), expected.snapshot())

    def test_matched_SPY_uses_independent_fills_budget_and_visible_residual(self):
        strategy = book()
        submit(strategy, quantity=100)
        source = strategy.process('ORDER1', market(), callback_at=at(minute=1))
        matched = MatchedSpyBudgetLedger()
        matched.register_strategy_buy(source)
        self.assertEqual(matched.snapshot()['entries'][0]['status'], 'unmatched')
        benchmark = book(sleeve='benchmark')
        submit(benchmark, identity='SPYBUY', security='SPY-SEC', symbol='SPY', quantity=100,
               limit='6', when=at(minute=1))
        spy = benchmark.process('SPYBUY', market(security='SPY-SEC', symbol='SPY', role='benchmark', price='5'), callback_at=at(minute=2))
        matched.record_spy_buy(source.fill_id, spy)
        state = matched.snapshot()
        self.assertEqual(state['entries'][0]['budget'], '1001.5')
        self.assertEqual(state['entries'][0]['spent'], '501.25')
        self.assertEqual(state['entries'][0]['residual_cash_budget'], '500.25')
        self.assertFalse(state['matched_SPY_parity_verified'])
        self.assertFalse(state['matched_exit_schedule_implemented'])
        matched.register_strategy_buy(source)
        matched.record_spy_buy(source.fill_id, spy)
        self.assertEqual(matched.snapshot(), state)
        overspend = replace(spy, fill_id='OVERSPEND', quantity=300, notional=spy.price * 300)
        with self.assertRaisesRegex(ExploratoryExecutionError, 'exceeds_source_cash_budget'):
            matched.record_spy_buy(source.fill_id, overspend)
        self.assertEqual(matched.snapshot(), state)
        later_source = replace(source, fill_id='LATER_SOURCE', at=spy.at)
        matched.register_strategy_buy(later_source)
        with self.assertRaisesRegex(ExploratoryExecutionError, 'must_follow_source_fill'):
            matched.record_spy_buy(later_source.fill_id, replace(spy, fill_id='SAME_CLOCK_SPY'))


if __name__ == '__main__':
    unittest.main()
