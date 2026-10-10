"""Local package preparation is never a launch or readiness approval."""
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.__main__ import main


class PreparationCliTests(unittest.TestCase):
    def run_command(self, arguments):
        with contextlib.redirect_stdout(io.StringIO()) as output, \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("launch forbidden")):
            status = main(arguments)
        return status, json.loads(output.getvalue())

    def test_prepare_then_verify_exact_local_bundle_without_launch(self):
        with TemporaryDirectory(prefix="gdr-preparation-cli-") as directory:
            status, prepared = self.run_command(["prepare-bundle", "--output-dir", directory])
            self.assertEqual(status, 0)
            artifact = Path(prepared["artifact"])
            self.assertEqual(artifact.parent, Path(directory).resolve())
            self.assertEqual(artifact.name, prepared["sha256"] + ".zip")
            self.assertEqual(hash_bytes(artifact.read_bytes()), prepared["sha256"])
            status, verified = self.run_command(["verify-bundle", "--bundle-file", str(artifact),
                                                 "--expected-sha256", prepared["sha256"]])
            self.assertEqual(status, 0)
            for report in (prepared, verified):
                self.assertFalse(report["external_authority"])
                self.assertEqual(report["qc_attempts"], 0)
                self.assertEqual(report["preflight"]["status"], "blocked")
                self.assertFalse(report["preflight"]["qc_launch_allowed"])
                self.assertEqual(report["preflight"]["readiness"]["native_engine_execution"], "unverified")
                self.assertEqual(report["preflight"]["readiness"]["empirical_order_based_backtest"], "blocked")
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_prepare_without_output_has_no_artifact_and_preflight_still_exits_two(self):
        status, report = self.run_command(["prepare-bundle"])
        self.assertEqual(status, 0)
        self.assertNotIn("artifact", report)
        self.assertEqual(len(report["sha256"]), 64)
        self.assertEqual(self.run_command(["launch-preflight"])[0], 2)

    def test_qc_project_preparation_is_metadata_only_not_launch_approval(self):
        status, report = self.run_command(["prepare-qc-project"])
        self.assertEqual(status, 0)
        self.assertEqual(report["status"], "local_qc_project_preparation_only")
        self.assertNotIn("artifact", report)
        self.assertFalse(report["external_authority"])
        self.assertEqual(report["qc_attempts"], 0)
        self.assertEqual(report["preflight"]["status"], "blocked")
        self.assertFalse(report["preflight"]["qc_launch_allowed"])
        self.assertEqual(report["preflight"]["readiness"]["empirical_order_based_backtest"], "blocked")
        self.assertLessEqual(len(report["manifest"]["project_files"]), 25)
        self.assertIn("main.py", report["manifest"]["project_files"])

    def test_preflight_does_not_conflate_synthetic_run_with_empirical_authority(self):
        status, report = self.run_command(["launch-preflight"])
        self.assertEqual(status, 2)
        self.assertFalse(report["qc_upload_allowed"])
        self.assertFalse(report["qc_launch_allowed"])
        self.assertEqual(report["external_evaluation_scope"], "synthetic_only_order_based_integration_not_empirical")
        self.assertIn("reviewed_root_entrypoint_and_exact_372_frame_transport",
                      report["required_before_external_evaluation"])
        self.assertIn("existing_project_file_and_remaining_log_quotas_cover_complete_native_evidence",
                      report["required_before_external_evaluation"])
        self.assertIn("retained_owner_cycle_and_latest_head_preserve_attempt_budget_across_corrections",
                      report["required_before_external_evaluation"])
        self.assertNotIn("pinned_native_engine_and_binding_validation",
                         report["required_before_external_evaluation"])
        self.assertIn("pinned_native_engine_and_binding_validation",
                      report["required_before_empirical_evaluation"])
        self.assertIn("owner_freeze_and_separate_exact_source_outcome_and_QC_authority",
                      report["required_before_empirical_evaluation"])

    def test_wrong_retained_hash_and_nonregular_archive_are_errors(self):
        with TemporaryDirectory(prefix="gdr-preparation-cli-") as directory:
            _, prepared = self.run_command(["prepare-bundle", "--output-dir", directory])
            for path, anchor in ((prepared["artifact"], "0" * 64), (directory, prepared["sha256"])):
                with contextlib.redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(main(["verify-bundle", "--bundle-file", path, "--expected-sha256", anchor]), 1)
                self.assertEqual(json.loads(output.getvalue())["status"], "offline_command_failed")

    def test_no_approval_launch_or_ambiguous_flag_routes(self):
        cases = (["prepare-bundle", "--approved"], ["prepare-bundle", "--launch"],
                 ["prepare-qc-project", "--approved"], ["prepare-qc-project", "--launch"],
                 ["prepare-qc-project", "--output-dir", "x"],
                 ["verify-bundle"], ["verify-bundle", "--bundle-file", "x"],
                 ["show-candidate", "--expected-sha256", "0" * 64],
                 ["verify-bundle", "--bundle-file", "x", "--expected-sha256", "0" * 64, "--output-dir", "x"])
        for arguments in cases:
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit) as raised:
                main(arguments)
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
