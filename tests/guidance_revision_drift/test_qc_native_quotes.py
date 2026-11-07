"""Invented native-shaped streams; these tests contain no QC market data."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import unittest
from zoneinfo import ZoneInfo

from research.guidance_revision_drift.historical_market import instant_ns
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes
from research.guidance_revision_drift.qc_native_quotes import QcNativeQuoteBatch


NY = ZoneInfo("America/New_York")
DECISION = datetime(2025, 4, 4, 14, tzinfo=timezone.utc)
CALLBACK = DECISION + timedelta(minutes=1)


def native_tick(at, side="bid", price="9.99", size=100, exchange="Q", **changes):
    row = {"time_ny": at.astimezone(NY).isoformat(timespec="milliseconds"),
           "bid_price": price if side == "bid" else "0",
           "ask_price": price if side == "ask" else "0",
           "bid_size": size if side == "bid" else 0,
           "ask_size": size if side == "ask" else 0,
           "exchange": exchange, "sale_condition": "1", "suspicious": False,
           "is_fill_forward": False}
    row.update(changes)
    return row


def native_pair(at, bid="9.99", ask="10.01", exchange="Q"):
    return [native_tick(at, "bid", bid, exchange=exchange),
            native_tick(at, "ask", ask, exchange=exchange)]


def native_body():
    return {"schema": "gdr.qc-native-quotes.v1", "provider": "quantconnect",
            "data_type": "Tick.Quote", "security_id": "INVENTED-SECURITY",
            "symbol": "INVENTED", "role": "stock", "session_date": "2025-04-04",
            "session_open_utc": "2025-04-04T13:30:00Z",
            "session_close_utc": "2025-04-04T20:00:00Z", "normalization": "Raw",
            "fill_forward": False, "ticks_complete": True, "minutes_complete": True,
            "ticks": native_pair(DECISION - timedelta(seconds=1))
                     + native_pair(CALLBACK - timedelta(seconds=1)),
            "minutes": [{"time_ny": "2025-04-04T10:00:00.000-04:00",
                         "end_time_ny": "2025-04-04T10:01:00.000-04:00",
                         "open": "10", "high": "11", "low": "9", "close": "10.5",
                         "volume": 10000, "is_fill_forward": False}]}


def native_batch(body=None):
    return QcNativeQuoteBatch.from_bytes(canonical_bytes(native_body() if body is None else body))


class QcNativeQuoteTests(unittest.TestCase):
    def test_input_bounds_and_declared_flags_are_not_measured_completeness(self):
        from research.guidance_revision_drift.qc_native_quotes import MAX_BYTES, MAX_TICKS
        body = native_body()
        body["ticks"] = [native_tick(DECISION)] * (MAX_TICKS + 1)
        with self.assertRaisesRegex(InputError, "bounded nonempty native tick"):
            native_batch(body)
        with self.assertRaises(InputError):
            QcNativeQuoteBatch.from_bytes(b" " * (MAX_BYTES + 1))
        body = native_body()
        body["ticks"][0]["is_fill_forward"] = True
        body["ticks"][0]["suspicious"] = True
        summary = native_batch(body).projection()
        self.assertEqual(summary["flagged_fill_forward_ticks"], 1)
        self.assertEqual(summary["flagged_suspicious_ticks"], 1)
        self.assertIs(summary["declared_fill_forward"], False)
        self.assertIs(summary["supplied_completeness_only"], True)

    def test_repeated_price_venue_tie_keeps_exact_best_price_under_low_context(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION, bid="9.99002", ask="10.01", exchange="Q")
        body["ticks"] += native_pair(DECISION, bid="9.99001", ask="10.02", exchange="P")
        with localcontext() as context:
            context.prec = 2
            quote = native_batch(body).decision_quote(DECISION)
        self.assertEqual(quote.bid, Decimal("9.99002"))
        self.assertEqual(quote.bid_exchange, "Q")

    def test_unknown_exchange_labels_and_outside_session_submission_refuse(self):
        for label in ("UNKNOWN", "unknown", "NASDAQ", "q", "?", "0"):
            body = native_body()
            body["ticks"][0]["exchange"] = label
            with self.subTest(label=label), self.assertRaises(InputError):
                native_batch(body)
        with self.assertRaises(InputError):
            native_batch().subsequent_minute(submitted_at=DECISION - timedelta(hours=1), callback_at=CALLBACK)

    def test_forged_decision_clock_refuses_cleanly_before_conversion(self):
        value = native_batch()
        quote = value.decision_quote(DECISION)
        for clock in (-10**100, 10**100, "x", True, None, quote.as_of_ns + 1):
            with self.subTest(clock_type=type(clock).__name__), self.assertRaises(InputError):
                value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                    decision_quote=replace(quote, as_of_ns=clock))

    def test_direct_snapshots_reject_nonfinite_money_aliases_and_bad_identity(self):
        quote = native_batch().decision_quote(DECISION)
        for fields in ({"bid": Decimal("NaN")}, {"ask": Decimal("sNaN")},
                       {"bid": "9.99"}, {"bid_size": True}, {"ask_size": 0},
                       {"source_sha256": "bad"}, {"bid_exchange": "UNKNOWN"},
                       {"observed_time_ns": quote.as_of_ns + 1_000_000}):
            with self.subTest(fields=tuple(fields)), self.assertRaises(InputError):
                replace(quote, **fields)

    def test_native_side_clocks_and_completed_post_submission_volume(self):
        value = native_batch()
        decision = value.decision_quote(DECISION)
        sample = value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                                         decision_quote=decision)
        self.assertEqual((decision.bid, decision.ask), (Decimal("9.99"), Decimal("10.01")))
        self.assertEqual(decision.bid_updated_ns, instant_ns(DECISION - timedelta(seconds=1)))
        self.assertEqual(decision.ask_updated_ns, decision.bid_updated_ns)
        self.assertEqual(decision.as_of_ns, instant_ns(DECISION))
        self.assertEqual(sample.minute.start_timestamp_ns, instant_ns(DECISION))
        self.assertEqual(sample.minute.end_timestamp_ns, instant_ns(CALLBACK))
        self.assertEqual(sample.projection()["minute_participation_cap_shares"], 100)
        self.assertGreater(sample.quote.bid_updated_ns, instant_ns(DECISION))
        self.assertGreater(sample.quote.ask_updated_ns, instant_ns(DECISION))
        self.assertEqual((value.security_id, value.symbol, value.role),
                         ("INVENTED-SECURITY", "INVENTED", "stock"))

    def test_future_ticks_are_sliced_out_and_not_used_to_complete_a_side(self):
        body = native_body()
        body["ticks"] = [native_tick(DECISION - timedelta(seconds=1))]
        body["ticks"] += [native_tick(DECISION + timedelta(milliseconds=1), "ask", "10.01")]
        value = native_batch(body)
        with self.assertRaises(InputError):
            value.decision_quote(DECISION)
        self.assertEqual(value.quote_at(DECISION + timedelta(milliseconds=1)).ask, Decimal("10.01"))

    def test_independent_bid_and_ask_age_are_both_enforced(self):
        body = native_body()
        body["ticks"] = [native_tick(DECISION - timedelta(seconds=60), "bid")]
        body["ticks"] += [native_tick(DECISION, "ask", "10.01")]
        self.assertEqual(native_batch(body).decision_quote(DECISION).bid, Decimal("9.99"))
        body["ticks"][0]["time_ny"] = native_tick(DECISION - timedelta(seconds=60, milliseconds=1))["time_ny"]
        with self.assertRaises(InputError):
            native_batch(body).decision_quote(DECISION)

    def test_last_bad_size_or_price_never_reveals_an_older_valid_side(self):
        for change in ({"bid_price": "0", "bid_size": 100}, {"bid_size": 0},
                       {"bid_price": "-1"}, {"bid_price": "12"}):
            body = native_body()
            body["ticks"] = native_pair(DECISION - timedelta(seconds=1))
            body["ticks"].append(native_tick(DECISION, **change))
            with self.subTest(change=change), self.assertRaises(InputError):
                native_batch(body).decision_quote(DECISION)

    def test_unknown_flags_suspicious_and_fill_forward_poison_both_sides(self):
        for change in ({"sale_condition": "4"}, {"sale_condition": "3"},
                       {"sale_condition": "0"}, {"suspicious": True},
                       {"is_fill_forward": True}):
            body = native_body()
            body["ticks"] = native_pair(DECISION - timedelta(seconds=3))
            body["ticks"].append(native_tick(DECISION - timedelta(seconds=2), **change))
            body["ticks"].append(native_tick(DECISION - timedelta(seconds=1), "ask", "10.01"))
            with self.subTest(change=change), self.assertRaises(InputError):
                native_batch(body).decision_quote(DECISION)
            body["ticks"].append(native_tick(DECISION, "bid"))
            self.assertEqual(native_batch(body).decision_quote(DECISION).bid, Decimal("9.99"))

    def test_all_zero_unknown_side_invalidates_until_both_sides_refresh(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION - timedelta(seconds=3))
        body["ticks"].append(native_tick(DECISION - timedelta(seconds=2), price="0", size=0))
        body["ticks"].append(native_tick(DECISION - timedelta(seconds=1), "ask", "10.01"))
        with self.assertRaises(InputError):
            native_batch(body).decision_quote(DECISION)
        body["ticks"].append(native_tick(DECISION))
        self.assertEqual(native_batch(body).decision_quote(DECISION).bid, Decimal("9.99"))

    def test_unused_zero_side_is_not_a_withdrawal(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION - timedelta(seconds=1))
        body["ticks"].append(native_tick(DECISION, "bid", "10"))
        result = native_batch(body).decision_quote(DECISION)
        self.assertEqual(result.ask, Decimal("10.01"))
        self.assertEqual(result.ask_updated_ns, instant_ns(DECISION - timedelta(seconds=1)))

    def test_same_millisecond_independent_side_order_commutes(self):
        left = native_body()
        right = deepcopy(left)
        right["ticks"] = list(reversed(right["ticks"][:2])) + list(reversed(right["ticks"][2:]))
        lq = native_batch(left).decision_quote(DECISION)
        rq = native_batch(right).decision_quote(DECISION)
        self.assertEqual((lq.bid, lq.ask, lq.bid_updated_ns, lq.ask_updated_ns),
                         (rq.bid, rq.ask, rq.bid_updated_ns, rq.ask_updated_ns))

    def test_identical_duplicate_does_not_inflate_displayed_size_or_volume(self):
        body = native_body()
        body["ticks"].insert(1, deepcopy(body["ticks"][0]))
        body["minutes"].append(deepcopy(body["minutes"][0]))
        value = native_batch(body)
        self.assertEqual(value.decision_quote(DECISION).bid_size, 100)
        self.assertEqual(value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK)
                         .projection()["minute_participation_cap_shares"], 100)

    def test_conflicting_same_side_tie_is_not_resolved_by_row_order(self):
        for change in ({"bid_price": "9.98"}, {"bid_size": 200},
                       {"sale_condition": "4"}, {"suspicious": True},
                       {"is_fill_forward": True}):
            body = native_body()
            body["ticks"] = native_pair(DECISION - timedelta(seconds=1))
            body["ticks"].append(dict(body["ticks"][0], **change))
            for rows in (body["ticks"], list(reversed(body["ticks"]))):
                with self.subTest(change=change), self.assertRaises(InputError):
                    native_batch(dict(body, ticks=rows)).decision_quote(DECISION)
            body["ticks"] += native_pair(DECISION)
            self.assertEqual(native_batch(body).decision_quote(DECISION).ask, Decimal("10.01"))

    def test_bad_same_millisecond_flag_cannot_be_rescued_by_regular_same_time_rows(self):
        body = native_body()
        body["ticks"] = [native_tick(DECISION, sale_condition="4")] + native_pair(DECISION)
        with self.assertRaises(InputError):
            native_batch(body).decision_quote(DECISION)

    def test_known_bad_or_stale_venue_is_not_dropped_to_reveal_a_nicer_quote(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION - timedelta(seconds=61), exchange="P")
        body["ticks"] += native_pair(DECISION, exchange="Q")
        with self.assertRaises(InputError):
            native_batch(body).decision_quote(DECISION)
        body["ticks"] = native_pair(DECISION - timedelta(seconds=1), exchange="P")
        body["ticks"] += native_pair(DECISION, exchange="Q")
        body["ticks"].append(native_tick(DECISION, size=0, exchange="P"))
        with self.assertRaises(InputError):
            native_batch(body).decision_quote(DECISION)

    def test_observed_venue_best_sides_are_selected_without_summing_sizes(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION - timedelta(seconds=1), bid="9.98", ask="10.01", exchange="P")
        body["ticks"] += native_pair(DECISION, bid="9.99", ask="10.02", exchange="Q")
        value = native_batch(body).decision_quote(DECISION)
        self.assertEqual((value.bid, value.ask), (Decimal("9.99"), Decimal("10.01")))
        self.assertEqual((value.bid_size, value.ask_size), (100, 100))
        self.assertIs(value.projection()["nbbo_verified"], False)

    def test_crossed_observed_best_pair_is_refused_without_healing(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION, bid="10", ask="10.01", exchange="P")
        body["ticks"] += native_pair(DECISION, bid="10.02", ask="10.03", exchange="Q")
        with self.assertRaises(InputError):
            native_batch(body).decision_quote(DECISION)

    def test_spread_boundary_is_exact_and_context_independent(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION, bid="399", ask="401")
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(native_batch(body).decision_quote(DECISION).ask, Decimal("401"))
            body["ticks"][1]["ask_price"] = "401.00000000000000001"
            with self.assertRaises(InputError):
                native_batch(body).decision_quote(DECISION)
            self.assertEqual(native_batch(body).quote_at(DECISION).ask, Decimal("401.00000000000000001"))

    def test_both_execution_sides_must_follow_submission(self):
        body = native_body()
        body["ticks"] = native_pair(DECISION)
        body["ticks"].append(native_tick(CALLBACK - timedelta(seconds=1), "ask", "10.01"))
        value = native_batch(body)
        with self.assertRaises(InputError):
            value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                                    decision_quote=value.decision_quote(DECISION))
        body["ticks"].append(native_tick(CALLBACK, "bid"))
        self.assertEqual(native_batch(body).subsequent_minute(submitted_at=DECISION,
                         callback_at=CALLBACK).quote.bid_updated_ns, instant_ns(CALLBACK))

    def test_incomplete_and_pre_submission_volume_is_not_borrowed(self):
        value = native_batch()
        for submitted, callback in ((DECISION + timedelta(microseconds=1), CALLBACK),
                                    (DECISION, CALLBACK - timedelta(microseconds=1)),
                                    (DECISION, CALLBACK + timedelta(microseconds=1)),
                                    (DECISION, DECISION)):
            with self.subTest(submitted=submitted, callback=callback), self.assertRaises(InputError):
                value.subsequent_minute(submitted_at=submitted, callback_at=callback)

    def test_source_membership_and_decision_before_submission_are_required(self):
        value = native_batch()
        other = native_batch(dict(native_body(), security_id="INVENTED-OTHER"))
        with self.assertRaises(InputError):
            value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                                    decision_quote=other.decision_quote(DECISION))
        late = value.quote_at(CALLBACK - timedelta(seconds=1))
        with self.assertRaises(InputError):
            value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK, decision_quote=late)

    def test_session_offset_millisecond_and_ordering_contracts_refuse(self):
        for stamp in ("2025-04-04T09:59:59.000-05:00", "2025-04-04T09:59:59.000",
                      "2025-04-04T09:59:59.000001-04:00", "2025-04-04T09:29:59.000-04:00"):
            body = native_body()
            body["ticks"][0]["time_ny"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(InputError):
                native_batch(body)
        body = native_body()
        body["ticks"] = body["ticks"][2:] + body["ticks"][:2]
        with self.assertRaises(InputError):
            native_batch(body)
        for at in (DECISION.replace(tzinfo=None), DECISION + timedelta(seconds=1),
                   DECISION + timedelta(days=1)):
            with self.subTest(at=at), self.assertRaises(InputError):
                native_batch().decision_quote(at)

    def test_winter_and_half_day_bounds_remain_explicit(self):
        body = native_body()
        body.update(session_date="2025-11-28", session_open_utc="2025-11-28T14:30:00Z",
                    session_close_utc="2025-11-28T18:00:00Z")
        decision = datetime(2025, 11, 28, 15, tzinfo=timezone.utc)
        body["ticks"] = native_pair(decision)
        body["minutes"][0].update(time_ny="2025-11-28T10:00:00.000-05:00",
                                  end_time_ny="2025-11-28T10:01:00.000-05:00")
        self.assertEqual(native_batch(body).decision_quote(decision).bid, Decimal("9.99"))
        body["ticks"] += native_pair(datetime(2025, 11, 28, 18, 0, 0, 1000, tzinfo=timezone.utc))
        with self.assertRaises(InputError):
            native_batch(body)

    def test_raw_completeness_and_explicit_benchmark_contracts(self):
        for field, invalid in (("normalization", "Adjusted"), ("fill_forward", True),
                               ("ticks_complete", False), ("minutes_complete", False),
                               ("ticks_complete", 1), ("fill_forward", 0),
                               ("provider", "massive"), ("data_type", "QuoteBar")):
            with self.subTest(field=field), self.assertRaises(InputError):
                native_batch(dict(native_body(), **{field: invalid}))
        value = native_batch(dict(native_body(), security_id="INVENTED-SPY", symbol="SPY", role="benchmark"))
        self.assertEqual(value.decision_quote(DECISION).ask, Decimal("10.01"))
        with self.assertRaises(InputError):
            native_batch(dict(native_body(), role="benchmark"))

    def test_paired_ticks_unknown_venue_unknown_fields_and_bad_types_refuse(self):
        for changes in ({"ask_price": "10.01", "ask_size": 100}, {"exchange": ""},
                        {"exchange": "not an exchange"}, {"bid_size": True},
                        {"bid_size": "100.5"}, {"suspicious": 0}, {"is_fill_forward": 0},
                        {"sale_condition": "not-hex"}, {"unknown": 1}):
            body = native_body()
            body["ticks"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(InputError):
                native_batch(body)
        with self.assertRaises(InputError):
            native_batch(dict(native_body(), authority=True))
        for raw in (canonical_bytes(native_body()).replace(b'"9.99"', b'NaN'),
                    canonical_bytes(native_body()).replace(b'"9.99"', b'Infinity'),
                    canonical_bytes(native_body()).replace(b'"9.99"', b'true')):
            with self.assertRaises(InputError):
                QcNativeQuoteBatch.from_bytes(raw)

    def test_provider_numeric_lexemes_never_round_through_binary_float(self):
        raw = canonical_bytes(native_body()).replace(b'"9.99"', b'9.9900000000000000000000000001')
        value = QcNativeQuoteBatch.from_bytes(raw)
        self.assertEqual(value.decision_quote(DECISION).bid, Decimal("9.9900000000000000000000000001"))

    def test_bad_trade_minute_is_not_accepted_as_native_volume(self):
        for changes in ({"volume": "1.5"}, {"volume": -1}, {"volume": True},
                        {"is_fill_forward": True}, {"low": "12"},
                        {"end_time_ny": "2025-04-04T10:00:59.000-04:00"},
                        {"time_ny": "2025-04-04T10:00:00.001-04:00"}, {"unknown": 1}):
            body = native_body()
            body["minutes"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(InputError):
                native_batch(body)
        body = native_body()
        body["minutes"].append(dict(body["minutes"][0], volume=20000))
        with self.assertRaises(InputError):
            native_batch(body)

    def test_detached_projections_do_not_assert_coverage_or_source_clock_inventions(self):
        body = native_body()
        value = native_batch(body)
        before = value.decision_quote(DECISION).projection()
        detached = value.decision_quote(DECISION).projection()
        body["ticks"][0]["bid_price"] = "99"
        detached["bid"] = "99"
        self.assertEqual(value.decision_quote(DECISION).projection(), before)
        for key in ("coverage_verified", "nbbo_verified", "point_in_time_data",
                    "native_execution_evidence", "execution_authority"):
            self.assertIs(before[key], False)
        self.assertFalse(any("sip" in key or "participant" in key or "sequence" in key for key in before))
        self.assertEqual(value.sha256, QcNativeQuoteBatch.from_bytes(value.raw_bytes).sha256)


if __name__ == "__main__":
    unittest.main()
