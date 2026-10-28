"""Invented full order/cash rehearsals; no empirical, provider or native result."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
import json
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import load_candidate
from research.guidance_revision_drift.execution_contract import ExecutionContract, default_contract
from research.guidance_revision_drift.guidance_inputs import GuidanceDocument, GuidanceReceipt, GuidanceLedger
from research.guidance_revision_drift.historical_market import HistoricalMarketBatch, instant_ns
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes
from research.guidance_revision_drift.multi_session import MultiSessionReplay, run_replay
from research.guidance_revision_drift.pre_qc import rehearsal_inputs
from research.guidance_revision_drift.research_reference import CalendarInput, ReferenceBook, NY


def at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), NY).astimezone(timezone.utc)


def inputs(count=23, *, volume=50000):
    source = rehearsal_inputs()
    calendar = source["calendar"]
    start = calendar.index(source["entry_session"])
    dates = tuple(row.session_date for row in calendar.sessions[start:start + count])
    market = []
    for session_date in dates:
        for original in source["market"]:
            body = json.loads(original.raw_bytes)
            price = "53" if body["role"] == "benchmark" else "10"
            body.update(session_date=session_date.isoformat(), session_open_utc=at(session_date, 9, 30).isoformat().replace("+00:00", "Z"),
                        session_close_utc=at(session_date, 16).isoformat().replace("+00:00", "Z"))
            body["quotes"] = [{"bid_price": price, "ask_price": price, "bid_size": 10000, "ask_size": 10000,
                "sip_timestamp": instant_ns(at(session_date, 10, minute) - timedelta(seconds=1)),
                "participant_timestamp": instant_ns(at(session_date, 10, minute) - timedelta(seconds=1)),
                "sequence_number": minute + 1, "conditions": []} for minute in range(7)]
            body["minutes"] = [{"o": price, "h": price, "l": price, "c": price,
                "v": volume, "t": instant_ns(at(session_date, 10, minute)) // 1000000} for minute in range(6)]
            market.append(HistoricalMarketBatch(canonical_bytes(body)))
    settlement_days = tuple(row.session_date for row in calendar.sessions)
    return {"candidate": load_candidate(), "calendar": calendar, "references": source["references"],
        "guidance": source["guidance"], "market_batches": tuple(market),
        "contract": default_contract(settlement_days, calendar_source_sha256=hash_bytes(b"INVENTED-SERVICE-DAYS")),
        "first_session": dates[0], "last_session": dates[-1]}


def action(data, kind, *, index=1, security="INVENTED-SEC", cash=None, ratio=None, minute=None):
    dates = data["calendar"].sessions
    session_date = dates[data["calendar"].index(data["first_session"]) + index].session_date
    effective = at(session_date, 9, 30) if minute is None else at(session_date, 10, minute)
    pay = dates[data["calendar"].index(session_date) + 1].session_date.isoformat() if cash is not None else None
    return {"action_id": "INVENTED-ACTION", "security_id": security, "kind": kind,
        "effective_at": effective.isoformat().replace("+00:00", "Z"),
        "received_at": (effective - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "validated_at": (effective - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "source_sha256": hash_bytes(b"INVENTED-ACTION-ECONOMICS"),
        "ratio": ratio, "cash_per_share": cash, "pay_date": pay}


class MultiSessionTests(unittest.TestCase):
    def test_actual_full_replay_reconciles_cash_and_both_order_based_sleeves(self):
        data = inputs()
        result = run_replay(**data)
        self.assertTrue(result["complete_software_replay"])
        self.assertEqual(len(result["daily_nav"]), 23)
        stock, spy = result["strategy"], result["comparator"]
        self.assertEqual([row["quantity"] for row in stock["fills"]], [495, 495])
        self.assertEqual([row["side"] for row in stock["fills"]], ["buy", "sell"])
        self.assertEqual([row["quantity"] for row in spy["fills"]], [92, 92])
        self.assertEqual(Decimal(stock["settled_cash"]), Decimal("99990.1000"))
        self.assertEqual(Decimal(spy["settled_cash"]), Decimal("99993.1240"))
        self.assertEqual(stock["positions"], [])
        self.assertTrue(all(row["quantity"] == 0 for row in spy["positions"]))
        self.assertEqual(stock["receivables"], [])
        self.assertEqual(spy["receivables"], [])
        self.assertFalse(result["comparison_parity_blocked"])
        self.assertEqual(result["permanent_parity_blockers"], [])
        reconciliation = spy["positions"][0]["entry_budget_reconciliation"]
        self.assertEqual(Decimal(reconciliation["admission_rounding_cash"]), Decimal("29.1900"))
        self.assertEqual(Decimal(reconciliation["released_price_reserve"]), Decimal("46.3220"))
        self.assertEqual(Decimal(reconciliation["actual_cash_residual"]), Decimal("75.5120"))
        self.assertTrue(reconciliation["within_rounding"])
        for fill in stock["fills"] + spy["fills"]:
            self.assertGreater(fill["quote_sip_ns"], instant_ns(datetime.fromisoformat(
                next(order["submitted_at"] for order in stock["orders"] + spy["orders"] if order["order_id"] == fill["order_id"]).replace("Z", "+00:00"))))
            self.assertEqual(fill["minute_end_ns"], instant_ns(datetime.fromisoformat(fill["at"].replace("Z", "+00:00"))))
        for field in ("native_execution_verified", "backtest_ready", "point_in_time_data", "source_rights_verified",
                      "settlement_calendar_verified", "independent_review_complete", "empirical_evaluation_allowed",
                      "qc_access_allowed", "real_orders_allowed"):
            self.assertIs(result[field], False)
        self.assertEqual(result["empirical_looks"], 0)
        self.assertEqual(result["qc_attempts"], 0)

    def test_duplicate_session_and_run_are_idempotent_and_detached(self):
        replay = MultiSessionReplay(**inputs(count=2))
        first = replay.step_session(replay.days[0])
        before = canonical_bytes(replay.snapshot())
        first["state_sha256"] = "0" * 64
        self.assertNotEqual(replay.step_session(replay.days[0]), first)
        self.assertEqual(canonical_bytes(replay.snapshot()), before)
        replay.run()
        self.assertEqual(canonical_bytes(replay.run()), canonical_bytes(replay.snapshot()))
        changed = next(iter(replay.market))
        raw = json.loads(replay.market[changed].raw_bytes)
        raw["minutes"][0]["v"] += 1
        replay.market[changed] = HistoricalMarketBatch(canonical_bytes(raw))
        with self.assertRaises(InputError):
            replay.step_session(replay.days[0])

    def test_nonchronological_step_and_noninvented_or_protected_run_refuse(self):
        data = inputs(count=2)
        replay = MultiSessionReplay(**data)
        with self.assertRaises(InputError):
            replay.step_session(replay.days[1])
        self.assertEqual(replay.snapshot()["strategy"]["orders"], [])
        for data_class in ("historical_reconstruction", "provider_capture", "approved", True):
            with self.subTest(data_class=data_class), self.assertRaises(InputError):
                MultiSessionReplay(**data, data_class=data_class)
        data["last_session"] = date(2026, 9, 1)
        with self.assertRaises(InputError):
            MultiSessionReplay(**data)

    def test_partial_source_fills_keep_one_commission_and_matching_tranches(self):
        result = run_replay(**inputs(count=2, volume=10000))
        stock = result["strategy"]
        buys = [row for row in stock["fills"] if row["side"] == "buy"]
        self.assertEqual([row["quantity"] for row in buys], [100, 100, 100, 100, 95])
        self.assertEqual(sum(Decimal(row["fee"]) for row in buys), Decimal("2.475"))
        self.assertEqual(len(result["comparator"]["positions"]), 5)
        self.assertEqual(len(result["comparator"]["fills"]), 5)
        self.assertTrue(all(row["at"] > source["at"] for row, source in zip(result["comparator"]["fills"], buys)))
        self.assertFalse(result["complete_software_replay"])

    def test_entry_remainder_cancels_without_topup_or_fee_reset(self):
        data = inputs(count=2, volume=1000)
        result = run_replay(**data)
        order = result["strategy"]["orders"][0]
        self.assertEqual(order["status"], "cancelled")
        self.assertEqual(order["filled_quantity"], 50)
        self.assertEqual(Decimal(order["reserved_notional"]), 0)
        self.assertEqual(Decimal(order["reserved_fee"]), 0)
        self.assertEqual(Decimal(order["fees_paid"]), 1)
        self.assertEqual(len([row for row in result["strategy"]["orders"] if row["side"] == "buy"]), 1)

    def test_time_exit_is_session_21_and_sale_cash_waits_for_dated_settlement(self):
        data = inputs()
        replay = MultiSessionReplay(**data)
        for session_date in replay.days[:21]:
            replay.step_session(session_date)
        result = replay.snapshot()
        sells = [row for row in result["strategy"]["fills"] if row["side"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["at"][:10], replay.days[20].isoformat())
        self.assertEqual(sells[0]["exit_reason"], "time")
        self.assertTrue(result["strategy"]["receivables"])
        self.assertEqual(Decimal(result["strategy"]["settled_cash"]), Decimal("95045.05"))
        replay.step_session(replay.days[21])
        self.assertEqual(replay.snapshot()["strategy"]["receivables"], [])

    def test_explicit_dividend_is_entitled_once_and_not_spendable_before_pay_date(self):
        data = inputs(count=2)
        value = action(data, "dividend", cash="1")
        result = run_replay(**data, actions=(value, deepcopy(value)))
        dividend = [row for row in result["strategy"]["receivables"] if row["kind"] == "dividend"]
        self.assertEqual(len(dividend), 1)
        self.assertEqual(Decimal(dividend[0]["amount"]), 495)
        self.assertEqual(Decimal(result["strategy"]["settled_cash"]), Decimal("95045.05"))
        conflict = deepcopy(value)
        conflict["cash_per_share"] = "2"
        with self.assertRaises(InputError):
            MultiSessionReplay(**data, actions=(value, conflict))

    def test_cash_terminal_is_not_a_stock_fill_or_a_spy_cash_injection(self):
        data = inputs(count=4)
        value = action(data, "terminal_cash", cash="7")
        result = run_replay(**data, actions=(value,))
        self.assertTrue(result["complete_software_replay"])
        self.assertEqual(len(result["strategy"]["fills"]), 1)
        self.assertEqual(result["strategy"]["positions"], [])
        self.assertEqual(Decimal(result["strategy"]["settled_cash"]), Decimal("98510.05"))
        spy_sells = [row for row in result["comparator"]["fills"] if row["side"] == "sell"]
        self.assertEqual(len(spy_sells), 1)
        self.assertEqual(spy_sells[0]["at"][:10], data["calendar"].sessions[data["calendar"].index(data["first_session"]) + 1].session_date.isoformat())
        self.assertEqual(spy_sells[0]["exit_reason"], "terminal_entitlement")
        self.assertFalse(any(row["kind"] == "terminal_cash" and row["sleeve"] == "comparator" for row in result["cash_movements"]))

    def test_unresolved_terminal_keeps_exposure_and_stops_callback_fills(self):
        data = inputs(count=3)
        result = run_replay(**data, actions=(action(data, "terminal_unresolved"),))
        self.assertFalse(result["complete_software_replay"])
        self.assertEqual(result["strategy"]["positions"][0]["quantity"], 495)
        self.assertTrue(result["unresolved"])
        self.assertIsNone(result["daily_nav"][-1]["strategy_nav"])
        self.assertFalse(any(row["side"] == "sell" for row in result["strategy"]["fills"]))
        data = inputs(count=1)
        result = run_replay(**data, actions=(action(data, "terminal_unresolved", index=0, minute=1),))
        self.assertEqual(result["strategy"]["fills"], [])
        self.assertEqual(result["strategy"]["orders"][0]["status"], "cancelled")

    def test_future_or_missing_daily_mark_never_becomes_zero_or_previous_close(self):
        data = inputs(count=2)
        values = data["references"].to_dict()
        last = data["last_session"].isoformat()
        for row in values["daily_bars"]:
            if row["security_id"] == "INVENTED-SEC" and row["session_date"] == last:
                row["validated_at"] = at(data["last_session"], 18, 1).isoformat().replace("+00:00", "Z")
        data["references"] = ReferenceBook.from_dict(values)
        result = run_replay(**data)
        self.assertIsNone(result["daily_nav"][-1]["strategy_nav"])
        self.assertFalse(result["complete_software_replay"])

    def test_18_cutoff_accepts_a_daily_close_validated_after_1605_not_before_known(self):
        data = inputs(count=1)
        values = data["references"].to_dict()
        for row in values["daily_bars"]:
            if row["session_date"] == data["first_session"].isoformat():
                row["validated_at"] = at(data["first_session"], 17).isoformat().replace("+00:00", "Z")
        data["references"] = ReferenceBook.from_dict(values)
        result = run_replay(**data)
        self.assertIsNotNone(result["daily_nav"][0]["strategy_nav"])
        self.assertEqual(result["daily_nav"][0]["observed_at"], at(data["first_session"], 18).isoformat().replace("+00:00", "Z"))

    def test_ambient_decimal_and_pure_boundaries_do_not_change_replay(self):
        data = inputs(count=2)
        expected = canonical_bytes(run_replay(**data))
        with localcontext() as context, patch("builtins.open", side_effect=AssertionError("file forbidden")), \
                patch("socket.socket.connect", side_effect=AssertionError("network forbidden")), \
                patch("subprocess.run", side_effect=AssertionError("process forbidden")):
            context.prec = 2
            self.assertEqual(canonical_bytes(run_replay(**data)), expected)

    def test_separate_positive_parity_fixture_keeps_its_original_execution(self):
        data = inputs()
        batches = []
        for batch in data["market_batches"]:
            raw = json.loads(batch.raw_bytes)
            if raw["role"] == "benchmark":
                for quote in raw["quotes"]:
                    quote["bid_price"] = quote["ask_price"] = "100"
                for minute in raw["minutes"]:
                    for name in ("o", "h", "l", "c"):
                        minute[name] = "100"
            batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        references = data["references"].to_dict()
        for row in references["daily_bars"]:
            if row["security_id"] == "INVENTED-SPY":
                row["raw_close"] = "100"
        data["references"], data["market_batches"] = ReferenceBook.from_dict(references), tuple(batches)
        result = run_replay(**data)
        self.assertTrue(result["complete_software_replay"])
        self.assertFalse(result["comparison_parity_blocked"])
        self.assertEqual([row["quantity"] for row in result["comparator"]["fills"]], [49, 49])

    def test_partial_spy_risk_exit_carries_same_order_and_fee_across_sessions(self):
        data = inputs()
        exit_date = data["calendar"].sessions[data["calendar"].index(data["first_session"]) + 20].session_date
        batches = []
        for batch in data["market_batches"]:
            raw = json.loads(batch.raw_bytes)
            if batch.role == "benchmark" and batch.session_date == exit_date:
                for minute in raw["minutes"]:
                    minute["v"] = 1000
            batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        data["market_batches"] = tuple(batches)
        result = run_replay(**data)
        sells = [row for row in result["comparator"]["fills"] if row["side"] == "sell"]
        self.assertTrue(result["complete_software_replay"])
        self.assertEqual(sum(row["quantity"] for row in sells), 92)
        self.assertEqual(len({row["order_id"] for row in sells}), 1)
        self.assertEqual(sum(Decimal(row["fee"]) for row in sells), 1)
        self.assertEqual(sells[-1]["at"][:10], data["calendar"].sessions[data["calendar"].index(exit_date) + 1].session_date.isoformat())
        self.assertTrue(result["comparison_parity_blocked"])

    def test_twelve_shared_capacity_orders_use_creation_order_not_lexical_ids(self):
        replay = MultiSessionReplay(**inputs(count=1, volume=1000))
        when = at(replay.days[0], 10)
        for index in range(12):
            key = "INVENTED-TRANCHE-" + str(index)
            replay._state["tranches"][key] = {"tranche_id": key, "source_security_id": "INVENTED-SEC",
                "quantity": 0, "source_budget": Decimal("100"), "entry_spent": Decimal(0)}
            replay._order("comparator", replay.spy, "buy", 1, when, Decimal("159000000"),
                          limit=Decimal("53.53"), tranche=key)
        replay._fill_orders("comparator", when + timedelta(minutes=1))
        self.assertEqual([row["order_id"] for row in replay._state["fills"]],
                         ["OFFLINE-ORDER-" + str(index) for index in range(1, 11)])

    def test_fractional_scheduled_split_quantity_refuses_before_mutating_holdings(self):
        data = inputs(count=2)
        replay = MultiSessionReplay(**data, actions=(action(data, "split", ratio="0.4"),))
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[1], "trim", 3)
        replay.step_session(replay.days[1])
        self.assertEqual(replay.snapshot()["strategy"]["positions"][0]["quantity"], 495)
        self.assertEqual(replay._state["due"]["INVENTED-SEC"]["trim"]["quantity"], 3)
        self.assertEqual(replay.snapshot()["unresolved"]["INVENTED-SEC"], "fractional_split_cash_in_lieu_unsupported")

    def test_preclose_publication_cannot_be_a_complete_daily_close(self):
        data = inputs(count=1)
        values = data["references"].to_dict()
        for row in values["daily_bars"]:
            if row["security_id"] == "INVENTED-SEC" and row["session_date"] == data["first_session"].isoformat():
                for field in ("published_at", "received_at", "validated_at"):
                    row[field] = at(data["first_session"], 15).isoformat().replace("+00:00", "Z")
        data["references"] = ReferenceBook.from_dict(values)
        result = run_replay(**data)
        self.assertIsNone(result["daily_nav"][0]["strategy_nav"])

    def test_runtime_spy_identity_mutation_invalidates_even_a_cached_retry(self):
        replay = MultiSessionReplay(**inputs(count=1))
        replay.step_session(replay.days[0])
        replay.spy = "INVENTED-SEC"
        with self.assertRaises(InputError):
            replay.step_session(replay.days[0])

    def test_terminal_source_cancels_spy_entry_before_same_callback_fill(self):
        data = inputs(count=3)
        result = run_replay(**data, actions=(action(data, "terminal_cash", index=0, minute=2, cash="7"),))
        self.assertEqual(result["comparator"]["fills"], [])
        self.assertEqual(result["comparator"]["orders"][0]["status"], "cancelled")
        self.assertEqual(Decimal(result["comparator"]["settled_cash"]), Decimal("100000"))
        self.assertTrue(result["comparison_parity_blocked"])

    def test_late_known_terminal_timing_is_permanent_even_without_intervening_trade(self):
        data = inputs(count=4)
        value = action(data, "terminal_cash", cash="7")
        effective = datetime.fromisoformat(value["effective_at"].replace("Z", "+00:00"))
        value["received_at"] = (effective + timedelta(minutes=32)).isoformat().replace("+00:00", "Z")
        value["validated_at"] = (effective + timedelta(minutes=33)).isoformat().replace("+00:00", "Z")
        result = run_replay(**data, actions=(value,))
        self.assertTrue(result["complete_software_replay"])
        self.assertIn("late_known_terminal_comparator_timing_mismatch", [row["reason"] for row in result["permanent_parity_blockers"]])

    def test_unordered_simultaneous_same_security_actions_refuse_in_both_orders(self):
        data = inputs(count=2)
        split, dividend = action(data, "split", ratio="2"), action(data, "dividend", cash="1")
        dividend["action_id"] = "INVENTED-DIVIDEND"
        for rows in ((split, dividend), (dividend, split)):
            with self.subTest(order=[row["kind"] for row in rows]), self.assertRaises(InputError):
                MultiSessionReplay(**data, actions=rows)

    def test_future_invalidation_never_expands_an_earlier_due_trim(self):
        replay = MultiSessionReplay(**inputs(count=4))
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[1], "trim", 100)
        replay._schedule("INVENTED-SEC", replay.days[2], "guidance_invalidation", 495)
        replay.step_session(replay.days[1])
        sells = [row for row in replay.snapshot()["strategy"]["fills"] if row["side"] == "sell"]
        self.assertEqual([row["quantity"] for row in sells], [100])
        self.assertEqual(sells[0]["exit_reason"], "trim")
        replay.step_session(replay.days[2])
        sells = [row for row in replay.snapshot()["strategy"]["fills"] if row["side"] == "sell"]
        self.assertEqual([row["quantity"] for row in sells], [100, 395])
        self.assertEqual(sells[-1]["exit_reason"], "guidance_invalidation")

    def test_tiny_spy_quote_affordability_is_logarithmically_bounded(self):
        data = inputs(count=1)
        batches = []
        for batch in data["market_batches"]:
            raw = json.loads(batch.raw_bytes)
            if batch.role == "benchmark":
                for quote in raw["quotes"]:
                    quote["bid_price"] = quote["ask_price"] = "0.001"
                for minute in raw["minutes"]:
                    for field in ("o", "h", "l", "c"):
                        minute[field] = "0.001"
            batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        data["market_batches"] = tuple(batches)
        original = ExecutionContract.commission
        calls = []
        def counted(contract, quantity, mode):
            calls.append(quantity)
            if len(calls) > 100:
                raise AssertionError("unbounded fee-affordability iteration")
            return original(contract, quantity, mode)
        with patch.object(ExecutionContract, "commission", counted):
            result = run_replay(**data)
        self.assertLess(len(calls), 100)
        self.assertTrue(result["comparator"]["orders"])

    def test_risk_exit_does_not_require_new_entry_price_or_liquidity_floor(self):
        data = inputs(count=4)
        dates = data["calendar"].sessions
        start = data["calendar"].index(data["first_session"])
        trigger = dates[start + 1].session_date
        exit_date = dates[start + 2].session_date
        book = data["references"].to_dict()
        for row in book["daily_bars"]:
            if row["security_id"] == "INVENTED-SEC" and row["session_date"] >= trigger.isoformat():
                row["raw_close"] = "2"
        batches = []
        for batch in data["market_batches"]:
            raw = json.loads(batch.raw_bytes)
            if batch.role == "stock" and batch.session_date >= exit_date:
                for quote in raw["quotes"]:
                    quote["bid_price"] = quote["ask_price"] = "2"
                for minute in raw["minutes"]:
                    for field in ("o", "h", "l", "c"):
                        minute[field] = "2"
            batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        data["references"], data["market_batches"] = ReferenceBook.from_dict(book), tuple(batches)
        result = run_replay(**data)
        sells = [row for row in result["strategy"]["fills"] if row["side"] == "sell"]
        self.assertEqual(sells[0]["exit_reason"], "position_stop")
        self.assertEqual(sells[0]["at"][:10], exit_date.isoformat())
        self.assertEqual(sells[0]["quantity"], 495)

    def test_new_sector_and_symbol_are_asof_and_old_symbol_cannot_fill_exit(self):
        data = inputs(count=3)
        tomorrow = data["calendar"].sessions[data["calendar"].index(data["first_session"]) + 1].session_date
        values = data["references"].to_dict()
        old = values["references"][0]
        new = {**old, "valid_from": tomorrow.isoformat(), "sector": "utilities", "symbol": "RENAMED"}
        old["valid_through"] = data["first_session"].isoformat()
        values["references"].append(new)
        data["references"] = ReferenceBook.from_dict(values)
        replay = MultiSessionReplay(**data)
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[1], "position_stop", 495)
        replay.step_session(replay.days[1])
        position = replay.snapshot()["strategy"]["positions"][0]
        self.assertEqual(position["sector"], "utilities")
        self.assertEqual(position["entry_sector"], "technology")
        self.assertEqual(position["symbol"], "RENAMED")
        self.assertFalse(any(row["side"] == "sell" for row in replay.snapshot()["strategy"]["fills"]))
        batches = []
        for batch in data["market_batches"]:
            raw = json.loads(batch.raw_bytes)
            if batch.role == "stock" and batch.session_date >= tomorrow:
                raw["symbol"] = "RENAMED"
            batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        data["market_batches"] = tuple(batches)
        replay = MultiSessionReplay(**data)
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[1], "position_stop", 495)
        replay.step_session(replay.days[1])
        self.assertEqual([row["quantity"] for row in replay.snapshot()["strategy"]["fills"] if row["side"] == "sell"], [495])

    def test_bank_payment_day_can_be_absent_from_trading_calendar(self):
        data = inputs(count=4)
        value = action(data, "dividend", cash="1")
        bank_day = value["pay_date"]
        calendar = data["calendar"].to_dict()
        calendar["sessions"] = [row for row in calendar["sessions"] if row["date"] != bank_day]
        data["calendar"] = CalendarInput.from_dict(calendar)
        references = data["references"].to_dict()
        references["calendar_sha256"] = data["calendar"].sha256
        data["references"] = ReferenceBook.from_dict(references)
        data["market_batches"] = tuple(batch for batch in data["market_batches"] if batch.session_date.isoformat() != bank_day)
        result = run_replay(**data, actions=(value,))
        self.assertEqual(Decimal(result["strategy"]["settled_cash"]), Decimal("95540.05"))
        self.assertFalse(any(row["kind"] == "dividend" for row in result["strategy"]["receivables"]))

    def test_invalidation_racing_partial_entry_exits_every_actual_share(self):
        data = inputs(count=4, volume=10000)
        document = data["guidance"].receipts[-1].document.to_dict()
        raw = canonical_bytes({"invented": "WITHDRAWAL"})
        announced = at(data["first_session"], 10, 1) + timedelta(seconds=15)
        validated = at(data["first_session"], 10, 2)
        document.update(disclosure_id="INVENTED-WITHDRAWAL", kind="withdrawal", supersedes="INVENTED-RAISE",
            published_at=announced.isoformat().replace("+00:00", "Z"), periods=[], source_payload_sha256=hash_bytes(raw))
        data["guidance"] = data["guidance"].append(GuidanceReceipt(raw, GuidanceDocument.from_dict(document),
            (announced + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"), validated.isoformat().replace("+00:00", "Z")))
        result = run_replay(**data)
        buys = [row for row in result["strategy"]["fills"] if row["side"] == "buy"]
        sells = [row for row in result["strategy"]["fills"] if row["side"] == "sell"]
        self.assertEqual([row["quantity"] for row in buys], [100, 100])
        self.assertEqual(sum(row["quantity"] for row in sells), 200)
        self.assertTrue(all(row["exit_reason"] == "guidance_invalidation" for row in sells))
        self.assertEqual(result["strategy"]["positions"], [])

    def test_paired_nav_gap_blocks_even_flat_new_entry_planning(self):
        replay = MultiSessionReplay(**inputs(count=2))
        first_day = replay.days[0]
        replay._state["daily_nav"].append({"session_date": first_day - timedelta(days=1),
                                          "strategy_nav": Decimal("100000"), "comparator_nav": None})
        replay._entries(at(first_day, 10))
        self.assertEqual(replay._state["orders"], {})
        self.assertIn("entry_control_unresolved_valuations", [row["reason"] for row in replay._state["refusals"]])

    def test_program_drawdown_stops_entries_but_completes_next_session_liquidation(self):
        data = inputs(count=4)
        source = data["guidance"].receipts
        originals, revised, books, batches = [], [], data["references"].to_dict(), []
        template = books["references"][0]
        bars = [row for row in books["daily_bars"] if row["security_id"] == "INVENTED-SEC"]
        trigger = data["calendar"].sessions[data["calendar"].index(data["first_session"]) + 1].session_date
        for index in range(4):
            security, issuer = "INVENTED-SEC-" + str(index), "INVENTED-ISSUER-" + str(index)
            for target, original in ((originals, source[0]), (revised, source[1])):
                doc = original.document.to_dict()
                doc.update(security_id=security, issuer_id=issuer, disclosure_id=doc["disclosure_id"] + "-" + str(index))
                target.append(GuidanceReceipt(original.raw_bytes, GuidanceDocument.from_dict(doc), original.received_at, original.validated_at))
            books["references"].append({**template, "security_id": security, "issuer_id": issuer, "sector": "SECTOR-" + str(index)})
            books["daily_bars"].extend({**row, "security_id": security,
                "raw_close": "2" if row["session_date"] >= trigger.isoformat() else "10"} for row in bars)
            for batch in data["market_batches"]:
                if batch.role != "stock":
                    continue
                raw = json.loads(batch.raw_bytes)
                raw["security_id"] = security
                if batch.session_date > trigger:
                    for quote in raw["quotes"]:
                        quote["bid_price"] = quote["ask_price"] = "2"
                    for minute in raw["minutes"]:
                        for field in ("o", "h", "l", "c"):
                            minute[field] = "2"
                batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        data["guidance"] = GuidanceLedger(tuple(originals + revised))
        data["references"] = ReferenceBook.from_dict(books)
        data["market_batches"] = tuple(batches) + tuple(batch for batch in data["market_batches"] if batch.role == "benchmark")
        result = run_replay(**data)
        self.assertTrue(result["program_stop_active"])
        self.assertEqual(result["strategy"]["positions"], [])
        self.assertEqual([row["exit_reason"] for row in result["strategy"]["fills"] if row["side"] == "sell"], ["program_drawdown"] * 4)
        self.assertEqual(len(result["daily_nav"]), 4)


# GDR-CR53-002/003 helpers. Every row stays invented; each helper rewrites only
# the named invented field and keeps the strict contracts' own validation.
def stamp(value):
    return value.isoformat().replace("+00:00", "Z")


def session(data, offset):
    calendar = data["calendar"]
    return calendar.sessions[calendar.index(data["first_session"]) + offset].session_date


def edit_batches(data, edit):
    batches = []
    for batch in data["market_batches"]:
        raw = json.loads(batch.raw_bytes)
        edit(batch, raw)
        batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
    data["market_batches"] = tuple(batches)


def edit_bars(data, edit):
    book = data["references"].to_dict()
    for row in book["daily_bars"]:
        edit(row)
    data["references"] = ReferenceBook.from_dict(book)


def reprice(data, role, price, *, from_date=None):
    security = "INVENTED-SPY" if role == "benchmark" else "INVENTED-SEC"

    def quotes(batch, raw):
        if batch.role == role and (from_date is None or batch.session_date >= from_date):
            for quote in raw["quotes"]:
                quote["bid_price"] = quote["ask_price"] = price
            for minute in raw["minutes"]:
                for field in ("o", "h", "l", "c"):
                    minute[field] = price

    def closes(row):
        if row["security_id"] == security and (from_date is None or row["session_date"] >= from_date.isoformat()):
            row["raw_close"] = price
    edit_batches(data, quotes)
    edit_bars(data, closes)


def redate(data, security, from_date, *, clock=None, keep_old=False, **changes):
    book = data["references"].to_dict()
    old = next(row for row in book["references"] if row["security_id"] == security)
    new = {**old, "valid_from": from_date.isoformat(), **changes}
    if clock is not None:
        new.update(published_at=stamp(clock[0]), received_at=stamp(clock[1]), validated_at=stamp(clock[2]))
    if not keep_old:
        old["valid_through"] = (from_date - timedelta(days=1)).isoformat()
    book["references"].append(new)
    data["references"] = ReferenceBook.from_dict(book)


def withdraw(data, validated):
    document = data["guidance"].receipts[-1].document.to_dict()
    raw = canonical_bytes({"invented": "WITHDRAWAL", "validated": stamp(validated)})
    document.update(disclosure_id="INVENTED-WITHDRAWAL", kind="withdrawal", supersedes="INVENTED-RAISE",
                    published_at=stamp(validated - timedelta(seconds=2)), periods=[], source_payload_sha256=hash_bytes(raw))
    data["guidance"] = data["guidance"].append(GuidanceReceipt(raw, GuidanceDocument.from_dict(document),
        stamp(validated - timedelta(seconds=1)), stamp(validated)))


def known_action(kind, security, effective, validated, *, cash=None, pay=None, key="INVENTED-ACTION"):
    return {"action_id": key, "security_id": security, "kind": kind, "effective_at": stamp(effective),
            "received_at": stamp(validated - timedelta(minutes=1)), "validated_at": stamp(validated),
            "source_sha256": hash_bytes(b"INVENTED-ACTION-ECONOMICS"), "ratio": None,
            "cash_per_share": cash, "pay_date": None if pay is None else pay.isoformat()}


def securities(data, count):
    """Clone the invented event onto separate issuers and sectors."""
    source = data["guidance"].receipts
    originals, revised, ids, batches = [], [], [], []
    book = data["references"].to_dict()
    template = book["references"][0]
    bars = [row for row in book["daily_bars"] if row["security_id"] == "INVENTED-SEC"]
    for index in range(count):
        security, issuer = "INVENTED-SEC-" + str(index), "INVENTED-ISSUER-" + str(index)
        for target, original in ((originals, source[0]), (revised, source[1])):
            doc = original.document.to_dict()
            doc.update(security_id=security, issuer_id=issuer, disclosure_id=doc["disclosure_id"] + "-" + str(index))
            target.append(GuidanceReceipt(original.raw_bytes, GuidanceDocument.from_dict(doc), original.received_at, original.validated_at))
        book["references"].append({**template, "security_id": security, "issuer_id": issuer, "sector": "SECTOR-" + str(index)})
        book["daily_bars"].extend({**row, "security_id": security} for row in bars)
        for batch in data["market_batches"]:
            if batch.role == "stock":
                raw = json.loads(batch.raw_bytes)
                raw["security_id"] = security
                batches.append(HistoricalMarketBatch(canonical_bytes(raw)))
        ids.append(security)
    data["guidance"] = GuidanceLedger(tuple(originals + revised))
    data["references"] = ReferenceBook.from_dict(book)
    data["market_batches"] = tuple(batches) + tuple(batch for batch in data["market_batches"] if batch.role == "benchmark")
    return ids


def reasons(rows):
    return [row["reason"] for row in rows]


def sells(result, sleeve="strategy"):
    return [row for row in result[sleeve]["fills"] if row["side"] == "sell"]


def postpone(data, security, days=1):
    """Publish one cloned security's revision later, so it enters later."""
    shift = lambda text: stamp(datetime.fromisoformat(text.replace("Z", "+00:00")) + timedelta(days=days))
    receipts = []
    for receipt in data["guidance"].receipts:
        document = receipt.document.to_dict()
        if document["security_id"] == security and document["disclosure_id"].startswith("INVENTED-RAISE"):
            document["published_at"] = shift(document["published_at"])
            receipt = GuidanceReceipt(receipt.raw_bytes, GuidanceDocument.from_dict(document),
                                      shift(receipt.received_at), shift(receipt.validated_at))
        receipts.append(receipt)
    data["guidance"] = GuidanceLedger(tuple(sorted(receipts, key=lambda row: row.validated_at)))


class ReviewPinTests(unittest.TestCase):
    def test_unmatched_spy_exposure_at_the_replay_boundary_blocks_parity(self):
        # GDR-CR53-002: a terminal unwind after the last session left SPY held
        # with no order, no blocker and comparison_parity_blocked=False.
        data = inputs(count=2)
        reprice(data, "benchmark", "100")
        day1 = session(data, 1)
        known = at(day1, 10, 30)
        result = run_replay(**data, actions=(known_action("terminal_cash", "INVENTED-SEC", known, known, cash="7", pay=day1),))
        self.assertEqual(result["strategy"]["positions"], [])
        self.assertEqual([row["quantity"] for row in result["comparator"]["positions"]], [49])
        self.assertFalse(result["complete_software_replay"])
        self.assertTrue(result["comparison_parity_blocked"])
        self.assertEqual(reasons(result["permanent_parity_blockers"]), ["unmatched_comparator_exposure_at_replay_boundary"])

    def test_action_and_input_inventory_rules_each_refuse_at_binding(self):
        data = inputs(count=2)
        day0, day1 = data["first_session"], data["last_session"]
        opening = at(day1, 9, 30)
        dividend, split = action(data, "dividend", cash="1"), action(data, "split", ratio="2")
        actions = {
            "received_after_validated": {**dividend, "received_at": stamp(opening - timedelta(seconds=30)),
                                         "validated_at": stamp(opening - timedelta(minutes=1))},
            "split_cash_in_lieu": {**split, "cash_per_share": "1"},
            "payment_before_ex_date": {**dividend, "pay_date": day0.isoformat()},
            "unsupported_kind_with_economics": {**action(data, "noncash_merger"), "cash_per_share": "1"},
            "late_split": {**split, "received_at": stamp(opening), "validated_at": stamp(opening + timedelta(minutes=1))},
            "zero_split_ratio": {**split, "ratio": "0"},
            "dividend_not_at_ex_open": action(data, "dividend", cash="1", minute=0),
            "known_after_window": action(data, "dividend", index=3, cash="1"),
        }
        for rule, value in actions.items():
            with self.subTest(rule=rule), self.assertRaises(InputError):
                MultiSessionReplay(**data, actions=(value,))
        service = tuple(row.session_date for row in data["calendar"].sessions if row.session_date.isoformat() != dividend["pay_date"])
        with self.assertRaises(InputError):
            MultiSessionReplay(**{**data, "contract": default_contract(service, calendar_source_sha256=hash_bytes(b"INVENTED-SERVICE-DAYS"))},
                               actions=(dividend,))
        batches = data["market_batches"]
        stock = next(batch for batch in batches if batch.role == "stock" and batch.session_date == day0)
        spy = next(batch for batch in batches if batch.role == "benchmark" and batch.session_date == day0)

        def rebuilt(batch, **fields):
            raw = json.loads(batch.raw_bytes)
            raw.update(fields)
            return HistoricalMarketBatch(canonical_bytes(raw))
        changed = json.loads(stock.raw_bytes)
        changed["minutes"][0]["v"] += 1
        inventories = {
            "session_bounds_differ": tuple(batch for batch in batches if batch is not stock) + (rebuilt(stock, session_close_utc=stamp(at(day0, 13))),),
            "conflicting_batch": batches + (HistoricalMarketBatch(canonical_bytes(changed)),),
            "second_spy_identity": batches + (rebuilt(spy, security_id="INVENTED-SPY-2"),),
            "batch_outside_window": batches + tuple(batch for batch in inputs(count=3)["market_batches"] if batch.session_date > day1)[:1],
        }
        for rule, market in inventories.items():
            with self.subTest(rule=rule), self.assertRaises(InputError):
                MultiSessionReplay(**{**data, "market_batches": market})
        calendar, extra, cursor = data["calendar"].to_dict(), [], date(2022, 12, 1)
        while cursor < date.fromisoformat(calendar["covered_from"]):
            if cursor.weekday() < 5:
                extra.append({"date": cursor.isoformat(), "open_utc": stamp(at(cursor, 9, 30)), "close_utc": stamp(at(cursor, 16))})
            cursor += timedelta(days=1)
        calendar.update(covered_from=extra[0]["date"], sessions=extra + calendar["sessions"])
        long = CalendarInput.from_dict(calendar)
        with self.assertRaises(InputError):
            MultiSessionReplay(**{**data, "calendar": long, "first_session": long.sessions[0].session_date})

    def test_mode_session_inventory_and_repeated_receipts_cannot_change(self):
        data = inputs(count=3)
        replay = MultiSessionReplay(**data)
        replay.step_session(replay.days[0])
        repeated = replay.step_session(replay.days[0])
        repeated["state_sha256"] = "0" * 64
        self.assertNotEqual(replay.step_session(replay.days[0])["state_sha256"], "0" * 64)
        replay.mode = "stress"
        with self.assertRaises(InputError):
            replay.step_session(replay.days[1])
        replay = MultiSessionReplay(**data)
        replay.days = (replay.days[0], replay.days[2])
        with self.assertRaises(InputError):
            replay.step_session(replay.days[0])

    def test_failed_session_restores_all_of_its_effects(self):
        replay = MultiSessionReplay(**inputs(count=1))
        with patch.object(MultiSessionReplay, "_close", side_effect=InputError("invented close failure")), \
                self.assertRaises(InputError):
            replay.step_session(replay.days[0])
        self.assertEqual(replay.snapshot()["strategy"]["orders"], [])
        replay.step_session(replay.days[0])
        self.assertEqual(len(replay.snapshot()["strategy"]["fills"]), 1)

    def test_invalidation_exit_follows_the_previous_session_cutoff(self):
        for offset, hour, exit_offset in ((0, 18, 1), (1, 8, 2)):
            data = inputs(count=4)
            withdraw(data, at(session(data, offset), hour))
            exits = sells(run_replay(**data))
            with self.subTest(offset=offset, hour=hour):
                self.assertEqual({row["at"][:10] for row in exits}, {session(data, exit_offset).isoformat()})
                self.assertEqual(sum(row["quantity"] for row in exits), 495)
        data = inputs(count=1)
        withdraw(data, at(data["first_session"], 11))
        self.assertEqual(run_replay(**data)["unresolved"], {"INVENTED-SEC": "invalidation_exit_outside_replay_window"})

    def test_known_cancellation_stops_later_fills_and_racing_shares_exit_together(self):
        data = inputs(count=4, volume=10000)
        withdraw(data, at(data["first_session"], 10, 2) + timedelta(seconds=30))
        self.assertEqual([row["quantity"] for row in run_replay(**data)["strategy"]["fills"] if row["side"] == "buy"], [100, 100])
        data = inputs(count=4, volume=10000)
        withdraw(data, at(data["first_session"], 10, 2))
        exits = sells(run_replay(**data))
        self.assertEqual({row["at"][:10] for row in exits}, {session(data, 1).isoformat()})
        self.assertEqual(sum(row["quantity"] for row in exits), 200)

    def test_close_trims_drift_above_the_position_and_dated_sector_caps(self):
        data = inputs(count=2)
        first = data["first_session"].isoformat()
        edit_bars(data, lambda row: row.update(raw_close="12") if (row["security_id"], row["session_date"]) == ("INVENTED-SEC", first) else None)
        self.assertEqual([(row["quantity"], row["exit_reason"]) for row in sells(run_replay(**data))], [(75, "trim")])
        data = inputs(count=3)
        ids = securities(data, 4)
        for security in ids:
            redate(data, security, session(data, 1), sector="SHARED")
        result = run_replay(**data)
        self.assertEqual([(row["security_id"], row["exit_reason"]) for row in sells(result)], [(ids[3], "trim")])
        held = {row["security_id"]: row["quantity"] for row in result["strategy"]["positions"]}
        self.assertEqual([held[security] for security in ids], [495, 495, 495, 14])

    def test_position_stop_is_inclusive_at_ninety_percent_of_entry_cost(self):
        data = inputs(count=2)
        first = data["first_session"].isoformat()
        edit_bars(data, lambda row: row.update(raw_close="9.0045") if (row["security_id"], row["session_date"]) == ("INVENTED-SEC", first) else None)
        self.assertEqual([(row["quantity"], row["exit_reason"]) for row in sells(run_replay(**data))], [(495, "position_stop")])

    def test_program_drawdown_is_measured_from_the_high_water_nav(self):
        data = inputs(count=4)
        ids = securities(data, 4)
        dividends = tuple({**action(data, "dividend", security=security, cash="5"), "action_id": "INVENTED-DIVIDEND-" + security}
                          for security in ids)
        crash = session(data, 2).isoformat()
        edit_bars(data, lambda row: row.update(raw_close="0.01") if row["security_id"] in ids and row["session_date"] == crash else None)
        result = run_replay(**data, actions=dividends)
        self.assertTrue(result["program_stop_active"])
        self.assertEqual([row["exit_reason"] for row in sells(result)], ["program_drawdown"] * 4)

    def test_paired_daily_nav_counts_receivables_and_spy_value(self):
        nav = run_replay(**inputs())["daily_nav"]
        self.assertEqual((Decimal(nav[0]["strategy_nav"]), Decimal(nav[0]["comparator_nav"])), (Decimal("99995.05"), Decimal("99996.562")))
        self.assertEqual((Decimal(nav[20]["strategy_receivables"]), Decimal(nav[20]["strategy_nav"])), (Decimal("4945.05"), Decimal("99990.1")))
        data = inputs()
        late = session(data, 1)
        # Published after 18:00: missing for that day's mark, usable for later ADV.
        edit_bars(data, lambda row: row.update(published_at=stamp(at(late, 18, 1)), received_at=stamp(at(late, 18, 2)),
                  validated_at=stamp(at(late, 18, 3))) if (row["security_id"], row["session_date"]) == ("INVENTED-SPY", late.isoformat()) else None)
        result = run_replay(**data)
        self.assertIsNotNone(result["daily_nav"][1]["strategy_nav"])
        self.assertIsNone(result["daily_nav"][1]["comparator_nav"])
        self.assertIn("missing_daily_valuation", reasons(result["permanent_parity_blockers"]))
        self.assertEqual(result["strategy"]["positions"], [])
        self.assertFalse(result["complete_software_replay"])

    def test_daily_mark_must_be_one_positive_visible_close(self):
        for change in ("zero", "duplicate"):
            data = inputs(count=1)
            book = data["references"].to_dict()
            row = next(row for row in book["daily_bars"]
                       if (row["security_id"], row["session_date"]) == ("INVENTED-SEC", data["first_session"].isoformat()))
            if change == "zero":
                row["raw_close"] = "0"
            else:
                book["daily_bars"].append({**row, "raw_close": "11"})
            data["references"] = ReferenceBook.from_dict(book)
            with self.subTest(change=change):
                self.assertIsNone(run_replay(**data)["daily_nav"][0]["strategy_nav"])

    def test_unsettled_cash_and_boundary_orders_keep_the_replay_incomplete(self):
        result = run_replay(**inputs(count=21))
        self.assertEqual(result["strategy"]["positions"], [])
        self.assertTrue(result["strategy"]["receivables"])
        self.assertFalse(result["complete_software_replay"])
        self.assertEqual(run_replay(**inputs(count=20))["unresolved"], {"INVENTED-SEC": "required_exit_outside_replay_window"})
        data = inputs(count=21)
        exit_date = session(data, 20)
        edit_batches(data, lambda batch, raw: [minute.update(v=1000) for minute in raw["minutes"]]
                     if batch.role == "benchmark" and batch.session_date == exit_date else None)
        self.assertIn("unmatched_comparator_order_at_replay_boundary", reasons(run_replay(**data)["permanent_parity_blockers"]))

    def test_executed_trim_clears_its_due_and_a_pending_exit_enlarges_once(self):
        replay = MultiSessionReplay(**inputs(count=3))
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[1], "trim", 100)
        self.assertEqual([row["quantity"] for row in sells(replay.run())], [100])
        data = inputs(count=3)
        slow = session(data, 1)
        edit_batches(data, lambda batch, raw: [minute.update(v=1000) for minute in raw["minutes"]]
                     if batch.role == "stock" and batch.session_date == slow else None)
        replay = MultiSessionReplay(**data)
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[1], "trim", 100)
        replay.step_session(replay.days[1])
        replay._schedule("INVENTED-SEC", replay.days[2], "guidance_invalidation", 495)
        result = replay.run()
        self.assertEqual(sum(row["quantity"] for row in sells(result)), 495)
        self.assertEqual(len({row["order_id"] for row in sells(result)}), 1)
        self.assertEqual(sells(result)[-1]["exit_reason"], "guidance_invalidation")
        self.assertEqual(result["strategy"]["positions"], [])

    def test_exit_participation_is_bounded_by_each_session_adv(self):
        data = inputs()
        first = data["first_session"].isoformat()
        edit_bars(data, lambda row: row.update(volume=10000) if row["security_id"] == "INVENTED-SEC" and row["session_date"] >= first else None)
        exits = sells(run_replay(**data))
        self.assertEqual(exits[0]["at"][:10], session(data, 20).isoformat())
        self.assertEqual(sum(row["quantity"] for row in exits if row["at"][:10] == exits[0]["at"][:10]), 10)

    def test_buy_never_fills_above_its_limit(self):
        data = inputs(count=1)
        edit_batches(data, lambda batch, raw: raw["quotes"][1].update(bid_price="10.2", ask_price="10.2") if batch.role == "stock" else None)
        buys = run_replay(**data)["strategy"]["fills"]
        self.assertEqual(buys[0]["at"], stamp(at(data["first_session"], 10, 2)))
        self.assertTrue(all(Decimal(row["price"]) <= Decimal("10.10") for row in buys))

    def test_comparator_partial_timing_and_close_cancellation_are_permanent(self):
        data = inputs(count=1)
        edit_batches(data, lambda batch, raw: [minute.update(v=500) for minute in raw["minutes"]] if batch.role == "benchmark" else None)
        result = run_replay(**data)
        self.assertIn("comparator_partial_or_unmatched_execution", reasons(result["permanent_parity_blockers"]))
        self.assertIn("comparator_unfilled_remainder_at_close", reasons(result["permanent_parity_blockers"]))
        self.assertEqual(result["comparator"]["orders"][0]["status"], "cancelled")
        data = inputs(count=1)
        # Without the 10:01:59 SPY quote, the 10:02 callback has no fresh quote.
        edit_batches(data, lambda batch, raw: raw.update(quotes=raw["quotes"][:2] + raw["quotes"][3:]) if batch.role == "benchmark" else None)
        self.assertIn("comparator_timing_mismatch", reasons(run_replay(**data)["permanent_parity_blockers"]))

    def test_comparator_risk_reducing_sell_precedes_buy_in_shared_minute_capacity(self):
        replay = MultiSessionReplay(**inputs(count=1, volume=100))
        when = at(replay.days[0], 10)
        for key, held in (("INVENTED-TRANCHE-BUY", 0), ("INVENTED-TRANCHE-SELL", 1)):
            replay._state["tranches"][key] = {"tranche_id": key, "source_security_id": "INVENTED-SEC",
                "quantity": held, "source_budget": Decimal("100"), "entry_spent": Decimal(0)}
        replay._order("comparator", replay.spy, "buy", 1, when, Decimal("159000000"), limit=Decimal("53.53"), tranche="INVENTED-TRANCHE-BUY")
        replay._order("comparator", replay.spy, "sell", 1, when, Decimal("159000000"), tranche="INVENTED-TRANCHE-SELL")
        replay._fill_orders("comparator", when + timedelta(minutes=1))
        self.assertEqual([row["side"] for row in replay._state["fills"]], ["sell"])

    def test_open_buy_reserves_its_remaining_minimum_commission(self):
        replay = MultiSessionReplay(**inputs(count=1, volume=10000))
        when = at(replay.days[0], 10)
        replay._order("strategy", "INVENTED-SEC", "buy", 495, when, Decimal("30000000"), limit=Decimal("10.10"),
                      issuer="INVENTED-ISSUER", sector="technology", event=replay.guidance.receipts[-1].document.sha256)
        self.assertEqual(replay._reserved("strategy"), Decimal("5001.975"))
        replay._fill_orders("strategy", when + timedelta(minutes=1))
        self.assertEqual(replay._reserved("strategy"), Decimal("3990.975"))

    def test_split_scales_holding_stop_reference_and_due_but_waits_for_open_orders(self):
        data = inputs(count=3)
        reprice(data, "stock", "5", from_date=session(data, 1))
        replay = MultiSessionReplay(**data, actions=(action(data, "split", ratio="2"),))
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[2], "trim", 100)
        result = replay.run()
        self.assertEqual([(row["quantity"], row["exit_reason"]) for row in sells(result)], [(200, "trim")])
        self.assertEqual(result["strategy"]["positions"][0]["quantity"], 790)
        data = inputs()
        exit_date = session(data, 20)
        edit_batches(data, lambda batch, raw: [minute.update(v=1000) for minute in raw["minutes"]]
                     if batch.role == "benchmark" and batch.session_date == exit_date else None)
        result = run_replay(**data, actions=(action(data, "split", index=21, security="INVENTED-SPY", ratio="2"),))
        self.assertEqual(result["unresolved"].get("INVENTED-SPY"), "split_requires_reconciled_orders")

    def test_spy_dividend_and_terminal_actions_apply_to_comparator_tranches(self):
        data = inputs(count=2)
        result = run_replay(**data, actions=(action(data, "dividend", security="INVENTED-SPY", cash="1"),))
        self.assertEqual([(row["kind"], Decimal(row["amount"])) for row in result["comparator"]["receivables"]], [("dividend", Decimal("92"))])
        self.assertEqual(result["strategy"]["receivables"], [])
        data = inputs(count=2)
        result = run_replay(**data, actions=(action(data, "terminal_cash", security="INVENTED-SPY", cash="60"),))
        self.assertTrue(all(row["quantity"] == 0 for row in result["comparator"]["positions"]))
        self.assertEqual([Decimal(row["amount"]) for row in result["comparator"]["receivables"]], [Decimal("5520")])
        self.assertIn("comparator_terminal_ends_matched_schedule", reasons(result["permanent_parity_blockers"]))
        data = inputs(count=2)
        result = run_replay(**data, actions=(action(data, "noncash_merger", security="INVENTED-SPY"),))
        self.assertEqual(result["unresolved"].get("INVENTED-SPY"), "unsupported_or_unresolved_terminal_economics")
        self.assertIn("unsupported_terminal_comparison_schedule", reasons(result["permanent_parity_blockers"]))

    def test_late_terminal_after_a_fill_or_another_action_needs_reconciliation(self):
        data = inputs(count=2)
        day0 = data["first_session"]
        late = known_action("terminal_cash", "INVENTED-SEC", at(day0, 10) + timedelta(seconds=30), at(day0, 10, 5),
                            cash="7", pay=session(data, 1))
        result = run_replay(**data, actions=(late,))
        self.assertEqual(result["unresolved"].get("INVENTED-SEC"), "late_terminal_entitlement_changed_after_effective_time")
        data = inputs(count=3)
        day0, day1 = data["first_session"], session(data, 1)
        late = known_action("terminal_cash", "INVENTED-SEC", at(day0, 19), at(day1, 11), cash="7", pay=day1, key="INVENTED-TERMINAL")
        result = run_replay(**data, actions=(late, action(data, "dividend", cash="1")))
        self.assertEqual(result["unresolved"].get("INVENTED-SEC"), "late_terminal_entitlement_changed_after_effective_time")

    def test_action_between_clock_events_applies_and_clears_its_due_exits(self):
        data = inputs(count=2)
        known = at(session(data, 1), 11)
        result = run_replay(**data, actions=(known_action("terminal_cash", "INVENTED-SEC", known, known, cash="7", pay=session(data, 1)),))
        self.assertEqual(result["strategy"]["positions"], [])
        self.assertIn("INVENTED-ACTION", result["actions"])
        data = inputs(count=2)
        replay = MultiSessionReplay(**data, actions=(action(data, "terminal_cash", cash="7"),))
        replay.step_session(replay.days[0])
        replay._schedule("INVENTED-SEC", replay.days[1], "trim", 100)
        self.assertEqual(replay.run()["scheduled_exits"], {})

    def test_held_exit_uses_only_a_visible_unique_listed_same_issuer_identity(self):
        def replayed(edit):
            data = inputs(count=2)
            edit(data, data["first_session"], session(data, 1))
            replay = MultiSessionReplay(**data)
            replay.step_session(replay.days[0])
            replay._schedule("INVENTED-SEC", replay.days[1], "position_stop", 495)
            replay.step_session(replay.days[1])
            return replay.snapshot()
        blocked = {
            "published_after_cutoff": lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, sector="utilities",
                clock=(at(day1, 12), at(day1, 12, 1), at(day1, 12, 2))),
            "published_at_cutoff": lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, sector="utilities",
                clock=(at(day0, 18), at(day0, 18), at(day0, 18))),
            "validated_after_cutoff": lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, sector="utilities",
                clock=(at(day0, 17), at(day0, 17, 30), at(day0, 19))),
            "ambiguous": lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, keep_old=True, sector="utilities"),
            "delisted": lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, status="delisted"),
            "changed_issuer": lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, issuer_id="OTHER-ISSUER"),
        }
        for rule, edit in blocked.items():
            result = replayed(edit)
            with self.subTest(rule=rule):
                self.assertEqual(sells(result), [])
                self.assertIn("missing_exit_liquidity", reasons(result["refusals"]))
        for rule, edit in (("changed_issuer", blocked["changed_issuer"]),
                           ("missing_sector", lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, sector=None)),
                           ("renamed_without_new_batch", lambda data, day0, day1: redate(data, "INVENTED-SEC", day1, symbol="RENAMED"))):
            with self.subTest(rule=rule):
                self.assertIn("missing_current_portfolio_valuation_blocks_entries", reasons(replayed(edit)["refusals"]))
        result = replayed(lambda data, day0, day1: redate(data, "INVENTED-SPY", day1, symbol="IVV"))
        self.assertIn("comparator_exit_liquidity_refused", reasons(result["permanent_parity_blockers"]))

    def test_engine_state_sets_each_entry_control(self):
        def refusals(data, prepare=None, actions=()):
            replay = MultiSessionReplay(**data, actions=actions)
            replay.step_session(replay.days[0])
            if prepare is not None:
                prepare(replay)
            replay.step_session(replay.days[1])
            return reasons(replay.snapshot()["refusals"])
        data = inputs(count=2)
        self.assertIn("entry_control_exits_or_trims_pending",
                      refusals(data, lambda replay: replay._schedule("INVENTED-SEC", replay.days[1], "trim", 100)))
        data = inputs(count=2)
        self.assertIn("entry_control_unresolved_actions", refusals(data, actions=(action(data, "terminal_unresolved"),)))
        data = inputs(count=2)
        self.assertIn("entry_control_unresolved_actions",
                      refusals(data, actions=(action(data, "terminal_cash", security="INVENTED-SPY", cash="60"),)))
        data = inputs(count=2)
        missing = session(data, 1)
        data["market_batches"] = tuple(batch for batch in data["market_batches"] if not (batch.role == "stock" and batch.session_date == missing))
        self.assertIn("missing_current_portfolio_valuation_blocks_entries", refusals(data))
        replay = MultiSessionReplay(**inputs(count=2))
        replay._state["daily_nav"].append({"session_date": replay.days[0] - timedelta(days=1),
                                          "strategy_nav": None, "comparator_nav": Decimal("100000")})
        replay._entries(at(replay.days[0], 10))
        self.assertIn("entry_control_unresolved_valuations", reasons(replay._state["refusals"]))
        replay = MultiSessionReplay(**inputs(count=2))
        replay._state["stopped"] = True
        replay._entries(at(replay.days[0], 10))
        self.assertEqual(replay._state["orders"], {})
        self.assertIn("entry_control_program_stop_active", reasons(replay._state["refusals"]))

    def test_spy_entry_needs_a_tight_quote_and_a_fee_inclusive_budget(self):
        data = inputs(count=1)
        edit_batches(data, lambda batch, raw: raw["quotes"][1].update(bid_price="52") if batch.role == "benchmark" else None)
        result = run_replay(**data)
        self.assertEqual(result["comparator"]["orders"], [])
        self.assertIn("comparator_entry_market_input_refused", reasons(result["permanent_parity_blockers"]))
        # 100.06 needs the source fee for the 49th share; at 99.04 the fee
        # spent keeps the residual below one more share.
        for price in ("100.06", "99.04"):
            data = inputs(count=1)
            reprice(data, "benchmark", price)
            result = run_replay(**data)
            with self.subTest(price=price):
                self.assertEqual([row["quantity"] for row in result["comparator"]["fills"]], [49])
                self.assertNotIn("comparator_budget_mismatch_beyond_rounding", reasons(result["permanent_parity_blockers"]))

    def test_source_exit_sells_only_its_own_tranches(self):
        data = inputs(count=2)
        first, second = securities(data, 2)
        replay = MultiSessionReplay(**data)
        replay.step_session(replay.days[0])
        replay._schedule(first, replay.days[1], "position_stop", 495)
        replay.step_session(replay.days[1])
        tranches = {row["source_security_id"]: row["quantity"] for row in replay.snapshot()["comparator"]["positions"]}
        self.assertEqual(tranches, {first: 0, second: 92})

    def test_spy_exit_requests_follow_each_executed_strategy_fraction(self):
        # Pending SPY sells are excluded from the base, so slow SPY execution
        # cannot front-load the comparator ahead of the strategy's own exits.
        data = inputs()
        exit_date = session(data, 20)

        def edit(batch, raw):
            if batch.session_date == exit_date:
                for minute in raw["minutes"]:
                    minute["v"] = 10000 if batch.role == "stock" else 500
        edit_batches(data, edit)
        result = run_replay(**data)
        self.assertEqual([row["quantity"] for row in sells(result)], [100, 100, 100, 100, 95])
        self.assertEqual([row["quantity"] for row in result["comparator"]["orders"] if row["side"] == "sell"], [18, 18, 18, 19, 19])

    def test_carried_spy_exit_waits_for_the_next_session_decision(self):
        data = inputs()
        exit_date, next_date = session(data, 20), session(data, 21)

        def edit(batch, raw):
            if batch.role == "benchmark" and batch.session_date == exit_date:
                for minute in raw["minutes"]:
                    minute["v"] = 1000
            if batch.role == "benchmark" and batch.session_date == next_date:
                opening = at(next_date, 9, 30)
                raw["quotes"].insert(0, {**raw["quotes"][0], "sip_timestamp": instant_ns(opening + timedelta(seconds=30)),
                                         "participant_timestamp": instant_ns(opening + timedelta(seconds=30))})
                for number, quote in enumerate(raw["quotes"], 1):
                    quote["sequence_number"] = number
                raw["minutes"].insert(0, {**raw["minutes"][0], "t": instant_ns(opening) // 1000000})
        edit_batches(data, edit)
        carried = [row for row in sells(run_replay(**data), "comparator") if row["at"][:10] == next_date.isoformat()]
        self.assertTrue(carried)
        self.assertTrue(all(row["at"] > stamp(at(next_date, 10)) for row in carried))


class CounterReviewActionTests(unittest.TestCase):
    """GDR-CCR55-001: action uncertainty needs reconciliation, not another action."""

    def _uncertain_split(self, security, *, count=5):
        data = inputs(count=count)
        reprice(data, "benchmark", "100")
        split = {**known_action("split", security, at(session(data, 1), 9, 30),
            at(session(data, 0), 17), key="INVENTED-SPLIT"), "ratio": "1.5"}
        return data, split

    def _cash(self, data, security, *, minute=30, key="INVENTED-CASH"):
        known = at(session(data, 1), 10, minute)
        return known_action("terminal_cash", security, known, known, cash="7",
                            pay=session(data, 2), key=key)

    def test_repeated_cash_terminal_cannot_clear_unknown_entitled_shares(self):
        for security, sleeve in (("INVENTED-SEC", "strategy"), ("INVENTED-SPY", "comparator")):
            data, split = self._uncertain_split(security)
            first = self._cash(data, security)
            second = self._cash(data, security, minute=31, key="INVENTED-CASH-2")
            baseline = run_replay(**data, actions=(split, first))
            result = run_replay(**data, actions=(split, first, second))
            with self.subTest(security=security):
                self.assertEqual(result["unresolved"].get(security), "unsupported_or_unresolved_terminal_economics")
                self.assertEqual(result[sleeve]["settled_cash"], baseline[sleeve]["settled_cash"])
                self.assertEqual(result[sleeve]["positions"], baseline[sleeve]["positions"])
                self.assertFalse(result["complete_software_replay"])

    def test_dividend_after_unknown_split_never_credits_guessed_shares(self):
        for security, sleeve in (("INVENTED-SEC", "strategy"), ("INVENTED-SPY", "comparator")):
            data, split = self._uncertain_split(security)
            dividend = known_action("dividend", security, at(session(data, 2), 9, 30),
                at(session(data, 1), 17), cash="1", pay=session(data, 3), key="INVENTED-DIVIDEND")
            baseline = run_replay(**data, actions=(split,))
            result = run_replay(**data, actions=(split, dividend))
            with self.subTest(security=security):
                self.assertEqual(result[sleeve]["settled_cash"], baseline[sleeve]["settled_cash"])
                self.assertEqual(result[sleeve]["receivables"], [])
                self.assertEqual(result["unresolved"].get(security), "fractional_split_cash_in_lieu_unsupported")

    def test_later_integral_split_does_not_scale_an_unknown_share_basis(self):
        for security, sleeve in (("INVENTED-SEC", "strategy"), ("INVENTED-SPY", "comparator")):
            data, split = self._uncertain_split(security)
            later = {**known_action("split", security, at(session(data, 2), 9, 30),
                at(session(data, 1), 17), key="INVENTED-LATER-SPLIT"), "ratio": "2"}
            baseline = run_replay(**data, actions=(split,))
            result = run_replay(**data, actions=(split, later))
            with self.subTest(security=security):
                self.assertEqual(result[sleeve]["positions"], baseline[sleeve]["positions"])
                self.assertEqual(result["unresolved"].get(security), "fractional_split_cash_in_lieu_unsupported")

    def test_unsupported_terminal_economics_stay_unresolved_across_numeric_actions(self):
        for security, sleeve in (("INVENTED-SEC", "strategy"), ("INVENTED-SPY", "comparator")):
            for kind in ("noncash_merger", "cvr", "terminal_unresolved"):
                for later_kind in ("terminal_cash", "dividend", "split"):
                    data = inputs(count=4)
                    known = at(session(data, 1), 9, 30)
                    unsupported = known_action(kind, security, known, known, key="INVENTED-UNSUPPORTED")
                    later_known = at(session(data, 2), 9, 30)
                    later = known_action(later_kind, security, later_known, at(session(data, 1), 17),
                        cash="1" if later_kind != "split" else None,
                        pay=session(data, 3) if later_kind != "split" else None, key="INVENTED-LATER")
                    if later_kind == "split":
                        later["ratio"] = "2"
                    baseline = run_replay(**data, actions=(unsupported,))
                    result = run_replay(**data, actions=(unsupported, later))
                    with self.subTest(security=security, kind=kind, later_kind=later_kind):
                        self.assertEqual(result["unresolved"].get(security), "unsupported_or_unresolved_terminal_economics")
                        self.assertEqual(result[sleeve]["settled_cash"], baseline[sleeve]["settled_cash"])
                        self.assertEqual(result[sleeve]["positions"], baseline[sleeve]["positions"])

    def test_late_terminal_uncertainty_cannot_be_cleared_by_another_payout(self):
        data = inputs(count=4)
        day0, day1 = session(data, 0), session(data, 1)
        first = known_action("terminal_cash", "INVENTED-SEC", at(day0, 10) + timedelta(seconds=30),
            at(day0, 10, 5), cash="7", pay=session(data, 2), key="INVENTED-LATE-CASH")
        second = self._cash(data, "INVENTED-SEC")
        baseline = run_replay(**data, actions=(first,))
        result = run_replay(**data, actions=(first, second))
        self.assertEqual(result["unresolved"].get("INVENTED-SEC"), "unsupported_or_unresolved_terminal_economics")
        self.assertEqual(result["strategy"]["settled_cash"], baseline["strategy"]["settled_cash"])
        self.assertEqual(result["strategy"]["positions"], baseline["strategy"]["positions"])

    def test_exit_window_uncertainty_does_not_overwrite_unknown_action_economics(self):
        data, split = self._uncertain_split("INVENTED-SEC", count=2)
        withdraw(data, at(session(data, 1), 10, 30))
        cash = self._cash(data, "INVENTED-SEC", minute=31)
        result = run_replay(**data, actions=(split, cash))
        self.assertEqual(result["unresolved"].get("INVENTED-SEC"), "unsupported_or_unresolved_terminal_economics")
        self.assertEqual([row["quantity"] for row in result["strategy"]["positions"]], [495])
        self.assertEqual(result["strategy"]["receivables"], [])
        # A time exit outside the boundary must preserve the same uncertainty.
        data, _ = self._uncertain_split("INVENTED-SEC", count=21)
        split = {**known_action("split", "INVENTED-SEC", at(session(data, 20), 9, 30),
            at(session(data, 19), 17), key="INVENTED-LAST-SPLIT"), "ratio": "1.5"}
        self.assertEqual(run_replay(**data, actions=(split,))["unresolved"].get("INVENTED-SEC"),
                         "fractional_split_cash_in_lieu_unsupported")


class EdgePinTests(unittest.TestCase):
    """GDR-CR53-008 edges and the GDR-CR54-002 regression (section 54)."""

    def test_cash_terminal_after_an_unresolved_split_stays_unresolved(self):
        # GDR-CR54-002: a fractional split left the share count unknown, yet
        # the payout counted 495 pre-split shares and the replay completed.
        data = inputs(count=5)
        reprice(data, "benchmark", "100")
        day0, day1 = session(data, 0), session(data, 1)
        split = {**known_action("split", "INVENTED-SEC", at(day1, 9, 30), at(day0, 17), key="INVENTED-SPLIT"), "ratio": "1.5"}
        known = at(day1, 10, 30)
        terminal = known_action("terminal_cash", "INVENTED-SEC", known, known, cash="7", pay=session(data, 2), key="INVENTED-TERMINAL")
        result = run_replay(**data, actions=(split, terminal))
        self.assertEqual(result["unresolved"], {"INVENTED-SEC": "unsupported_or_unresolved_terminal_economics"})
        self.assertEqual([row["quantity"] for row in result["strategy"]["positions"]], [495])
        self.assertEqual({row["strategy_receivables"] for row in result["daily_nav"]}, {"0"})
        self.assertFalse(result["complete_software_replay"])
        self.assertTrue(result["comparison_parity_blocked"])

    def test_cash_terminal_clears_a_moot_exit_outside_the_window(self):
        # MSAA13: the payout ends the holding, so its pending exit is moot.
        data = inputs(count=1)
        day0 = session(data, 0)
        withdraw(data, at(day0, 10, 30))
        self.assertEqual(run_replay(**data)["unresolved"], {"INVENTED-SEC": "invalidation_exit_outside_replay_window"})
        known = at(day0, 11)
        result = run_replay(**data, actions=(known_action("terminal_cash", "INVENTED-SEC", known, known, cash="10", pay=day0),))
        self.assertEqual(result["unresolved"], {})
        self.assertEqual(result["strategy"]["positions"], [])

    def test_entry_account_counts_an_outstanding_strategy_receivable(self):
        # MSE14: at a 9.9 mark the later entry sizes from NAV 99945.55, one
        # share under the cap; the dividend receivable restores 495.
        data = inputs(count=3)
        held, later = securities(data, 2)
        postpone(data, later)
        day0, day1 = session(data, 0), session(data, 1)

        def marked(batch, raw):
            if raw["security_id"] == held and batch.session_date == day1:
                for quote in raw["quotes"]:
                    quote.update(bid_price="9.9", ask_price="9.9")
        edit_batches(data, marked)
        dividend = known_action("dividend", held, at(day1, 9, 30), at(day0, 17), cash="0.2", pay=session(data, 3))
        for actions, quantity in (((), 494), ((dividend,), 495)):
            fills = run_replay(**data, actions=actions)["strategy"]["fills"]
            with self.subTest(dividend=bool(actions)):
                self.assertEqual([(row["security_id"], row["quantity"]) for row in fills], [(held, 495), (later, quantity)])

    def test_gross_cap_trims_the_eleventh_position_in_sorted_order(self):
        # MSC9, MSC11: dividends make room for an eleventh entry; at a close
        # of 11 the 50% gross cap leaves the last sorted holding 312 shares.
        data = inputs(count=3)
        ids = securities(data, 11)
        postpone(data, ids[10])
        day0, day1 = session(data, 0), session(data, 1)
        dividends = tuple(known_action("dividend", security, at(day1, 9, 30), at(day0, 17), cash="2.1",
                                       pay=session(data, 3), key="INVENTED-DIVIDEND-" + security) for security in ids[:10])
        edit_bars(data, lambda row: row.update(raw_close="11") if row["security_id"] in ids and row["session_date"] == day1.isoformat() else None)
        result = run_replay(**data, actions=dividends)
        self.assertEqual(len([row for row in result["strategy"]["fills"] if row["side"] == "buy"]), 11)
        self.assertEqual([(row["security_id"], row["quantity"], row["exit_reason"]) for row in sells(result)], [(ids[9], 183, "trim")])

    def test_terminal_unwind_counts_a_pending_spy_sell_of_the_same_tranche(self):
        # MSY1: seven trim-matched SPY shares are still pending at the unwind.
        data = inputs(count=4)
        day0, day1 = session(data, 0), session(data, 1)
        edit_bars(data, lambda row: row.update(raw_close="12") if (row["security_id"], row["session_date"]) == ("INVENTED-SEC", day0.isoformat()) else None)

        def slow(batch, raw):
            if batch.role == "benchmark" and batch.session_date == day1:
                for minute in raw["minutes"]:
                    minute["v"] = 100
        edit_batches(data, slow)
        known = at(day1, 10, 30)
        result = run_replay(**data, actions=(known_action("terminal_cash", "INVENTED-SEC", known, known, cash="12", pay=day1),))
        self.assertEqual([(row["quantity"], row["exit_reason"]) for row in result["comparator"]["orders"] if row["side"] == "sell"],
                         [(13, "trim"), (79, "terminal_entitlement")])
        self.assertEqual([row["quantity"] for row in result["comparator"]["positions"]], [0])

    def test_carried_spy_sell_stops_at_a_dated_spy_issuer_change(self):
        # MSF5: the carried order keeps the issuer it was submitted under.
        data = inputs()
        exit_date, next_date = session(data, 20), session(data, 21)

        def slow(batch, raw):
            if batch.role == "benchmark" and batch.session_date == exit_date:
                for minute in raw["minutes"]:
                    minute["v"] = 1000
        edit_batches(data, slow)
        redate(data, "INVENTED-SPY", next_date, issuer_id="INVENTED-SPY-ISSUER-2")
        result = run_replay(**data)
        self.assertEqual([row for row in sells(result, "comparator") if row["at"][:10] == next_date.isoformat()], [])
        self.assertIn("subsequent_quote_minute_or_settlement_refused", reasons(result["permanent_parity_blockers"]))

    def test_exit_fee_above_a_sub_dollar_notional_is_paid_from_settled_cash(self):
        # MSF26: 495 shares at 0.003998 raise 1.97901 against a 2.475 fee.
        data = inputs(count=2)
        day0, day1 = session(data, 0), session(data, 1)
        edit_bars(data, lambda row: row.update(raw_close="9") if (row["security_id"], row["session_date"]) == ("INVENTED-SEC", day0.isoformat()) else None)

        def tiny(batch, raw):
            if batch.role == "stock" and batch.session_date == day1:
                for quote in raw["quotes"]:
                    quote.update(bid_price="0.004", ask_price="0.004")
        edit_batches(data, tiny)
        result = run_replay(**data)
        sale = sells(result)[0]
        shortfall = Decimal(sale["fee"]) - Decimal(sale["price"]) * sale["quantity"]
        self.assertEqual(shortfall, Decimal("0.49599"))
        self.assertEqual(Decimal(result["daily_nav"][1]["strategy_settled_cash"]), Decimal("95045.05") - shortfall)

    def test_program_drawdown_includes_exactly_eighty_five_percent(self):
        # MSC2: four 500-share holdings make the day-1 NAV exactly 85000.
        data = inputs(count=3)
        ids = securities(data, 4)

        def entry(batch, raw):
            if batch.role == "stock":
                for quote in raw["quotes"]:
                    quote.update(bid_price="9.89", ask_price="9.89")
        edit_batches(data, entry)
        closes = {session(data, 0).isoformat(): "9.89", session(data, 1).isoformat(): "2.399945"}
        edit_bars(data, lambda row: row.update(raw_close=closes[row["session_date"]]) if row["security_id"] in ids and row["session_date"] in closes else None)
        result = run_replay(**data)
        self.assertEqual(Decimal(result["daily_nav"][1]["strategy_nav"]), Decimal("85000"))
        self.assertTrue(result["program_stop_active"])
        self.assertEqual([row["exit_reason"] for row in sells(result)], ["program_drawdown"] * 4)

    def test_spy_entry_budget_admits_an_exactly_equal_cost(self):
        # MSP5: 30 x 165.049958 + 1 equals the 509-share source cost 4952.49874.
        data = inputs(count=1, volume=60000)
        reprice(data, "stock", "9.72")
        reprice(data, "benchmark", "163.4158")
        result = run_replay(**data)
        self.assertEqual([row["quantity"] for row in result["strategy"]["fills"]], [509])
        self.assertEqual([row["quantity"] for row in result["comparator"]["fills"]], [30])
        self.assertEqual(result["permanent_parity_blockers"], [])


class BudgetReconciliationTests(unittest.TestCase):
    def test_fixed_base_and_stress_keep_exact_orders_fills_cash_and_idle_reserves(self):
        expected = {
            "base": ("4954.9500", "53.0265", "99993.1240", "29.1900", "46.3220", "75.5120"),
            "stress": ("4959.9000", "53.0795", "99981.3720", "33.1400", "41.4460", "74.5860"),
        }
        for mode, values in expected.items():
            with self.subTest(mode=mode):
                result = run_replay(**inputs(), mode=mode)
                budget, price, cash, rounding, released, residual = map(Decimal, values)
                comparator = result["comparator"]
                self.assertTrue(result["complete_software_replay"])
                self.assertFalse(result["comparison_parity_blocked"])
                self.assertEqual(result["permanent_parity_blockers"], [])
                self.assertEqual([row["quantity"] for row in comparator["orders"]], [92, 92])
                self.assertEqual([row["quantity"] for row in comparator["fills"]], [92, 92])
                self.assertEqual([row["side"] for row in comparator["fills"]], ["buy", "sell"])
                self.assertEqual(Decimal(comparator["fills"][0]["price"]), price)
                self.assertEqual(comparator["fills"][0]["at"], "2025-04-04T14:02:00Z")
                self.assertEqual(comparator["fills"][1]["at"], "2025-05-05T14:02:00Z")
                self.assertEqual(Decimal(comparator["settled_cash"]), cash)
                tranche = comparator["positions"][0]
                proof = tranche["entry_budget_reconciliation"]
                self.assertEqual(Decimal(tranche["source_budget"]), budget)
                self.assertEqual(proof["order_id"], comparator["orders"][0]["order_id"])
                self.assertEqual(Decimal(proof["limit_price"]), Decimal("53.53"))
                self.assertEqual(proof["filled_quantity"], 92)
                self.assertEqual(Decimal(proof["admission_rounding_cash"]), rounding)
                self.assertEqual(Decimal(proof["released_price_reserve"]), released)
                self.assertEqual(Decimal(proof["actual_cash_residual"]), residual)
                self.assertEqual(rounding + released, residual)
                self.assertEqual(Decimal(proof["committed_limit_cost"]) + rounding, budget)
                self.assertGreater(residual, price)
                self.assertLess(rounding, Decimal(proof["next_share_limit_cost"]))
                self.assertTrue(proof["within_rounding"])
                for field in ("backtest_ready", "native_execution_verified", "empirical_evaluation_allowed",
                              "qc_access_allowed", "real_orders_allowed"):
                    self.assertIs(result[field], False)

    @staticmethod
    def undersized_order(original):
        def submit(replay, sleeve, security, side, quantity, at, adv20, **kwargs):
            # Resubmit a genuinely smaller whole-share order through the real
            # reservation function; do not corrupt its cash or remaining fields.
            if sleeve == "comparator" and side == "buy":
                quantity -= 1
            return original(replay, sleeve, security, side, quantity, at, adv20, **kwargs)
        return submit

    def test_one_share_underallocation_still_blocks_with_coherent_reservations(self):
        original = MultiSessionReplay._order
        with patch.object(MultiSessionReplay, "_order", self.undersized_order(original)):
            result = run_replay(**inputs(count=1))
        comparator = result["comparator"]
        self.assertEqual(comparator["orders"][0]["quantity"], 91)
        self.assertEqual(comparator["orders"][0]["filled_quantity"], 91)
        self.assertEqual(Decimal(comparator["orders"][0]["reserved_notional"]), 0)
        proof = comparator["positions"][0]["entry_budget_reconciliation"]
        self.assertGreater(Decimal(proof["admission_rounding_cash"]), Decimal(proof["next_share_limit_cost"]))
        self.assertFalse(proof["within_rounding"])
        self.assertIn("comparator_budget_mismatch_beyond_rounding", reasons(result["permanent_parity_blockers"]))
        self.assertTrue(result["comparison_parity_blocked"])

    def test_limit_commitment_cannot_exceed_source_budget_despite_price_improvement(self):
        original = MultiSessionReplay._order
        def oversized(replay, sleeve, security, side, quantity, at, adv20, **kwargs):
            if sleeve == "comparator" and side == "buy":
                quantity += 1
            return original(replay, sleeve, security, side, quantity, at, adv20, **kwargs)
        with patch.object(MultiSessionReplay, "_order", oversized):
            result = run_replay(**inputs(count=1))
        tranche = result["comparator"]["positions"][0]
        proof = tranche["entry_budget_reconciliation"]
        self.assertEqual(proof["filled_quantity"], 93)
        # The full cash sleeve funds it and the eventual fill costs less than
        # the source budget, but the original limit commitment exceeded it.
        self.assertGreater(Decimal(proof["actual_cash_residual"]), 0)
        self.assertLess(Decimal(proof["admission_rounding_cash"]), 0)
        self.assertFalse(proof["within_rounding"])
        self.assertIn("comparator_budget_mismatch_beyond_rounding", reasons(result["permanent_parity_blockers"]))

    def test_exact_next_share_cost_is_underallocation_not_rounding(self):
        data = inputs(count=1, volume=60000)
        reprice(data, "stock", "9.72")
        reprice(data, "benchmark", "163.4158")
        admitted = run_replay(**data)["comparator"]["positions"][0]["entry_budget_reconciliation"]
        self.assertEqual(admitted["filled_quantity"], 30)
        self.assertEqual(Decimal(admitted["admission_rounding_cash"]), 0)
        self.assertTrue(admitted["within_rounding"])
        original = MultiSessionReplay._order
        with patch.object(MultiSessionReplay, "_order", self.undersized_order(original)):
            result = run_replay(**data)
        proof = result["comparator"]["positions"][0]["entry_budget_reconciliation"]
        self.assertEqual(proof["filled_quantity"], 29)
        self.assertEqual(Decimal(proof["admission_rounding_cash"]), Decimal(proof["next_share_limit_cost"]))
        self.assertFalse(proof["within_rounding"])
        self.assertIn("comparator_budget_mismatch_beyond_rounding", reasons(result["permanent_parity_blockers"]))

    def test_next_share_cost_uses_the_commission_floor_crossover(self):
        for mode, price, quantity, fee, increment in (
                ("base", "24.6", 199, "1", "0"),
                ("base", "24.5", 200, "1", "0.005"),
                ("stress", "12.3", 399, "2", "0"),
                ("stress", "12.25", 400, "2", "0.005")):
            with self.subTest(mode=mode, quantity=quantity):
                data = inputs(count=1)
                reprice(data, "benchmark", price)
                result = run_replay(**data, mode=mode)
                proof = result["comparator"]["positions"][0]["entry_budget_reconciliation"]
                self.assertEqual(proof["filled_quantity"], quantity)
                self.assertEqual(Decimal(proof["cumulative_fee"]), Decimal(fee))
                self.assertEqual(Decimal(proof["next_share_limit_cost"]) - Decimal(proof["limit_price"]), Decimal(increment))
                self.assertTrue(proof["within_rounding"])
                self.assertEqual(result["permanent_parity_blockers"], [])

    def test_favorable_execution_releases_reserve_without_resizing_or_top_up(self):
        data = inputs(count=1)
        def cheaper(batch, raw):
            if batch.role == "benchmark":
                for quote in raw["quotes"][2:]:
                    quote.update(bid_price="40", ask_price="40")
        edit_batches(data, cheaper)
        result = run_replay(**data)
        comparator = result["comparator"]
        proof = comparator["positions"][0]["entry_budget_reconciliation"]
        self.assertEqual(len(comparator["orders"]), 1)
        self.assertEqual(comparator["orders"][0]["quantity"], 92)
        self.assertEqual([row["quantity"] for row in comparator["fills"]], [92])
        self.assertEqual(Decimal(proof["admission_rounding_cash"]), Decimal("29.1900"))
        self.assertEqual(Decimal(proof["released_price_reserve"]), Decimal("1242.9200"))
        self.assertEqual(Decimal(proof["actual_cash_residual"]), Decimal("1272.1100"))
        self.assertTrue(proof["within_rounding"])
        self.assertEqual(result["permanent_parity_blockers"], [])

    def test_above_limit_comparator_has_no_fill_or_completed_budget_proof(self):
        data = inputs(count=1)
        def more_expensive(batch, raw):
            if batch.role == "benchmark":
                for quote in raw["quotes"][2:]:
                    quote.update(bid_price="55", ask_price="55")
        edit_batches(data, more_expensive)
        result = run_replay(**data)
        self.assertEqual(result["comparator"]["fills"], [])
        self.assertIsNone(result["comparator"]["positions"][0]["entry_budget_reconciliation"])
        self.assertEqual(result["comparator"]["orders"][0]["status"], "cancelled")
        self.assertIn("comparator_unfilled_remainder_at_close", reasons(result["permanent_parity_blockers"]))
        self.assertTrue(result["comparison_parity_blocked"])

    def test_partial_comparator_execution_keeps_one_fee_and_its_mismatch(self):
        for mode, fee in (("base", "1"), ("stress", "2")):
            with self.subTest(mode=mode):
                data = inputs(count=1)
                edit_batches(data, lambda batch, raw: [minute.update(v=3000) for minute in raw["minutes"]]
                             if batch.role == "benchmark" else None)
                result = run_replay(**data, mode=mode)
                fills = result["comparator"]["fills"]
                self.assertEqual([row["quantity"] for row in fills], [30, 30, 30, 2])
                self.assertEqual(sum(Decimal(row["fee"]) for row in fills), Decimal(fee))
                proof = result["comparator"]["positions"][0]["entry_budget_reconciliation"]
                self.assertEqual(proof["filled_quantity"], 92)
                self.assertEqual(Decimal(proof["cumulative_fee"]), Decimal(fee))
                self.assertTrue(proof["within_rounding"])
                self.assertIn("comparator_partial_or_unmatched_execution", reasons(result["permanent_parity_blockers"]))
                self.assertTrue(result["comparison_parity_blocked"])

    def test_funding_and_zero_share_refusals_are_not_certified_by_rounding(self):
        replay = MultiSessionReplay(**inputs(count=1))
        replay._state["cash"]["comparator"] = Decimal("2500")
        result = replay.run()
        self.assertIn("comparator_funding_mismatch", reasons(result["permanent_parity_blockers"]))
        proof = result["comparator"]["positions"][0]["entry_budget_reconciliation"]
        self.assertFalse(proof["within_rounding"])
        self.assertIn("comparator_budget_mismatch_beyond_rounding", reasons(result["permanent_parity_blockers"]))
        data = inputs(count=1)
        reprice(data, "benchmark", "10000")
        result = run_replay(**data)
        self.assertEqual(result["comparator"]["orders"], [])
        self.assertIsNone(result["comparator"]["positions"][0]["entry_budget_reconciliation"])
        self.assertIn("comparator_rounded_to_zero", reasons(result["permanent_parity_blockers"]))
        self.assertTrue(result["comparison_parity_blocked"])

    def test_completed_admission_audit_stays_fixed_after_a_spy_split(self):
        data = inputs(count=2)
        replay = MultiSessionReplay(**data, actions=(action(data, "split", security="INVENTED-SPY", ratio="2"),))
        replay.step_session(replay.days[0])
        before = replay.snapshot()["comparator"]["positions"][0]
        replay.step_session(replay.days[1])
        after = replay.snapshot()["comparator"]["positions"][0]
        self.assertEqual(before["quantity"], 92)
        self.assertEqual(after["quantity"], 184)
        self.assertEqual(before["entry_budget_reconciliation"], after["entry_budget_reconciliation"])
        self.assertEqual(before["source_budget"], after["source_budget"])
        self.assertEqual(before["entry_spent"], after["entry_spent"])
        self.assertTrue(after["entry_budget_reconciliation"]["within_rounding"])


if __name__ == "__main__":
    unittest.main()
