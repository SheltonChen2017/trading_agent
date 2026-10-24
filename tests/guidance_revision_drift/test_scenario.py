"""Built-in synthetic event-to-order report, CLI and immutable artifact path."""
import contextlib
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_payload
from research.guidance_revision_drift.__main__ import main
from research.guidance_revision_drift.artifacts import read_fixture
from research.guidance_revision_drift.controls import FixtureLedger
from research.guidance_revision_drift.fixtures import example_corpus
from research.guidance_revision_drift.scenario import run_fixture_report


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_fixture_report()

    def test_both_cost_modes_complete_actual_synthetic_orders_and_settlement(self):
        self.assertEqual([r["mode"] for r in self.report["runs"]], ["base", "stress"])
        for run in self.report["runs"]:
            strategy = run["strategy"]
            self.assertEqual([f["side"] for f in strategy["fills"]], ["buy", "sell"])
            self.assertEqual(strategy["fills"][0]["quantity"], strategy["fills"][1]["quantity"])
            self.assertEqual(strategy["positions"], [])
            self.assertEqual(strategy["receivables"], [])
            self.assertEqual(strategy["reserved_cash"], "0")
            self.assertFalse(strategy["completion_blocked"])
            self.assertEqual(strategy["missing_session_closes"], [])
            self.assertEqual(run["eligibility"]["entry_session"], "2025-04-04")
            self.assertEqual(run["diagnostics"]["status"], "fixture_diagnostics_only")
            self.assertFalse(run["research_accepted"])
        base, stress = (r["strategy"] for r in self.report["runs"])
        self.assertLess(Decimal(stress["settled_cash"]), Decimal(base["settled_cash"]))

    def test_every_explicit_fixture_session_including_idle_days_has_paired_nav(self):
        days = [s.session_date.isoformat() for s in example_corpus().schedule.sessions]
        self.assertEqual(len(days), 93)
        for run in self.report["runs"]:
            self.assertEqual([r[0] for r in run["paired_daily_nav"]], days)
            self.assertEqual(run["paired_daily_nav"][0][1:], ["100000", "100000"])
            entry_day = run["strategy"]["fills"][0]["at"][:10]
            exit_day = run["strategy"]["fills"][1]["at"][:10]
            self.assertEqual(days.index(exit_day) - days.index(entry_day), 20)
            self.assertEqual(run["diagnostics"]["return_intervals"], 92)
            self.assertEqual(run["adapter_callback_count"], 93)

    def test_report_binds_actual_inputs_code_and_separate_base_stress_receipts(self):
        ledger = FixtureLedger.from_bytes(canonical_json(self.report["ledger"]).encode())
        self.assertEqual(ledger.epoch.code_sha256, hash_payload(self.report["source_manifest"]))
        self.assertEqual(ledger.epoch.source_sha256, example_corpus().sha256)
        self.assertEqual([r.status for r in ledger.receipts], ["started", "completed", "started", "completed"])
        for receipt, run in zip(ledger.receipts[1::2], self.report["runs"]):
            self.assertEqual(receipt.output_sha256, hash_payload(run))
        self.assertEqual(self.report["empirical_looks"], 0)
        self.assertEqual(self.report["qc_attempts"], 0)
        self.assertFalse(self.report["external_authority"])
        self.assertFalse(self.report["point_in_time_data"])
        self.assertFalse(self.report["market_evidence"])

    def test_report_is_reproducible_and_has_no_implicit_write_network_or_process(self):
        original_open = os.open
        def read_only(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            return original_open(path, flags, *args, **kwargs)
        with patch("os.open", side_effect=read_only), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("network forbidden")), \
             patch("os.getenv", side_effect=AssertionError("environment forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process forbidden")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["synthetic-demo"]), 0)
        self.assertEqual(json.loads(out.getvalue()), self.report)

    def test_explicit_artifact_export_is_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            for repeat in range(2):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(main(["synthetic-demo", "--output-dir", folder]), 0)
                receipt = json.loads(out.getvalue())
                path = Path(receipt["artifact"])
                self.assertEqual(path.parent, Path(folder).resolve())
                self.assertEqual(json.loads(read_fixture(path)), self.report)
                self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_invalid_output_directory_reports_failure_without_success_payload(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out, \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(["synthetic-demo", "--output-dir", str(Path(folder) / "missing")]), 1)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(json.loads(err.getvalue())["status"], "offline_command_failed")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_cli_has_no_empirical_input_or_launch_override(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["adapter-manifest"]), 0)
        self.assertEqual(json.loads(out.getvalue()), self.report["adapter"])
        for args in (["synthetic-demo", "--input", "market.csv"], ["synthetic-demo", "--approved"],
                     ["preflight", "--output-dir", "."], ["qc-launch"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(args)


if __name__ == "__main__":
    unittest.main()
