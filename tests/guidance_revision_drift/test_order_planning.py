"""Proposed offline buy intents are not fills or native/market evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
import json
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import load_candidate
from research.guidance_revision_drift.guidance_inputs import GuidanceDocument, GuidanceLedger, GuidanceReceipt
from research.guidance_revision_drift.historical_market import HistoricalMarketBatch
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes
from research.guidance_revision_drift.order_planning import AccountSnapshot, plan_session
from research.guidance_revision_drift.pre_qc import rehearsal_inputs
from research.guidance_revision_drift.research_reference import ReferenceBook
from tests.guidance_revision_drift.test_guidance_inputs import receipt, raised


class OrderPlanningTests(unittest.TestCase):
    def setUp(self):
        self.inputs = rehearsal_inputs()
        self.candidate = load_candidate()

    def plan(self, *, mode="base"):
        data = self.inputs
        return plan_session(self.candidate, data["calendar"], data["references"], data["guidance"],
            data["market"], data["account"], data["entry_session"], mode=mode)

    def account(self, **changes):
        values = self.inputs["account"].to_dict()
        values.update(changes)
        self.inputs["account"] = AccountSnapshot.from_dict(values)

    def reasons(self):
        return self.plan()["candidates"][0]["reasons"]

    def test_exact_cash_and_notional_caps_are_distinct_and_no_spy_order_is_submitted(self):
        report = self.plan()
        row = report["candidates"][0]
        self.assertEqual(row["status"], "provisional_entry_intent")
        self.assertEqual(row["priority_rank"], 1)
        intent = row["intent"]
        self.assertEqual(intent["whole_shares"], 495)
        self.assertEqual(Decimal(intent["reserved_notional"]), Decimal("4999.50"))
        self.assertEqual(Decimal(intent["reserved_fee"]), Decimal("2.475"))
        self.assertEqual(Decimal(report["remaining_declared_settled_cash"]), Decimal("94998.025"))
        self.assertFalse(intent["comparator"]["order_now"])
        self.assertIn("each_actual_strategy_fill", intent["comparator"]["trigger"])
        self.assertEqual(intent["proposed_time_exit_session"], self.inputs["calendar"].time_exit(self.inputs["entry_session"]).isoformat())
        self.assertEqual(report["orders_submitted"], 0)
        self.assertEqual(report["fills"], [])
        self.assertFalse(report["complete_execution_gate"])
        for field in ("native_execution_verified", "backtest_ready", "point_in_time_data", "source_rights_verified",
                      "account_authenticity_verified", "calendar_and_mapping_verified", "empirical_evaluation_allowed",
                      "qc_access_allowed", "real_orders_allowed"):
            self.assertIs(report[field], False)

    def test_hostile_decimal_context_preserves_intent_bytes(self):
        expected = canonical_bytes(self.plan())
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(canonical_bytes(self.plan()), expected)

    def test_pending_fees_reserve_cash_and_pending_issuer_blocks_positive_intent(self):
        self.account(pending_buys=[{"order_id": "PENDING", "issuer_id": "INVENTED-ISSUER", "sector": "technology",
                                   "reserved_notional": "50", "reserved_fee": "1"}])
        report = self.plan()
        self.assertIn("issuer_already_held_or_pending", report["candidates"][0]["reasons"])
        self.assertEqual(report["remaining_declared_settled_cash"], "99949")
        self.assertIsNone(report["candidates"][0]["intent"])

    def test_gross_and_sector_reservations_block_without_spending_unsettled_cash(self):
        for sector, notional, expected in (("technology", "15000", "sector"), ("other", "50000", "gross")):
            self.account(pending_buys=[{"order_id": "PENDING", "issuer_id": "OTHER", "sector": sector,
                                      "reserved_notional": notional, "reserved_fee": "1"}])
            report = self.plan()
            with self.subTest(cap=expected):
                self.assertIn("insufficient_declared_cash_or_exposure_capacity", report["candidates"][0]["reasons"])
        self.account(settled_cash="0", pending_buys=[], receivables=[{"amount": "100000",
            "settlement_session": self.inputs["calendar"].sessions[self.inputs["calendar"].index(self.inputs["entry_session"]) + 1].session_date.isoformat()}])
        self.assertIn("insufficient_declared_cash_or_exposure_capacity", self.reasons())

    def test_due_receivable_requires_reconciliation_never_automatically_becomes_cash(self):
        self.account(receivables=[{"amount": "10", "settlement_session": self.inputs["entry_session"].isoformat()}])
        self.assertIn("due_receivable_requires_reconciliation", self.reasons())
        self.assertEqual(self.plan()["remaining_declared_settled_cash"], "100000")

    def test_known_or_unknown_risk_control_states_block_provisional_new_exposure(self):
        original = self.inputs["account"].to_dict()
        for name in original["entry_controls"]:
            for state in (True, None):
                changed = deepcopy(original)
                changed["entry_controls"][name] = state
                self.inputs["account"] = AccountSnapshot.from_dict(changed)
                with self.subTest(name=name, state=state):
                    self.assertIn("entry_control_" + name, self.reasons())
                    self.assertIsNone(self.plan()["candidates"][0]["intent"])

    def test_future_receivable_date_need_not_be_a_trading_session_or_become_cash(self):
        # The supplied trading calendar omits this date. A separately supplied
        # payment/service calendar owns its validity, not the NYSE schedule.
        with self.assertRaises(InputError):
            self.inputs["calendar"].index(date(2025, 4, 18))
        self.account(receivables=[{"amount": "10", "settlement_session": "2025-04-18"}])
        report = self.plan()
        self.assertEqual(report["nav_from_declared_inputs"], "100010")
        self.assertEqual(report["remaining_declared_settled_cash"], "94998.025")
        self.assertFalse(report["backtest_ready"])

    def test_extreme_current_price_does_not_create_unbounded_order_quantity(self):
        self.account(settled_cash="1000000000000000000")
        import json
        raw = json.loads(self.inputs["market"][0].raw_bytes)
        for quote in raw["quotes"]:
            quote["bid_price"] = quote["ask_price"] = "0.00000000000000000000000000000001"
        self.inputs["market"] = (HistoricalMarketBatch(canonical_bytes(raw)), self.inputs["market"][1])
        self.assertIn("planned_whole_share_quantity_exceeds_supported_bound", self.reasons())

    def test_zero_affordable_whole_shares_is_a_named_refusal_and_fee_stays_separate(self):
        self.account(settled_cash="1")
        report = self.plan(mode="stress")
        self.assertIn("insufficient_declared_cash_or_exposure_capacity", report["candidates"][0]["reasons"])
        self.assertIsNone(report["candidates"][0]["intent"])

    def test_attempted_event_and_earlier_eligible_opportunity_cannot_retry(self):
        anchor = self.plan()["candidates"][0]["event_sha256"]
        self.account(attempted_event_sha256s=[anchor])
        self.assertIn("event_already_attempted", self.reasons())
        self.inputs = rehearsal_inputs()
        next_day = self.inputs["calendar"].sessions[self.inputs["calendar"].index(self.inputs["entry_session"]) + 1].session_date
        # Remove market input rather than fabricating an account/quote time;
        # the earlier-opportunity refusal is still independently retained.
        at = self.inputs["calendar"].sessions[self.inputs["calendar"].index(next_day)].open_utc + timedelta(minutes=30)
        self.inputs["entry_session"] = next_day
        self.inputs["market"] = ()
        self.account(at=at.isoformat().replace("+00:00", "Z"))
        self.assertIn("earlier_supplied_input_opportunity_already_eligible", self.reasons())

    def test_missing_or_bad_spy_cannot_make_a_positive_stock_intent(self):
        self.inputs["market"] = self.inputs["market"][:1]
        self.assertIn("missing_distinct_spy_market_input", self.reasons())
        self.inputs = rehearsal_inputs()
        spy = self.inputs["market"][1].projection()
        # Raw source shape is intentionally explicit; mutate the actual raw
        # JSON through the strict parser, not a normalized quote projection.
        import json
        raw = json.loads(self.inputs["market"][1].raw_bytes)
        raw["quotes"][0]["bid_price"] = "54"
        self.inputs["market"] = (self.inputs["market"][0], HistoricalMarketBatch(canonical_bytes(raw)))
        self.assertIn("benchmark_decision_quote_refused", self.reasons())

    def test_guidance_and_reference_identity_mismatch_is_retained(self):
        values = self.inputs["references"].to_dict()
        values["references"][0]["issuer_id"] = "OTHER-ISSUER"
        self.inputs["references"] = ReferenceBook.from_dict(values)
        self.assertIn("guidance_reference_issuer_mismatch", self.reasons())

    def test_post_cutoff_invalidation_blocks_entry_but_late_positive_cannot_create_it(self):
        withdrawal = receipt("INVENTED-WITHDRAW", "2025-04-04", kind="withdrawal", periods=[],
            supersedes="INVENTED-RAISE", provider="massive_benzinga", issuer_id="INVENTED-ISSUER",
            security_id="INVENTED-SEC", published_at="2025-04-04T13:00:00Z",
            received_at="2025-04-04T13:01:00Z", validated_at="2025-04-04T13:02:00Z")
        self.inputs["guidance"] = self.inputs["guidance"].append(withdrawal)
        self.assertIn("guidance_invalidated_between_cutoff_and_decision", self.reasons())
        self.assertIsNone(self.plan()["candidates"][0]["intent"])
        self.inputs = rehearsal_inputs()
        from research.guidance_revision_drift.guidance_inputs import GuidanceReceipt
        first, second = self.inputs["guidance"].receipts
        late = GuidanceReceipt(second.raw_bytes, second.document, "2025-04-04T12:00:00Z", "2025-04-04T12:01:00Z")
        self.inputs["guidance"] = GuidanceLedger((first, late))
        self.assertEqual(self.plan()["candidates"], [])

    def test_exact_rational_ranking_does_not_round_a_tie_into_security_order(self):
        data = self.inputs
        ledger = GuidanceLedger()
        old_rows, new_rows = [], []
        previous = "1000000000000000000000000000000"
        for security, tail in (("A-SECURITY", "1"), ("Z-SECURITY", "2")):
            current = "102000000000000000000000000000" + tail
            common = {"security_id": security, "issuer_id": security + "-ISSUER"}
            old_rows.append(receipt(security + "-OLD", "2025-03-03", **common,
                period_values={"revenue": {"lower": previous, "upper": previous, "kind": "point"}}))
            new_rows.append(raised(security + "-NEW", "2025-04-01", **common,
                period_values={"revenue": {"lower": current, "upper": current, "kind": "point"}}))
        for item in old_rows + new_rows:
            ledger = ledger.append(item)
        references = data["references"].to_dict()
        original = references["references"][0]
        history = [row for row in references["daily_bars"] if row["security_id"] == "INVENTED-SEC"]
        market = [data["market"][1]]
        for security in ("A-SECURITY", "Z-SECURITY"):
            references["references"].append({**original, "security_id": security, "issuer_id": security + "-ISSUER"})
            references["daily_bars"].extend({**row, "security_id": security} for row in history)
            import json
            raw = json.loads(data["market"][0].raw_bytes)
            raw["security_id"] = security
            market.append(HistoricalMarketBatch(canonical_bytes(raw)))
        data["references"] = ReferenceBook.from_dict(references)
        data["guidance"], data["market"] = ledger, tuple(market)
        report = self.plan()
        ordered = sorted(report["candidates"], key=lambda row: row["priority_rank"])
        self.assertEqual([row["security_id"] for row in ordered], ["Z-SECURITY", "A-SECURITY"])

    def test_account_exact_schema_future_marks_overreservation_and_duplicate_ids_refuse(self):
        original = self.inputs["account"].to_dict()
        for values in ({**original, "approved": True}, {**original, "settled_cash": True},
                       {**original, "attempted_event_sha256s": ["0" * 64, "0" * 64]},
                       {**original, "pending_buys": [{"order_id": "P", "issuer_id": "I", "sector": "S",
                                                    "reserved_notional": "100000", "reserved_fee": "1"}]}):
            with self.subTest(keys=set(values)), self.assertRaises(InputError):
                AccountSnapshot.from_dict(values)

    def test_first_actual_eligible_date_ranks_after_receipt_delay_not_theoretical_d_plus_three(self):
        data = self.inputs
        rows = [receipt("A-OLD", "2025-03-03", security_id="A-SEC", issuer_id="A-ISSUER"),
                receipt("B-OLD", "2025-03-03", security_id="B-SEC", issuer_id="B-ISSUER"),
                raised("B-NEW", "2025-04-01", security_id="B-SEC", issuer_id="B-ISSUER",
                       period_values={"revenue": {"lower": "103", "upper": "103", "kind": "point"}}),
                raised("A-NEW", "2025-03-31", security_id="A-SEC", issuer_id="A-ISSUER",
                       received_at="2025-04-03T14:01:00Z", validated_at="2025-04-03T14:02:00Z")]
        references = data["references"].to_dict()
        original = references["references"][0]
        history = [row for row in references["daily_bars"] if row["security_id"] == "INVENTED-SEC"]
        batches = [data["market"][1]]
        import json
        for name in ("A", "B"):
            references["references"].append({**original, "security_id": name + "-SEC", "issuer_id": name + "-ISSUER"})
            references["daily_bars"].extend({**row, "security_id": name + "-SEC"} for row in history)
            raw = json.loads(data["market"][0].raw_bytes)
            raw["security_id"] = name + "-SEC"
            batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        data["references"] = ReferenceBook.from_dict(references)
        data["guidance"], data["market"] = GuidanceLedger(tuple(rows)), tuple(batches)
        self.account(pending_buys=[{"order_id": "P" + str(i), "issuer_id": "O" + str(i),
            "sector": "technology", "reserved_notional": value, "reserved_fee": "1"}
            for i, value in enumerate(("5000", "5000", "4500"))])
        planned = sorted(self.plan()["candidates"], key=lambda row: row["priority_rank"])
        self.assertEqual([row["issuer_id"] for row in planned], ["B-ISSUER", "A-ISSUER"])
        self.assertEqual(planned[0]["intent"]["whole_shares"], 49)
        self.assertIsNone(planned[1]["intent"])

    def test_pure_planning_projection_is_detached_and_does_not_dispatch(self):
        expected = canonical_bytes(self.plan())
        output = self.plan()
        output["candidates"].clear()
        with patch("builtins.open", side_effect=AssertionError("file forbidden")), \
             patch("os.getenv", side_effect=AssertionError("environment forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            self.assertEqual(canonical_bytes(self.plan()), expected)

    # GDR-CR53-001: planner and account rules that no earlier case isolated.
    def _decision_on(self, offset):
        calendar = self.inputs["calendar"]
        session = calendar.sessions[calendar.index(self.inputs["entry_session"]) + offset]
        self.inputs["entry_session"], self.inputs["market"] = session.session_date, ()
        self.account(at=(session.open_utc + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"))

    def _two_events(self, eps_by_security):
        old_rows, new_rows, batches = [], [], [self.inputs["market"][1]]
        references = self.inputs["references"].to_dict()
        template = references["references"][0]
        history = [row for row in references["daily_bars"] if row["security_id"] == "INVENTED-SEC"]
        for security, eps in eps_by_security.items():
            common = {"security_id": security, "issuer_id": security + "-ISSUER"}
            old_rows.append(receipt(security + "-OLD", "2025-03-03", **common))
            new_rows.append(raised(security + "-NEW", "2025-04-01", **common,
                                   period_values={"eps": {"lower": eps, "upper": eps, "kind": "point"}}))
            references["references"].append({**template, **common})
            references["daily_bars"].extend({**row, "security_id": security} for row in history)
            raw = json.loads(self.inputs["market"][0].raw_bytes)
            raw["security_id"] = security
            batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        self.inputs["references"] = ReferenceBook.from_dict(references)
        self.inputs["guidance"] = GuidanceLedger(tuple(old_rows + new_rows))
        self.inputs["market"] = tuple(batches)

    def test_account_assertion_rules_each_refuse_alone(self):
        original = self.inputs["account"].to_dict()
        at = datetime.fromisoformat(original["at"].replace("Z", "+00:00"))

        def held(security, issuer, age=0):
            return {"security_id": security, "issuer_id": issuer, "sector": "technology", "quantity": 1,
                    "raw_mark": "10", "mark_at": (at - timedelta(seconds=age)).isoformat().replace("+00:00", "Z"),
                    "source_sha256": "0" * 64}
        AccountSnapshot.from_dict({**original, "positions": [held("HELD", "HELD-ISSUER", 60)]})
        pending = {"order_id": "PENDING", "issuer_id": "PENDING-ISSUER", "sector": "technology",
                   "reserved_notional": "1", "reserved_fee": "1"}
        controls = original["entry_controls"]
        cases = {"mark_older_than_60_seconds": {**original, "positions": [held("HELD", "HELD-ISSUER", 61)]},
                 "one_issuer_held_twice": {**original, "positions": [held("HELD-1", "HELD-ISSUER"), held("HELD-2", "HELD-ISSUER")]},
                 "text_control": {**original, "entry_controls": {**controls, "program_stop_active": "false"}},
                 "integer_control": {**original, "entry_controls": {**controls, "unresolved_actions": 0}},
                 "duplicate_pending_order": {**original, "pending_buys": [pending, {**pending, "issuer_id": "OTHER"}]}}
        for rule, values in cases.items():
            with self.subTest(rule=rule), self.assertRaises(InputError):
                AccountSnapshot.from_dict(values)
        with self.assertRaises(InputError):
            AccountSnapshot(canonical_bytes(original).replace(b",", b", ", 1))

    def test_account_must_be_asserted_at_the_decision_and_with_positive_nav(self):
        at = datetime.fromisoformat(self.inputs["account"].to_dict()["at"].replace("Z", "+00:00"))
        self.account(at=(at - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"))
        with self.assertRaises(InputError):
            self.plan()
        self.inputs = rehearsal_inputs()
        self.account(settled_cash="0")
        with self.assertRaises(InputError):
            self.plan()

    def test_cash_limited_sizing_reserves_the_minimum_and_per_share_fee(self):
        later = self.inputs["calendar"].sessions[self.inputs["calendar"].index(self.inputs["entry_session"]) + 1]
        # A future receivable keeps NAV caps wide while settled cash binds.
        for cash, shares, fee in (("101.5", 9, "1"), ("3041.5", 300, "1.5")):
            self.account(settled_cash=cash, receivables=[{"amount": "100000",
                         "settlement_session": later.session_date.isoformat()}])
            with self.subTest(cash=cash):
                intent = self.plan()["candidates"][0]["intent"]
                self.assertEqual(intent["whole_shares"], shares)
                self.assertEqual(Decimal(intent["reserved_fee"]), Decimal(fee))

    def test_position_fraction_and_entry_notional_caps_each_bind_alone(self):
        for cash, shares in (("50000", 247), ("200000", 495)):
            self.account(settled_cash=cash)
            with self.subTest(cash=cash):
                self.assertEqual(self.plan()["candidates"][0]["intent"]["whole_shares"], shares)

    def test_entry_before_the_third_session_after_announcement_refuses(self):
        self._decision_on(-1)
        self.assertIn("outside_first_three_entry_opportunities", self.reasons())

    def test_publication_exactly_at_the_cutoff_is_outside_the_cohort(self):
        first, second = self.inputs["guidance"].receipts
        stamp = self.inputs["calendar"].cutoff(self.inputs["entry_session"]).isoformat().replace("+00:00", "Z")
        document = second.document.to_dict()
        document["published_at"] = stamp
        self.inputs["guidance"] = GuidanceLedger((first, GuidanceReceipt(
            second.raw_bytes, GuidanceDocument.from_dict(document), stamp, stamp)))
        self.assertIn("publication_not_strictly_before_cutoff", self.reasons())

    def test_missing_earlier_opportunity_evidence_refuses_a_later_session(self):
        calendar = self.inputs["calendar"]
        dropped = calendar.sessions[calendar.index(self.inputs["entry_session"]) - 20].session_date.isoformat()
        values = self.inputs["references"].to_dict()
        values["daily_bars"] = [row for row in values["daily_bars"]
                                if (row["security_id"], row["session_date"]) != ("INVENTED-SEC", dropped)]
        self.inputs["references"] = ReferenceBook.from_dict(values)
        self._decision_on(1)
        reasons = self.reasons()
        self.assertIn("earlier_opportunity_evidence_incomplete", reasons)
        self.assertNotIn("earlier_supplied_input_opportunity_already_eligible", reasons)

    def test_stock_and_benchmark_identity_mismatches_are_named(self):
        original = self.inputs["market"]
        raw = json.loads(original[0].raw_bytes)
        raw["symbol"] = "OTHER"
        self.inputs["market"] = (HistoricalMarketBatch(canonical_bytes(raw)), original[1])
        self.assertIn("stock_symbol_reference_mismatch", self.reasons())
        self.inputs["market"] = original
        values = self.inputs["references"].to_dict()
        values["references"][1]["status"] = "delisted"
        self.inputs["references"] = ReferenceBook.from_dict(values)
        self.assertIn("benchmark_security_not_listed", self.reasons())

    def test_wide_stock_decision_spread_refuses_the_entry(self):
        raw = json.loads(self.inputs["market"][0].raw_bytes)
        raw["quotes"][0]["bid_price"] = "9.9"
        self.inputs["market"] = (HistoricalMarketBatch(canonical_bytes(raw)), self.inputs["market"][1])
        self.assertIn("stock_decision_quote_refused", self.reasons())
        self.assertIsNone(self.plan()["candidates"][0]["intent"])

    def test_duplicate_security_or_second_benchmark_batch_refuses(self):
        stock, spy = self.inputs["market"]
        raw = json.loads(spy.raw_bytes)
        raw["security_id"] = "INVENTED-SPY-2"
        for market in ((stock, stock, spy), (stock, spy, HistoricalMarketBatch(canonical_bytes(raw)))):
            self.inputs["market"] = market
            with self.subTest(count=len(market)), self.assertRaises(InputError):
                self.plan()

    def test_eps_revision_breaks_an_exact_revenue_tie(self):
        self._two_events({"A-SECURITY": "1.05", "Z-SECURITY": "1.10"})
        ordered = sorted(self.plan()["candidates"], key=lambda row: row["priority_rank"])
        self.assertEqual([row["security_id"] for row in ordered], ["Z-SECURITY", "A-SECURITY"])

    def test_gross_room_accumulates_across_ranked_intents(self):
        self._two_events({"A-SECURITY": "1.10", "Z-SECURITY": "1.05"})
        self.account(pending_buys=[{"order_id": "P" + str(index), "issuer_id": "O" + str(index),
            "sector": "SECTOR-" + str(index), "reserved_notional": "15000", "reserved_fee": "1"}
            for index in range(3)])
        ordered = sorted(self.plan()["candidates"], key=lambda row: row["priority_rank"])
        self.assertEqual(ordered[0]["intent"]["whole_shares"], 495)
        self.assertIsNone(ordered[1]["intent"])
        self.assertEqual(ordered[1]["reasons"], ["insufficient_declared_cash_or_exposure_capacity"])

    def test_one_issuer_receives_at_most_one_intent_per_session(self):
        first, second = self.inputs["guidance"].receipts
        raw = canonical_bytes({"invented": "SECOND-RAISE"})
        document = second.document.to_dict()
        document.update(disclosure_id="INVENTED-RAISE-2", published_at="2025-04-01T13:00:00Z",
                        source_payload_sha256=hash_bytes(raw))
        document["periods"][0]["revenue"] = {"lower": "105000000", "upper": "105000000", "kind": "point"}
        document["periods"][0]["eps"] = {"lower": "1.11", "upper": "1.11", "kind": "point"}
        self.inputs["guidance"] = GuidanceLedger((first, second, GuidanceReceipt(
            raw, GuidanceDocument.from_dict(document), "2025-04-01T13:01:00Z", "2025-04-01T13:02:00Z")))
        rows = self.plan()["candidates"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len([row for row in rows if row["intent"] is not None]), 1)
        self.assertIn(["issuer_reserved_by_prior_ranked_intent"], [row["reasons"] for row in rows])


if __name__ == "__main__":
    unittest.main()
