"""Invented preparation inputs never become market or execution evidence."""
from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import Candidate, load_candidate
from research.guidance_revision_drift.exploratory_preparation import prepare_exploratory_backtest
from research.guidance_revision_drift.guidance_dataset import GuidanceDataset
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes
from tests.guidance_revision_drift.test_guidance_dataset import build, profile, scope


def prepare(dataset=None, **changes):
    dataset = dataset or build()
    options = {
        "expected_dataset_sha256": dataset.sha256,
        "producing_source_sha256": "1" * 64,
        "quote_coverage_sha256": "2" * 64,
        "quote_condition_overlay_sha256": "3" * 64,
        "preparation_id": "invented-pilot",
        "owner_direction_reference": "invented-preparation-scope",
        "study_start": "2025-01-01", "study_end": "2025-12-31",
    }
    options.update(changes)
    return prepare_exploratory_backtest(load_candidate(), dataset.canonical_bytes, **options)


class ExploratoryPreparationTests(unittest.TestCase):
    def test_assumed_history_preserves_original_refusals_and_never_creates_signals(self):
        issues = ["immediate_issuer_guidance_predecessor_unverified"]
        dataset = build((profile(issues=issues),
                         profile("fixture-d2", "2025-02-02", "fixture-d1", issues=issues)))
        original = dataset.canonical_bytes
        with patch("research.guidance_revision_drift.formulas.evaluate_range_revisions",
                   side_effect=AssertionError("financial evaluation invoked")):
            result = prepare(dataset)
        self.assertEqual(result["roles"], {"baseline_placeholder": 1, "pair_placeholder": 1})
        self.assertEqual(result["roster"][1]["original_decision"]["disposition"], "refused")
        self.assertEqual(result["roster"][1]["assumption_ids"], ["supplied_guidance_history"])
        self.assertFalse(result["roster"][1]["assumptions_applied"])
        self.assertFalse(result["roster"][1]["qualifying_signal_computed"])
        self.assertEqual(dataset.canonical_bytes, original)
        for before, row in zip(dataset.to_dict()["profiles"], result["roster"], strict=True):
            self.assertEqual(row["original_profile_sha256"], hash_bytes(canonical_bytes(before)))
            self.assertIsNone(row["published_at"])
            self.assertEqual(row["actual_captured_at"], before["captured_at"])

    def test_missing_semantics_changed_definitions_and_new_issues_remain_excluded(self):
        for changes in ({"revenue_basis": None}, {"adjustment_definition": None},
                        {"adjustment_definition": "invented-different"},
                        {"issues": ["unrecognized_new_quality_issue"]}):
            with self.subTest(changes=changes):
                result = prepare(build((profile(), profile("fixture-d2", "2025-02-02", "fixture-d1", **changes))))
                row = result["roster"][1]
                self.assertEqual(row["preparation_role"], "excluded")
                self.assertTrue(row["exclusion_reasons"])
                self.assertEqual(result["profile_count"], 2)

    def test_missing_intervening_record_cannot_be_skipped(self):
        rows = (profile(), profile("fixture-d2", "2025-02-02", "fixture-d1", eps=None),
                profile("fixture-d3", "2025-03-02", "fixture-d1"))
        result = prepare(build(rows, scoped=scope(ids=("fixture-d1", "fixture-d2", "fixture-d3"))))
        self.assertEqual(len(result["roster"]), 3)
        last = result["roster"][-1]
        self.assertEqual(last["original_decision"]["predecessor_profile_id"], "fixture-d2")
        self.assertEqual(last["preparation_role"], "excluded")
        self.assertIn("declared_predecessor_is_not_immediate_supplied_profile", last["exclusion_reasons"])

    def test_nonnull_unsupported_baseline_semantics_are_not_assumed(self):
        for changes in ({"currency": "EUR"}, {"period": "Q1"}, {"revenue_basis": "adj"},
                        {"eps_basis": "gaap"}, {"revenue_units": "unsupported_units"}):
            with self.subTest(changes=changes):
                dataset = build((profile(**changes), profile("fixture-d2", "2025-02-02", "fixture-d1")))
                row = prepare(dataset)["roster"][0]
                self.assertEqual(row["preparation_role"], "excluded")
                self.assertTrue(row["exclusion_reasons"])

    def test_literal_unknown_issue_cannot_impersonate_generated_predecessor_issue(self):
        forged = "predecessor_issue_immediate_issuer_guidance_predecessor_unverified"
        dataset = build((profile(issues=[forged]), profile("fixture-d2", "2025-02-02", "fixture-d1")))
        row = prepare(dataset)["roster"][0]
        self.assertEqual(row["preparation_role"], "excluded")
        self.assertIn(forged, row["exclusion_reasons"])

    def test_missing_expected_profiles_remain_in_denominator(self):
        dataset = build(scoped=scope(ids=("fixture-d1", "fixture-d2", "fixture-d3")))
        result = prepare(dataset)
        self.assertEqual(result["missing_expected_profile_ids"], ["fixture-d3"])
        self.assertEqual(result["roles"], {"excluded": 2})

    def test_numeric_quote_checks_accounting_and_unchanged_rules_are_not_waived(self):
        result = prepare()
        rules = load_candidate().to_dict()
        for name, value in result["economic_rules"].items():
            self.assertEqual(value, rules[name])
        self.assertTrue(result["economic_rules"]["portfolio"]["settled_cash_only"])
        self.assertTrue(result["market_inputs"]["references_are_not_a_price_tape"])
        self.assertIsNone(result["market_inputs"]["price_tape_sha256"])
        self.assertFalse(result["market_inputs"]["execution_qualified"])
        self.assertFalse(result["market_inputs"]["original_conditions_recovered"])
        self.assertTrue(all(not row["applied"] and not row["fact_verified"] for row in result["proposed_exceptions"]))
        self.assertFalse(result["runnable"])
        self.assertFalse(result["backtest_ready"])
        self.assertFalse(result["qc_access_allowed"])
        self.assertEqual(result["outcome_calculations"], 0)
        self.assertTrue(all(value is False for value in result["original_guidance_gates"].values()))

    def test_draft_dates_cannot_open_protected_outcomes_or_drop_declared_scope(self):
        for options in ({"study_end": "2026-09-01"}, {"study_end": "2027-10-01"},
                        {"study_start": "2012-12-31"}, {"study_start": "2025-02-01"},
                        {"study_end": "2025-06-01"}, {"study_start": "2025-12-31", "study_end": "2025-01-01"}):
            with self.subTest(options=options), self.assertRaises(InputError):
                prepare(**options)

    def test_hashes_and_scope_references_are_validated_before_output(self):
        for options in ({"expected_dataset_sha256": "0" * 64},
                        {"producing_source_sha256": "invalid"},
                        {"quote_coverage_sha256": True},
                        {"owner_direction_reference": "https://example.invalid/?secret=x"}):
            with self.subTest(options=options), self.assertRaises(InputError):
                prepare(**options)

    def test_report_is_detached_and_cannot_be_loaded_as_approved_dataset_or_candidate(self):
        dataset = build()
        result = prepare(dataset)
        raw = canonical_bytes(result)
        with self.assertRaises(InputError):
            GuidanceDataset.from_bytes(raw, expected_sha256=hash_bytes(raw))
        with self.assertRaises(ValueError):
            Candidate.from_bytes(raw)
        mutated = deepcopy(result)
        mutated["original_guidance_gates"]["execution_ready"] = True
        mutated["economic_rules"]["portfolio"]["settled_cash_only"] = False
        self.assertTrue(all(value is False for value in dataset.to_dict()["gates"].values()))
        self.assertEqual(prepare(dataset), result)


if __name__ == "__main__":
    unittest.main()
