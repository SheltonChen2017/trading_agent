"""Metadata evidence must never become provider, PIT or evaluation authority."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.contracts import load_candidate
from research.guidance_revision_drift.readiness import preflight
from research.guidance_revision_drift.coverage_preflight import (
    CoverageError, assess_coverage, observed_manifest, main,
)


class CoveragePreflightTests(unittest.TestCase):
    def setUp(self):
        self.candidate = load_candidate()
        self.raw = observed_manifest()

    def assess(self, body=None):
        raw = self.raw if body is None else canonical_json(body).encode()
        return assess_coverage(self.candidate, raw, expected_sha256=hash_bytes(raw))

    def test_real_account_metadata_supersedes_basic_and_expired_ratings_guess(self):
        report = self.assess()
        products = {row["provider"]: row for row in report["subscriptions"]}
        self.assertEqual(products["massive"]["products"], [
            "benzinga_analyst_insights", "benzinga_analyst_ratings", "stocks_starter"])
        self.assertEqual(products["massive"]["displayed_access_end_date"], "2026-11-06")
        self.assertEqual(products["eodhd"]["displayed_access_end_date"], "2026-11-14")
        self.assertEqual(products["fmp"]["displayed_access_end_date"], "2026-11-13")
        self.assertEqual(products["sharadar"]["evidence_class"], "owner_report")
        self.assertEqual(products["sharadar"]["nominal_history_years"], 5)
        self.assertEqual(report["manifest_sha256"], hash_bytes(self.raw))
        self.assertFalse(report["metadata_authenticity_verified"])

    def test_wrong_events_snapshots_and_bars_never_satisfy_missing_guidance_or_nbbo(self):
        report = self.assess()
        matrix = {row["provider"]: row for row in report["coverage"]}
        self.assertEqual(matrix["eodhd"]["guidance"], "analyst_consensus_not_issuer_guidance")
        self.assertEqual(matrix["massive"]["guidance"], "ratings_and_insights_not_issuer_guidance")
        self.assertEqual(matrix["eodhd"]["current_bid_ask"], "documented_delayed_snapshot_only")
        self.assertEqual(matrix["massive"]["minute_volume"], "documented_aggregate_candidate_not_row_verified")
        for row in matrix.values():
            self.assertNotEqual(row["historical_stock_nbbo"], "verified")
            self.assertNotEqual(row["historical_spy_nbbo"], "verified")
        for blocker in ("issuer_guidance_versions_unestablished", "historical_stock_nbbo_unestablished",
                        "historical_spy_nbbo_unestablished", "source_rights_and_retention_unverified"):
            self.assertIn(blocker, report["blockers"])

    def test_five_year_tiers_do_not_relax_six_year_common_history_floor(self):
        history = self.assess()["history"]
        self.assertEqual(history["proposed_minimum_usable_years"], 6)
        self.assertEqual(history["individual_nominal_tiers_below_floor"], ["fmp", "massive", "sharadar"])
        self.assertIsNone(history["common_usable_years_verified"])
        self.assertFalse(history["minimum_common_history_established"])
        self.assertFalse(history["sources_stitched_or_window_shortened"])

    def test_stock_only_and_analyst_only_metadata_do_not_invent_other_products(self):
        for products, years, guidance, volume in (
            (["stocks_starter"], 5, "issuer_guidance_not_in_reported_products",
             "documented_aggregate_candidate_not_row_verified"),
            (["benzinga_analyst_ratings"], None, "ratings_and_insights_not_issuer_guidance",
             "not_in_reported_product"),
        ):
            with self.subTest(products=products):
                body = json.loads(self.raw)
                massive = next(row for row in body["subscriptions"] if row["provider"] == "massive")
                massive["products"], massive["nominal_history_years"] = products, years
                result = next(row for row in self.assess(body)["coverage"] if row["provider"] == "massive")
                self.assertEqual(result["guidance"], guidance)
                self.assertEqual(result["minute_volume"], volume)

    def test_no_overrides_can_promote_readiness_or_change_original_candidate(self):
        before = preflight(self.candidate).to_dict()
        report = self.assess()
        for key in ("ready_for_backtesting", "point_in_time_evidence_verified", "qc_access_allowed",
                    "provider_access_allowed", "outcome_access_allowed", "orders_allowed"):
            self.assertIs(report[key], False)
        self.assertEqual(report["original_readiness"], before)
        self.assertEqual(preflight(self.candidate).to_dict(), before)
        for key in ("approved", "rights_verified", "point_in_time_data", "ready_for_backtesting",
                    "stock_quotes", "spy_quotes", "previous_guidance", "api_key", "raw_payload"):
            with self.subTest(key=key):
                body = json.loads(self.raw)
                body[key] = True
                with self.assertRaises(CoverageError):
                    self.assess(body)

    def test_missing_provider_is_explicit_unknown_and_does_not_drop_requirements(self):
        body = json.loads(self.raw)
        body["subscriptions"] = []
        report = self.assess(body)
        self.assertEqual([row["provider"] for row in report["coverage"]], ["eodhd", "fmp", "massive", "sharadar"])
        self.assertTrue(all(row["guidance"] == "unknown_no_subscription_metadata" for row in report["coverage"]))
        self.assertIn("missing_subscription_metadata", report["blockers"])
        self.assertIn("historical_spy_nbbo_unestablished", report["blockers"])

    def test_raw_hash_candidate_and_strict_json_contract(self):
        malformed = [b"", b"[]", b"{}", b'{"schema":1,"schema":2}', b'{"v":1.5}',
                     b'{"v":NaN}', b'{"v":Infinity}', b"\xff", b" " * 65537]
        for raw in malformed:
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(CoverageError):
                    assess_coverage(self.candidate, raw, expected_sha256=hash_bytes(raw))
        for digest in ("0" * 64, "A" * 64, True, None):
            with self.subTest(digest=digest), self.assertRaises(CoverageError):
                assess_coverage(self.candidate, self.raw, expected_sha256=digest)
        with self.assertRaises(CoverageError):
            assess_coverage(None, self.raw, expected_sha256=hash_bytes(self.raw))
        body = json.loads(self.raw)
        body["candidate_sha256"] = "0" * 64
        with self.assertRaises(CoverageError):
            self.assess(body)

    def test_bad_or_conflicting_metadata_refuses_without_secret_echo(self):
        changes = [
            ("nominal_history_years", True), ("nominal_history_years", 6),
            ("products", ["eod_all_world", "eod_all_world"]), ("products", ["unknown"]),
            ("products", [{}]), ("products", [True]),
            ("products", "eod_all_world"), ("evidence_class", "verified"),
            ("observed_on", "2026-10-25"), ("observed_on", "2026-02-30"),
            ("displayed_access_end_date", None), ("status", "approved"),
            ("evidence_ref", "SECRET-DO-NOT-ECHO"),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                body = json.loads(self.raw)
                body["subscriptions"][0][key] = value
                with self.assertRaises(CoverageError) as caught:
                    self.assess(body)
                self.assertNotIn("SECRET-DO-NOT-ECHO", str(caught.exception))
        body = json.loads(self.raw)
        body["subscriptions"].append(body["subscriptions"][0])
        with self.assertRaises(CoverageError):
            self.assess(body)
        body = json.loads(self.raw)
        body["subscriptions"][0]["rights_verified"] = True
        with self.assertRaises(CoverageError):
            self.assess(body)

    def test_each_inventory_rule_refuses_alone(self):
        # GDR-CR47-002: each case breaks exactly one rule no other case isolated.
        def row(body, provider):
            return next(item for item in body["subscriptions"] if item["provider"] == provider)
        cases = {
            "basic-format date": lambda body: body.update(as_of_date="20261024"),
            "unknown provider": lambda body: row(body, "eodhd").update(provider="example_vendor"),
            "owner report with displayed end": lambda body: row(body, "sharadar").update(
                displayed_access_end_date="2026-11-14"),
            "owner report with account reference": lambda body: row(body, "sharadar").update(
                evidence_ref="authenticated_subscription_page"),
            "empty product list": lambda body: row(body, "eodhd").update(products=[]),
        }
        for label, change in cases.items():
            body = json.loads(self.raw)
            change(body)
            with self.subTest(case=label), self.assertRaises(CoverageError) as raised:
                self.assess(body)
            self.assertNotIn("example_vendor", str(raised.exception))
        # A duplicated provider must not mask a missing one: four rows, Sharadar absent.
        body = json.loads(self.raw)
        rows = body["subscriptions"]
        rows[rows.index(row(body, "sharadar"))] = json.loads(json.dumps(row(body, "eodhd")))
        with self.assertRaisesRegex(CoverageError, "duplicate provider"):
            self.assess(body)

    def test_cancellation_is_not_expired_but_end_date_is_not_future_authority(self):
        report = self.assess()
        massive = next(row for row in report["subscriptions"] if row["provider"] == "massive")
        self.assertEqual(massive["access_date_screen"], "before_displayed_end_not_entitlement_proof")
        body = json.loads(self.raw)
        body["as_of_date"] = "2026-11-14"
        report = self.assess(body)
        for row in report["subscriptions"]:
            if row["provider"] != "sharadar":
                self.assertEqual(row["access_date_screen"], "at_or_after_displayed_end_recheck_required")
        self.assertFalse(report["ready_for_backtesting"])
        self.assertIn("displayed_access_end_requires_recheck", report["blockers"])

    def test_detached_output_and_deterministic_order(self):
        original = self.assess()
        original_bytes = canonical_json(original)
        changed = self.assess()
        changed["subscriptions"][0]["products"].clear()
        changed["coverage"].clear()
        changed["public_documentation"].clear()
        changed["original_readiness"]["authority"]["qc_launch"] = True
        changed["blockers"].clear()
        self.assertEqual(canonical_json(self.assess()), original_bytes)
        self.assertEqual(self.assess(), original)
        body = json.loads(self.raw)
        body["subscriptions"].reverse()
        reordered = self.assess(body)
        self.assertEqual(reordered["subscriptions"], original["subscriptions"])
        self.assertEqual(reordered["coverage"], original["coverage"])

    def test_assessment_is_pure_and_stdout_cli_reads_only_pinned_draft(self):
        with patch("builtins.open", side_effect=AssertionError("file forbidden")), \
             patch("os.open", side_effect=AssertionError("file forbidden")), \
             patch("os.getenv", side_effect=AssertionError("environment forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process forbidden")):
            report = self.assess()
            with patch("research.guidance_revision_drift.coverage_preflight.load_candidate", return_value=self.candidate), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), 2)
            self.assertEqual(json.loads(output.getvalue()), report)

    def test_actual_cli_opens_only_the_pinned_draft_read_only(self):
        expected = Path(__file__).resolve().parents[2] / "research/guidance_revision_drift/specs/gdr0a.draft.json"
        opened = []
        original_open = os.open

        def guarded_open(path, flags, *args, **kwargs):
            self.assertEqual(Path(path).resolve(), expected)
            self.assertEqual(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND), 0)
            opened.append(Path(path).resolve())
            return original_open(path, flags, *args, **kwargs)

        with patch("os.open", side_effect=guarded_open), \
             patch("builtins.open", side_effect=AssertionError("unexpected file API")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
        self.assertEqual(opened, [expected, expected])
        self.assertFalse(json.loads(output.getvalue())["ready_for_backtesting"])


if __name__ == "__main__":
    unittest.main()
