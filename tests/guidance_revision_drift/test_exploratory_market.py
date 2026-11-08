"""Invented paired quote and FirstRate rows; no data, provider or SDK access."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
import unittest

from research.guidance_revision_drift.exploratory_market import (
    AlpacaQuoteBatch, ExploratoryMarketBatch, attach_first_rate_minutes,
    decode_alpaca_quote_pages,
)
from research.guidance_revision_drift.firstrate import parse_line, reconcile_records
from research.guidance_revision_drift.historical_market import instant_ns
from research.guidance_revision_drift.input_contracts import InputError
from research.guidance_revision_drift.research_reference import CalendarSession


AT = datetime(2025, 4, 4, 14, tzinfo=timezone.utc)
ASSUMPTION = 'a' * 64


def session():
    return CalendarSession(date(2025, 4, 4), AT - timedelta(minutes=30), AT + timedelta(hours=6))


def quote(stamp='2025-04-04T13:59:59.000000001Z', **changes):
    row = {'t': stamp, 'bp': 10, 'ap': 10.01, 'bs': 2, 'as': 3,
           'bx': 'Q', 'ax': 'P', 'c': ['R'], 'z': 'C'}
    row.update(changes)
    return row


def raw_page(rows=None, token=None, symbol='SYN', **changes):
    body = {'symbol': symbol, 'quotes': [quote()] if rows is None else rows, 'next_page_token': token}
    body.update(changes)
    return json.dumps(body, separators=(',', ':')).encode()


def batch(rows=None, *, pages=None, allow=False, anchor=None, symbol='SYN', role='stock',
          supplied_session=None, capture_start_ns=None, capture_end_ns=None):
    supplied = supplied_session or session()
    return decode_alpaca_quote_pages(tuple(pages) if pages is not None else (raw_page(rows, symbol=symbol),),
        security_id='INVENTED-SECURITY', symbol=symbol, role=role, session=supplied,
        capture_start_ns=instant_ns(supplied.open_utc) if capture_start_ns is None else capture_start_ns,
        capture_end_ns=instant_ns(supplied.close_utc) if capture_end_ns is None else capture_end_ns,
        allow_unknown_conditions=allow, assumption_sha256=anchor)


def minute_rows(symbol='SYN', stamp='2025-04-04 10:00:00', volume='10000'):
    parsed = parse_line((stamp + ',10,11,9,10.5,' + volume + '\n').encode(), source_id='INVENTED-SOURCE',
        member=symbol + '_full_1min_UNADJUSTED.txt', line_number=1, symbol=symbol, kind='minute')
    return reconcile_records((parsed,)).accepted


class ExploratoryMarketTests(unittest.TestCase):
    def test_decimal_and_nanosecond_lexemes_remain_exact(self):
        raw = raw_page().replace(b'"bp":10,', b'"bp":10.000000000000000000000001,')
        with localcontext() as ctx:
            ctx.prec = 2
            value = batch(pages=[raw]).decision_quote(AT)
            self.assertEqual(value.bid, Decimal('10.000000000000000000000001'))
            self.assertEqual(value.timestamp_ns, instant_ns(AT - timedelta(seconds=1)) + 1)
            projected = value.projection()
            self.assertEqual(projected['bid'], '10.000000000000000000000001')
        self.assertIsNone(projected['participant_timestamp_ns'])
        self.assertIsNone(projected['sip_timestamp_ns'])
        self.assertIsNone(projected['sequence_number'])
        self.assertFalse(projected['source_execution_qualified'])

    def test_unknown_literal_is_retained_and_requires_explicit_model(self):
        rows = [quote(c=['?'])]
        original = batch(rows)
        self.assertEqual(original.quotes[0].conditions, ('?',))
        with self.assertRaises(InputError):
            original.decision_quote(AT)
        assumed = batch(rows, allow=True, anchor=ASSUMPTION)
        value = assumed.decision_quote(AT)
        self.assertEqual(value.conditions, ('?',))
        self.assertTrue(value.unknown_condition_assumed)
        self.assertEqual(value.projection()['condition_model_assumption_sha256'], ASSUMPTION)
        for name in ('source_execution_qualified', 'point_in_time_data', 'original_condition_recovered'):
            self.assertFalse(value.projection()[name])

    def test_unknown_model_choice_cannot_admit_known_adverse_or_missing_flags(self):
        for flags in (['N'], ['R', 'N'], ['?', 'N'], [], [' ']):
            with self.subTest(flags=flags):
                value = batch([quote(c=flags)], allow=True, anchor=ASSUMPTION)
                with self.assertRaises(InputError):
                    value.decision_quote(AT)
        self.assertTrue(batch([quote(c=['R', '?'])], allow=True, anchor=ASSUMPTION).decision_quote(AT).unknown_condition_assumed)

    def test_choice_and_anchor_must_be_strict_and_consistent(self):
        for allow, anchor in ((1, ASSUMPTION), (True, None), (True, 'bad'), (False, ASSUMPTION)):
            with self.subTest(allow=allow, anchor=anchor), self.assertRaises(InputError):
                batch(allow=allow, anchor=anchor)

    def test_latest_invalid_row_never_reveals_earlier_valid_quote(self):
        good = quote('2025-04-04T13:59:58Z')
        for changes in ({'c': ['N']}, {'c': ['?']}, {'bp': 0}, {'bs': 0}, {'bp': 11}, {'bx': ' '}):
            with self.subTest(changes=changes):
                value = batch([good, quote(**changes)])
                self.assertEqual(len(value.quotes), 2)
                with self.assertRaises(InputError):
                    value.decision_quote(AT)

    def test_equal_clock_conflicts_refuse_until_strictly_later_refresh(self):
        one, two = quote(), quote(bp=9.99)
        for rows in ([one, two], [two, one]):
            with self.subTest(order=rows), self.assertRaisesRegex(InputError, 'ambiguous'):
                batch(rows).decision_quote(AT)
        rows = [one, two, quote('2025-04-04T13:59:59.000000002Z')]
        self.assertEqual(batch(rows).decision_quote(AT).timestamp_ns % 1000, 2)

    def test_equal_clock_identical_duplicate_state_does_not_add_liquidity(self):
        value = batch([quote(), quote()])
        self.assertEqual(len(value.quotes), 2)
        self.assertEqual(value.decision_quote(AT).bid_size_raw, 2)

    def test_strict_freshness_and_after_submission_keep_ns_boundary(self):
        self.assertEqual(batch([quote('2025-04-04T13:59:00Z')]).decision_quote(AT).bid, Decimal(10))
        with self.assertRaisesRegex(InputError, 'stale'):
            batch([quote('2025-04-04T13:58:59.999999999Z')]).decision_quote(AT)
        with self.assertRaises(InputError):
            batch([quote('2025-04-04T14:00:00Z')]).quote_at(AT + timedelta(seconds=1), after=AT)
        value = batch([quote('2025-04-04T14:00:00.000000001Z')])
        self.assertEqual(value.quote_at(AT + timedelta(seconds=1), after=AT).timestamp_ns, instant_ns(AT) + 1)

    def test_money_clock_size_and_json_mutations_refuse(self):
        changed = ({'bp': '10'}, {'bp': True}, {'bp': -1}, {'bs': 1.5}, {'bs': True},
                   {'as': -1}, {'t': '2025-04-04T13:59:59.1234567890Z'},
                   {'t': '2025-04-04T13:59:59-00:00'}, {'t': '2025-04-05T13:59:59Z'},
                   {'z': 'O'}, {'bx': 'UNKNOWN'}, {'c': [True]}, {'c': ['R', 'R', 'R']})
        for changes in changed:
            with self.subTest(changes=changes), self.assertRaises(InputError):
                batch([quote(**changes)])
        raw = raw_page()
        for changed_raw in (raw.replace(b'"bp":10', b'"bp":NaN'),
                            raw.replace(b'"bp":10', b'"bp":Infinity'),
                            raw.replace(b'"bp":10', b'"bp":10,"bp":11')):
            with self.subTest(raw=changed_raw), self.assertRaises(InputError):
                batch(pages=[changed_raw])

    def test_symbol_currency_roles_and_pages_are_exact(self):
        for raw in (raw_page(symbol='OTHER'), raw_page(currency='EUR'), raw_page(extra=False)):
            with self.subTest(raw=raw), self.assertRaises(InputError):
                batch(pages=[raw])
        for symbol, role in (('SPY', 'stock'), ('SYN', 'benchmark'), ('SPY', 'other')):
            with self.subTest(symbol=symbol, role=role), self.assertRaises(InputError):
                batch(symbol=symbol, role=role)
        self.assertEqual(batch(symbol='SPY', role='benchmark').symbol, 'SPY')

    def test_complete_page_chain_and_global_clock_order_are_required(self):
        first = raw_page([quote('2025-04-04T13:59:58Z')], token='NEXT')
        last = raw_page([quote()])
        self.assertEqual(len(batch(pages=[first, last]).quotes), 2)
        cases = ([first], [last, last], [first, raw_page(token='NEXT')],
                 [raw_page(token=''), last], [raw_page(token=True), last],
                 [raw_page([quote()], token='NEXT'), raw_page([quote('2025-04-04T13:59:58Z')])])
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises(InputError):
                batch(pages=pages)

    def test_empty_page_is_retained_as_missing_quote_not_fabricated(self):
        value = batch([])
        self.assertEqual(value.quotes, ())
        with self.assertRaisesRegex(InputError, 'no observed'):
            value.decision_quote(AT)

    def test_actual_capture_bounds_fence_later_selection_and_execution_input(self):
        # The latest row is fresh at 10:07, but the requested capture ended 10:06:30.
        value = batch([quote('2025-04-04T14:06:15Z')],
            capture_start_ns=instant_ns(AT - timedelta(minutes=1)),
            capture_end_ns=instant_ns(AT + timedelta(minutes=6, seconds=30)))
        self.assertEqual(value.quote_at(AT + timedelta(minutes=6, seconds=15)).bid, Decimal(10))
        with self.assertRaisesRegex(InputError, 'captured request interval'):
            value.quote_at(AT + timedelta(minutes=7))
        market = attach_first_rate_minutes(value, minute_rows(stamp='2025-04-04 10:06:00'))
        with self.assertRaisesRegex(InputError, 'captured request interval'):
            market.subsequent_minute(submitted_at=AT + timedelta(minutes=6),
                                     callback_at=AT + timedelta(minutes=7))

    def test_capture_bounds_are_required_strict_ordered_and_in_session(self):
        with self.assertRaises(TypeError):
            decode_alpaca_quote_pages((raw_page(),), security_id='INVENTED-SECURITY',
                symbol='SYN', role='stock', session=session())
        start, end = instant_ns(session().open_utc), instant_ns(session().close_utc)
        for one, two in ((True, end), (start, False), (Decimal(start), end),
                         (end, start), (start, start), (start - 1, end), (start, end + 1)):
            with self.subTest(bounds=(one, two)), self.assertRaises(InputError):
                batch(capture_start_ns=one, capture_end_ns=two)

    def test_raw_rows_and_selection_must_respect_inclusive_capture_edges(self):
        start, end = instant_ns(AT - timedelta(seconds=1)), instant_ns(AT + timedelta(seconds=1))
        value = batch([quote('2025-04-04T13:59:59Z')], capture_start_ns=start, capture_end_ns=end)
        self.assertEqual(value.quote_at(AT - timedelta(seconds=1)).timestamp_ns, start)
        for at in (AT - timedelta(seconds=2), AT + timedelta(seconds=1, microseconds=1)):
            with self.subTest(at=at), self.assertRaisesRegex(InputError, 'captured request interval'):
                value.quote_at(at)
        exact_end = batch([quote('2025-04-04T14:00:01Z')], capture_start_ns=start, capture_end_ns=end)
        self.assertEqual(exact_end.quote_at(AT + timedelta(seconds=1)).timestamp_ns, end)
        for stamp in ('2025-04-04T13:59:58.999999999Z', '2025-04-04T14:00:01.000000001Z'):
            with self.subTest(stamp=stamp), self.assertRaises(InputError):
                batch([quote(stamp)], capture_start_ns=start, capture_end_ns=end)
        one_ns_earlier_end = batch([quote('2025-04-04T13:59:59.999999999Z')],
            capture_start_ns=start, capture_end_ns=instant_ns(AT) - 1)
        with self.assertRaisesRegex(InputError, 'captured request interval'):
            one_ns_earlier_end.quote_at(AT)

    def test_capture_bounds_bind_identity_distinctly_from_returned_extent(self):
        one = batch(capture_start_ns=instant_ns(AT - timedelta(minutes=1)),
                    capture_end_ns=instant_ns(AT + timedelta(minutes=6)))
        two = replace(one, capture_end_ns=one.capture_end_ns + 1)
        three = replace(one, capture_start_ns=one.capture_start_ns - 1)
        self.assertNotEqual(one.sha256, two.sha256)
        self.assertNotEqual(one.sha256, three.sha256)
        projected = one.projection()
        self.assertEqual(projected['capture_start_ns'], one.capture_start_ns)
        self.assertEqual(projected['capture_end_ns'], one.capture_end_ns)
        self.assertNotEqual(projected['first_returned_quote_ns'], one.capture_start_ns)
        self.assertNotEqual(projected['last_returned_quote_ns'], one.capture_end_ns)
        self.assertFalse(projected['source_completeness_verified'])

    def test_protected_session_refuses_and_raw_units_are_not_converted(self):
        forbidden = CalendarSession(date(2026, 9, 1), datetime(2026, 9, 1, 13, 30, tzinfo=timezone.utc),
                                    datetime(2026, 9, 1, 20, tzinfo=timezone.utc))
        with self.assertRaises(InputError):
            batch(supplied_session=forbidden)
        before = batch().decision_quote(AT)
        self.assertEqual((before.raw_size_unit, before.bid_size_raw), ('round_lots', 2))
        day = date(2025, 11, 5)
        later = CalendarSession(day, datetime(2025, 11, 5, 14, 30, tzinfo=timezone.utc), datetime(2025, 11, 5, 21, tzinfo=timezone.utc))
        value = batch([quote('2025-11-05T14:59:59Z')], supplied_session=later)
        self.assertEqual(value.decision_quote(datetime(2025, 11, 5, 15, tzinfo=timezone.utc)).raw_size_unit, 'shares')

    def test_unchanged_entry_clock_and_spread_remain_enforced(self):
        with self.assertRaisesRegex(InputError, '10:00'):
            batch().decision_quote(AT - timedelta(seconds=1))
        with self.assertRaisesRegex(InputError, 'spread'):
            batch([quote(bp=9, ap=11)]).decision_quote(AT)
        self.assertEqual(batch([quote(bp=9, ap=11)]).quote_at(AT).bid, Decimal(9))

    def test_first_rate_completed_minute_and_subsequent_quote_bind_together(self):
        quotes = batch([quote(), quote('2025-04-04T14:00:59.999999999Z')])
        market = attach_first_rate_minutes(quotes, minute_rows())
        result = market.subsequent_minute(submitted_at=AT, callback_at=AT + timedelta(minutes=1),
                                          decision_quote=market.decision_quote(AT))
        self.assertEqual(result.quote.timestamp_ns, instant_ns(AT + timedelta(minutes=1)) - 1)
        self.assertEqual(result.minute.volume, 10000)
        self.assertEqual(result.projection()['minute_participation_cap_shares'], 100)
        self.assertEqual((market.security_id, market.symbol, market.role), ('INVENTED-SECURITY', 'SYN', 'stock'))
        self.assertIsInstance(market.sha256, str)
        self.assertFalse(market.projection()['backtest_ready'])

    def test_missing_wrong_overlapping_duplicate_and_warning_minutes_refuse(self):
        quotes = batch([quote('2025-04-04T14:00:59Z')])
        for rows in ((), minute_rows('OTHER'), minute_rows() + minute_rows(),
                     (replace(minute_rows()[0], warnings=('unresolved',)),)):
            with self.subTest(rows=rows), self.assertRaises(InputError):
                attach_first_rate_minutes(quotes, rows)
        market = attach_first_rate_minutes(quotes, minute_rows())
        for submitted, callback in ((AT + timedelta(seconds=1), AT + timedelta(minutes=1)),
                                    (AT, AT + timedelta(minutes=2)), (AT, AT)):
            with self.subTest(submitted=submitted, callback=callback), self.assertRaises(InputError):
                market.subsequent_minute(submitted_at=submitted, callback_at=callback)

    def test_same_quote_before_submission_cannot_create_later_execution(self):
        market = attach_first_rate_minutes(batch([quote('2025-04-04T14:00:00Z')]), minute_rows())
        with self.assertRaisesRegex(InputError, 'subsequent'):
            market.subsequent_minute(submitted_at=AT, callback_at=AT + timedelta(minutes=1))

    def test_source_identity_changes_and_tampered_batch_rechecks_bytes(self):
        one = batch()
        two = batch(allow=True, anchor=ASSUMPTION)
        self.assertNotEqual(one.sha256, two.sha256)
        with self.assertRaises(FrozenInstanceError):
            one.symbol = 'OTHER'
        for field, changed in (('symbol', 'OTHER'), ('session', None),
                               ('allow_unknown_conditions', 1)):
            value = batch()
            object.__setattr__(value, field, changed)
            with self.subTest(field=field), self.assertRaises(InputError):
                value.quote_at(AT)

    def test_public_quote_cannot_hide_invalid_mutable_or_float_fields(self):
        original = batch().quotes[0]
        for changes in ({'bid': 10.0}, {'bid': Decimal('NaN')}, {'timestamp_ns': True},
                        {'conditions': ['R']}, {'bid_size_raw': True},
                        {'source_page_sha256': 'bad'}, {'raw_size_unit': 'guessed_shares'},
                        {'unknown_condition_assumption_sha256': ASSUMPTION}):
            with self.subTest(changes=changes), self.assertRaises(InputError):
                replace(original, **changes)


if __name__ == '__main__':
    unittest.main()
