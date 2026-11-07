"""Invented input parity only; no provider rows, orders or native execution."""
from datetime import timedelta
from decimal import Decimal, localcontext
import unittest
from unittest.mock import patch

from data.financial_primitives import exact_decimal_multiply
from research.guidance_revision_drift.historical_market import instant_ns
from research.guidance_revision_drift.input_contracts import InputError
from research.guidance_revision_drift.order_planning import _affordable
from research.guidance_revision_drift.qc_native_quotes import QcNativeQuoteBatch
from research.guidance_revision_drift.qc_quote_parity import compare_native_quote_parity
from research.guidance_revision_drift.simulation import commission_total, execution_price
from tests.guidance_revision_drift.test_historical_market import (
    CALLBACK, DECISION, batch as paired_batch, market_body, quote,
)
from tests.guidance_revision_drift.test_qc_native_quotes import (
    native_batch, native_body, native_pair, native_tick,
)


def compare(native=None, paired=None):
    return compare_native_quote_parity(native or native_batch(), paired or paired_batch(),
        decision_at=DECISION, submitted_at=DECISION, callback_at=CALLBACK)


class QcQuoteParityTests(unittest.TestCase):
    def test_equivalent_stock_and_spy_inputs_match_without_provider_clock_equivalence(self):
        for role, symbol, security in (("stock", "INVENTED", "INVENTED-SECURITY"),
                                       ("benchmark", "SPY", "INVENTED-SPY")):
            native, paired = native_body(), market_body()
            for body in (native, paired):
                body.update(role=role, symbol=symbol, security_id=security)
            result = compare(native_batch(native), paired_batch(paired))
            with self.subTest(role=role):
                self.assertEqual(result["status"], "matched_usable_inputs")
                self.assertIs(result["usable_input_parity"], True)
                self.assertEqual(result["mismatches"], [])
                for name in ("decision", "execution"):
                    self.assertEqual(result["checks"][name], {
                        "native_status": "accepted", "paired_status": "accepted",
                        "acceptance_match": True, "quote_values_match": True})
                self.assertIs(result["execution_minute_values_match"], True)
                self.assertIs(result["execution_minute_capacity_match"], True)
                self.assertIs(result["clock_equivalence_verified"], False)

    def test_report_emits_hashes_and_checks_without_raw_values_or_authority(self):
        native, paired = native_batch(), paired_batch()
        report = compare(native, paired)
        self.assertEqual(report["native_source_sha256"], native.sha256)
        self.assertEqual(report["paired_source_sha256"], paired.sha256)
        self.assertEqual(report["decision_at_ns"], instant_ns(DECISION))
        self.assertEqual(report["submitted_at_ns"], instant_ns(DECISION))
        self.assertEqual(report["callback_at_ns"], instant_ns(CALLBACK))
        for key in ("nbbo_verified", "coverage_verified", "point_in_time_data",
                    "native_execution_evidence", "backtest_ready", "execution_authority"):
            self.assertIs(report[key], False)
        for value in ("9.99", "10.01", "10.5", "bid_updated_ns", "sip_timestamp"):
            self.assertNotIn(value, str(report))
        report["checks"]["decision"]["native_status"] = "changed"
        self.assertEqual(compare(native, paired)["checks"]["decision"]["native_status"], "accepted")

    def test_invalid_latest_native_side_surfaces_decision_acceptance_mismatch(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION - timedelta(seconds=1)) + [
            native_tick(DECISION, side="bid", price="0", size=100)] + native_pair(
                CALLBACK - timedelta(seconds=1))
        result = compare(native_batch(body))
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("decision_acceptance", result["mismatches"])
        self.assertEqual(result["checks"]["decision"]["native_status"], "refused")
        self.assertEqual(result["checks"]["execution"]["native_status"], "accepted")

    def test_two_refusals_are_visible_and_never_usable_parity(self):
        native, paired = native_body(), market_body()
        native["ticks"] = native_pair(DECISION - timedelta(seconds=1), bid="12", ask="10") + native_pair(
            CALLBACK - timedelta(seconds=1), bid="12", ask="10")
        paired["quotes"] = [quote(DECISION - timedelta(seconds=1), bid="12", ask="10"),
            quote(CALLBACK - timedelta(seconds=1), sequence=2, bid="12", ask="10")]
        result = compare(native_batch(native), paired_batch(paired))
        self.assertEqual(result["status"], "matched_refusals")
        self.assertIs(result["usable_input_parity"], False)
        self.assertEqual(result["mismatches"], [])
        for name in ("decision", "execution"):
            self.assertEqual(result["checks"][name]["native_status"], "refused")
            self.assertEqual(result["checks"][name]["paired_status"], "refused")
            self.assertIsNone(result["checks"][name]["quote_values_match"])

    def test_asymmetric_side_age_cannot_be_hidden_by_newer_other_side(self):
        body = native_body()
        body["ticks"] = [native_tick(DECISION - timedelta(seconds=61), side="bid"),
            native_tick(DECISION - timedelta(seconds=1), side="ask", price="10.01")]
        body["ticks"] += native_pair(CALLBACK - timedelta(seconds=1))
        result = compare(native_batch(body))
        self.assertIn("decision_acceptance", result["mismatches"])
        self.assertIs(result["usable_input_parity"], False)

    def test_execution_needs_both_selected_side_updates_after_submission(self):
        native, paired = native_body(), market_body()
        native["ticks"] = native_pair(DECISION) + [
            native_tick(CALLBACK - timedelta(seconds=1), side="ask", price="10.01")]
        paired["quotes"] = [quote(DECISION), quote(CALLBACK - timedelta(seconds=1), sequence=2)]
        result = compare(native_batch(native), paired_batch(paired))
        self.assertEqual(result["checks"]["decision"]["native_status"], "accepted")
        self.assertIn("execution_acceptance", result["mismatches"])

    def test_future_invalid_input_does_not_change_either_as_of_selection(self):
        native, paired = native_body(), market_body()
        later = CALLBACK + timedelta(milliseconds=1)
        native["ticks"] += native_pair(later, bid="12", ask="10")
        paired["quotes"].append(quote(later, sequence=3, bid="12", ask="10"))
        result = compare(native_batch(native), paired_batch(paired))
        self.assertEqual(result["status"], "matched_usable_inputs")

    def test_price_size_minute_and_capacity_differences_are_not_silently_accepted(self):
        native = native_body()
        native["ticks"] = native_pair(DECISION - timedelta(seconds=1), ask="10.02") + native_pair(
            CALLBACK - timedelta(seconds=1), bid="9.98")
        native["ticks"][-1]["ask_size"] = 200
        native["minutes"][0]["volume"] = 9999
        result = compare(native_batch(native))
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(set(result["mismatches"]), {
            "decision_quote_values", "execution_quote_values",
            "execution_minute_values", "execution_minute_capacity"})
        self.assertIs(result["usable_input_parity"], False)

    def test_missing_execution_interval_remains_a_refusal_on_both_sources(self):
        native, paired = native_body(), market_body()
        minute = native["minutes"][0]
        minute["time_ny"] = "2025-04-04T10:01:00.000-04:00"
        minute["end_time_ny"] = "2025-04-04T10:02:00.000-04:00"
        paired["minutes"][0]["t"] = instant_ns(CALLBACK) // 1_000_000
        result = compare(native_batch(native), paired_batch(paired))
        self.assertEqual(result["status"], "matched_refusals")
        self.assertEqual(result["checks"]["decision"]["native_status"], "accepted")
        self.assertEqual(result["checks"]["execution"]["native_status"], "refused")
        self.assertIs(result["usable_input_parity"], False)

    def test_original_sizing_impact_fee_and_volume_functions_have_identical_inputs(self):
        native, paired = native_batch(), paired_batch()
        left, right = (value.decision_quote(DECISION) for value in (native, paired))
        left_run, right_run = (value.subsequent_minute(submitted_at=DECISION,
            callback_at=CALLBACK) for value in (native, paired))
        with localcontext() as context:
            context.prec = 2
            for mode in ("base", "stress"):
                limit_left = exact_decimal_multiply(left.ask, Decimal("1.01"))
                limit_right = exact_decimal_multiply(right.ask, Decimal("1.01"))
                quantity_left = _affordable(Decimal("5000"), limit_left, mode)
                quantity_right = _affordable(Decimal("5000"), limit_right, mode)
                with self.subTest(mode=mode):
                    self.assertEqual(quantity_left, quantity_right)
                    self.assertGreater(quantity_left, 0)
                    self.assertEqual(commission_total(quantity_left, mode), commission_total(quantity_right, mode))
                    for side in ("buy", "sell"):
                        self.assertEqual(execution_price(side, left_run.quote.bid, left_run.quote.ask, mode),
                                         execution_price(side, right_run.quote.bid, right_run.quote.ask, mode))
                    self.assertEqual(left_run.minute.volume // 100, right_run.minute.volume // 100)
                    self.assertEqual(left_run.minute.volume // 100, 100)

    def test_identity_and_request_clock_mismatches_refuse_before_comparison(self):
        for changed in ({"security_id": "INVENTED-OTHER"}, {"symbol": "OTHER"},
                        {"role": "benchmark", "symbol": "SPY"}):
            native = native_body()
            native.update(changed)
            with self.subTest(changed=changed), self.assertRaisesRegex(InputError, "security and session"):
                compare(native_batch(native))
        for times in ((DECISION.replace(tzinfo=None), DECISION, CALLBACK),
                      (CALLBACK, DECISION, CALLBACK), (DECISION, DECISION, DECISION)):
            with self.subTest(times=times), self.assertRaises(InputError):
                compare_native_quote_parity(native_batch(), paired_batch(),
                    decision_at=times[0], submitted_at=times[1], callback_at=times[2])
        with self.assertRaisesRegex(InputError, "exact native"):
            compare_native_quote_parity(paired_batch(), paired_batch(), decision_at=DECISION,
                submitted_at=DECISION, callback_at=CALLBACK)

    def test_programming_errors_are_not_turned_into_matched_refusals(self):
        with patch.object(QcNativeQuoteBatch, "decision_quote", side_effect=RuntimeError("test defect")):
            with self.assertRaises(RuntimeError):
                compare()


if __name__ == "__main__":
    unittest.main()
