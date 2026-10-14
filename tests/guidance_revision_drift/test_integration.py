"""End-to-end invented lineage/input/accounting/restart stress cases."""
from copy import deepcopy
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data.hashing import hash_payload
from research.guidance_revision_drift.fixtures import fixture_instant
from research.guidance_revision_drift.integration import (
    SCENARIOS, fixture_lineage, run_integrated_fixture, run_integration_report,
)
from research.guidance_revision_drift.reporting import source_manifest


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Capture actual source bytes once, not hardcoded expected hashes. This
        # also prevents unrelated concurrent authoring from mixing epochs in
        # this test's repeated runs of already-imported functions.
        cls.manifest = source_manifest()
        with patch("research.guidance_revision_drift.integration.source_manifest", return_value=cls.manifest):
            cls.report = run_integration_report()
        cls.rows = {(row["mode"], row["scenario"]): row for row in cls.report["runs"]}

    def test_every_recipe_retains_complete_calendar_and_verified_command_replay(self):
        self.assertEqual(set(self.rows), {("base", name) for name in SCENARIOS} | {("stress", "actions")})
        for row in self.rows.values():
            self.assertEqual(row["calendar_observations"], 93)
            self.assertTrue(row["final_recovery_exact"])
            self.assertGreater(row["command_count"], 186)
            for field in ("report_sha256", "journal_head_sha256", "state_sha256", "checkpoint_sha256",
                          "provider_lineage_head", "source_sha256", "code_sha256", "calendar_sha256"):
                self.assertEqual(len(row[field]), 64)
        self.assertEqual(self.report["qc_attempts"], 0)
        self.assertEqual(self.report["research_looks"], 0)
        self.assertFalse(self.report["cloud_completed"])
        self.assertFalse(self.report["external_authority"])

    def test_actions_flow_through_both_sleeves_and_settle_all_positions(self):
        for mode in ("base", "stress"):
            row = self.rows[mode, "actions"]
            self.assertEqual(row["corporate_action_count"], 4)
            # The split doubles the holding above the fixed minute capacity:
            # one entry plus two real partial exits must both be mirrored.
            self.assertEqual(row["strategy_fill_count"], 3)
            self.assertEqual(row["comparator_fill_count"], 3)
            self.assertFalse(row["strategy_completion_blocked"])
            self.assertFalse(row["comparator_completion_blocked"])
            self.assertEqual(row["diagnostic_status"], "fixture_diagnostics_only")
        self.assertFalse(self.rows["base", "actions"]["comparator_parity_blocked"])

    def test_missing_and_stale_decision_inputs_refuse_and_never_create_fill(self):
        for name in ("missing_data", "stale_data"):
            row = self.rows["base", name]
            self.assertEqual(row["strategy_fill_count"], 0)
            self.assertEqual(row["comparator_fill_count"], 0)
            self.assertEqual(len(row["input_refusals"]), 1)
        self.assertEqual(self.rows["base", "missing_data"]["input_refusals"][0]["reason"], "missing_market_input")
        self.assertIn("stale", self.rows["base", "stale_data"]["input_refusals"][0]["reason"])

    def test_underfill_and_terminal_schedule_blockers_survive_recovery_and_later_prices(self):
        partial = self.rows["base", "underfill"]
        self.assertTrue(partial["comparator_parity_blocked"])
        self.assertIn("partial_or_unmatched_execution", [row["reason"] for row in partial["parity_blockers"]])
        terminal = self.rows["base", "source_terminal"]
        self.assertEqual(terminal["strategy_fill_count"], 1)
        self.assertEqual(terminal["comparator_fill_count"], 1)
        self.assertTrue(terminal["comparator_completion_blocked"])
        self.assertIn("source_terminal_comparator_schedule_unsupported",
                      [row["reason"] for row in terminal["parity_blockers"]])

    def test_missing_historical_nav_blocks_completion_after_eventual_liquidation(self):
        missing = self.rows["base", "missing_nav"]
        self.assertEqual(missing["strategy_fill_count"], 2)
        self.assertTrue(missing["strategy_completion_blocked"])
        self.assertEqual(missing["diagnostic_status"], "blocked_missing_paired_nav")

    def test_restarted_and_uninterrupted_exact_head_state_and_report_reproduce(self):
        reports = []
        for restart in (False, True):
            with TemporaryDirectory(prefix="gdr-integration-test-") as directory, patch(
                    "research.guidance_revision_drift.integration.source_manifest", return_value=self.manifest):
                reports.append(run_integrated_fixture(Path(directory), restart_after_entry=restart))
        left, right = reports
        for field in ("state_sha256", "journal_head_sha256", "checkpoint_sha256", "paired_daily_nav", "state"):
            self.assertEqual(left[field], right[field])
        normalized = deepcopy(left)
        normalized["midrun_recovery_performed"] = True
        self.assertEqual(hash_payload(normalized), hash_payload(right))
        self.assertEqual(hash_payload(right), self.rows["base", "actions"]["report_sha256"])

    def test_provider_shaped_lineage_is_asof_not_a_normalized_fixture_shortcut(self):
        lineage = fixture_lineage()
        old = lineage.as_of(fixture_instant(date(2025, 3, 31), 10))
        raised = lineage.as_of(fixture_instant(date(2025, 4, 4), 10))
        self.assertEqual(old.receipt_statuses, ("bootstrap",))
        self.assertEqual(raised.receipt_statuses, ("bootstrap", "candidate"))
        self.assertEqual(raised.book.decisions[-1].candidate.disclosure_id, "SYN-RAISE")
        self.assertIn(b'"benzinga_id"', lineage.receipts[0][0].raw_bytes)

    def test_unknown_recipe_cannot_launch_arbitrary_or_external_evaluation(self):
        with TemporaryDirectory(prefix="gdr-integration-test-") as directory:
            for kwargs in ({"mode": "live"}, {"scenario": "uploaded"}, {"restart_after_entry": 1}):
                with self.assertRaises(ValueError):
                    run_integrated_fixture(Path(directory), **kwargs)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
