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
        self.assertTrue(result["comparison_parity_blocked"])
        self.assertIn("comparator_budget_mismatch_beyond_rounding", [row["reason"] for row in result["permanent_parity_blockers"]])
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

    def test_separate_positive_parity_fixture_does_not_erase_53_price_blocker(self):
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


if __name__ == "__main__":
    unittest.main()
