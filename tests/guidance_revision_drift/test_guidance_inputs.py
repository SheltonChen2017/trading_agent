"""Invented local records exercise the real-input contract, never vendor data."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.guidance_inputs import (
    GuidanceDocument, GuidanceInputError, GuidanceLedger, GuidanceReceipt,
    compare_revision,
)
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes


def period(**changes):
    values = {"period": "FY", "fiscal_year": 2025, "fiscal_start": "2025-01-01", "fiscal_end": "2025-12-31",
        "currency": "USD", "revenue_units": "USD_millions", "eps_units": "USD_per_share",
        "revenue_basis": "gaap", "eps_basis": "adj", "adjustment_definition": "fixture-adjustment-v1",
        "share_basis": "fixture-unsplit-v1", "scope": "fixture-organic-v1",
        "revenue": {"lower": "100", "upper": "100", "kind": "point"},
        "eps": {"lower": "1", "upper": "1", "kind": "point"}}
    values.update(changes)
    return values


def receipt(identity="fixture-d1", day="2025-01-02", *, period_values=None, raw_tag="original", **changes):
    raw = canonical_bytes({"invented_source": identity, "invented_day": day, "invented_tag": raw_tag})
    received = changes.pop("received_at", day + "T12:01:00Z")
    validated = changes.pop("validated_at", day + "T12:02:00Z")
    values = {"schema": "gdr.guidance-input.v1", "provider": "fixture-provider", "issuer_id": "fixture-issuer",
        "security_id": "fixture-security", "disclosure_id": identity, "provider_version": "v1",
        "kind": "disclosure", "supersedes": None, "published_at": day + "T12:00:00Z",
        "provider_available_at": None, "source_payload_sha256": hash_bytes(raw),
        "release_type": "official", "positioning": "primary", "periods": [period(**(period_values or {}))]}
    values.update(changes)
    return GuidanceReceipt(raw, GuidanceDocument.from_dict(values), received, validated)


def raised(identity="fixture-d2", day="2025-02-02", **changes):
    supplied = {"revenue": {"lower": "102", "upper": "102", "kind": "point"},
                "eps": {"lower": "1.05", "upper": "1.05", "kind": "point"}}
    supplied.update(changes.pop("period_values", {}))
    return receipt(identity, day, period_values=supplied, **changes)


class GuidanceInputTests(unittest.TestCase):
    def test_exact_pair_arithmetic_normalizes_usd_without_decimal_context(self):
        old = receipt(period_values={"revenue_units": "USD", "revenue": {"lower": "100000000", "upper": "100000000", "kind": "point"}})
        new = raised()
        with localcontext() as context:
            context.prec = 2
            compared = compare_revision(new.document, old.document)
        self.assertTrue(compared.passes_arithmetic)
        self.assertEqual(compared.arithmetic.current_revenue_midpoint, Decimal("102"))
        self.assertEqual(compared.arithmetic.revenue_revision_fraction, Decimal("0.02"))
        self.assertFalse(compared.to_dict()["point_in_time_data"])
        self.assertFalse(compared.to_dict()["predecessor_completeness_verified"])

    def test_subthreshold_floor_and_lower_bound_failures_remain_visible(self):
        old = receipt()
        new = raised(period_values={"revenue": {"lower": "101.999999999999999999", "upper": "101.999999999999999999", "kind": "point"}})
        compared = compare_revision(new.document, old.document)
        self.assertFalse(compared.passes_arithmetic)
        self.assertIn("revenue_raise_threshold_not_met", compared.refusal_reasons)
        floor = receipt(period_values={"eps": {"lower": "0.249", "upper": "0.249", "kind": "point"}})
        self.assertIn("previous_eps_midpoint_below_floor", compare_revision(raised().document, floor.document).refusal_reasons)
        cut = raised(period_values={"revenue": {"lower": "99", "upper": "110", "kind": "range"}})
        self.assertIn("revenue_lower_bound_reduced", compare_revision(cut.document, old.document).refusal_reasons)

    def test_canonical_document_is_detached_and_raw_hash_is_bound(self):
        original = receipt()
        supplied = original.document.to_dict()
        copied = GuidanceDocument.from_dict(supplied)
        supplied["periods"][0]["revenue"]["lower"] = "999"
        self.assertEqual(copied.sha256, original.document.sha256)
        copied.to_dict()["periods"].clear()
        self.assertEqual(copied.sha256, original.document.sha256)
        with self.assertRaises(FrozenInstanceError):
            copied.canonical_bytes = b"{}"
        with self.assertRaises(GuidanceInputError):
            GuidanceReceipt(b"different", copied, original.received_at, original.validated_at)
        object.__setattr__(copied, "canonical_bytes", b"{}")
        with self.assertRaises(GuidanceInputError):
            GuidanceReceipt(original.raw_bytes, copied, original.received_at, original.validated_at)

    def test_unknown_authority_and_missing_fields_refuse(self):
        values = receipt().document.to_dict()
        for name in values:
            changed = deepcopy(values)
            del changed[name]
            with self.subTest(missing=name), self.assertRaises(InputError):
                GuidanceDocument.from_dict(changed)
        for name in ("approved", "point_in_time_data", "rights_verified", "qc_allowed"):
            with self.subTest(authority=name), self.assertRaises(InputError):
                GuidanceDocument.from_dict({**values, name: True})

    def test_malformed_json_decimal_ranges_and_periods_refuse(self):
        for raw in (b"{}", b"[]", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.2}', b" " * 65537):
            with self.subTest(raw=raw[:30]), self.assertRaises(InputError):
                GuidanceDocument.from_bytes(raw)
        for value in (None, True, 1.0, "NaN", "1e2", "-Infinity", "1" * 65):
            with self.subTest(value=value), self.assertRaises(InputError):
                receipt(period_values={"eps": {"lower": value, "upper": value, "kind": "point"}})
        for changes in ({"revenue": {"lower": "2", "upper": "1", "kind": "range"}},
                        {"eps": {"lower": "1", "upper": "1", "kind": "range"}},
                        {"eps": {"lower": "1", "upper": "2", "kind": "point"}},
                        {"fiscal_year": True}, {"fiscal_start": "2025-09-01"},
                        {"period": "Q1"}, {"currency": "EUR"}, {"eps_units": "cents"}):
            with self.subTest(changes=changes), self.assertRaises(InputError):
                receipt(period_values=changes)
        raw = receipt().document.canonical_bytes
        with self.assertRaises(InputError):
            GuidanceDocument.from_bytes(raw + b"\n")

    def test_publication_availability_receipt_and_validation_clocks_are_distinct(self):
        good = receipt(provider_available_at="2025-01-02T12:00:30Z")
        self.assertIsNotNone(good.document.to_dict()["provider_available_at"])
        self.assertFalse(good.document.point_in_time_data)
        for changes in ({"published_at": "2025-01-02T12:00:00"},
                        {"provider_available_at": "2025-01-02T11:59:59Z"},
                        {"provider_available_at": "2025-01-02T12:01:01Z"},
                        {"received_at": "2025-01-02T11:59:00Z"},
                        {"validated_at": "2025-01-02T12:00:59Z"}):
            with self.subTest(changes=changes), self.assertRaises(InputError):
                receipt(**changes)

    def test_duplicate_redelivery_retains_first_receipt_and_does_not_refresh_news(self):
        first = receipt()
        duplicate = GuidanceReceipt(first.raw_bytes, first.document, "2025-02-03T12:01:00Z", "2025-02-03T12:02:00Z")
        ledger = GuidanceLedger().append(first).append(raised()).append(duplicate)
        projection = ledger.as_of("2025-03-01T00:00:00Z")
        self.assertEqual([row.disposition for row in projection.decisions], ["baseline", "comparison", "duplicate_delivery"])
        self.assertEqual(len(projection.active_comparisons), 1)
        self.assertEqual(projection.active_comparisons[0].predecessor_sha256, first.document.sha256)
        self.assertEqual(len(ledger.receipts), 3)

    def test_same_version_conflict_is_retained_and_quarantines_issuer(self):
        original = receipt()
        conflict = receipt(period_values={"eps": {"lower": "2", "upper": "2", "kind": "point"}},
                           raw_tag="conflict", received_at="2025-02-03T12:01:00Z", validated_at="2025-02-03T12:02:00Z")
        ledger = GuidanceLedger((original, raised(), conflict, raised("fixture-d3", "2025-03-03")))
        decisions = ledger.as_of("2025-04-01T00:00:00Z").decisions
        self.assertEqual(decisions[2].disposition, "quarantined")
        self.assertEqual(decisions[2].invalidated_disclosure_ids, ("fixture-d2",))
        self.assertEqual(decisions[3].refusal_reasons, ("issuer_quarantined",))
        self.assertEqual(len(ledger.receipts), 4)

    def test_new_version_cannot_turn_same_id_economic_edit_into_fresh_news(self):
        edit = raised("fixture-d1", "2025-02-02", provider_version="v2", raw_tag="edit")
        projection = GuidanceLedger((receipt(), edit)).as_of("2025-03-01T00:00:00Z")
        self.assertEqual(projection.decisions[-1].disposition, "quarantined")
        self.assertFalse(projection.active_comparisons)

    def test_metadata_edit_preserves_original_baseline_semantics(self):
        first = receipt()
        edited = receipt(provider_version="v2", raw_tag="metadata", received_at="2025-01-03T12:01:00Z", validated_at="2025-01-03T12:02:00Z")
        projection = GuidanceLedger((first, edited, raised())).as_of("2025-03-01T00:00:00Z")
        self.assertEqual(projection.decisions[1].disposition, "metadata_edit")
        self.assertEqual(projection.decisions[-1].comparison.predecessor_sha256, first.document.sha256)

    def test_immediate_incompatible_predecessor_blocks_older_comparable_fallback(self):
        old = receipt()
        incompatible = receipt("fixture-d2", "2025-02-02", period_values={"adjustment_definition": "fixture-adjustment-v2"})
        new = raised("fixture-d3", "2025-03-03")
        decision = GuidanceLedger((old, incompatible, new)).as_of("2025-04-01T00:00:00Z").decisions[-1]
        self.assertEqual(decision.disposition, "refused")
        self.assertIn("changed_adjustment_definition", decision.refusal_reasons)
        self.assertEqual(decision.comparison.predecessor_sha256, incompatible.document.sha256)

    def test_correction_invalidates_without_creating_or_retiming_positive_comparison(self):
        correction = receipt("fixture-correction", "2025-02-03", kind="correction", supersedes="fixture-d2")
        ledger = GuidanceLedger((receipt(), raised(), correction))
        before = ledger.as_of("2025-02-02T23:59:59Z")
        after = ledger.as_of("2025-03-01T00:00:00Z")
        self.assertEqual(len(before.active_comparisons), 1)
        self.assertFalse(after.active_comparisons)
        self.assertEqual(after.decisions[-1].disposition, "correction")
        self.assertEqual(after.decisions[-1].invalidated_disclosure_ids, ("fixture-d2",))
        self.assertIsNone(after.decisions[-1].comparison)
        self.assertIn("correction_or_withdrawal_cannot_create_positive_comparison",
                      compare_revision(correction.document, receipt().document).refusal_reasons)

    def test_unknown_correction_and_wrong_issuer_do_not_become_baselines(self):
        unknown = receipt("fixture-correction", "2025-02-03", kind="correction", supersedes="fixture-missing")
        wrong = receipt("fixture-withdrawal", "2025-02-04", kind="withdrawal", supersedes="fixture-d1",
                        issuer_id="fixture-other", periods=[])
        projection = GuidanceLedger((receipt(), unknown, wrong)).as_of("2025-03-01T00:00:00Z")
        for decision in projection.decisions[1:]:
            self.assertEqual(decision.disposition, "refused")
            self.assertEqual(decision.refusal_reasons, ("unknown_or_wrong_identity_superseded_disclosure",))

    def test_withdrawal_blocks_next_revision_and_correction_cannot_resurrect_it(self):
        withdrawal = receipt("fixture-withdrawal", "2025-02-03", kind="withdrawal", supersedes="fixture-d2", periods=[])
        correction = raised("fixture-correction", "2025-02-04", kind="correction", supersedes="fixture-d2")
        projection = GuidanceLedger((receipt(), raised(), withdrawal, correction, raised("fixture-d3", "2025-03-03"))).as_of("2025-04-01T00:00:00Z")
        self.assertEqual(projection.decisions[-1].refusal_reasons, ("immediate_predecessor_withdrawn",))
        self.assertFalse(projection.active_comparisons)

    def test_delayed_predecessor_capture_cannot_be_backdated(self):
        old = receipt(received_at="2025-02-02T12:00:30Z", validated_at="2025-02-02T12:00:45Z")
        projection = GuidanceLedger((old, raised())).as_of("2025-03-01T00:00:00Z")
        self.assertIn("predecessor_not_locally_validated_before_disclosure", projection.decisions[-1].refusal_reasons)
        self.assertFalse(projection.active_comparisons)

    def test_later_cut_or_lost_comparability_invalidates_active_observation(self):
        for changed in (receipt("fixture-d3", "2025-03-03"),
                        raised("fixture-d3", "2025-03-03", period_values={"share_basis": "fixture-new-shares"})):
            with self.subTest(share_basis=changed.document.to_dict()["periods"][0]["share_basis"]):
                projection = GuidanceLedger((receipt(), raised(), changed)).as_of("2025-04-01T00:00:00Z")
                self.assertFalse(projection.active_comparisons)
                self.assertEqual(projection.decisions[-1].invalidated_disclosure_ids, ("fixture-d2",))

    def test_multi_fy_cut_invalidates_old_fy_even_when_new_nearest_fy_differs(self):
        next_year = period(fiscal_year=2026, fiscal_start="2026-01-01", fiscal_end="2026-12-31")
        # Both years are supplied, and a known cut to the existing FY remains
        # relevant even when a next-FY guidance range also appears.
        updated = receipt("fixture-d3", "2026-01-02", periods=[period(), next_year])
        projection = GuidanceLedger((receipt(), raised(), updated)).as_of("2026-02-01T00:00:00Z")
        self.assertFalse(projection.active_comparisons)
        self.assertEqual(projection.decisions[-1].invalidated_disclosure_ids, ("fixture-d2",))

    def test_simultaneous_and_late_discovered_history_quarantines_instead_of_skipping(self):
        for day in ("2025-02-02", "2025-01-15"):
            discovered = receipt("fixture-discovered", day, received_at="2025-02-03T12:01:00Z", validated_at="2025-02-03T12:02:00Z")
            projection = GuidanceLedger((receipt(), raised(), discovered, raised("fixture-d4", "2025-04-01"))).as_of("2025-05-01T00:00:00Z")
            with self.subTest(day=day):
                self.assertEqual(projection.decisions[2].disposition, "quarantined")
                self.assertEqual(projection.decisions[2].invalidated_disclosure_ids, ("fixture-d2",))
                self.assertEqual(projection.decisions[3].refusal_reasons, ("issuer_quarantined",))
                self.assertFalse(projection.active_comparisons)

    def test_unknown_correction_blocks_later_comparison_for_incomplete_chain(self):
        unknown = receipt("fixture-correction", "2025-02-03", kind="correction", supersedes="fixture-unseen")
        projection = GuidanceLedger((receipt(), raised(), unknown, raised("fixture-d4", "2025-04-01"))).as_of("2025-05-01T00:00:00Z")
        self.assertEqual(projection.decisions[2].invalidated_disclosure_ids, ("fixture-d2",))
        self.assertEqual(projection.decisions[-1].refusal_reasons, ("issuer_quarantined",))
        self.assertFalse(projection.active_comparisons)

    def test_explicit_same_id_correction_without_provider_version_is_not_new_news(self):
        old = receipt(provider_version=None)
        corrected = receipt("fixture-d1", "2025-01-03", provider_version=None, kind="correction", supersedes="fixture-d1")
        projection = GuidanceLedger((old, corrected, raised())).as_of("2025-03-01T00:00:00Z")
        self.assertEqual(projection.decisions[1].disposition, "correction")
        self.assertIsNone(projection.decisions[1].comparison)
        self.assertEqual(projection.decisions[2].comparison.predecessor_sha256, corrected.document.sha256)

    def test_reused_earlier_provider_version_conflict_is_not_hidden_by_metadata_edit(self):
        second = receipt(provider_version="v2", raw_tag="metadata-2", received_at="2025-01-03T12:01:00Z", validated_at="2025-01-03T12:02:00Z")
        third = receipt(provider_version="v3", raw_tag="metadata-3", received_at="2025-01-04T12:01:00Z", validated_at="2025-01-04T12:02:00Z")
        conflict = receipt("fixture-d1", "2025-01-05", provider_version="v2", raw_tag="reused-version", kind="correction", supersedes="fixture-d1")
        projection = GuidanceLedger((receipt(), second, third, conflict)).as_of("2025-03-01T00:00:00Z")
        self.assertEqual(projection.decisions[-1].disposition, "quarantined")

    def test_later_received_older_or_equal_correction_cannot_replace_newer_effective_values(self):
        latest = raised("fixture-c-latest", "2025-03-03", kind="correction", supersedes="fixture-d1",
                        period_values={"revenue": {"lower": "110", "upper": "110", "kind": "point"},
                                       "eps": {"lower": "1.10", "upper": "1.10", "kind": "point"}})
        may = raised("fixture-d-may", "2025-05-01",
                     period_values={"revenue": {"lower": "106", "upper": "106", "kind": "point"},
                                    "eps": {"lower": "1.11", "upper": "1.11", "kind": "point"}})
        for published in ("2025-02-02", "2025-03-03"):
            delayed = raised("fixture-c-delayed", published, kind="correction", supersedes="fixture-d1",
                             received_at="2025-04-01T12:01:00Z", validated_at="2025-04-01T12:02:00Z")
            ledger = GuidanceLedger((receipt(), latest, delayed, may))
            projection = ledger.as_of("2025-06-01T00:00:00Z")
            with self.subTest(published=published):
                self.assertEqual(projection.decisions[2].refusal_reasons,
                                 ("mutation_not_later_than_previous_applied_mutation",))
                self.assertEqual(projection.decisions[-1].refusal_reasons, ("issuer_quarantined",))
                self.assertIsNone(projection.decisions[-1].comparison)
                self.assertFalse(projection.active_comparisons)
                self.assertEqual(len(ledger.receipts), 4)
                # The precise regression: selecting the delayed older values
                # would turn a failing May comparison into a passing one.
                self.assertTrue(compare_revision(may.document, delayed.document).passes_arithmetic)
                self.assertFalse(compare_revision(may.document, latest.document).passes_arithmetic)

    def test_older_or_equal_withdrawal_after_correction_quarantines_and_invalidates(self):
        latest = receipt("fixture-c-latest", "2025-03-03", kind="correction", supersedes="fixture-d1")
        active = raised("fixture-d-active", "2025-03-04")
        for published in ("2025-02-02", "2025-03-03"):
            delayed = receipt("fixture-w-delayed", published, kind="withdrawal", supersedes="fixture-d1", periods=[],
                              received_at="2025-04-01T12:01:00Z", validated_at="2025-04-01T12:02:00Z")
            ledger = GuidanceLedger((receipt(), latest, active, delayed))
            before = ledger.as_of("2025-03-31T23:59:59Z")
            after = ledger.as_of("2025-04-02T00:00:00Z")
            with self.subTest(published=published):
                self.assertEqual(len(before.active_comparisons), 1)
                self.assertEqual(after.decisions[-1].refusal_reasons,
                                 ("mutation_not_later_than_previous_applied_mutation",))
                self.assertEqual(after.decisions[-1].invalidated_disclosure_ids, ("fixture-d-active",))
                self.assertFalse(after.active_comparisons)

    def test_withdrawal_clock_is_retained_for_later_correction_order_and_no_resurrection(self):
        withdrawal = receipt("fixture-w-latest", "2025-03-03", kind="withdrawal", supersedes="fixture-d1", periods=[])
        for published, expected in (("2025-02-02", "mutation_not_later_than_previous_applied_mutation"),
                                    ("2025-03-03", "mutation_not_later_than_previous_applied_mutation"),
                                    ("2025-03-04", "immediate_predecessor_withdrawn")):
            correction = receipt("fixture-c-after-w", published, kind="correction", supersedes="fixture-d1",
                                 received_at="2025-04-01T12:01:00Z", validated_at="2025-04-01T12:02:00Z")
            projection = GuidanceLedger((receipt(), withdrawal, correction, raised("fixture-d-next", "2025-05-01"))).as_of("2025-06-01T00:00:00Z")
            with self.subTest(published=published):
                if published != "2025-03-04":
                    self.assertEqual(projection.decisions[2].refusal_reasons, (expected,))
                    self.assertEqual(projection.decisions[-1].refusal_reasons, ("issuer_quarantined",))
                else:
                    self.assertEqual(projection.decisions[2].disposition, "correction")
                    self.assertEqual(projection.decisions[-1].refusal_reasons, (expected,))
                self.assertFalse(projection.active_comparisons)

    def test_increasing_correction_clocks_apply_latest_without_rewriting_earlier_projection(self):
        first = receipt("fixture-c-first", "2025-02-02", kind="correction", supersedes="fixture-d1")
        second = receipt("fixture-c-second", "2025-03-03", kind="correction", supersedes="fixture-d1")
        next_release = raised("fixture-d-next", "2025-04-01")
        ledger = GuidanceLedger((receipt(), first, second, next_release))
        earlier = ledger.as_of("2025-02-28T23:59:59Z")
        later = ledger.as_of("2025-05-01T00:00:00Z")
        self.assertEqual(len(earlier.decisions), 2)
        self.assertEqual(earlier.decisions[-1].disposition, "correction")
        self.assertEqual(later.decisions[-1].comparison.predecessor_sha256, second.document.sha256)
        self.assertTrue(later.decisions[-1].comparison.passes_arithmetic)

    def test_as_of_slices_validation_and_refuses_invalid_empty_cutoff(self):
        ledger = GuidanceLedger((receipt(), raised()))
        self.assertEqual(len(ledger.as_of("2025-02-02T12:01:59Z").decisions), 1)
        self.assertEqual(len(ledger.as_of("2025-02-02T12:02:00Z").decisions), 2)
        with self.assertRaises(InputError):
            GuidanceLedger().as_of("not-a-clock")
        with self.assertRaises(InputError):
            GuidanceLedger((raised(), receipt()))

    def test_resource_bounds_apply_before_serialization(self):
        with patch("research.guidance_revision_drift.guidance_inputs.MAX_RECEIPTS", 1):
            with self.assertRaises(InputError):
                GuidanceLedger((receipt(), raised()))
        with patch("research.guidance_revision_drift.guidance_inputs.MAX_LEDGER_BYTES", 500):
            with self.assertRaises(InputError):
                GuidanceLedger((receipt(),))
        with self.assertRaises(InputError):
            GuidanceLedger([receipt()])

    def test_complete_ledger_roundtrip_anchor_and_corruption_detection(self):
        ledger = GuidanceLedger((receipt(), raised()))
        raw = ledger.to_bytes()
        restored = GuidanceLedger.from_bytes(raw, expected_head=ledger.head_sha256)
        self.assertEqual(restored.to_bytes(), raw)
        self.assertFalse(restored.as_of("2025-03-01T00:00:00Z").to_dict()["point_in_time_data"])
        for wrong in (raw.replace(b'"point_in_time_data":false', b'"point_in_time_data":true'),
                      raw.replace(b"fixture-adjustment-v1", b"fixture-adjustment-v2"), raw + b"\n"):
            with self.subTest(wrong=wrong[-40:]), self.assertRaises(InputError):
                GuidanceLedger.from_bytes(wrong, expected_head=ledger.head_sha256)
        with self.assertRaises(InputError):
            GuidanceLedger.from_bytes(GuidanceLedger((receipt(),)).to_bytes(), expected_head=ledger.head_sha256)
        with self.assertRaises(InputError):
            GuidanceLedger.from_bytes(raw, expected_head="0" * 64)

    def test_multi_fy_selects_nearest_unexpired_and_preserves_scope_refusals(self):
        next_year = period(fiscal_year=2026, fiscal_start="2026-01-01", fiscal_end="2026-12-31")
        old = receipt(periods=[period(), next_year])
        new = raised(periods=[period(revenue={"lower": "102", "upper": "102", "kind": "point"},
                                             eps={"lower": "1.05", "upper": "1.05", "kind": "point"}), next_year])
        self.assertEqual(compare_revision(new.document, old.document).fiscal_year, 2025)
        for field in ("scope", "share_basis", "revenue_basis", "eps_basis"):
            changed = raised(period_values={field: "fixture-changed"})
            with self.subTest(field=field):
                self.assertFalse(compare_revision(changed.document, old.document).passes_arithmetic)
                self.assertIn("changed_" + field, compare_revision(changed.document, old.document).refusal_reasons)

    def test_no_network_files_environment_or_provider_seams(self):
        with patch("socket.socket.connect", side_effect=AssertionError("network")), \
             patch("builtins.open", side_effect=AssertionError("files")), \
             patch("os.getenv", side_effect=AssertionError("environment")):
            ledger = GuidanceLedger((receipt(), raised()))
            self.assertEqual(ledger.as_of("2025-03-01T00:00:00Z").decisions[-1].disposition, "comparison")


if __name__ == "__main__":
    unittest.main()
