"""Offline composed callback and complete account-audit acceptance tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.guidance_revision_drift.callback_plan as module
from research.guidance_revision_drift.callback_plan import (
    CallbackPlan, CallbackPlanError, PairedAccountAudit, account_row, audit_paired_accounts,
    build_callback_plan, verify_callback_plan,
)
from research.guidance_revision_drift.comparison import MatchedComparator
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant
from research.guidance_revision_drift.integration import fixture_lineage
from research.guidance_revision_drift.lineage import ProviderLineage
from research.guidance_revision_drift.market_inputs import SyntheticMarketInput
from research.guidance_revision_drift.paired_bridge import PairedSyntheticBridge, SYMBOLS
from research.guidance_revision_drift.simulation import Minute, Quote, Session, Simulation
from research.guidance_revision_drift.vendor_payloads import SyntheticGuidanceContext, VendorObservation


def encoded(value):
    return canonical_json(value).encode()


class CallbackPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = build_callback_plan()
        cls.body = cls.base.to_dict()

    def test_complete_calendar_eligibility_and_subsequent_execution_are_derived(self):
        body = self.base.to_dict()
        dates = [session.session_date.isoformat() for session in example_corpus().schedule.sessions]
        self.assertEqual([row["session"] for row in body["rows"]], dates)
        self.assertEqual(len(dates), 93)
        eligible = [row for row in body["rows"] if row["entry_eligible"]]
        self.assertEqual([row["session"] for row in eligible], ["2025-04-04"])
        for row in body["rows"]:
            for role in ("source_minute", "comparator_minute"):
                if row[role] is not None:
                    self.assertGreater(row[role]["at"], row["decision_at"])
                    self.assertEqual(row[role]["issuer"], "SYN-SPY" if role == "comparator_minute" else "SYN-ISSUER-A")
            if row["comparator_quote"] is not None:
                self.assertGreater(row["comparator_minute"]["at"], row["comparator_quote"]["at"])
        self.assertIn("preceding_session_outside_fixture", body["rows"][0]["refusals"])
        before_old = next(row for row in body["rows"] if row["session"] == "2025-02-28")
        before_raise = next(row for row in body["rows"] if row["session"] == "2025-03-31")
        self.assertEqual(before_old["receipts_seen"], 0)
        self.assertEqual(before_raise["receipts_seen"], 1)

    def test_missing_and_stale_opportunities_are_retained_without_later_retry(self):
        for recipe, message in (("missing_data", "missing_decision_market_input"),
                                ("stale_data", "future or stale")):
            with self.subTest(recipe=recipe):
                rows = build_callback_plan(recipe).rows
                self.assertEqual(len(rows), 93)
                row = next(row for row in rows if row["assessment"]["eligible_session"] is not None)
                self.assertIsNone(row["decision_quote"])
                self.assertTrue(any(message in reason for reason in row["refusals"]))
                self.assertFalse(any(row["entry_eligible"] for row in rows))
                later = next(row for row in rows if row["session"] == "2025-04-07")
                self.assertIn("earlier_eligible_opportunity_was_missed", later["refusals"])

    def test_delayed_guidance_receipt_is_not_backdated_into_entry(self):
        lineage = fixture_lineage()
        prior, current = lineage.receipts
        context = current[0].context.to_dict()
        context["received_at"] = "2025-04-08T12:01:00Z"
        context["validated_at"] = "2025-04-08T12:02:00Z"
        delayed = ProviderLineage((prior, (VendorObservation(current[0].raw_bytes,
            SyntheticGuidanceContext.from_dict(context)), False)))
        with patch.object(module, "fixture_lineage", return_value=delayed):
            rows = build_callback_plan().rows
        early = next(row for row in rows if row["session"] == "2025-04-04")
        late = next(row for row in rows if row["session"] == "2025-04-08")
        self.assertEqual(early["receipts_seen"], 1)
        self.assertFalse(early["entry_eligible"])
        self.assertEqual(late["receipts_seen"], 2)
        self.assertIn("stale_event", late["refusals"])
        self.assertFalse(any(row["entry_eligible"] for row in rows))

    def test_future_or_delayed_execution_input_refuses_without_backdated_minute(self):
        original = module._market
        def future_market(schedule, day, end, **kwargs):
            market = original(schedule, day, end, **kwargs)
            if end == fixture_instant(day, 10, 1):
                body = market.to_dict()
                body["validated_at"] = (end + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
                return SyntheticMarketInput.from_dict(body)
            return market
        with patch.object(module, "_market", side_effect=future_market):
            rows = build_callback_plan().rows
        self.assertTrue(all(row["source_minute"] is None for row in rows))
        self.assertTrue(any("unavailable as of callback" in reason for row in rows for reason in row["refusals"]))
        self.assertFalse(any(row["entry_eligible"] for row in rows))

    def test_retained_anchor_reconstruction_and_no_mutable_projection(self):
        raw = self.base.canonical_bytes
        self.assertEqual(verify_callback_plan(raw, expected_sha256=hash_bytes(raw)).canonical_bytes, raw)
        body = self.base.to_dict()
        body["rows"][0]["receipts_seen"] = 999
        self.assertNotEqual(encoded(body), self.base.canonical_bytes)
        entry_index = next(index for index, row in enumerate(self.body["rows"]) if row["entry_eligible"])
        for change in (lambda value: value["rows"].pop(),
                       lambda value: value["rows"][entry_index].update(entry_eligible=False),
                       lambda value: value.update(native_runtime_verified=True),
                       lambda value: value["rows"][entry_index]["source_minute"].update(at=value["rows"][entry_index]["decision_at"])):
            forged = deepcopy(self.body)
            change(forged)
            with self.assertRaises(CallbackPlanError):
                verify_callback_plan(encoded(forged), expected_sha256=hash_bytes(encoded(forged)))
        with self.assertRaisesRegex(CallbackPlanError, "retained anchor"):
            verify_callback_plan(raw, expected_sha256="0" * 64)
        for bad in ("real", None, True, 1):
            with self.subTest(bad=bad), self.assertRaises(CallbackPlanError):
                build_callback_plan(bad)


class AccountAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        corpus = example_corpus()
        cls.days = tuple(session.session_date for session in corpus.schedule.sessions)
        sessions = tuple(Session(s.session_date, s.open_utc, s.close_utc) for s in corpus.schedule.sessions)
        strategy, comparator = Simulation(sessions), MatchedComparator(sessions)
        rows = []
        for day in cls.days:
            strategy.close_session(day, {})
            comparator.close_session(day, Decimal("100"))
            rows.append(account_row(day, strategy.snapshot(), comparator.snapshot(),
                                    marks={"strategy": {}, "comparator": {}}))
        cls.rows = tuple(rows)
        cls.anchor = hash_payload([hash_bytes(row) for row in cls.rows])
        cls.strategy, cls.comparator = strategy.snapshot(), comparator.snapshot()

    def audit(self, observed=None, expected=None):
        expected = self.rows if expected is None else expected
        return audit_paired_accounts(self.rows if observed is None else observed, expected,
            session_dates=self.days, expected_sha256=hash_payload([hash_bytes(raw) for raw in expected])).to_dict()

    def test_complete_paired_calendar_matches_but_never_promotes_evidence(self):
        report = self.audit()
        self.assertEqual(report["calendar_rows"], 93)
        self.assertTrue(report["fixture_consistency_complete"])
        self.assertEqual(report["status"], "consistent_offline_fixture")
        for field in ("native_runtime_verified", "settlement_parity_verified", "empirical_backtest_ready",
                      "external_authenticity_verified", "execution_authorized"):
            self.assertIs(report[field], False)

    def test_forged_audit_constructor_cannot_promote_or_hide_missing_rows(self):
        report = self.audit()
        for changes in ({"native_runtime_verified": True}, {"external_authenticity_verified": True},
                        {"empirical_backtest_ready": True}, {"observed_rows": 92},
                        {"calendar_rows": True}, {"unexpected": "approval"}):
            with self.subTest(changes=changes), self.assertRaises(CallbackPlanError):
                PairedAccountAudit(encoded({**report, **changes}))

    def test_callback_plan_drives_actual_paired_fills_and_full_account_audit(self):
        bridge, rows = PairedSyntheticBridge(), []
        def acknowledge():
            while bridge.pending_receipts():
                receipt = bridge.pending_receipts()[0]
                protocol = bridge.snapshot()["protocol"]
                key = receipt["sleeve"], receipt["order_id"]
                binding = next((row for row in protocol["bindings"] if (row["sleeve"], row["order_id"]) == key), None)
                if binding is None:
                    bridge.bind(*key, len(protocol["bindings"]) + 1, SYMBOLS[key[0]])
                    binding = bridge.snapshot()["protocol"]["bindings"][-1]
                native_id = binding["native_id"]
                event_id = bridge._event_ids.get((key[0], native_id), -1) + 1
                bridge.acknowledge(key[0], native_id, event_id, symbol=receipt["symbol"], status=receipt["status"],
                    at=datetime.fromisoformat(receipt["at"]), quantity=receipt["quantity"],
                    price=Decimal(receipt["price"]), fee=Decimal(receipt["fee"]))
        def quote(body):
            return None if body is None else Quote(datetime.fromisoformat(body["at"]), Decimal(body["bid"]), Decimal(body["ask"]))
        for row in build_callback_plan().rows:
            day, at = date.fromisoformat(row["session"]), datetime.fromisoformat(row["decision_at"])
            bridge.decision(at, quote(row["decision_quote"]))
            acknowledge()
            for sleeve, field in (("strategy", "source_minute"), ("comparator", "comparator_minute")):
                body = row[field]
                if body is not None:
                    minute = Minute(body["issuer"], datetime.fromisoformat(body["at"]), Decimal(body["bid"]),
                        Decimal(body["ask"]), body["volume"], Decimal(body["adv20"]), date.fromisoformat(body["settlement_session"]))
                    bridge.minute(sleeve, minute, **({"comparator_quote": quote(row["comparator_quote"])} if sleeve == "strategy" else {}))
                    acknowledge()
            bridge.cancel(at + timedelta(minutes=5))
            acknowledge()
            state = bridge.close(day, Decimal("50"), Decimal("100"))
            marks = {"strategy": {position["issuer"]: "50" for position in state["strategy"]["positions"]},
                     "comparator": {"SYN-SPY": "100"} if any(t["quantity"] for t in state["comparator"]["tranches"]) else {}}
            rows.append(account_row(day, state["strategy"], state["comparator"], marks=marks))
        self.assertEqual(len(state["strategy"]["fills"]), 2)
        self.assertEqual(len(state["comparator"]["fills"]), 2)
        report = self.audit(tuple(rows), tuple(rows))
        self.assertTrue(report["fixture_consistency_complete"])
        held = next(module._decode(raw, module.MAX_ACCOUNT_ROW_BYTES) for raw in rows
                    if module._decode(raw, module.MAX_ACCOUNT_ROW_BYTES)["strategy"]["holdings"])
        self.assertGreater(Decimal(held["strategy"]["fees"]), 0)
        self.assertTrue(held["comparator"]["holdings"])

    def test_transient_cash_cost_quantity_mark_order_and_nav_changes_survive_liquidation(self):
        fields = ("settled_cash", "reserved_cash", "available_cash", "immediate_cash", "receivables",
                  "holdings", "fees", "marks", "pending_orders", "orders_sha256", "fills_sha256", "nav")
        for field in fields:
            with self.subTest(field=field):
                rows = list(self.rows)
                value = module._decode(rows[40], module.MAX_ACCOUNT_ROW_BYTES)
                value["strategy"][field] = ([{"tampered": True}] if field in ("receivables", "holdings", "pending_orders")
                    else {"SYN-ISSUER-A": "1"} if field == "marks" else "0" * 64 if field.endswith("sha256") else "1")
                rows[40] = encoded(value)
                if field not in ("fees", "orders_sha256", "fills_sha256"):
                    with self.assertRaises(ValueError):
                        self.audit(tuple(rows))
                else:
                    report = self.audit(tuple(rows))
                    self.assertTrue(report["terminal_flat_and_settled"])
                    self.assertFalse(report["fixture_consistency_complete"])
                    self.assertIn({"session": self.days[40].isoformat(), "field": "strategy." + field}, report["mismatches"])
        rows = list(self.rows)
        body = module._decode(rows[40], module.MAX_ACCOUNT_ROW_BYTES)
        for field in ("settled_cash", "available_cash", "immediate_cash", "nav"):
            body["strategy"][field] = "100001"
        rows[40] = encoded(body)
        self.assertFalse(self.audit(tuple(rows))["fixture_consistency_complete"])

    def test_missing_duplicate_reordered_and_wrong_epoch_rows_never_disappear(self):
        report = self.audit(self.rows[:30] + self.rows[31:])
        self.assertFalse(report["fixture_consistency_complete"])
        self.assertEqual(report["mismatches"], [{"session": self.days[30].isoformat(), "field": "missing_account_row"}])
        for rows in (self.rows[:5] + (self.rows[4],) + self.rows[6:], tuple(reversed(self.rows))):
            with self.assertRaisesRegex(CallbackPlanError, "chronological"):
                self.audit(rows)
        with self.assertRaisesRegex(CallbackPlanError, "complete fixed"):
            audit_paired_accounts(self.rows, self.rows, session_dates=self.days[:-1], expected_sha256=self.anchor)
        with self.assertRaisesRegex(CallbackPlanError, "retained anchor"):
            audit_paired_accounts(self.rows, self.rows, session_dates=self.days, expected_sha256="0" * 64)

    def test_permanent_parity_terminal_and_missing_nav_block_even_after_later_flat_close(self):
        for sleeve, field, value in (("comparator", "permanent_blockers", ["unmatched_terminal"]),
                                    ("strategy", "nav", None)):
            rows = list(self.rows)
            body = module._decode(rows[45], module.MAX_ACCOUNT_ROW_BYTES)
            body[sleeve][field] = value
            if field == "nav":
                body[sleeve]["holdings"] = [{"issuer": "SYN-ISSUER-A", "quantity": 1}]
                body[sleeve]["marks"] = {"SYN-ISSUER-A": None}
                body[sleeve]["terminal_complete"] = False
            else:
                body[sleeve]["terminal_complete"] = False
            rows[45] = encoded(body)
            report = self.audit(tuple(rows), tuple(rows))
            self.assertTrue(report["terminal_flat_and_settled"])
            self.assertFalse(report["fixture_consistency_complete"])
            self.assertTrue(report["permanent_blockers"])
        rows = list(self.rows)
        body = module._decode(rows[-1], module.MAX_ACCOUNT_ROW_BYTES)
        body["comparator"]["terminal_complete"] = False
        rows[-1] = encoded(body)
        with self.assertRaisesRegex(CallbackPlanError, "terminal status"):
            self.audit(tuple(rows), tuple(rows))

    def test_reanchored_matching_final_account_cannot_self_assert_liquidation(self):
        value = module._decode(self.rows[-1], module.MAX_ACCOUNT_ROW_BYTES)
        value["strategy"].update(holdings=[{"issuer": "SYN-ISSUER-A", "quantity": 98}],
            pending_orders=[{"order_id": "SYN-FORGED", "quantity": 1, "remaining": 1,
                             "side": "buy", "status": "open", "reserved_notional": "999", "reserved_fee": "1"}],
            receivables=[{"id": "SYN-FORGED-PAYMENT", "amount": "100", "pay_session": "2025-05-15"}],
            reserved_cash="1000", terminal_complete=True)
        rows = self.rows[:-1] + (encoded(value),)
        with self.assertRaises(ValueError):
            self.audit(rows, rows)
        for change in (lambda row: row.update(reserved_cash="1000"),
                       lambda row: row.update(holdings=[{"issuer": "SYN-ISSUER-A", "quantity": True}]),
                       lambda row: row.update(receivables=[{"id": "SYN-BAD", "amount": "NaN", "pay_session": "2025-05-14"}]),
                       lambda row: row.update(pending_orders=[{"order_id": "SYN-BAD", "remaining": 2, "quantity": 1, "side": "buy", "status": "open"}]),
                       lambda row: row.update(marks={"SYN-ISSUER-A": "1"}),
                       lambda row: row.update(nav="1")):
            body = module._decode(self.rows[-1], module.MAX_ACCOUNT_ROW_BYTES)
            change(body["strategy"])
            forged = self.rows[:-1] + (encoded(body),)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.audit(forged, forged)

    def test_coherent_open_position_never_claims_terminal_flatness(self):
        value = module._decode(self.rows[-1], module.MAX_ACCOUNT_ROW_BYTES)
        value["strategy"].update(holdings=[{"issuer": "SYN-ISSUER-A", "quantity": 1}],
            marks={"SYN-ISSUER-A": "50"}, nav="100050", terminal_complete=False)
        rows = self.rows[:-1] + (encoded(value),)
        self.assertFalse(self.audit(rows, rows)["fixture_consistency_complete"])
        value["strategy"]["terminal_complete"] = True
        rows = self.rows[:-1] + (encoded(value),)
        with self.assertRaisesRegex(CallbackPlanError, "terminal status"):
            self.audit(rows, rows)

    def _flat_first_close_projection(self):
        corpus = example_corpus()
        day = corpus.schedule.sessions[0].session_date
        sessions = tuple(Session(x.session_date, x.open_utc, x.close_utc) for x in corpus.schedule.sessions)
        strategy, comparator = Simulation(sessions), MatchedComparator(sessions)
        strategy.close_session(day, {})
        comparator.close_session(day, None)
        row = module.account_row(day, strategy.snapshot(), comparator.snapshot(),
                                 marks={"strategy": {}, "comparator": {}})
        projection = __import__("json").loads(row)["strategy"]
        module._checked_account(projection, sleeve="strategy", day=day)
        return projection, day

    def test_account_semantics_refuse_a_phantom_reservation_with_no_pending_order(self):
        # The audit's expected rows are caller-supplied under a retained anchor,
        # so a forged but matching pair must still be refused on its own
        # semantics. Reserved cash with no pending order, kept arithmetically
        # consistent with available cash, is otherwise a "complete" flat row.
        projection, day = self._flat_first_close_projection()
        settled = Decimal(projection["settled_cash"])
        forged = dict(projection, reserved_cash="10", available_cash=str(settled - Decimal("10")))
        with self.assertRaisesRegex(module.CallbackPlanError, "observed reservation differs from pending orders"):
            module._checked_account(forged, sleeve="strategy", day=day)

    def test_account_semantics_refuse_a_receivable_dated_on_its_own_close(self):
        # A receivable paid on or before the observed close should already be
        # settled cash; an otherwise self-consistent forged row carrying one
        # must be refused rather than accepted as unsettled proceeds.
        projection, day = self._flat_first_close_projection()
        settled = Decimal(projection["settled_cash"])
        forged = dict(projection,
                      receivables=[{"id": "SYN-PAST-PROCEEDS", "kind": "sale", "amount": "10",
                                    "pay_session": day.isoformat()}],
                      immediate_cash=str(settled + Decimal("10")), nav=str(settled + Decimal("10")),
                      terminal_complete=False)
        with self.assertRaisesRegex(module.CallbackPlanError, "future-dated receivable"):
            module._checked_account(forged, sleeve="strategy", day=day)

    def test_snapshot_nav_cash_marks_and_non_synthetic_inputs_refuse_atomically(self):
        original = encoded((self.strategy, self.comparator)[0])
        for change in (lambda value: value.update(available_cash="1"),
                       lambda value: value["navs"][-1].update(nav="1"),
                       lambda value: value.update(synthetic_only=1),
                       lambda value: value["positions"].append({"issuer": "AAPL", "quantity": 1})):
            value = deepcopy(self.strategy)
            change(value)
            with self.assertRaises(ValueError):
                account_row(self.days[-1], value, self.comparator, marks={"strategy": {}, "comparator": {}})
        self.assertEqual(encoded(self.strategy), original)
        for raw in (b'{"schema":1,"schema":1}', b'{"value":NaN}', b'{"value":1.1}', b"{}"):
            with self.assertRaises(ValueError):
                self.audit((raw,))
        body = module._decode(self.rows[0], module.MAX_ACCOUNT_ROW_BYTES)
        for field in ("native_runtime_verified", "external_authenticity_verified", "settlement_parity_verified"):
            hostile = deepcopy(body)
            hostile[field] = True
            with self.assertRaisesRegex(CallbackPlanError, "nonpromoting"):
                self.audit((encoded(hostile),) + self.rows[1:])


if __name__ == "__main__":
    unittest.main()
