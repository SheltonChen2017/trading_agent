"""Only invented values in public-field-shaped records; no vendor access."""
from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from unittest.mock import patch

from research.guidance_revision_drift.events import EventBook
from research.guidance_revision_drift.vendor_payloads import (
    SyntheticGuidanceContext, VendorObservation, VendorPayloadError, parse_synthetic_guidance,
)


def context(identity="SYN-D1", day="2025-01-02", **changes):
    values = {"schema": "gdr.synthetic.vendor-context.v1", "provider_id": identity,
        "ticker": "SYN-TICKER-A", "issuer_id": "SYN-ISSUER-A", "security_id": "SYN-SEC-A",
        "version": 1, "kind": "disclosure", "supersedes": None,
        "published_at": day + "T12:00:00Z", "received_at": day + "T12:01:00Z",
        "validated_at": day + "T12:02:00Z", "announcement_timezone": "America/New_York",
        "fiscal_start": "2025-01-01", "fiscal_end": "2025-12-31", "fiscal_year": 2025,
        "revenue_input_units": "USD", "eps_input_units": "USD_per_share",
        "revenue_basis": "gaap", "eps_basis": "adj", "adjustment_definition": "SYN-ADJ-1",
        "share_basis": "SYN-SHARES-1", "scope": "SYN-ORGANIC-1",
        "revenue_kind": "point", "eps_kind": "point", "release_type": "official", "positioning": "primary"}
    values.update(changes)
    return SyntheticGuidanceContext.from_dict(values)


def payload(identity="SYN-D1", day="2025-01-02", **changes):
    values = {"benzinga_id": identity, "ticker": "SYN-TICKER-A", "date": day, "time": "07:00:00",
        "last_updated": day + "T12:00:00Z", "currency": "USD", "eps_method": "adj",
        "revenue_method": "gaap", "fiscal_period": "FY", "fiscal_year": 2025,
        "max_eps_guidance": 1, "min_eps_guidance": 1, "max_revenue_guidance": 100000000,
        "min_revenue_guidance": 100000000, "release_type": "official", "positioning": "primary"}
    values.update(changes)
    return values


def raw(identity="SYN-D1", day="2025-01-02", **changes):
    return json.dumps(payload(identity, day, **changes), sort_keys=True).encode()


def observation(identity="SYN-D1", day="2025-01-02", *, changes=None, context_changes=None):
    return parse_synthetic_guidance(raw(identity, day, **(changes or {})), context(identity, day, **(context_changes or {})))


class VendorPayloadTests(unittest.TestCase):
    def test_exact_json_numbers_normalize_without_binary_float_or_decimal_context(self):
        source = raw().replace(b'"min_eps_guidance": 1', b'"min_eps_guidance": 1.123456789123456789')
        source = source.replace(b'"max_eps_guidance": 1', b'"max_eps_guidance": 1.123456789123456789')
        with localcontext() as ctx:
            ctx.prec = 3
            result = parse_synthetic_guidance(source, context())
        self.assertEqual(result.disclosure.periods[0].eps.lower, Decimal("1.123456789123456789"))
        self.assertEqual(result.disclosure.periods[0].revenue.lower, Decimal("100"))
        self.assertEqual(result.raw_bytes, source)

    def test_units_require_explicit_context_and_scale_exactly(self):
        result = observation(changes={"min_revenue_guidance": 100, "max_revenue_guidance": 100},
                             context_changes={"revenue_input_units": "USD_millions"})
        self.assertEqual(result.disclosure.periods[0].revenue.lower, Decimal("100"))
        for changes in ({"revenue_input_units": "millions"}, {"eps_input_units": "cents"}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                context(**changes)

    def test_raw_and_context_are_immutable_and_projections_detached(self):
        supplied = context()
        result = parse_synthetic_guidance(raw(), supplied)
        before = result.sha256
        supplied.to_dict()["issuer_id"] = "SYN-OTHER"
        result.disclosure.to_dict()["periods"].clear()
        self.assertEqual(result.sha256, before)
        with self.assertRaises(FrozenInstanceError):
            result.raw_bytes = b"{}"
        object.__setattr__(supplied, "canonical_bytes", b"{}")
        self.assertEqual(result.sha256, before)
        with self.assertRaises(VendorPayloadError):
            parse_synthetic_guidance(raw(), supplied)

    def test_all_context_fields_required_and_unknown_authority_refuses(self):
        original = context().to_dict()
        for name in original:
            changed = dict(original)
            del changed[name]
            with self.subTest(missing=name), self.assertRaises(VendorPayloadError):
                SyntheticGuidanceContext.from_dict(changed)
        for name in ("approved", "point_in_time_data", "capture_verified"):
            with self.subTest(name=name), self.assertRaises(VendorPayloadError):
                SyntheticGuidanceContext.from_dict({**original, name: True})

    def test_required_provider_fields_and_unknown_keys_refuse(self):
        for name in payload():
            changed = payload()
            del changed[name]
            with self.subTest(name=name), self.assertRaises(VendorPayloadError):
                parse_synthetic_guidance(json.dumps(changed).encode(), context())
        with self.assertRaises(VendorPayloadError):
            observation(changes={"is_pit": True})

    def test_malformed_encoding_duplicates_and_resource_limits_refuse(self):
        for malformed in (b'{}', b'[]', b'\xff', b'\xef\xbb\xbf{}', b'{"x":1,"x":2}',
                          b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e1000}', b'[' * 2000 + b']' * 2000,
                          b' ' * 32769, bytearray(raw())):
            with self.subTest(malformed_type=type(malformed)), self.assertRaises(VendorPayloadError):
                parse_synthetic_guidance(malformed, context())

    def test_non_synthetic_id_and_identity_context_mismatch_refuse(self):
        for changes in ({"provider_id": "AAPL"}, {"ticker": "AAPL"}, {"issuer_id": "1234"},
                        {"security_id": "US1234"}, {"version": True}, {"version": 0}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                context(**changes)
        for changes in ({"benzinga_id": "SYN-WRONG"}, {"ticker": "SYN-OTHER"}, {"benzinga_id": "12345"}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                observation(changes=changes)

    def test_period_basis_currency_and_range_refusals(self):
        for changes in ({"fiscal_period": "Q1"}, {"fiscal_year": True}, {"fiscal_year": 2024},
                        {"eps_method": "gaap"}, {"revenue_method": "adj"}, {"currency": "EUR"},
                        {"min_revenue_guidance": None}, {"min_eps_guidance": "1"},
                        {"min_eps_guidance": None}, {"min_eps_guidance": True},
                        {"min_revenue_guidance": 100000001}, {"min_eps_guidance": 2},
                        {"positioning": "secondary"}, {"importance": 6}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                observation(changes=changes)
        for changes in ({"fiscal_end": "2025-03-31"}, {"fiscal_year": 2024}, {"revenue_basis": "adj"},
                        {"share_basis": "unknown"}, {"eps_kind": "range"}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                observation(context_changes=changes)

    def test_explicit_range_and_negative_eps_are_not_fabricated_points(self):
        result = observation(changes={"min_eps_guidance": -1, "max_eps_guidance": 2,
                                      "min_revenue_guidance": 99000000, "max_revenue_guidance": 101000000},
                             context_changes={"eps_kind": "range", "revenue_kind": "range"})
        self.assertEqual(result.disclosure.periods[0].eps.lower, Decimal("-1"))

    def test_publication_timezone_is_explicit_and_utc_date_can_differ(self):
        ctx = context(published_at="2025-01-03T01:00:00Z", received_at="2025-01-03T01:01:00Z",
                      validated_at="2025-01-03T01:02:00Z")
        result = parse_synthetic_guidance(raw(time="20:00:00", last_updated="2025-01-03T01:00:00Z"), ctx)
        self.assertEqual(result.disclosure.published_at.day, 3)
        for changes in ({"time": "08:00:00"}, {"date": "2025-01-03"},
                        {"last_updated": "2025-01-02T12:02:00Z"}, {"last_updated": "2024-12-31T12:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                observation(changes=changes)
        for changes in ({"received_at": "2025-01-02T11:00:00Z"}, {"announcement_timezone": "EST"},
                        {"published_at": "2026-01-02T12:00:00Z"}, {"validated_at": "2025-01-02T12:00:30Z"}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                context(**changes)

    def test_vendor_previous_values_never_manufacture_captured_predecessor(self):
        result = observation(changes={"previous_min_revenue_guidance": 1, "previous_max_revenue_guidance": 1,
                                      "previous_min_eps_guidance": 0, "previous_max_eps_guidance": 0})
        decision = EventBook().ingest(result.disclosure).decisions[-1]
        self.assertEqual(decision.disposition, "baseline")
        self.assertIsNone(decision.candidate)
        for changes in ({"previous_min_eps_guidance": 1},
                        {"previous_min_eps_guidance": 2, "previous_max_eps_guidance": 1}):
            with self.subTest(changes=changes), self.assertRaises(VendorPayloadError):
                observation(changes=changes)

    def test_no_io_or_environment_seams(self):
        with patch("socket.socket.connect", side_effect=AssertionError("network")), \
             patch("builtins.open", side_effect=AssertionError("files")), \
             patch("os.getenv", side_effect=AssertionError("environment")):
            self.assertTrue(observation().disclosure.sha256)


if __name__ == "__main__":
    unittest.main()
