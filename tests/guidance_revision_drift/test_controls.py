"""Synthetic accounting cannot become empirical access or authority."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
import json
import unittest

from research.guidance_revision_drift.controls import (
    FixtureEpoch, FixtureLedger, FixtureReceipt, ResearchControlError,
    qc_recovery_disposition, refuse_external_action,
)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.epoch = FixtureEpoch("a" * 64, "b" * 64, "c" * 64)
        self.ledger = FixtureLedger(self.epoch)

    def test_base_and_stress_have_separate_preserved_receipts(self):
        ledger = self.ledger.start("fixture-base", "base", "d" * 64)
        ledger = ledger.finish("fixture-base", output_sha256="e" * 64)
        ledger = ledger.start("fixture-stress", "stress", "d" * 64)
        ledger = ledger.finish("fixture-stress", output_sha256="f" * 64, failed=True)
        self.assertEqual(len(ledger.receipts), 4)
        self.assertEqual(ledger.receipts[-1].status, "failed")
        self.assertEqual(FixtureLedger.from_bytes(ledger.to_bytes()), ledger)
        self.assertEqual(ledger.to_dict()["empirical_looks"], 0)
        self.assertEqual(ledger.to_dict()["qc_attempts"], 0)
        self.assertFalse(ledger.to_dict()["point_in_time_data"])

    def test_no_reuse_terminal_without_start_or_changed_epoch(self):
        started = self.ledger.start("fixture-a", "base", "d" * 64)
        done = started.finish("fixture-a", output_sha256="e" * 64)
        for callback in (
            lambda: started.start("fixture-a", "base", "d" * 64),
            lambda: done.finish("fixture-a", output_sha256="e" * 64),
            lambda: self.ledger.finish("fixture-a", output_sha256="e" * 64),
            lambda: FixtureLedger(replace(self.epoch, source_sha256="e" * 64), started.receipts),
            lambda: FixtureLedger(self.epoch, tuple(reversed(done.receipts))),
            lambda: FixtureLedger(self.epoch, (replace(started.receipts[0], sequence=2),)),
        ):
            with self.subTest(callback=callback), self.assertRaises(ResearchControlError):
                callback()

    def test_broken_previous_hash_link_is_refused_with_intact_sequence_and_epoch(self):
        # The sequence and epoch checks alone would accept a receipt whose
        # previous_sha256 no longer names its predecessor; the chain link must
        # be verified in its own right, in memory and on decode.
        done = self.ledger.start("fixture-a", "base", "d" * 64).finish("fixture-a", output_sha256="e" * 64)
        broken = replace(done.receipts[1], previous_sha256="f" * 64)
        with self.assertRaisesRegex(ResearchControlError, "broken receipt chain"):
            FixtureLedger(self.epoch, (done.receipts[0], broken))
        body = done.to_dict()
        body["receipts"][1]["previous_sha256"] = "f" * 64
        with self.assertRaises(ResearchControlError):
            FixtureLedger.from_bytes(json.dumps(body).encode())

    def test_immutable_projections_and_forged_objects_revalidated(self):
        ledger = self.ledger.start("fixture-a", "base", "d" * 64)
        with self.assertRaises(FrozenInstanceError):
            ledger.receipts = ()
        projection = ledger.to_dict()
        projection["receipts"][0]["status"] = "completed"
        self.assertEqual(ledger.receipts[0].status, "started")
        object.__setattr__(ledger.receipts[0], "sequence", True)
        with self.assertRaises(ResearchControlError):
            ledger.to_bytes()

    def test_unknown_fields_types_and_approval_mutations_refuse(self):
        body = self.ledger.to_dict()
        for key, value in (("approved", True), ("empirical_looks", 1), ("empirical_looks", False),
                           ("qc_attempts", 1), ("point_in_time_data", True), ("schema", "changed")):
            changed = dict(body, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ResearchControlError):
                FixtureLedger.from_bytes(json.dumps(changed).encode())
        for raw in (b'{"schema":1,"schema":2}', b'{"n":NaN}', b'[]', b'{"n":1.2}', b'{}'):
            with self.assertRaises(ResearchControlError):
                FixtureLedger.from_bytes(raw)

    def test_hashes_code_and_ids_are_strict(self):
        for digest in (True, "x" * 64, "a" * 63, "A" * 64):
            with self.assertRaises(ResearchControlError):
                FixtureEpoch(digest, "b" * 64, "c" * 64)
        for revision in (True, "c" * 63, "main", "C" * 64):
            with self.assertRaises(ResearchControlError):
                replace(self.epoch, code_sha256=revision)
        for run_id in (True, "real-run", "fixture-", "fixture-" + "a" * 49):
            with self.assertRaises(ResearchControlError):
                self.ledger.start(run_id, "base", "d" * 64)

    def test_all_external_actions_deny_even_old_dates(self):
        for action in ("provider", "outcomes", "qc_upload", "qc_launch", "capture", "paper", "live"):
            with self.subTest(action=action), self.assertRaisesRegex(ResearchControlError, "not authorized"):
                refuse_external_action(action, start=date(2024, 1, 1), end=date(2024, 12, 31))
        for end in (date(2026, 9, 1), date(2027, 9, 1), date(2029, 8, 31)):
            with self.assertRaisesRegex(ResearchControlError, "protected"):
                refuse_external_action("outcomes", start=date(2024, 1, 1), end=end)

    def test_windows_and_attempt_count_types_refuse(self):
        for start, end in ((date(2024, 1, 1), None), (True, True),
                           (datetime(2024, 1, 1), date(2024, 1, 2)),
                           (date(2024, 1, 2), date(2024, 1, 1))):
            with self.assertRaises(ResearchControlError):
                refuse_external_action("outcomes", start=start, end=end)
        for count in (True, -1, 4, 1.0):
            with self.assertRaises(ResearchControlError):
                qc_recovery_disposition(count)
        self.assertIn("Mia", qc_recovery_disposition(3))
        for count in (0, 1, 2):
            self.assertIn("requires_separate", qc_recovery_disposition(count))

    def test_capacity_boundary_and_failed_flag(self):
        ledger = self.ledger
        for i in range(32):
            ledger = ledger.start(f"fixture-{i}", "base", "a" * 64)
            ledger = ledger.finish(f"fixture-{i}", output_sha256="b" * 64)
        self.assertEqual(FixtureLedger.from_bytes(ledger.to_bytes()), ledger)
        with self.assertRaises(ResearchControlError):
            ledger.start("fixture-overflow", "base", "a" * 64)
        with self.assertRaises(ResearchControlError):
            self.ledger.finish("fixture-a", output_sha256="b" * 64, failed=1)


if __name__ == "__main__":
    unittest.main()
