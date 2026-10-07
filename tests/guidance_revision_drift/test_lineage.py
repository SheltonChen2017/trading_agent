"""Synthetic provider receipt replay, no capture/PIT or market-edge claims."""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from data.hashing import canonical_json
from research.guidance_revision_drift.lineage import LineageError, ProviderLineage
from research.guidance_revision_drift.vendor_payloads import parse_synthetic_guidance
from tests.guidance_revision_drift.test_vendor_payloads import context, observation, raw


def instant(value="2025-12-31T23:59:59+00:00"):
    return datetime.fromisoformat(value)


def raised_lineage():
    source = raw("SYN-D2", "2025-02-03", min_revenue_guidance=102000000, max_revenue_guidance=102000000)
    source = source.replace(b'"min_eps_guidance": 1', b'"min_eps_guidance": 1.05')
    source = source.replace(b'"max_eps_guidance": 1', b'"max_eps_guidance": 1.05')
    return ProviderLineage().append(observation(), bootstrap=True).append(
        parse_synthetic_guidance(source, context("SYN-D2", "2025-02-03")))


class ProviderLineageTests(unittest.TestCase):
    def test_archive_and_book_replay_only_validated_receipts(self):
        journal = raised_lineage()
        early = journal.as_of(instant("2025-02-03T12:01:59+00:00"))
        now = journal.as_of(instant("2025-02-03T12:02:00+00:00"))
        self.assertEqual(early.receipt_statuses, ("bootstrap",))
        self.assertEqual(now.receipt_statuses, ("bootstrap", "candidate"))
        self.assertEqual(journal.archive_as_of(instant()), now.archive)
        self.assertEqual(len(early.book.entries), 1)

    def test_chain_roundtrip_retains_raw_exact_bytes_and_context(self):
        journal = raised_lineage()
        restored = ProviderLineage.from_bytes(journal.to_bytes(), expected_head=journal.head_sha256)
        self.assertEqual(restored, journal)
        self.assertFalse(journal.to_dict()["point_in_time_data"])
        projection = journal.to_dict()
        projection["receipts"].clear()
        self.assertEqual(len(journal.receipts), 2)

    def test_later_duplicate_retains_receipt_but_preserves_original_capture(self):
        journal = raised_lineage()
        current = journal.receipts[-1][0]
        duplicate_context = current.context.to_dict()
        duplicate_context.update(received_at="2025-02-04T12:01:00Z", validated_at="2025-02-04T12:02:00Z")
        from research.guidance_revision_drift.vendor_payloads import SyntheticGuidanceContext
        journal2 = journal.append(parse_synthetic_guidance(current.raw_bytes,
                                  SyntheticGuidanceContext.from_dict(duplicate_context)))
        replay = journal2.as_of(instant())
        self.assertEqual(replay.receipt_statuses, ("bootstrap", "candidate", "duplicate_delivery"))
        self.assertEqual(replay.archive, journal.as_of(instant()).archive)
        self.assertEqual(len(journal2.receipts), 3)
        self.assertNotEqual(journal2.head_sha256, journal.head_sha256)
        self.assertNotEqual(replay.observation_sha256s[-1], replay.observation_sha256s[-2])

    def test_conflicting_same_version_is_retained_and_invalidates_candidate(self):
        journal = raised_lineage().append(observation("SYN-D2", "2025-02-03",
            changes={"notes": "invented conflicting delivery"},
            context_changes={"received_at": "2025-02-04T12:01:00Z", "validated_at": "2025-02-04T12:02:00Z"}))
        replay = journal.as_of(instant())
        self.assertEqual(replay.receipt_statuses[-1], "quarantined")
        self.assertEqual(replay.book.decisions[-1].invalidated_disclosure_ids, ("SYN-D2",))
        self.assertEqual(len(journal.receipts), 3)

    def test_version_gaps_quarantine_without_guessing_missing_receipts(self):
        journal = raised_lineage().append(observation("SYN-D2", "2025-02-03",
            context_changes={"version": 3, "received_at": "2025-02-04T12:01:00Z", "validated_at": "2025-02-04T12:02:00Z"}))
        self.assertEqual(journal.as_of(instant()).receipt_statuses[-1], "quarantined")

    def test_metadata_version_does_not_create_new_candidate(self):
        journal = raised_lineage()
        previous = journal.receipts[-1][0]
        source = previous.raw_bytes[:-1] + b', "notes": "invented metadata edit"}'
        ctx = previous.context.to_dict()
        ctx.update(version=2, received_at="2025-02-04T12:01:00Z", validated_at="2025-02-04T12:02:00Z")
        from research.guidance_revision_drift.vendor_payloads import SyntheticGuidanceContext
        replay = journal.append(parse_synthetic_guidance(source, SyntheticGuidanceContext.from_dict(ctx))).as_of(instant())
        self.assertEqual(replay.receipt_statuses[-1], "metadata_edit")

    def test_correction_invalidates_and_can_be_later_captured_predecessor(self):
        journal = raised_lineage().append(observation("SYN-D1", "2025-02-04",
            context_changes={"version": 2, "kind": "correction", "supersedes": "SYN-D1"}))
        corrected = journal.as_of(instant())
        self.assertEqual(corrected.receipt_statuses[-1], "correction")
        self.assertEqual(corrected.book.decisions[-1].invalidated_disclosure_ids, ("SYN-D2",))
        # Correcting D1 only invalidates a decision; it never itself creates one.
        self.assertIsNone(corrected.book.decisions[-1].candidate)
        # A later correction of the latest original becomes its effective
        # predecessor for a genuinely later management disclosure.
        journal = journal.append(observation("SYN-D2", "2025-02-05",
            context_changes={"version": 2, "kind": "correction", "supersedes": "SYN-D2"}))
        later = raised_lineage().receipts[-1][0]
        source = later.raw_bytes.replace(b"SYN-D2", b"SYN-D3").replace(b"2025-02-03", b"2025-02-06")
        journal = journal.append(parse_synthetic_guidance(source, context("SYN-D3", "2025-02-06")))
        decision = journal.as_of(instant()).book.decisions[-1]
        self.assertEqual(decision.disposition, "candidate")
        self.assertEqual(decision.candidate.previous.to_dict()["kind"], "correction")

    def test_withdrawal_is_explicit_and_blocks_later_predecessor_use(self):
        source = b'{"benzinga_id":"SYN-D2","ticker":"SYN-TICKER-A","date":"2025-02-04","time":"07:00:00","last_updated":"2025-02-04T12:00:00Z"}'
        withdrawn = parse_synthetic_guidance(source, context("SYN-D2", "2025-02-04", version=2,
                                                kind="withdrawal", supersedes="SYN-D2"))
        journal = raised_lineage().append(withdrawn).append(observation("SYN-D3", "2025-02-05"))
        replay = journal.as_of(instant())
        self.assertEqual(replay.receipt_statuses[-2], "withdrawal")
        self.assertIn("immediate_predecessor_withdrawn", replay.book.decisions[-1].refusal_reasons)

    def test_zero_revenue_cut_is_risk_information_not_dropped_by_parser(self):
        journal = raised_lineage().append(observation("SYN-CUT", "2025-02-04",
            changes={"min_revenue_guidance": 0, "max_revenue_guidance": 0}))
        last = journal.as_of(instant()).book.decisions[-1]
        self.assertIsNone(last.candidate)
        self.assertEqual(last.invalidated_disclosure_ids, ("SYN-D2",))

    def test_delayed_publication_receipt_never_reorders_original_history(self):
        journal = raised_lineage().append(observation("SYN-LATE", "2025-01-03",
            context_changes={"received_at": "2025-02-04T12:01:00Z", "validated_at": "2025-02-04T12:02:00Z"}))
        self.assertIn("simultaneous_or_late_discovered_disclosure", journal.as_of(instant()).book.decisions[-1].refusal_reasons)
        self.assertEqual(journal.as_of(instant("2025-02-03T23:59:59+00:00")), raised_lineage().as_of(instant()))

    def test_out_of_order_validation_and_bad_cutoff_refuse(self):
        with self.assertRaisesRegex(LineageError, "validation_receipt_order"):
            raised_lineage().append(observation("SYN-EARLY", "2025-01-04"))
        for cutoff in (datetime(2025, 1, 1), datetime(2026, 1, 1, tzinfo=timezone.utc), "2025-01-01"):
            with self.subTest(cutoff=cutoff), self.assertRaises(LineageError):
                raised_lineage().as_of(cutoff)

    def test_tied_validation_preserves_explicit_sequence_and_cannot_rebootstrap(self):
        journal = raised_lineage()
        duplicate = journal.receipts[-1][0]
        replay = journal.append(duplicate).as_of(instant())
        self.assertEqual(replay.receipt_statuses[-1], "duplicate_delivery")
        with self.assertRaises(LineageError):
            journal.append(duplicate, bootstrap=True)
        with self.assertRaises(LineageError):
            ProviderLineage().append(observation(), bootstrap=1)

    def test_permanent_identity_remap_retains_receipt_but_refuses_projection(self):
        journal = raised_lineage().append(observation("SYN-D2", "2025-02-03",
            context_changes={"version": 2, "security_id": "SYN-SEC-OTHER",
                "received_at": "2025-02-04T12:01:00Z", "validated_at": "2025-02-04T12:02:00Z"}))
        self.assertEqual(len(journal.receipts), 3)
        with self.assertRaisesRegex(LineageError, "permanent_identity_remap"):
            journal.as_of(instant())
        self.assertEqual(journal.as_of(instant("2025-02-03T23:59:59+00:00")).receipt_statuses[-1], "candidate")

    def test_chain_tampering_truncation_and_false_pit_refuse(self):
        journal = raised_lineage()
        for mutation in (lambda v: v["receipts"].pop(), lambda v: v["receipts"].reverse(),
                         lambda v: v.update(point_in_time_data=True),
                         lambda v: v["receipts"][0].update(sequence=True),
                         lambda v: v["receipts"][1].update(previous_sha256="0" * 64),
                         lambda v: v["receipts"][0].update(raw_sha256="0" * 64),
                         lambda v: v["receipts"][0].update(raw_hex="00"),
                         lambda v: v["receipts"][0]["context"].update(issuer_id="SYN-OTHER")):
            values = copy.deepcopy(journal.to_dict())
            mutation(values)
            with self.subTest(values=values), self.assertRaises(LineageError):
                ProviderLineage.from_bytes(canonical_json(values).encode(), expected_head=journal.head_sha256)
        with self.assertRaises(LineageError):
            ProviderLineage.from_bytes(journal.to_bytes(), expected_head="0" * 64)

    def test_forged_mutable_input_cannot_rewrite_a_retained_journal(self):
        source = observation()
        journal = ProviderLineage().append(source, bootstrap=True)
        old_head = journal.head_sha256
        object.__setattr__(source, "raw_bytes", b"{}")
        self.assertEqual(journal.head_sha256, old_head)
        with self.assertRaises(LineageError):
            journal.append(source)

    def test_checkpoint_type_cannot_override_comparison(self):
        class Anything:
            def __eq__(self, other):
                return True
        journal = raised_lineage()
        with self.assertRaises(LineageError):
            ProviderLineage.from_bytes(journal.to_bytes(), expected_head=Anything())

    def test_raw_journal_has_bounded_size_and_receipt_count(self):
        item = observation()
        with self.assertRaises(LineageError):
            ProviderLineage(((item, False),) * 129)
        with self.assertRaises(LineageError):
            ProviderLineage.from_bytes(b" " * 12_582_913, expected_head="0" * 64)


if __name__ == "__main__":
    unittest.main()
