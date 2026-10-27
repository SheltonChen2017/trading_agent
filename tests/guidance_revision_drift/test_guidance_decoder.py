"""Invented pre-quarantine records prove offline consistency, never provenance."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import localcontext
import json
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.guidance_decoder import (
    CONTEXT_SCHEMA, GuidanceDecoderError, decode_guidance,
)
from research.guidance_revision_drift.guidance_inputs import GuidanceLedger, GuidanceReceipt
from research.guidance_revision_drift.input_contracts import canonical_bytes


def payload(**changes):
    values = {"benzinga_id": "invented-d1", "ticker": "INVENTED-A", "date": "2025-01-02",
        "time": "07:00:00", "currency": "USD", "eps_method": "adj", "revenue_method": "gaap",
        "fiscal_period": "FY", "fiscal_year": 2025, "max_eps_guidance": 1, "min_eps_guidance": 1,
        "max_revenue_guidance": 100000000, "min_revenue_guidance": 100000000,
        "release_type": "official", "positioning": "primary"}
    values.update(changes)
    return values


def raw(**changes):
    return json.dumps(payload(**changes), sort_keys=True).encode("utf-8")


def context(source, *, document_changes=None, period_changes=None, **changes):
    period = {"period": "FY", "fiscal_year": 2025, "fiscal_start": "2025-01-01",
        "fiscal_end": "2025-12-31", "currency": "USD", "revenue_units": "USD_millions",
        "eps_units": "USD_per_share", "revenue_basis": "gaap", "eps_basis": "adj",
        "adjustment_definition": "invented-adjustment-v1", "share_basis": "invented-unsplit-v1",
        "scope": "invented-organic-v1", "revenue": {"lower": "100", "upper": "100", "kind": "point"},
        "eps": {"lower": "1", "upper": "1", "kind": "point"}}
    period.update(deepcopy(period_changes or {}))
    document = {"schema": "gdr.guidance-input.v1", "provider": "massive_benzinga",
        "issuer_id": "invented-issuer", "security_id": "invented-security", "disclosure_id": "invented-d1",
        "provider_version": None, "kind": "disclosure", "supersedes": None,
        "published_at": "2025-01-02T12:00:00Z", "provider_available_at": None,
        "source_payload_sha256": hash_bytes(source), "release_type": "official", "positioning": "primary",
        "periods": [period]}
    document.update(deepcopy(document_changes or {}))
    values = {"schema": CONTEXT_SCHEMA, "source_payload_sha256": hash_bytes(source), "ticker": "INVENTED-A",
        "document": document, "received_at": "2025-01-02T12:01:00Z", "validated_at": "2025-01-02T12:02:00Z",
        "announcement_timezone": "America/New_York", "revenue_input_units": "USD",
        "eps_input_units": "USD_per_share", "revenue_kind": "point", "eps_kind": "point"}
    values.update(deepcopy(changes))
    return values


def decode(source=None, **changes):
    source = raw() if source is None else source
    supplied = canonical_bytes(context(source, **changes))
    return decode_guidance(source, supplied, expected_context_sha256=hash_bytes(supplied))


class GuidanceDecoderTests(unittest.TestCase):
    def test_actual_receipt_preserves_raw_and_asserted_semantics_without_pit(self):
        source = raw()
        result = decode(source)
        self.assertIs(type(result), GuidanceReceipt)
        self.assertEqual(result.raw_bytes, source)
        self.assertEqual(result.document.to_dict(), context(source)["document"])
        self.assertFalse(result.document.point_in_time_data)
        self.assertIsNone(result.document.to_dict()["provider_available_at"])
        self.assertIsNone(result.document.to_dict()["provider_version"])
        projected = GuidanceLedger((result,)).as_of("2025-01-03T00:00:00Z").to_dict()
        self.assertFalse(projected["point_in_time_data"])
        self.assertFalse(projected["source_completeness_verified"])
        self.assertEqual(projected["provenance"], "caller_supplied_unverified")
        with self.assertRaises(FrozenInstanceError):
            result.raw_bytes = b"{}"
        result.document.to_dict()["periods"].clear()
        self.assertEqual(len(result.document.to_dict()["periods"]), 1)

    def test_context_hash_checked_before_any_json_parse(self):
        with patch("research.guidance_revision_drift.guidance_decoder.decode_object",
                   side_effect=AssertionError("parsed before hash")):
            with self.assertRaisesRegex(GuidanceDecoderError, "semantic_context_content_hash_mismatch"):
                decode_guidance(b"private-invalid-json", b"invalid-json", expected_context_sha256="0" * 64)

    def test_raw_hash_checked_before_raw_json_parse(self):
        source = b"private-invalid-json"
        supplied = canonical_bytes(context(source, source_payload_sha256="0" * 64))
        with self.assertRaisesRegex(GuidanceDecoderError, "semantic_context_source_hash_mismatch"):
            decode_guidance(source, supplied, expected_context_sha256=hash_bytes(supplied))
        supplied = canonical_bytes(context(source, document_changes={"source_payload_sha256": "0" * 64}))
        with self.assertRaisesRegex(GuidanceDecoderError, "normalized_document_source_hash_mismatch"):
            decode_guidance(source, supplied, expected_context_sha256=hash_bytes(supplied))

    def test_context_exact_schema_unknown_authority_and_canonical_bytes(self):
        original = context(raw())
        for name in original:
            supplied = deepcopy(original)
            del supplied[name]
            data = canonical_bytes(supplied)
            with self.subTest(missing=name), self.assertRaises(GuidanceDecoderError):
                decode_guidance(raw(), data, expected_context_sha256=hash_bytes(data))
        for changes in ({"schema": "unknown"}, {"point_in_time_data": True}, {"approved": True},
                        {"ticker": "OTHER"}, {"revenue_input_units": "millions"},
                        {"eps_input_units": "cents"}, {"revenue_kind": "confirmed"},
                        {"eps_kind": "range"}, {"announcement_timezone": "EST"}):
            with self.subTest(changes=changes), self.assertRaises(GuidanceDecoderError):
                decode(**changes)
        data = canonical_bytes(original) + b"\n"
        with self.assertRaises(GuidanceDecoderError):
            decode_guidance(raw(), data, expected_context_sha256=hash_bytes(data))
        duplicate = canonical_bytes(original).replace(b'"ticker":"INVENTED-A"',
                                                      b'"ticker":"INVENTED-A","ticker":"INVENTED-A"')
        with self.assertRaises(GuidanceDecoderError):
            decode_guidance(raw(), duplicate, expected_context_sha256=hash_bytes(duplicate))

    def test_every_required_provider_field_and_unknown_field_refuse(self):
        for name in payload():
            supplied = payload()
            del supplied[name]
            with self.subTest(missing=name), self.assertRaises(GuidanceDecoderError):
                decode(json.dumps(supplied).encode())
        for name in ("provider_available_at", "version", "is_pit", "confirmed_forecast"):
            with self.subTest(unknown=name), self.assertRaises(GuidanceDecoderError):
                decode(raw(**{name: True}))

    def test_each_known_provider_semantic_mismatch_refuses(self):
        cases = ({"benzinga_id": "invented-other"}, {"ticker": "OTHER"}, {"date": "2025-01-03"},
            {"time": "07:00:01"}, {"currency": "EUR"}, {"eps_method": "gaap"},
            {"revenue_method": "adj"}, {"fiscal_period": "Q1"}, {"fiscal_year": 2024},
            {"fiscal_year": True}, {"release_type": "preliminary"}, {"positioning": "secondary"},
            {"min_revenue_guidance": 99000000}, {"max_revenue_guidance": 101000000},
            {"min_eps_guidance": -1}, {"max_eps_guidance": 2},
            {"min_eps_guidance": 2, "max_eps_guidance": 2},
            {"min_revenue_guidance": 101000000, "max_revenue_guidance": 101000000})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(GuidanceDecoderError):
                decode(raw(**changes))

    def test_ordered_ranges_and_explicit_points_are_crosschecked(self):
        source = raw(min_revenue_guidance=99000000, max_revenue_guidance=101000000,
                     min_eps_guidance=-1, max_eps_guidance=2)
        result = decode(source, revenue_kind="range", eps_kind="range", period_changes={
            "revenue": {"lower": "99", "upper": "101", "kind": "range"},
            "eps": {"lower": "-1", "upper": "2", "kind": "range"}})
        self.assertEqual(result.document.to_dict()["periods"][0]["eps"]["lower"], "-1")
        for changes in ({"min_eps_guidance": 2}, {"min_revenue_guidance": 100000001}):
            with self.subTest(changes=changes), self.assertRaises(GuidanceDecoderError):
                decode(raw(**changes))
        # Both raw equal bounds and normalized equal bounds are valid, but a
        # sidecar cannot reclassify an equal-ended provider record as a range.
        with self.assertRaises(GuidanceDecoderError):
            decode(revenue_kind="range")

    def test_decimal_numeric_lexemes_and_unit_scaling_ignore_ambient_context(self):
        source = raw().replace(b'100000000', b'100000000.123456789')
        source = source.replace(b'"min_eps_guidance": 1', b'"min_eps_guidance": 1.123456789123456789')
        source = source.replace(b'"max_eps_guidance": 1', b'"max_eps_guidance": 1.123456789123456789')
        period = {"revenue": {"lower": "100.000000123456789", "upper": "100.000000123456789", "kind": "point"},
                  "eps": {"lower": "1.123456789123456789", "upper": "1.123456789123456789", "kind": "point"}}
        with localcontext() as supplied:
            supplied.prec = 2
            result = decode(source, period_changes=period)
        self.assertEqual(result.document.to_dict()["periods"][0]["revenue"]["lower"], "100.000000123456789")
        self.assertEqual(decode(raw(min_revenue_guidance=100, max_revenue_guidance=100),
                                revenue_input_units="USD_millions").document.to_dict()["periods"][0]["revenue"]["lower"], "100")
        self.assertEqual(decode(period_changes={"revenue_units": "USD",
            "revenue": {"lower": "100000000", "upper": "100000000", "kind": "point"}}).raw_bytes, raw())

    def test_zero_and_negative_guidance_remain_predecessors_with_named_arithmetic_refusals(self):
        for value in (0, -1):
            previous = decode(raw(min_revenue_guidance=value, max_revenue_guidance=value,
                                  min_eps_guidance=value, max_eps_guidance=value),
                period_changes={"revenue_units": "USD", "revenue": {"lower": str(value), "upper": str(value), "kind": "point"},
                                "eps": {"lower": str(value), "upper": str(value), "kind": "point"}})
            current = decode(raw(benzinga_id="invented-d2", date="2025-02-02"),
                document_changes={"disclosure_id": "invented-d2", "published_at": "2025-02-02T12:00:00Z"},
                received_at="2025-02-02T12:01:00Z", validated_at="2025-02-02T12:02:00Z")
            decision = GuidanceLedger((previous, current)).as_of("2025-02-03T00:00:00Z").decisions[-1]
            with self.subTest(value=value):
                self.assertEqual(decision.comparison.predecessor_sha256, previous.document.sha256)
                self.assertIn("previous_revenue_midpoint_not_positive", decision.refusal_reasons)
                self.assertIn("previous_eps_midpoint_below_floor", decision.refusal_reasons)

    def test_provider_numeric_tokens_refuse_strings_bool_nonfinite_and_resource_abuse(self):
        for value in ("1", True, None, float("nan"), float("inf")):
            with self.subTest(value_type=type(value)), self.assertRaises(GuidanceDecoderError):
                decode(raw(min_eps_guidance=value))
        for source in (b"[]", b"{}", b"\xff", b'\xef\xbb\xbf{}', b'{"x":1,"x":2}',
                       b'{"x":1e1000}', b"[" * 2000 + b"]" * 2000, b" " * 65537,
                       raw().replace(b'"min_eps_guidance": 1', b'"min_eps_guidance": 1e-1000')):
            with self.subTest(length=len(source)), self.assertRaises(GuidanceDecoderError):
                decode(source)
        supplied = canonical_bytes(context(raw()))
        for source in (bytearray(raw()), b"", b" " * 65537):
            with self.subTest(source_type=type(source)), self.assertRaises(GuidanceDecoderError):
                decode_guidance(source, supplied, expected_context_sha256=hash_bytes(supplied))
        for supplied in (bytearray(supplied), b"", b" " * 73729):
            with self.subTest(context_type=type(supplied)), self.assertRaises(GuidanceDecoderError):
                decode_guidance(raw(), supplied, expected_context_sha256="0" * 64)

    def test_known_incompatible_immediate_prior_is_retained_and_blocks_older_fallback(self):
        baseline = decode()
        for source_field, basis_field, basis in (("eps_method", "eps_basis", "gaap"),
                ("eps_method", "eps_basis", "ffo"), ("revenue_method", "revenue_basis", "adj")):
            prior = decode(raw(benzinga_id="invented-d2", date="2025-02-02", **{source_field: basis}),
                document_changes={"disclosure_id": "invented-d2", "published_at": "2025-02-02T12:00:00Z"},
                period_changes={basis_field: basis}, received_at="2025-02-02T12:01:00Z",
                validated_at="2025-02-02T12:02:00Z")
            source = raw(benzinga_id="invented-d3", date="2025-03-03",
                         min_revenue_guidance=102000000, max_revenue_guidance=102000000)
            source = source.replace(b'"min_eps_guidance": 1', b'"min_eps_guidance": 1.05')
            source = source.replace(b'"max_eps_guidance": 1', b'"max_eps_guidance": 1.05')
            raised = decode(source, document_changes={"disclosure_id": "invented-d3", "published_at": "2025-03-03T12:00:00Z"},
                period_changes={"revenue": {"lower": "102", "upper": "102", "kind": "point"},
                                "eps": {"lower": "1.05", "upper": "1.05", "kind": "point"}},
                received_at="2025-03-03T12:01:00Z", validated_at="2025-03-03T12:02:00Z")
            projection = GuidanceLedger((baseline, prior, raised)).as_of("2025-03-04T00:00:00Z")
            with self.subTest(basis_field=basis_field, basis=basis):
                self.assertEqual(len(GuidanceLedger((baseline, raised)).as_of("2025-03-04T00:00:00Z").active_comparisons), 1)
                self.assertEqual(len(projection.decisions), 3)
                self.assertEqual(projection.decisions[-1].comparison.predecessor_sha256, prior.document.sha256)
                self.assertIn("unsupported_accounting_basis", projection.decisions[-1].refusal_reasons)
                self.assertFalse(projection.active_comparisons)
        # Matching context cannot legitimize an unknown provider method.
        for source_field, basis_field in (("eps_method", "eps_basis"), ("revenue_method", "revenue_basis")):
            with self.subTest(source_field=source_field), self.assertRaisesRegex(GuidanceDecoderError, "unrecognized_provider_accounting_method"):
                decode(raw(**{source_field: "invented-unknown"}), period_changes={basis_field: "invented-unknown"})

    def test_provider_version_availability_and_mutation_claims_are_unsupported(self):
        for changes in ({"provider": "fixture-provider"}, {"provider_version": "v1"},
                        {"provider_available_at": "2025-01-02T12:00:00Z"},
                        {"kind": "correction", "supersedes": "invented-d0"},
                        {"kind": "withdrawal", "supersedes": "invented-d0", "periods": []}):
            with self.subTest(changes=changes), self.assertRaises(GuidanceDecoderError):
                decode(document_changes=changes)
        # A sidecar changing a recognized basis alone still mismatches raw.
        for name, value in (("revenue_basis", "adj"), ("eps_basis", "gaap")):
            with self.subTest(name=name), self.assertRaises(GuidanceDecoderError):
                decode(period_changes={name: value})
        extra = context(raw())["document"]["periods"][0]
        extra.update(fiscal_year=2026, fiscal_start="2026-01-01", fiscal_end="2026-12-31")
        periods = context(raw())["document"]["periods"] + [extra]
        with self.assertRaisesRegex(GuidanceDecoderError, "single_full_year"):
            decode(document_changes={"periods": periods})

    def test_last_updated_is_optional_consistency_only_and_never_first_availability(self):
        result = decode(raw(last_updated="2025-01-02T12:00:30Z"))
        self.assertIsNone(result.document.to_dict()["provider_available_at"])
        self.assertEqual(result.received_at, "2025-01-02T12:01:00Z")
        for value in ("2025-01-02", "2025-01-02T11:59:59Z", "2025-01-02T12:01:01Z", 123, True):
            with self.subTest(value_type=type(value)), self.assertRaises(GuidanceDecoderError):
                decode(raw(last_updated=value))
        for changes in ({"received_at": "2025-01-02T11:59:59Z"},
                        {"validated_at": "2025-01-02T12:00:59Z"}):
            with self.subTest(changes=changes), self.assertRaises(GuidanceDecoderError):
                decode(**changes)

    def test_timezone_cross_date_explicit_utc_and_dst_ambiguous_nonexistent_refuse(self):
        result = decode(raw(time="20:00:00"), document_changes={"published_at": "2025-01-03T01:00:00Z"},
                        received_at="2025-01-03T01:01:00Z", validated_at="2025-01-03T01:02:00Z")
        self.assertEqual(result.document.to_dict()["published_at"], "2025-01-03T01:00:00Z")
        self.assertIs(type(decode(raw(time="12:00:00"), announcement_timezone="UTC")), GuidanceReceipt)
        for date, time, published in (("2025-11-02", "01:30:00", "2025-11-02T05:30:00Z"),
            ("2025-11-02", "01:30:00", "2025-11-02T06:30:00Z"),
            ("2025-03-09", "02:30:00", "2025-03-09T07:30:00Z")):
            with self.subTest(date=date, published=published), self.assertRaisesRegex(GuidanceDecoderError, "ambiguous_or_nonexistent"):
                decode(raw(date=date, time=time), document_changes={"published_at": published},
                       received_at=published, validated_at=published)
        for value in ("7:00:00", "07:00", "25:00:00", True):
            with self.subTest(value=value), self.assertRaises(GuidanceDecoderError):
                decode(raw(time=value))

    def test_optional_previous_and_estimated_fields_never_create_a_predecessor_or_filter(self):
        source = raw(previous_min_eps_guidance=0, previous_max_eps_guidance=0,
                     previous_min_revenue_guidance=-1, previous_max_revenue_guidance=0,
                     estimated_eps_guidance=100, estimated_revenue_guidance=999999999999,
                     notes="invented note", company_name="Invented company", importance=0)
        result = decode(source)
        decision = GuidanceLedger((result,)).as_of("2025-01-03T00:00:00Z").decisions[-1]
        self.assertEqual(decision.disposition, "baseline")
        self.assertIsNone(decision.comparison)
        self.assertEqual(result.document.to_dict()["periods"], decode().document.to_dict()["periods"])
        for changes in ({"previous_min_eps_guidance": 1},
                        {"previous_min_eps_guidance": 2, "previous_max_eps_guidance": 1},
                        {"estimated_eps_guidance": True}, {"estimated_revenue_guidance": "100"},
                        {"importance": True}, {"importance": 6}, {"notes": "secret\ntext"},
                        {"company_name": "x" * 4097}):
            with self.subTest(changes=changes), self.assertRaises(GuidanceDecoderError):
                decode(raw(**changes))

    def test_refusals_do_not_echo_source_and_decoder_has_no_io_seams(self):
        with self.assertRaises(GuidanceDecoderError) as caught:
            decode(raw(notes="private\nmarker"))
        self.assertNotIn("private", str(caught.exception))
        with self.assertRaises(GuidanceDecoderError) as caught:
            decode(raw(time="99:00:00"))
        self.assertTrue(caught.exception.__suppress_context__)
        with patch("socket.socket.connect", side_effect=AssertionError("network")), \
             patch("builtins.open", side_effect=AssertionError("files")), \
             patch("os.getenv", side_effect=AssertionError("environment")):
            self.assertIs(type(decode()), GuidanceReceipt)


if __name__ == "__main__":
    unittest.main()
