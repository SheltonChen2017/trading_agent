"""Synthetic order-comparator reconciliation and refusal tests only."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, localcontext
from zoneinfo import ZoneInfo

from research.guidance_revision_drift.comparison import ComparisonError, MatchedComparator
from research.guidance_revision_drift.simulation import Fill, Minute, Quote, Session


NY = ZoneInfo("America/New_York")
ADV = Decimal("1000000000")


def at(day="2024-03-11", minute=1, hour=10):
    return datetime.combine(date.fromisoformat(day), time(hour, minute), NY).astimezone(timezone.utc)


def fixture(mode="base"):
    dates = ("2024-03-11", "2024-03-12", "2024-03-13", "2024-03-14")
    sessions = tuple(Session(date.fromisoformat(d), at(d, 30, 9), at(d, 0, 16)) for d in dates)
    return MatchedComparator(sessions, mode=mode)


def source(side="buy", quantity=10, price="100", fee="1", day="2024-03-11", minute=1, issuer="SYN-A", order="SYN-STRATEGY-ORDER"):
    return Fill(order, "SYN-EVENT", issuer, side, quantity, Decimal(price), Decimal(fee), at(day, minute), date.fromisoformat("2024-03-12" if day == "2024-03-11" else "2024-03-14"))


def quote(timestamp=None, price="100"):
    return Quote(at() if timestamp is None else timestamp, Decimal(price), Decimal(price))


def minute(day="2024-03-11", value=2, volume=100000, price="100", settlement="2024-03-12"):
    return Minute("SYN-SPY", at(day, value), Decimal(price), Decimal(price), volume, ADV, date.fromisoformat(settlement))


def entries(comparator):
    comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
    return comparator.process_minute(minute())


def reasons(comparator):
    return tuple(row["reason"] for row in comparator.snapshot()["permanent_parity_blockers"])


class ComparatorTests(unittest.TestCase):
    def test_split_refuses_pending_orders_or_fractional_tranches_without_state_change(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        before = comparator.snapshot()
        with self.assertRaisesRegex(ComparisonError, "reconciled"):
            comparator.apply_split("SYN-SPLIT", Decimal("2"), at("2024-03-12", 30, 9))
        self.assertEqual(comparator.snapshot(), before)
        comparator.process_minute(minute())
        before = comparator.snapshot()
        with self.assertRaisesRegex(ComparisonError, "fractional"):
            comparator.apply_split("SYN-SPLIT", Decimal("0.5"), at("2024-03-12", 30, 9))
        self.assertEqual(comparator.snapshot(), before)

    def test_action_retries_conflicts_and_terminal_reopening_refuse(self):
        comparator = fixture()
        entries(comparator)
        comparator.apply_split("SYN-SPLIT", Decimal("2"), at("2024-03-12", 30, 9))
        before = comparator.snapshot()
        comparator.apply_split("SYN-SPLIT", Decimal("2"), at("2024-03-12", 30, 9))
        self.assertEqual(comparator.snapshot(), before)
        with self.assertRaisesRegex(ComparisonError, "conflicting"):
            comparator.apply_split("SYN-SPLIT", Decimal("3"), at("2024-03-12", 30, 9))
        self.assertEqual(comparator.snapshot(), before)
        comparator.terminal_settlement("SYN-END", at("2024-03-13", 30, 9), None, None)
        before = comparator.snapshot()
        self.assertIsNone(comparator.mark_nav(Decimal("999999")))
        with self.assertRaisesRegex(ComparisonError, "terminal"):
            comparator.record_entry("SYN-NEW", source(day="2024-03-13", order="SYN-NEW-ORDER"),
                quote=quote(at("2024-03-13")), adv20=ADV)
        self.assertEqual(comparator.snapshot(), before)

    def test_source_split_refuses_fractional_remaining_shares_without_flooring(self):
        # The paired coordinator reaches this only after the strategy engine
        # has accepted a whole-share split, but the method is public: a direct
        # caller must not have the remaining source shares silently floored.
        comparator = fixture()
        entries(comparator)
        before = comparator.snapshot()
        with self.assertRaisesRegex(ComparisonError, "fractional source split"):
            comparator.apply_source_split("SYN-SRC-SPLIT", "SYN-A", Decimal("0.25"), at("2024-03-12", 30, 9))
        self.assertEqual(comparator.snapshot(), before)
        comparator.apply_source_split("SYN-SRC-SPLIT-2", "SYN-A", Decimal("2"), at("2024-03-12", 30, 9))
        self.assertEqual(comparator.snapshot()["strategy_remaining"]["SYN-A"], 20)

    def test_entry_budget_includes_source_fee_and_rounding_cash_is_retained(self):
        comparator = fixture()
        fills = entries(comparator)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].quantity, 9)
        self.assertEqual(fills[0].price, Decimal("100.0500"))
        self.assertEqual(fills[0].fee, Decimal("1"))
        report = comparator.snapshot()
        self.assertEqual(report["tranches"][0]["source_budget"], "1001")
        self.assertEqual(report["tranches"][0]["entry_spent"], "901.45")
        self.assertEqual(report["settled_cash"], "99098.55")
        self.assertEqual(report["reserved_cash"], "0")
        self.assertFalse(report["synthetic_schedule_parity_blocked"])
        self.assertFalse(report["empirical_inference_permitted"])

    def test_same_bar_rejection_is_atomic_and_strictly_later_minute_fills(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        before = comparator.snapshot()
        with self.assertRaisesRegex(ComparisonError, "same-bar"):
            comparator.process_minute(minute(value=1))
        self.assertEqual(before, comparator.snapshot())
        self.assertEqual(comparator.process_minute(minute())[0].quantity, 9)

    def test_partial_capacity_match_fees_once_and_blocker_persists_after_repair(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        first = comparator.process_minute(minute(volume=400))
        second = comparator.process_minute(minute(value=3, volume=100000))
        self.assertEqual([f.quantity for f in first + second], [4, 5])
        self.assertEqual([f.fee for f in first + second], [Decimal("1"), Decimal("0")])
        self.assertIn("partial_or_unmatched_execution", reasons(comparator))
        self.assertTrue(comparator.snapshot()["synthetic_schedule_parity_blocked"])

    def test_late_or_zero_volume_opportunities_remain_permanent_mismatches(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        self.assertEqual(comparator.process_minute(minute(value=3, volume=0)), ())
        self.assertIn("timing_mismatch", reasons(comparator))
        comparator.process_minute(minute(value=4))
        self.assertIn("timing_mismatch", reasons(comparator))
        self.assertIn("partial_or_unmatched_execution", reasons(comparator))

    def test_base_and_stress_use_common_execution_and_commission_contract(self):
        base, stress = fixture(), fixture("stress")
        base_fill, stress_fill = entries(base)[0], entries(stress)[0]
        self.assertEqual(base_fill.price, Decimal("100.05"))
        self.assertEqual(stress_fill.price, Decimal("100.15"))
        self.assertEqual(base_fill.fee, Decimal("1"))
        self.assertEqual(stress_fill.fee, Decimal("2"))

    def test_multiple_tranches_share_capacity_and_cash_without_injection(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(quantity=1000), quote=quote(), adv20=ADV)
        comparator.record_entry("SYN-FILL-B", source(quantity=1000, issuer="SYN-B", order="SYN-STRATEGY-ORDER-B"), quote=quote(), adv20=ADV)
        self.assertIn("funding_mismatch", reasons(comparator))
        comparator.process_minute(minute(volume=500))
        self.assertEqual(sum(f.quantity for f in comparator.fills), 5)
        self.assertGreaterEqual(Decimal(comparator.snapshot()["settled_cash"]), Decimal("0"))
        report = comparator.snapshot()
        self.assertEqual(len(report["tranches"]), 2)
        self.assertEqual(report["initial_cash"], "100000")
        self.assertFalse(hasattr(comparator, "deposit"))

    def test_partial_then_final_exit_maps_actual_position_fraction_and_settles(self):
        comparator = fixture()
        entries(comparator)
        partial = source("sell", 5, day="2024-03-12", order="SYN-SELL-1")
        orders = comparator.record_exit("SYN-EXIT-A", partial, fraction_numerator=5, fraction_denominator=10, adv20=ADV)
        self.assertEqual(orders[0]["quantity"], 4)
        comparator.process_minute(minute(day="2024-03-12", settlement="2024-03-13"))
        final = source("sell", 5, day="2024-03-13", order="SYN-SELL-2")
        orders = comparator.record_exit("SYN-EXIT-B", final, fraction_numerator=5, fraction_denominator=5, adv20=ADV)
        self.assertEqual(orders[0]["quantity"], 5)
        comparator.process_minute(minute(day="2024-03-13", settlement="2024-03-14"))
        self.assertEqual(comparator.snapshot()["tranches"][0]["quantity"], 0)
        self.assertTrue(comparator.snapshot()["study_completion_blocked"])
        comparator.advance(at("2024-03-14", 30, 9))
        report = comparator.snapshot()
        self.assertEqual(report["receivables"], [])
        self.assertEqual(report["settled_cash"], "99996.1")
        self.assertFalse(report["study_completion_blocked"])

    def test_sale_proceeds_remain_unsettled_until_explicit_session_open(self):
        comparator = fixture()
        entries(comparator)
        before = Decimal(comparator.snapshot()["settled_cash"])
        comparator.record_exit("SYN-EXIT-A", source("sell", 10, day="2024-03-12"), fraction_numerator=10, fraction_denominator=10, adv20=ADV)
        comparator.process_minute(minute(day="2024-03-12", settlement="2024-03-13"))
        self.assertEqual(Decimal(comparator.snapshot()["settled_cash"]), before)
        comparator.advance(at("2024-03-13", 0, 9))
        self.assertEqual(Decimal(comparator.snapshot()["settled_cash"]), before)
        comparator.advance(at("2024-03-13", 30, 9))
        self.assertGreater(Decimal(comparator.snapshot()["settled_cash"]), before)

    def test_exit_cancels_unmatched_entry_and_retains_blocker(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        comparator.process_minute(minute(volume=400))
        comparator.record_exit("SYN-EXIT-A", source("sell", 10, day="2024-03-12"), fraction_numerator=10, fraction_denominator=10, adv20=ADV)
        self.assertIn("entry_unmatched_at_strategy_exit", reasons(comparator))
        self.assertEqual(comparator.snapshot()["reserved_cash"], "0")
        comparator.process_minute(minute(day="2024-03-12", settlement="2024-03-13"))
        self.assertEqual(comparator.snapshot()["tranches"][0]["quantity"], 0)

    def test_repeated_partial_strategy_fills_create_distinct_tranches_and_exits(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(quantity=5), quote=quote(), adv20=ADV)
        comparator.process_minute(minute())
        comparator.record_entry("SYN-FILL-B", source(quantity=5, fee="0", minute=2), quote=quote(at(minute=2)), adv20=ADV)
        comparator.process_minute(minute(value=3))
        self.assertEqual([t["quantity"] for t in comparator.snapshot()["tranches"]], [4, 4])
        orders = comparator.record_exit("SYN-EXIT-A", source("sell", 10, day="2024-03-12"), fraction_numerator=10, fraction_denominator=10, adv20=ADV)
        self.assertEqual(len(orders), 2)
        fills = comparator.process_minute(minute(day="2024-03-12", settlement="2024-03-13"))
        self.assertEqual([f.quantity for f in fills], [4, 4])

    def test_duplicate_fill_and_minute_replay_idempotence_and_conflicts_are_atomic(self):
        comparator = fixture()
        original = comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        comparator.process_minute(minute())
        before = comparator.snapshot()
        comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        self.assertEqual(comparator.process_minute(minute()), ())
        self.assertEqual(comparator.snapshot(), before)
        for operation in (lambda: comparator.record_entry("SYN-FILL-A", replace(source(), fee=Decimal("2")), quote=quote(), adv20=ADV),
                          lambda: comparator.record_entry("SYN-ALIAS", source(), quote=quote(), adv20=ADV),
                          lambda: comparator.process_minute(replace(minute(), volume=1))):
            with self.assertRaises(ComparisonError):
                operation()
            self.assertEqual(comparator.snapshot(), before)
        original["source_budget"] = Decimal("99999999")
        self.assertEqual(comparator.snapshot(), before)

    def test_unknown_exit_or_wrong_fraction_types_refuse_atomically(self):
        comparator = fixture()
        before = comparator.snapshot()
        with self.assertRaises(ComparisonError):
            comparator.record_exit("SYN-EXIT-A", source("sell"), fraction_numerator=10, fraction_denominator=10, adv20=ADV)
        self.assertEqual(comparator.snapshot(), before)
        entries(comparator)
        before = comparator.snapshot()
        for numerator, denominator in ((True, 10), (5.0, 10), (5, 10), (10, 9), (11, 10)):
            with self.subTest(numerator=numerator, denominator=denominator), self.assertRaises(ValueError):
                comparator.record_exit("SYN-EXIT-A", source("sell", 10, day="2024-03-12"), fraction_numerator=numerator, fraction_denominator=denominator, adv20=ADV)
            self.assertEqual(comparator.snapshot(), before)

    def test_invalid_prices_identities_settlement_and_future_quotes_are_atomic(self):
        comparator = fixture()
        before = comparator.snapshot()
        for changes in ({"price": True}, {"price": 100.0}, {"price": Decimal("NaN")},
                        {"quantity": True}, {"issuer": "AAPL"}, {"settlement_session": date(2024, 3, 10)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                comparator.record_entry("SYN-FILL-A", replace(source(), **changes), quote=quote(), adv20=ADV)
            self.assertEqual(comparator.snapshot(), before)
        for timestamp in (at() + timedelta(seconds=1), at() - timedelta(seconds=61)):
            with self.assertRaises(ComparisonError):
                comparator.record_entry("SYN-FILL-A", source(), quote=quote(timestamp), adv20=ADV)
            self.assertEqual(comparator.snapshot(), before)

    def test_limit_sizing_leftover_beyond_one_share_is_explicitly_blocked(self):
        comparator = fixture()
        comparator.record_entry("SYN-FILL-A", source(quantity=100), quote=quote(), adv20=ADV)
        comparator.process_minute(minute(price="90"))
        self.assertIn("budget_mismatch_beyond_rounding", reasons(comparator))

    def test_changed_ambient_decimal_context_does_not_change_accounting(self):
        expected = fixture()
        entries(expected)
        with localcontext() as context:
            context.prec = 2
            context.Emin = -2
            context.Emax = 2
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            actual = fixture()
            entries(actual)
            self.assertEqual(actual.snapshot(), expected.snapshot())

    def test_daily_nav_includes_idle_cash_positions_and_unsettled_receivables(self):
        comparator = fixture()
        entries(comparator)
        self.assertEqual(comparator.mark_nav(Decimal("100")), Decimal("99998.55"))
        first = comparator.close_session(date(2024, 3, 11), Decimal("100"))
        self.assertEqual(first["nav"], Decimal("99998.55"))
        comparator.record_exit("SYN-EXIT-A", source("sell", 10, day="2024-03-12"), fraction_numerator=10, fraction_denominator=10, adv20=ADV)
        comparator.process_minute(minute(day="2024-03-12", settlement="2024-03-13"))
        second = comparator.close_session(date(2024, 3, 12), None)
        self.assertEqual(second["receivables"], Decimal("898.55"))
        self.assertEqual(second["nav"], Decimal("99997.1"))
        self.assertEqual(comparator.snapshot()["missing_session_closes"], [])
        comparator.advance(at("2024-03-13", 30, 9))
        self.assertEqual(comparator.mark_nav(None), second["nav"])

    def test_missing_daily_marks_or_calendar_dates_are_retained_and_never_inferred(self):
        comparator = fixture()
        entries(comparator)
        self.assertIsNone(comparator.mark_nav(None))
        result = comparator.close_session(date(2024, 3, 12), None)
        self.assertIsNone(result["nav"])
        self.assertIn("missing_daily_observation:2024-03-11", reasons(comparator))
        self.assertIn("missing_mark:2024-03-12", reasons(comparator))
        comparator.close_session(date(2024, 3, 13), Decimal("100"))
        self.assertIn("missing_mark:2024-03-12", reasons(comparator))
        before = comparator.snapshot()
        with self.assertRaises(ValueError):
            comparator.close_session(date(2024, 3, 14), True)
        self.assertEqual(comparator.snapshot(), before)

    def test_caller_forced_mutation_cannot_rewrite_stored_fill_quote_or_minute(self):
        comparator = fixture()
        fill, observation, bar = source(), quote(), minute()
        comparator.record_entry("SYN-FILL-A", fill, quote=observation, adv20=ADV)
        comparator.process_minute(bar)
        before = comparator.snapshot()
        object.__setattr__(fill, "quantity", 999)
        object.__setattr__(observation, "ask", Decimal("200"))
        object.__setattr__(bar, "volume", 1)
        comparator.record_entry("SYN-FILL-A", source(), quote=quote(), adv20=ADV)
        self.assertEqual(comparator.process_minute(minute()), ())
        self.assertEqual(comparator.snapshot(), before)

    def test_historical_calendar_or_nav_gaps_block_completion_after_full_liquidation(self):
        for gap in ("calendar", "nav"):
            with self.subTest(gap=gap):
                comparator = fixture()
                entries(comparator)
                if gap == "nav":
                    comparator.close_session(date(2024, 3, 11), None)
                comparator.close_session(date(2024, 3, 12), Decimal("100"))
                comparator.record_exit("SYN-EXIT-A", source("sell", 10, day="2024-03-13"),
                    fraction_numerator=10, fraction_denominator=10, adv20=ADV)
                comparator.process_minute(minute(day="2024-03-13", settlement="2024-03-14"))
                comparator.close_session(date(2024, 3, 13), None)
                comparator.close_session(date(2024, 3, 14), None)
                report = comparator.snapshot()
                self.assertEqual(report["tranches"][0]["quantity"], 0)
                self.assertEqual(report["receivables"], [])
                self.assertTrue(all(order["status"] == "filled" for order in report["orders"]))
                self.assertTrue(report["study_completion_blocked"])


if __name__ == "__main__":
    unittest.main()
