"""Focused, synthetic-only incremental order/accounting fixtures."""
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, Inexact, ROUND_DOWN, Rounded, localcontext
import unittest
from zoneinfo import ZoneInfo

from data.financial_primitives import exact_decimal_add as add, exact_decimal_multiply as mul, exact_decimal_subtract as sub
from research.guidance_revision_drift.simulation import (
    Minute, Quote, Session, Simulation, SimulationError,
    commission_total, execution_price,
)

D = Decimal
NY = ZoneInfo("America/New_York")
ADV = D("20000000")


def timestamp(day, hour=10, minute=0, second=0):
    return datetime.combine(day, time(hour, minute, second), NY).astimezone(timezone.utc)


def fixture_sessions(count=30):
    days = []
    day = date(2020, 3, 2)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(Session(day, timestamp(day, 9, 30), timestamp(day, 16)))
        day += timedelta(days=1)
    return tuple(days)


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.sessions = fixture_sessions()
        self.sim = Simulation(self.sessions)

    def at(self, session=0, hour=10, minute=0, second=0):
        return timestamp(self.sessions[session].day, hour, minute, second)

    def entry(self, sim=None, issuer="SYN-A", event="SYN-E1", sector="technology", session=0, ask="100", bid="99.9", adv=ADV):
        sim = self.sim if sim is None else sim
        return sim.submit_entry(event, issuer, sector, self.at(session), Quote(self.at(session, 9, 59), D(bid), D(ask)), adv)

    def minute(self, session=0, minute=1, issuer="SYN-A", bid="99.9", ask="100", volume=1000000, adv=ADV, settle_offset=1):
        return Minute(issuer, self.at(session, 10, minute), D(bid), D(ask), volume, adv, self.sessions[session + settle_offset].day)

    def held(self, ask="100", bid="99.9"):
        order = self.entry(ask=ask, bid=bid)
        fill = self.sim.process_minute(self.minute(ask=ask, bid=bid))[0]
        self.assertEqual(fill.quantity, order.quantity)
        return order, fill

    def assert_atomic(self, operation):
        before = self.sim.snapshot()
        with self.assertRaises((SimulationError, ValueError)):
            operation()
        self.assertEqual(self.sim.snapshot(), before)

    def test_entry_limit_reserved_cash_and_next_data_only(self):
        order = self.entry()
        self.assertEqual(order.quantity, 49)
        self.assertEqual(order.limit, D("101"))
        self.assertEqual(order.reserved_notional, D("4949"))
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "4950")
        same = replace(self.minute(), at=self.at())
        self.assertEqual(self.sim.process_minute(same), ())
        fills = self.sim.process_minute(self.minute())
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].price, D("100.0500"))
        self.assertEqual(fills[0].fee, D("1"))
        self.assertEqual(self.sim.snapshot()["settled_cash"], "95096.55")
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "0")

    def test_quote_cutoffs_spread_and_one_refused_attempt(self):
        at = self.at()
        bad = Quote(at - timedelta(seconds=61), D("99.9"), D("100"))
        self.assertIsNone(self.sim.submit_entry("SYN-E1", "SYN-A", "tech", at, bad, ADV))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "stale_or_future_quote")
        self.assertIsNone(self.sim.submit_entry("SYN-E1", "SYN-A", "tech", at, bad, ADV))
        self.assert_atomic(lambda: self.entry())
        second = Simulation(self.sessions)
        self.assertIsNone(self.entry(second, bid="99", ask="100"))
        third = Simulation(self.sessions)
        # 2*(ask-bid) == .005*(ask+bid): exact 50bp full-spread edge.
        self.assertIsNotNone(self.entry(third, bid="99.75", ask="100.25"))

    def test_missing_quote_is_a_recorded_expired_attempt(self):
        self.assertIsNone(self.sim.submit_entry("SYN-E1", "SYN-A", "technology", self.at(), None, ADV))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "missing_quote")
        self.assert_atomic(lambda: self.entry())

    def test_invalid_type_and_forged_frozen_record_are_atomic(self):
        for bad in (D("NaN"), D("Infinity"), D("-1"), 1.0, True, D("1e100")):
            self.assert_atomic(lambda bad=bad: self.entry(adv=bad))
        quote = Quote(self.at(0, 9, 59), D("99.9"), D("100"))
        object.__setattr__(quote, "ask", D("NaN"))
        self.assert_atomic(lambda: self.sim.submit_entry("SYN-E1", "SYN-A", "tech", self.at(), quote, ADV))
        self.assert_atomic(lambda: self.sim.submit_entry("REAL-E", "AAPL", "tech", self.at(), Quote(self.at(), D("1"), D("1")), ADV))
        self.assert_atomic(lambda: self.entry(session=0, adv=D("0")))

    def test_calendar_is_explicit_detached_and_early_close_supported(self):
        s = self.sessions[0]
        with self.assertRaises(SimulationError):
            Simulation(list(self.sessions))
        with self.assertRaises(SimulationError):
            Simulation(tuple(reversed(self.sessions)))
        with self.assertRaises(SimulationError):
            Simulation(self.sessions, initial_cash=D("100"))
        object.__setattr__(s, "day", date(2000, 1, 1))
        self.assertIsNotNone(self.sim.submit_entry("SYN-E", "SYN-A", "tech", timestamp(date(2020, 3, 2)), Quote(timestamp(date(2020, 3, 2), 9, 59), D("100"), D("100")), ADV))
        early = fixture_sessions(3)
        early = (replace(early[0], closes_at=timestamp(early[0].day, 13)), *early[1:])
        engine = Simulation(early)
        with self.assertRaises(SimulationError):
            engine.process_minute(Minute("SYN-A", timestamp(early[0].day, 13, 1), D("100"), D("100"), 100, ADV, early[1].day))

    def test_mutated_returned_order_fill_snapshot_do_not_change_state(self):
        order = self.entry()
        object.__setattr__(order, "quantity", 99999)
        self.assertEqual(self.sim.orders[0].quantity, 49)
        fill = self.sim.process_minute(self.minute())[0]
        object.__setattr__(fill, "fee", D("0"))
        self.assertEqual(self.sim.fills[0].fee, D("1"))
        state = self.sim.snapshot()
        state["positions"][0]["quantity"] = 999
        self.assertEqual(self.sim.positions[0].quantity, 49)

    def test_pending_sector_and_gross_budgets(self):
        for n in range(3):
            self.assertIsNotNone(self.entry(issuer=f"SYN-A{n}", event=f"SYN-E{n}"))
        # 3*4949 reserves leaves153 of sector headroom: one share, not49.
        tiny = self.entry(issuer="SYN-A3", event="SYN-E3")
        self.assertEqual(tiny.quantity, 1)
        self.assertIsNone(self.entry(issuer="SYN-A4", event="SYN-E4"))
        engine = Simulation(self.sessions)
        for n in range(10):
            self.assertIsNotNone(self.entry(engine, issuer=f"SYN-A{n}", event=f"SYN-E{n}", sector=f"sector{n}"))
        last = self.entry(engine, issuer="SYN-A10", event="SYN-E10", sector="new")
        self.assertEqual(last.quantity, 5)
        self.assertIsNone(self.entry(engine, issuer="SYN-A11", event="SYN-E11", sector="newer"))
        self.assertLessEqual(D(engine.snapshot()["reserved_cash"]), D("100000"))

    def test_duplicate_issuer_and_event_do_not_pyramid(self):
        first = self.entry()
        self.assertEqual(self.entry(), first)
        self.assertEqual(len(self.sim.orders), 1)
        self.assertIsNone(self.entry(event="SYN-E2"))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "issuer_already_active")
        self.assert_atomic(lambda: self.entry(issuer="SYN-B"))

    def test_minute_volume_and_pinned_adv_replay(self):
        self.entry()
        minute = self.minute(volume=1000)
        self.assertEqual(self.sim.process_minute(minute)[0].quantity, 10)
        self.assertEqual(self.sim.process_minute(minute), ())
        self.assert_atomic(lambda: self.sim.process_minute(replace(minute, volume=2000)))
        self.assert_atomic(lambda: self.sim.process_minute(self.minute(minute=2, adv=D("9999999999"))))
        self.assertEqual(self.sim.positions[0].quantity, 10)
        self.assertEqual(self.sim.process_minute(self.minute(minute=2, volume=99)), ())

    def test_limit_price_protection_and_stress_prices(self):
        self.entry()
        self.assertEqual(self.sim.process_minute(self.minute(ask="101", bid="100.9")), ())
        self.assertEqual(execution_price("buy", D("100"), D("100"), "stress"), D("100.15"))
        self.assertEqual(execution_price("sell", D("100"), D("100"), "stress"), D("99.85"))
        self.assertEqual(commission_total(1, "stress"), D("2"))

    def test_partial_fills_commission_minimum_charged_once(self):
        order = self.entry(ask="10", bid="9.99")
        self.assertEqual(order.quantity, 495)
        one = self.sim.process_minute(self.minute(ask="10", bid="9.99", volume=100))[0]
        two = self.sim.process_minute(self.minute(minute=2, ask="10", bid="9.99", volume=20000))[0]
        self.assertEqual(one.fee, D("1"))
        self.assertEqual(two.quantity, 200)
        self.assertEqual(two.fee, D("0.005"))
        rest = self.sim.process_minute(self.minute(minute=3, ask="10", bid="9.99"))[0]
        self.assertEqual(add(add(one.fee, two.fee), rest.fee), D("2.475"))
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "0")

    def test_cancel_request_racing_fill_and_ack_release_once(self):
        order = self.entry()
        self.sim.process_minute(self.minute(volume=1000))
        before = D(self.sim.snapshot()["reserved_cash"])
        self.sim.cancel_entry_remainders(self.at(0, 10, 5))
        self.assertEqual(D(self.sim.snapshot()["reserved_cash"]), before)
        racing = self.sim.process_minute(self.minute(minute=6, volume=500))[0]
        self.assertEqual(racing.quantity, 5)
        acknowledged = self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 7))
        self.assertEqual(acknowledged.status, "cancelled")
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "0")
        before = self.sim.snapshot()
        self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 7))
        self.assertEqual(self.sim.snapshot(), before)
        self.assertEqual(self.sim.process_minute(self.minute(minute=8)), ())
        self.assertEqual(self.sim.positions[0].quantity, 15)

    def test_full_racing_fill_followed_by_cancel_ack(self):
        order = self.entry()
        self.sim.request_cancel(order.order_id, self.at(0, 10, 1))
        self.sim.process_minute(self.minute(minute=2))
        self.assertEqual(self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 3)).status, "filled")
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "0")
        self.sim.request_cancel(order.order_id, self.at(0, 10, 1))

    def test_unrequested_ack_and_out_of_order_changes_are_atomic(self):
        order = self.entry()
        self.assert_atomic(lambda: self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 1)))
        self.sim.process_minute(self.minute())
        self.assert_atomic(lambda: self.sim.advance(self.at()))
        self.assert_atomic(lambda: self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 2)))
        malformed = replace(self.minute(minute=2), settlement_session=self.sessions[0].day - timedelta(days=1))
        self.assert_atomic(lambda: self.sim.process_minute(malformed))

    def test_stop_schedules_next_session_exit_and_gap_loss_is_visible(self):
        order, entry = self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("90")})
        due = self.sim.snapshot()["scheduled_exits"]["SYN-A"]
        self.assertEqual(due["reason"], "position_stop")
        self.assertEqual(due["session"], self.sessions[1].day.isoformat())
        exits = self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})
        self.assertEqual(exits[0].quantity, order.quantity)
        exit_fill = self.sim.process_minute(self.minute(session=1, bid="70", ask="70.1"))[0]
        self.assertEqual(exit_fill.price, D("69.9650"))
        self.assertLess(exit_fill.price, mul(entry.price, D(".9")))
        self.assertEqual(self.sim.positions, ())

    def test_sale_net_receivable_not_settled_cash_and_exact_nav(self):
        order, entry = self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        cash = D(self.sim.snapshot()["settled_cash"])
        self.sim.request_exit("SYN-A", self.at(1), "guidance_invalidation", ADV)
        sale = self.sim.process_minute(self.minute(session=1))[0]
        expected = sub(mul(D(order.quantity), sale.price), sale.fee)
        self.assertEqual(D(self.sim.snapshot()["settled_cash"]), cash)
        self.assertEqual(D(self.sim.snapshot()["receivables"][0]["amount"]), expected)
        nav = self.sim.close_session(self.sessions[1].day, {})["nav"]
        self.assertEqual(nav, add(cash, expected))
        self.sim.advance(self.sessions[2].opens_at)
        self.assertEqual(self.sim.snapshot()["receivables"], [])
        self.assertEqual(D(self.sim.snapshot()["settled_cash"]), nav)

    def test_unsettled_proceeds_cannot_fund_renewed_full_size_entry(self):
        issuers = [f"SYN-A{n}" for n in range(10)]
        for cycle in range(2):
            entry_session, exit_session = cycle * 2, cycle * 2 + 1
            for n, issuer in enumerate(issuers):
                self.entry(issuer=issuer, event=f"SYN-E-{cycle}-{n}", sector=f"sector{n}", session=entry_session)
            for issuer in issuers:
                self.sim.process_minute(self.minute(session=entry_session, issuer=issuer))
            self.sim.close_session(self.sessions[entry_session].day, {i: D("100") for i in issuers})
            for issuer in issuers:
                self.sim.request_exit(issuer, self.at(exit_session), "guidance_invalidation", ADV)
            for issuer in issuers:
                self.sim.process_minute(self.minute(session=exit_session, issuer=issuer, settle_offset=20))
            self.sim.close_session(self.sessions[exit_session].day, {})
        available = D(self.sim.snapshot()["available_cash"])
        self.assertGreater(sum(D(r["amount"]) for r in self.sim.snapshot()["receivables"]), D("90000"))
        self.assertLess(available, D("2000"))
        new = self.entry(issuer="SYN-NEW", event="SYN-NEW-E", sector="new", session=4)
        self.assertLess(new.quantity, 49)
        self.assertLessEqual(add(new.reserved_notional, new.reserved_fee), available)

    def test_partial_exit_keeps_position_and_order_fee_once(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("90")})
        self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})
        first = self.sim.process_minute(self.minute(session=1, volume=1000))[0]
        second = self.sim.process_minute(self.minute(session=1, minute=2, volume=1000))[0]
        self.assertEqual(first.quantity, 10)
        self.assertEqual(second.fee, D("0"))
        self.assertEqual(self.sim.positions[0].quantity, 29)
        self.assertEqual(self.sim.snapshot()["scheduled_exits"]["SYN-A"]["quantity"], 29)

    def test_daily_dollar_participation_caps_exit_after_price_gap(self):
        self.held(ask="10", bid="9.99")
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("10")})
        self.sim.request_exit("SYN-A", self.at(1), "guidance_invalidation", ADV)
        first = self.sim.process_minute(self.minute(session=1, bid="1000", ask="1000"))[0]
        self.assertEqual(first.quantity, 20)
        self.assertEqual(self.sim.process_minute(self.minute(session=1, minute=2, bid="1000", ask="1000")), ())
        self.sim.close_session(self.sessions[1].day, {"SYN-A": D("1000")})
        self.sim.execute_due_exits(self.at(2), {"SYN-A": ADV})
        self.assertEqual(self.sim.process_minute(replace(self.minute(session=2, bid="1000", ask="1000"), at=self.at(2))), ())
        self.assertTrue(self.sim.process_minute(self.minute(session=2, bid="1000", ask="1000")))

    def test_missing_marks_block_entries_but_not_risk_reduction(self):
        self.held()
        record = self.sim.close_session(self.sessions[0].day, {})
        self.assertIsNone(record["nav"])
        self.assertEqual(record["missing_marks"], ("SYN-A",))
        self.assertIsNone(self.entry(issuer="SYN-B", event="SYN-E2", session=1))
        self.sim.request_exit("SYN-A", self.at(1), "guidance_invalidation", ADV)
        self.assertTrue(self.sim.process_minute(self.minute(session=1)))

    def test_held_portfolio_requires_fresh_current_quotes_for_nav_sizing(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        self.assertIsNone(self.entry(issuer="SYN-B", event="SYN-E2", session=1))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "missing_current_portfolio_quotes")
        at = self.at(1)
        stale = Quote(self.at(1, 9, 58), D("100"), D("100"))
        fresh = Quote(self.at(1, 9, 59), D("100"), D("100"))
        self.assertIsNone(self.sim.submit_entry("SYN-E3", "SYN-C", "energy", at, fresh, ADV, valuation_quotes={"SYN-A": stale}))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "stale_current_portfolio_quote")
        # Existing holding's drop changes current NAV and reduces the new
        # position target below USD5000, even with a valid prior-session mark.
        current = Quote(self.at(1, 9, 59), D("50"), D("50"))
        order = self.sim.submit_entry("SYN-E4", "SYN-D", "energy", at, fresh, ADV, valuation_quotes={"SYN-A": current})
        self.assertEqual(order.quantity, 48)

    def test_time_exit_is_session21_not20(self):
        self.held()
        for index in range(19):
            self.sim.close_session(self.sessions[index].day, {"SYN-A": D("100")})
        self.assertNotIn("SYN-A", self.sim.snapshot()["scheduled_exits"])
        self.sim.close_session(self.sessions[19].day, {"SYN-A": D("100")})
        due = self.sim.snapshot()["scheduled_exits"]["SYN-A"]
        self.assertEqual(due["reason"], "time")
        self.assertEqual(due["session"], self.sessions[20].day.isoformat())

    def test_program_drawdown_disables_entries_without_ending_observation(self):
        issuers = [f"SYN-A{n}" for n in range(10)]
        for n, issuer in enumerate(issuers):
            self.entry(issuer=issuer, event=f"SYN-E{n}", sector=f"sector{n}")
        for issuer in issuers:
            self.sim.process_minute(self.minute(issuer=issuer))
        self.sim.close_session(self.sessions[0].day, {i: D("50") for i in issuers})
        self.assertTrue(self.sim.snapshot()["stopped"])
        self.assertEqual({v["reason"] for v in self.sim.snapshot()["scheduled_exits"].values()}, {"program_drawdown"})
        self.assertIsNone(self.entry(issuer="SYN-N", event="SYN-NEW", session=1))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "program_stopped")
        self.sim.close_session(self.sessions[1].day, {i: D("100") for i in issuers})
        self.assertTrue(self.sim.snapshot()["stopped"])
        self.assertEqual(len(self.sim.snapshot()["navs"]), 2)

    def test_trims_finish_without_repeated_sales_and_exit_precedence(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("200")})
        due = self.sim.snapshot()["scheduled_exits"]["SYN-A"]
        self.assertEqual(due["reason"], "trim")
        self.assertIsNone(self.entry(issuer="SYN-B", event="SYN-E2", session=1))
        orders = self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})
        self.sim.process_minute(self.minute(session=1, bid="200", ask="200.1"))
        self.assertNotIn("SYN-A", self.sim.snapshot()["scheduled_exits"])
        self.assertEqual(self.sim.positions[0].quantity, 49 - orders[0].quantity)
        self.assertEqual(self.sim.execute_due_exits(self.at(1, 10, 1), {"SYN-A": ADV}), ())

    def test_partial_trim_upgrades_to_full_stop_without_stale_quantity_cap(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("200")})
        trim = self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})[0]
        self.assertEqual(trim.quantity, 23)
        self.sim.process_minute(self.minute(session=1, bid="200", ask="200.1", volume=100))
        self.assertEqual(self.sim.positions[0].quantity, 48)
        self.sim.close_session(self.sessions[1].day, {"SYN-A": D("80")})
        stop = self.sim.execute_due_exits(self.at(2), {"SYN-A": ADV})[0]
        self.assertEqual(stop.order_id, trim.order_id)
        self.assertEqual(stop.remaining, 48)
        self.assertEqual(stop.quantity, 49)
        self.assertEqual(stop.filled_quantity, 1)
        self.assertEqual(stop.fees_paid, D("1"))
        self.assertEqual(stop.exit_reason, "position_stop")
        self.assertEqual(self.sim.process_minute(replace(self.minute(session=2, bid="80", ask="80.1"), at=self.at(2))), ())
        sale = self.sim.process_minute(self.minute(session=2, bid="80", ask="80.1"))[0]
        self.assertEqual(sale.quantity, 48)
        self.assertEqual(sale.fee, D("0"))
        self.assertEqual(self.sim.positions, ())
        amendment = self.sim.snapshot()["order_amendments"][0]
        self.assertEqual(amendment["previous_remaining"], 22)
        self.assertEqual(amendment["remaining"], 48)
        self.assertEqual(amendment["previous_reason"], "trim")

    def test_cancel_pending_trim_upgrade_requires_explicit_acknowledgment(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("200")})
        trim = self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})[0]
        self.sim.process_minute(self.minute(session=1, bid="200", ask="200.1", volume=100))
        self.sim.request_cancel(trim.order_id, self.at(1, 10, 2))
        self.sim.close_session(self.sessions[1].day, {"SYN-A": D("80")})
        self.assertEqual(self.sim.execute_due_exits(self.at(2), {"SYN-A": ADV}), ())
        self.assertEqual(self.sim.snapshot()["order_amendments"], [])
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "reconcile_cancelled_exit_before_amendment")
        self.sim.acknowledge_cancel(trim.order_id, self.at(2))
        replacement = self.sim.execute_due_exits(self.at(2), {"SYN-A": ADV})[0]
        self.assertNotEqual(replacement.order_id, trim.order_id)
        self.assertEqual(replacement.remaining, 48)

    def test_invalidation_cancels_pending_and_reconciles_racing_fill(self):
        order = self.entry()
        self.sim.schedule_invalidation("SYN-A", self.sessions[1].day, self.at(0, 10, 1))
        racing = self.sim.process_minute(self.minute(minute=2, volume=500))[0]
        self.assertEqual(racing.quantity, 5)
        self.assertEqual(self.sim.snapshot()["scheduled_exits"]["SYN-A"]["quantity"], 5)
        self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 3))
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        self.assertTrue(self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV}))

    def test_invalidation_after_cutoff_and_pending_entry_exit_refuse(self):
        self.held()
        self.assert_atomic(lambda: self.sim.schedule_invalidation("SYN-A", self.sessions[1].day, self.at(0, 19)))
        engine = Simulation(self.sessions)
        self.entry(engine)
        engine.process_minute(self.minute(volume=500))
        engine.close_session(self.sessions[0].day, {"SYN-A": D("90")})
        self.assertEqual(engine.execute_due_exits(self.at(1), {"SYN-A": ADV}), ())
        self.assertEqual(engine.snapshot()["refusals"][-1]["reason"], "reconcile_racing_entry_before_exit")

    def test_invalidated_cancelled_attempt_does_not_invalidate_later_new_event(self):
        order = self.entry()
        self.sim.schedule_invalidation("SYN-A", self.sessions[1].day, self.at(0, 10, 1))
        self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 2))
        self.sim.close_session(self.sessions[0].day, {})
        self.assertIsNotNone(self.entry(session=1, event="SYN-NEW-E"))
        self.sim.process_minute(self.minute(session=1))
        self.assertEqual(self.sim.snapshot()["scheduled_exits"], {})

    def test_split_dividend_no_double_count_and_action_replay(self):
        order, fill = self.held()
        nav_before = self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})["nav"]
        at = self.sessions[1].opens_at
        self.sim.apply_split("SYN-SPLIT", "SYN-A", D("2"), at)
        self.assertEqual(self.sim.positions[0].quantity, order.quantity * 2)
        self.assertEqual(self.sim.positions[0].entry_notional, mul(fill.price, D(order.quantity)))
        self.sim.credit_dividend("SYN-DIV", "SYN-A", D("1"), at, self.sessions[3].day)
        self.sim.credit_dividend("SYN-DIV", "SYN-A", D("1"), at, self.sessions[3].day)
        nav = self.sim.close_session(self.sessions[1].day, {"SYN-A": D("49")})["nav"]
        self.assertEqual(nav, nav_before)
        self.assertEqual(len(self.sim.snapshot()["receivables"]), 1)
        self.sim.apply_split("SYN-SPLIT", "SYN-A", D("2"), at)
        self.assertEqual(self.sim.positions[0].quantity, 98)

    def test_fractional_split_rejected_atomically(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        self.assert_atomic(lambda: self.sim.apply_split("SYN-SPLIT", "SYN-A", D(".5"), self.sessions[1].opens_at))

    def test_due_exit_batch_rolls_back_prior_valid_mutation_on_later_bad_input(self):
        for n in range(2):
            self.entry(issuer=f"SYN-A{n}", event=f"SYN-E{n}", sector=f"sector{n}")
        for n in range(2):
            self.sim.process_minute(self.minute(issuer=f"SYN-A{n}"))
        self.sim.close_session(self.sessions[0].day, {"SYN-A0": D("90"), "SYN-A1": D("90")})
        # A bad second mapping value must not settle cash, move the clock, or
        # leave the first issuer with a newly created exit.
        self.assert_atomic(lambda: self.sim.execute_due_exits(self.at(1), {"SYN-A0": ADV, "SYN-A1": D("NaN")}))

    def test_split_adjusted_stop_and_missing_exit_liquidity_are_visible(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        self.sim.apply_split("SYN-SPLIT", "SYN-A", D("2"), self.sessions[1].opens_at)
        self.sim.close_session(self.sessions[1].day, {"SYN-A": D("50")})
        self.assertEqual(self.sim.snapshot()["scheduled_exits"], {})
        self.sim.close_session(self.sessions[2].day, {"SYN-A": D("45")})
        self.assertEqual(self.sim.snapshot()["scheduled_exits"]["SYN-A"]["reason"], "position_stop")
        self.assertEqual(self.sim.execute_due_exits(self.at(3), {}), ())
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "missing_exit_liquidity")

    def test_unresolved_terminal_action_keeps_position_no_invented_sale(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        self.sim.terminal_settlement("SYN-TERM", "SYN-A", self.sessions[1].opens_at, None, None)
        self.assertTrue(self.sim.snapshot()["completion_blocked"])
        self.sim.request_exit("SYN-A", self.at(1), "guidance_invalidation", ADV)
        self.assertEqual(self.sim.process_minute(self.minute(session=1)), ())
        self.assertEqual(self.sim.positions[0].quantity, 49)
        self.assertIsNone(self.sim.close_session(self.sessions[1].day, {"SYN-A": D("100")})["nav"])
        self.sim.terminal_settlement("SYN-RESOLVED", "SYN-A", self.sessions[2].opens_at, D("1000"), self.sessions[3].day)
        self.assertEqual(self.sim.positions, ())
        self.assertEqual(self.sim.snapshot()["unresolved"], {})

    def test_terminal_cancels_unfilled_entry_and_prevents_reopening_identity(self):
        order = self.entry()
        self.sim.terminal_settlement("SYN-TERMINAL", "SYN-A", self.at(0, 10, 1), None, None)
        self.assertEqual(self.sim.orders[0].status, "cancelled")
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "0")
        self.assertEqual(self.sim.process_minute(self.minute(minute=2)), ())
        self.sim.close_session(self.sessions[0].day, {})
        self.assertIsNone(self.entry(event="SYN-E2", session=1))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "issuer_terminated")

    def test_zero_terminal_payment_retains_loss(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        cash = D(self.sim.snapshot()["settled_cash"])
        self.sim.terminal_settlement("SYN-ZERO", "SYN-A", self.sessions[1].opens_at, D("0"), self.sessions[2].day)
        self.assertEqual(self.sim.close_session(self.sessions[1].day, {})["nav"], cash)

    def test_cash_journal_reconciles_paid_corporate_actions_and_fills(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        self.sim.credit_dividend("SYN-DIV", "SYN-A", D("1"), self.sessions[1].opens_at, self.sessions[2].day)
        self.sim.request_exit("SYN-A", self.at(1), "guidance_invalidation", ADV)
        self.sim.process_minute(self.minute(session=1))
        self.sim.advance(self.sessions[2].opens_at)
        snapshot = self.sim.snapshot()
        balance = D("0")
        for movement in snapshot["cash_movements"]:
            balance = add(balance, D(movement["delta"]))
            self.assertEqual(balance, D(movement["balance"]))
        self.assertEqual(balance, D(snapshot["settled_cash"]))
        self.assertIn("SYN-DIV", snapshot["corporate_actions"])
        self.assertEqual(snapshot["receivables"], [])

    def test_tiny_exit_fee_does_not_suppress_risk_reduction(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("0.001")})
        self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})
        fills = self.sim.process_minute(self.minute(session=1, bid="0.001", ask="0.001"))
        self.assertEqual(len(fills), 1)
        self.assertEqual(self.sim.positions, ())
        self.assertEqual(self.sim.snapshot()["receivables"][0]["amount"], "0")

    def test_missing_session_closes_are_visible_and_block_completion(self):
        self.sim.close_session(self.sessions[2].day, {})
        self.assertEqual(self.sim.snapshot()["missing_session_closes"], [s.day.isoformat() for s in self.sessions[:2]])
        self.assertTrue(self.sim.snapshot()["completion_blocked"])

    def test_missing_historical_nav_remains_blocked_after_liquidation_and_settlement(self):
        self.held()
        self.sim.close_session(self.sessions[0].day, {})
        self.sim.request_exit("SYN-A", self.at(1), "guidance_invalidation", ADV)
        self.sim.process_minute(self.minute(session=1))
        self.sim.close_session(self.sessions[1].day, {})
        self.sim.advance(self.sessions[2].opens_at)
        self.sim.close_session(self.sessions[2].day, {})
        snapshot = self.sim.snapshot()
        self.assertEqual(snapshot["positions"], [])
        self.assertEqual(snapshot["receivables"], [])
        self.assertEqual(snapshot["missing_valuation_sessions"], [self.sessions[0].day.isoformat()])
        self.assertTrue(snapshot["completion_blocked"])

    def test_program_drawdown_stop_is_inclusive_at_exactly_fifteen_percent(self):
        # Ten 50-share fills at 99.0495 (ask 99 plus 5 bp) leave settled cash
        # 50465.25; a raw close of 69.0695 values the 500 shares at 34534.75,
        # so NAV is exactly 85% of the 100000 high-water mark. The proposed
        # stop is "at or below" 15% drawdown: exactly 85% must stop the
        # program, and one tick above must not.
        for mark, stopped in ((D("69.0695"), True), (D("69.0696"), False)):
            with self.subTest(mark=mark):
                engine = Simulation(self.sessions)
                for n in range(10):
                    order = self.entry(engine, issuer=f"SYN-A{n}", event=f"SYN-E{n}", sector=f"sector{n}", ask="99", bid="98.9")
                    self.assertEqual(order.quantity, 50)
                for n in range(10):
                    fill = engine.process_minute(self.minute(issuer=f"SYN-A{n}", ask="99", bid="98.9"))[0]
                    self.assertEqual((fill.quantity, fill.price), (50, D("99.0495")))
                self.assertEqual(engine.snapshot()["settled_cash"], "50465.25")
                record = engine.close_session(self.sessions[0].day, {f"SYN-A{n}": mark for n in range(10)})
                self.assertEqual(record["nav"], D("85000") if stopped else D("85000.05"))
                self.assertIs(record["stopped"], stopped)
                reasons = {due["reason"] for due in engine.snapshot()["scheduled_exits"].values()}
                self.assertEqual(reasons, {"program_drawdown"} if stopped else {"position_stop"})

    def test_position_stop_is_inclusive_at_exactly_ninety_percent_of_entry_cost(self):
        # The entry fills 49 shares at 100.0500, so 90.0450 is exactly 90% of
        # the per-share entry cost. The proposed stop is "at or below": the
        # exact boundary must schedule the exit and one tick above must not.
        for mark, scheduled in ((D("90.0450"), True), (D("90.0451"), False)):
            with self.subTest(mark=mark):
                engine = Simulation(self.sessions)
                order = self.entry(engine)
                fill = engine.process_minute(self.minute())[0]
                self.assertEqual(mul(fill.price, D("0.9")), D("90.0450"))
                engine.close_session(self.sessions[0].day, {"SYN-A": mark})
                due = engine.snapshot()["scheduled_exits"]
                if scheduled:
                    self.assertEqual(due["SYN-A"]["reason"], "position_stop")
                    self.assertEqual(due["SYN-A"]["quantity"], order.quantity)
                else:
                    self.assertEqual(due, {})

    def test_due_exit_or_active_sell_refuses_new_entry_for_that_reason_even_with_fresh_quotes(self):
        # "Process exits and trims before entries." The refusal must come from
        # the precedence rule itself, not incidentally from a later check such
        # as a missing portfolio quote, so fresh valuation quotes are supplied.
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("200")})
        at = self.at(1)
        fresh = {"SYN-A": Quote(self.at(1, 9, 59), D("200"), D("200"))}
        quote = Quote(self.at(1, 9, 59), D("99.9"), D("100"))
        self.assertIn("SYN-A", self.sim.snapshot()["scheduled_exits"])
        self.assertIsNone(self.sim.submit_entry("SYN-E2", "SYN-B", "energy", at, quote, ADV, valuation_quotes=fresh))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "exits_must_precede_entries")
        trims = self.sim.execute_due_exits(at, {"SYN-A": ADV})
        self.assertEqual(len(trims), 1)
        self.assertIsNone(self.sim.submit_entry("SYN-E3", "SYN-C", "energy", at, quote, ADV, valuation_quotes=fresh))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "exits_must_precede_entries")
        self.sim.process_minute(self.minute(session=1, bid="200", ask="200.1"))
        self.sim.close_session(self.sessions[1].day, {"SYN-A": D("200")})
        self.assertEqual(self.sim.snapshot()["scheduled_exits"], {})
        later = {"SYN-A": Quote(self.at(2, 9, 59), D("200"), D("200"))}
        self.assertIsNotNone(self.sim.submit_entry("SYN-E4", "SYN-D", "energy", self.at(2),
                                                   Quote(self.at(2, 9, 59), D("99.9"), D("100")), ADV, valuation_quotes=later))

    def test_receivable_does_not_settle_on_a_pre_open_tick_of_its_pay_session(self):
        # Sale proceeds are receivables until the explicit pay session has
        # opened; a clock tick earlier on that date must not settle them.
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("100")})
        self.sim.request_exit("SYN-A", self.at(1), "guidance_invalidation", ADV)
        self.sim.process_minute(self.minute(session=1))
        cash = D(self.sim.snapshot()["settled_cash"])
        self.sim.advance(self.at(2, 9, 0))
        self.assertEqual(D(self.sim.snapshot()["settled_cash"]), cash)
        self.assertEqual(len(self.sim.snapshot()["receivables"]), 1)
        self.sim.advance(self.sessions[2].opens_at)
        self.assertEqual(self.sim.snapshot()["receivables"], [])
        self.assertGreater(D(self.sim.snapshot()["settled_cash"]), cash)

    def test_explicit_cancel_request_keeps_reserved_cash_until_acknowledged(self):
        # "Release unused reservations exactly once after confirmed terminal
        # fill/cancellation, never on a cancel request alone." The scheduled
        # 10:05 path is covered elsewhere; this pins the explicit request path.
        order = self.entry()
        reserved = D(self.sim.snapshot()["reserved_cash"])
        self.assertEqual(reserved, add(order.reserved_notional, order.reserved_fee))
        requested = self.sim.request_cancel(order.order_id, self.at(0, 10, 1))
        self.assertEqual(requested.status, "cancel_requested")
        self.assertEqual(D(self.sim.snapshot()["reserved_cash"]), reserved)
        self.assertEqual(self.sim.orders[0].reserved_notional, order.reserved_notional)
        self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 2))
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "0")

    def test_position_stop_stays_price_based_after_a_partial_trim(self):
        # The stop compares the mark against the split-adjusted entry cost per
        # original share. Trimming 23 of 49 shares must not shrink that basis:
        # a mark above 90% of the entry price must not stop the 26 remaining
        # shares, and a mark exactly at 90% still must.
        self.held()
        self.sim.close_session(self.sessions[0].day, {"SYN-A": D("200")})
        trim = self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})[0]
        self.assertEqual(trim.quantity, 23)
        self.sim.process_minute(self.minute(session=1, bid="200", ask="200.1"))
        self.assertEqual(self.sim.positions[0].quantity, 26)
        self.assertEqual(self.sim.positions[0].reference_quantity, D("49"))
        self.sim.close_session(self.sessions[1].day, {"SYN-A": D("95")})
        self.assertEqual(self.sim.snapshot()["scheduled_exits"], {})
        self.sim.close_session(self.sessions[2].day, {"SYN-A": D("90.0450")})
        due = self.sim.snapshot()["scheduled_exits"]["SYN-A"]
        self.assertEqual((due["reason"], due["quantity"]), ("position_stop", 26))

    def test_missing_prior_close_mark_refuses_entry_for_that_reason_despite_fresh_quotes(self):
        # A daily valuation gap pauses new entries even when the caller can
        # supply a fresh quote for the holding; the refusal must name the gap.
        self.held()
        self.sim.close_session(self.sessions[0].day, {})
        fresh = {"SYN-A": Quote(self.at(1, 9, 59), D("100"), D("100"))}
        quote = Quote(self.at(1, 9, 59), D("99.9"), D("100"))
        self.assertIsNone(self.sim.submit_entry("SYN-E2", "SYN-B", "energy", self.at(1), quote, ADV, valuation_quotes=fresh))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "missing_valuation")

    def test_minute_at_or_after_1005_converts_an_open_entry_to_cancel_requested(self):
        # Belt-and-braces for "cancel the unfilled remainder at 10:05": even
        # when the scheduled cancellation call is missed, executable market
        # data at or after 10:05 must mark the open buy as cancel_requested so
        # that only the documented racing fills remain possible until the
        # acknowledgment. A quote above the limit isolates the status change
        # from any fill. (A zero-volume minute carries no capacity and is
        # skipped before this conversion; the explicit 10:05 path covers it.)
        order = self.entry()
        self.assertEqual(self.sim.process_minute(self.minute(minute=4, bid="100.9", ask="101")), ())
        self.assertEqual(self.sim.orders[0].status, "open")
        self.assertEqual(self.sim.process_minute(self.minute(minute=5, bid="100.9", ask="101")), ())
        self.assertEqual(self.sim.orders[0].status, "cancel_requested")
        self.assertNotEqual(self.sim.snapshot()["reserved_cash"], "0")
        self.sim.acknowledge_cancel(order.order_id, self.at(0, 10, 6))
        self.assertEqual(self.sim.orders[0].status, "cancelled")
        self.assertEqual(self.sim.snapshot()["reserved_cash"], "0")

    def test_skipped_previous_session_close_refuses_entry_for_that_reason_despite_fresh_quotes(self):
        # If the previous session was never closed, its drawdown and stop
        # evaluation never ran; a new entry must be refused for exactly that
        # reason even when fresh quotes would allow NAV sizing.
        self.held()
        fresh = {"SYN-A": Quote(self.at(1, 9, 59), D("100"), D("100"))}
        quote = Quote(self.at(1, 9, 59), D("99.9"), D("100"))
        self.assertIsNone(self.sim.submit_entry("SYN-E2", "SYN-B", "energy", self.at(1), quote, ADV, valuation_quotes=fresh))
        self.assertEqual(self.sim.snapshot()["refusals"][-1]["reason"], "missing_previous_session_valuation")

    def test_terminal_payout_without_a_held_position_is_refused_atomically(self):
        # A pending, unfilled entry is not an entitlement. Crediting terminal
        # proceeds for shares never held would invent cash; the refusal must
        # be a SimulationError that leaves the order, cash and journal intact.
        self.entry()
        before = self.sim.snapshot()
        with self.assertRaisesRegex(SimulationError, "without a held entitlement"):
            self.sim.terminal_settlement("SYN-TERM", "SYN-A", self.at(0, 10, 1), D("1000"), self.sessions[1].day)
        self.assertEqual(self.sim.snapshot(), before)
        self.assertEqual(self.sim.orders[0].status, "open")

    def test_arithmetic_independent_of_ambient_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            order = self.entry()
            fill = self.sim.process_minute(self.minute())[0]
            self.assertEqual(order.quantity, 49)
            self.assertEqual(fill.price, D("100.0500"))
            self.assertEqual(self.sim.snapshot()["settled_cash"], "95096.55")
            self.sim.close_session(self.sessions[0].day, {"SYN-A": D("90")})
            self.sim.execute_due_exits(self.at(1), {"SYN-A": ADV})
            self.assertTrue(self.sim.process_minute(self.minute(session=1)))


if __name__ == "__main__":
    unittest.main()
