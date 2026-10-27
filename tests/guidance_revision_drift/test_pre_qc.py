"""Actual deterministic local handoff bytes, never QC readiness or execution."""
from __future__ import annotations

import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.bundle import BundlePublicationUncertain
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes
from research.guidance_revision_drift.pre_qc import build_handoff, verify_handoff, main


class PreQCHandoffTests(unittest.TestCase):
    def test_actual_handoff_reconstructs_complete_source_and_two_closed_plans(self):
        report = build_handoff()
        raw = canonical_bytes(report)
        self.assertEqual(verify_handoff(raw, expected_sha256=hash_bytes(raw)), report)
        self.assertEqual(canonical_bytes(build_handoff()), raw)
        self.assertEqual(report["source_bundle_members"], 59)
        self.assertEqual(set(report["plans"]), {"base", "stress"})
        for mode, plan in report["plans"].items():
            self.assertEqual(report["plan_sha256s"][mode], hash_bytes(canonical_bytes(plan)))
            self.assertEqual(plan["candidates"][0]["intent"]["whole_shares"], 495)
            self.assertEqual(plan["orders_submitted"], 0)
            self.assertEqual(plan["fills"], [])
        for key in ("native_adapter_implemented", "native_execution_verified", "data_rights_verified",
                    "backtest_ready", "qc_upload_allowed", "qc_launch_allowed", "real_orders_allowed",
                    "empirical_evaluation_allowed"):
            self.assertIs(report[key], False)
        self.assertTrue(all(value is None for value in report["unresolved_original_decisions"].values()))
        self.assertIn("terminal_stock_payout_to_SPY_unwind_rule", report["remaining_before_QC"])
        self.assertNotIn(b"source_payload_sha256", raw)
        self.assertNotIn(b"api_key", raw)

    def test_retained_hash_precedes_any_reconstruction(self):
        with patch("research.guidance_revision_drift.pre_qc.build_handoff", side_effect=AssertionError("built before anchor")):
            with self.assertRaises(InputError):
                verify_handoff(b"PRIVATE-INVALID", expected_sha256="0" * 64)

    def test_rehashed_approval_or_changed_plan_cannot_certify_itself(self):
        report = build_handoff()
        changed = deepcopy(report)
        changed["qc_launch_allowed"] = True
        raw = canonical_bytes(changed)
        with self.assertRaises(InputError):
            verify_handoff(raw, expected_sha256=hash_bytes(raw))
        changed = deepcopy(report)
        changed["plans"]["base"]["candidates"][0]["intent"]["whole_shares"] = 496
        raw = canonical_bytes(changed)
        with self.assertRaises(InputError):
            verify_handoff(raw, expected_sha256=hash_bytes(raw))

    def test_cli_archive_publication_keeps_exact_stdout_handoff_verifiable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(main(["--output-dir", str(destination)]), 0)
                raw = output.getvalue().encode()
                report = json.loads(raw)
                self.assertEqual(raw, canonical_bytes(report))
                self.assertEqual(verify_handoff(raw, expected_sha256=hash_bytes(raw)), report)
                self.assertIn("Local source archive: ", errors.getvalue())
            archives = tuple(destination.iterdir())
            self.assertEqual(len(archives), 1)
            self.assertEqual(archives[0].name, report["source_bundle_sha256"] + ".zip")
            self.assertEqual(hash_bytes(archives[0].read_bytes()), report["source_bundle_sha256"])
            manifest = destination / "handoff.json"
            manifest.write_bytes(raw)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--verify-file", str(manifest), "--sha256", hash_bytes(raw)]), 0)
            self.assertEqual(output.getvalue().encode(), raw)

    def test_unsupported_launch_flags_and_private_read_errors_refuse(self):
        for args in (["--launch"], ["--approved"], ["--sha256", "0" * 64],
                     ["--verify-file", "private"], ["--verify-file", "private", "--sha256", "0" * 64, "--output-dir", "x"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                main(args)
            self.assertEqual(stopped.exception.code, 2)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--verify-file", "/nonexistent/PRIVATE.json", "--sha256", "0" * 64]), 2)
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_output_directory_is_not_created_or_rebound(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--output-dir", str(missing)]), 2)
            self.assertFalse(missing.exists())
            self.assertFalse(json.loads(output.getvalue())["qc_launch_allowed"])

    def test_ambiguous_archive_publication_is_not_reported_as_definite_absence(self):
        report = build_handoff()
        with patch("research.guidance_revision_drift.pre_qc.build_handoff", return_value=report), \
             patch("research.guidance_revision_drift.pre_qc.publish_bundle", side_effect=BundlePublicationUncertain("private-path")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--output-dir", "unused"]), 3)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "pre_qc_publication_uncertain")
        self.assertTrue(result["source_archive_may_exist"])
        self.assertFalse(result["qc_launch_allowed"])
        self.assertNotIn("private-path", output.getvalue())


if __name__ == "__main__":
    unittest.main()
