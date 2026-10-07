"""Supplied synthetic corporate economics and paired rollback/replay."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
import unittest

from research.guidance_revision_drift.comparison import MatchedComparator
from research.guidance_revision_drift.corporate_actions import CorporateAction, apply_corporate_action
from research.guidance_revision_drift.fixtures import fixture_instant
from research.guidance_revision_drift.simulation import Simulation, Session, Quote, Minute
from research.guidance_revision_drift.timing import PinnedSchedule, Session as CalendarSession

D = Decimal
ADV = D("1000000000")


def at(day, hour=9, minute=30):
    return fixture_instant(date.fromisoformat(day), hour, minute)


def engines(*, partial_comparator=False):
    days = tuple(date.fromisoformat(d) for d in ("2025-04-03", "2025-04-04", "2025-04-07", "2025-04-08", "2025-04-09"))
    sessions = tuple(Session(d, fixture_instant(d, 9, 30), fixture_instant(d, 16)) for d in days)
    schedule = PinnedSchedule(tuple(CalendarSession(s.day, s.opens_at, s.closes_at) for s in sessions),
                              days[0], days[-1], "SYN-ACTION-CALENDAR")
    strategy, comparator = Simulation(sessions), MatchedComparator(sessions)
    strategy.submit_entry("SYN-EVENT", "SYN-A", "tech", at("2025-04-04", 10, 0),
                          Quote(at("2025-04-04", 10, 0), D("50"), D("50")), ADV)
    fill = strategy.process_minute(Minute("SYN-A", at("2025-04-04", 10, 1), D("50"), D("50"),
                                         100000, ADV, date(2025, 4, 7)))[0]
    comparator.record_entry("SYN-SOURCE-1", fill, quote=Quote(fill.at, D("100"), D("100")), adv20=ADV)
    comparator.process_minute(Minute("SYN-SPY", at("2025-04-04", 10, 2), D("100"), D("100"),
                                    100 if partial_comparator else 100000, ADV, date(2025, 4, 7)))
    return strategy, comparator, schedule


def action_body(schedule, kind="split", issuer="SYN-A", **changes):
    body = dict(schema="gdr.synthetic.corporate-action.v1", source_id="SYN-ACTION-SOURCE",
        action_id="SYN-ACTION-1", issuer_id=issuer, calendar_sha256=schedule.sha256,
        kind=kind, effective_at="2025-04-07T13:30:00Z", received_at="2025-04-04T20:00:00Z",
        validated_at="2025-04-04T20:00:00Z", ratio="2" if kind == "split" else None,
        amount="1" if kind == "dividend" else None, pay_session="2025-04-08" if kind == "dividend" else None)
    body.update(changes)
    return body


class CorporateActionTests(unittest.TestCase):
    def test_source_split_preserves_actual_fill_history_and_adjusts_exit_fraction(self):
        strategy, comparator, schedule = engines()
        original_fills = strategy.fills, comparator.fills
        held = strategy.positions[0].quantity
        spy = comparator.snapshot()["tranches"][0]["quantity"]
        apply_corporate_action(strategy, comparator, CorporateAction.from_dict(action_body(schedule)), schedule=schedule)
        self.assertEqual(strategy.positions[0].quantity, held * 2)
        self.assertEqual(comparator.snapshot()["strategy_remaining"]["SYN-A"], held * 2)
        self.assertEqual(comparator.snapshot()["tranches"][0]["source_quantity"], held)
        self.assertEqual((strategy.fills, comparator.fills), original_fills)
        strategy.request_exit("SYN-A", at("2025-04-07", 10, 0), "guidance_invalidation", ADV)
        fill = strategy.process_minute(Minute("SYN-A", at("2025-04-07", 10, 1), D("25"), D("25"),
                                             100000, ADV, date(2025, 4, 8)))[0]
        orders = comparator.record_exit("SYN-EXIT", fill, fraction_numerator=held * 2,
                                         fraction_denominator=held * 2, adv20=ADV)
        self.assertEqual(sum(o["quantity"] for o in orders), spy)

    def test_pending_comparator_split_refusal_rolls_back_already_applied_strategy_side(self):
        strategy, comparator, schedule = engines(partial_comparator=True)
        before = strategy.snapshot(), comparator.snapshot()
        with self.assertRaisesRegex(ValueError, "reconciled comparator orders"):
            apply_corporate_action(strategy, comparator, CorporateAction.from_dict(action_body(schedule)), schedule=schedule)
        self.assertEqual((strategy.snapshot(), comparator.snapshot()), before)

    def test_dividends_entitle_each_sleeve_independently_and_settle_once(self):
        strategy, comparator, schedule = engines()
        qty = strategy.positions[0].quantity
        spy = comparator.snapshot()["tranches"][0]["quantity"]
        strategy_cash = D(strategy.snapshot()["settled_cash"])
        spy_cash = D(comparator.snapshot()["settled_cash"])
        for issuer, identity, amount in (("SYN-A", "SYN-DIV-A", "1"), ("SYN-SPY", "SYN-DIV-SPY", "2")):
            action = CorporateAction.from_dict(action_body(schedule, "dividend", issuer,
                action_id=identity, amount=amount))
            apply_corporate_action(strategy, comparator, action, schedule=schedule)
            apply_corporate_action(strategy, comparator, action, schedule=schedule)
        self.assertEqual(D(strategy.snapshot()["receivables"][0]["amount"]), D(qty))
        self.assertEqual(D(comparator.snapshot()["receivables"][0]["amount"]), D(spy * 2))
        strategy.advance(at("2025-04-08"))
        comparator.advance(at("2025-04-08"))
        self.assertEqual(D(strategy.snapshot()["settled_cash"]), strategy_cash + D(qty))
        self.assertEqual(D(comparator.snapshot()["settled_cash"]), spy_cash + D(spy * 2))
        self.assertEqual(len(comparator.snapshot()["corporate_action_inputs"]), 2)

    def test_comparator_split_conserves_nav_at_explicit_postsplit_mark(self):
        strategy, comparator, schedule = engines()
        before = comparator.mark_nav(D("100"))
        strategy_before = strategy.snapshot()
        apply_corporate_action(strategy, comparator,
            CorporateAction.from_dict(action_body(schedule, issuer="SYN-SPY")), schedule=schedule)
        self.assertEqual(comparator.mark_nav(D("50")), before)
        self.assertEqual(strategy.snapshot(), strategy_before)

    def test_source_terminal_never_becomes_a_fabricated_spy_payout_or_exit(self):
        for amount, pay in (("4000", "2025-04-08"), (None, None)):
            strategy, comparator, schedule = engines()
            previous = comparator.snapshot()
            apply_corporate_action(strategy, comparator, CorporateAction.from_dict(action_body(schedule,
                "terminal", amount=amount, pay_session=pay)), schedule=schedule)
            after = comparator.snapshot()
            self.assertEqual(after["orders"], previous["orders"])
            self.assertEqual(after["tranches"], previous["tranches"])
            self.assertEqual(after["receivables"], previous["receivables"])
            self.assertIn("source_terminal_comparator_schedule_unsupported",
                          [row["reason"] for row in after["permanent_parity_blockers"]])
            self.assertTrue(after["study_completion_blocked"])
            if amount is None:
                strategy.close_session(date(2025, 4, 7), {"SYN-A": D("50")})
                self.assertIsNone(strategy.snapshot()["navs"][-1]["nav"])
            else:
                self.assertEqual(strategy.positions, ())
                self.assertEqual(strategy.snapshot()["receivables"][-1]["amount"], amount)

    def test_comparator_terminal_explicit_cash_or_permanent_unresolved_nav(self):
        for amount, pay in (("4800", "2025-04-08"), (None, None)):
            strategy, comparator, schedule = engines()
            before = strategy.snapshot()
            apply_corporate_action(strategy, comparator, CorporateAction.from_dict(action_body(schedule,
                "terminal", "SYN-SPY", amount=amount, pay_session=pay)), schedule=schedule)
            self.assertEqual(strategy.snapshot(), before)
            if amount is None:
                self.assertIsNone(comparator.mark_nav(D("100000")))
                self.assertTrue(comparator.snapshot()["unresolved_terminal"])
            else:
                self.assertEqual(comparator.snapshot()["tranches"][0]["quantity"], 0)
                self.assertEqual(comparator.snapshot()["receivables"][-1]["amount"], amount)
            self.assertTrue(comparator.snapshot()["synthetic_schedule_parity_blocked"])

    def test_fractional_noncash_unknown_and_unavailable_economics_refuse(self):
        strategy, comparator, schedule = engines()
        before = strategy.snapshot(), comparator.snapshot()
        for changes in ({"ratio": "0.3"}, {"kind": "noncash_merger"}, {"ratio": 2.0},
                        {"amount": "4"}, {"received_at": "2025-04-08T12:00:00Z"},
                        {"effective_at": "2025-04-07T14:00:00Z"}, {"calendar_sha256": "0" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                apply_corporate_action(strategy, comparator,
                    CorporateAction.from_dict(action_body(schedule, **changes)), schedule=schedule)
            self.assertEqual((strategy.snapshot(), comparator.snapshot()), before)

    def test_input_idempotence_conflicts_and_caller_mutation(self):
        strategy, comparator, schedule = engines()
        body = action_body(schedule)
        action = CorporateAction.from_dict(body)
        body["ratio"] = "999"
        action.to_dict()["ratio"] = "999"
        apply_corporate_action(strategy, comparator, action, schedule=schedule)
        before = strategy.snapshot(), comparator.snapshot()
        self.assertEqual(apply_corporate_action(strategy, comparator, action, schedule=schedule), action.sha256)
        self.assertEqual((strategy.snapshot(), comparator.snapshot()), before)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            apply_corporate_action(strategy, comparator, CorporateAction.from_dict(body), schedule=schedule)
        self.assertEqual((strategy.snapshot(), comparator.snapshot()), before)
        self.assertEqual(CorporateAction.from_bytes(action.canonical_bytes), action)

    def test_one_sleeve_receipt_cannot_acknowledge_an_untouched_partner(self):
        strategy, comparator, schedule = engines()
        other_strategy, _, _ = engines()
        action = CorporateAction.from_dict(action_body(schedule))
        apply_corporate_action(strategy, comparator, action, schedule=schedule)
        before = other_strategy.snapshot(), comparator.snapshot()
        with self.assertRaisesRegex(ValueError, "paired action receipt"):
            apply_corporate_action(other_strategy, comparator, action, schedule=schedule)
        self.assertEqual((other_strategy.snapshot(), comparator.snapshot()), before)

    def test_calendar_or_source_lineage_mismatch_refuses_both_sleeves(self):
        strategy, comparator, schedule = engines()
        no_source = MatchedComparator(tuple(strategy._sessions.values()))
        before = strategy.snapshot(), no_source.snapshot()
        with self.assertRaisesRegex(ValueError, "share lineage"):
            apply_corporate_action(strategy, no_source, CorporateAction.from_dict(action_body(schedule)), schedule=schedule)
        self.assertEqual((strategy.snapshot(), no_source.snapshot()), before)
        other_calendar = replace(schedule, schedule_id="SYN-OTHER")
        with self.assertRaisesRegex(ValueError, "calendar"):
            apply_corporate_action(strategy, comparator, CorporateAction.from_dict(action_body(schedule)), schedule=other_calendar)

    def test_malformed_duplicate_and_protected_action_inputs_refuse(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"ratio":2.0}', b'{"amount":NaN}', b"{}" * 10000):
            with self.assertRaises(ValueError):
                CorporateAction.from_bytes(raw)
        _, _, schedule = engines()
        body = action_body(schedule)
        body["effective_at"] = "2026-09-01T13:30:00Z"
        with self.assertRaises(ValueError):
            CorporateAction.from_dict(body)


if __name__ == "__main__":
    unittest.main()
