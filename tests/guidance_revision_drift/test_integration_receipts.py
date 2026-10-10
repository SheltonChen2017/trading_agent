"""Receipt availability at the fixed synthetic decision stream, not capture."""
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data.hashing import canonical_json
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant
from research.guidance_revision_drift.integration import fixture_lineage, run_integrated_fixture
from research.guidance_revision_drift.lineage import ProviderLineage
from research.guidance_revision_drift.persistence import LocalJournal
from research.guidance_revision_drift.reporting import source_manifest
from research.guidance_revision_drift.timing import NY
from research.guidance_revision_drift.vendor_payloads import (
    SyntheticGuidanceContext, parse_synthetic_guidance,
)


def delayed_fixture_lineage():
    """Invented unrelated issuers leave the original strategy economics alone."""
    original = fixture_lineage()
    template = original.receipts[0][0]
    receipts = list(original.receipts)
    for identity, published, received, validated in (
        # Friday night New York / Saturday UTC: no decision until Monday.
        ("SYN-NIGHT", "2025-03-08T04:30:00Z", "2025-03-08T04:31:00Z", "2025-03-08T04:32:00Z"),
        ("SYN-WEEKEND", "2025-03-08T17:00:00Z", "2025-03-09T12:00:00Z", "2025-03-09T12:01:00Z"),
        # Old publication dates cannot backdate these later captures. The two
        # equal validation clocks must retain receipt order, not publication order.
        ("SYN-DELAYED", "2025-03-06T12:00:00Z", "2025-03-10T13:59:59Z", "2025-03-10T14:00:00Z"),
        ("SYN-TIED", "2025-03-05T12:00:00Z", "2025-03-10T13:59:59Z", "2025-03-10T14:00:00Z"),
        ("SYN-AFTER-DECISION", "2025-03-10T12:00:00Z", "2025-03-10T14:00:00Z", "2025-03-10T14:00:01Z"),
        # There is no subsequent decision in this bounded recipe.
        ("SYN-AFTER-FINAL", "2025-05-15T12:00:00Z", "2025-05-15T15:00:00Z", "2025-05-15T15:01:00Z"),
    ):
        local = datetime.fromisoformat(published).astimezone(NY)
        context = template.context.to_dict()
        context.update(provider_id=identity, issuer_id=identity + "-ISSUER", security_id=identity + "-SEC",
                       published_at=published, received_at=received, validated_at=validated)
        payload = json.loads(template.raw_bytes)
        payload.update(benzinga_id=identity, date=local.date().isoformat(),
                       time=local.time().isoformat(), last_updated=published)
        receipts.append((parse_synthetic_guidance(canonical_json(payload).encode(),
                                                 SyntheticGuidanceContext.from_dict(context)), False))
    # A later exact redelivery is retained by provider lineage, but may not
    # reset the first receipt clocks or create another normalized event.
    raised = original.receipts[1][0]
    context = raised.context.to_dict()
    context.update(received_at="2025-04-02T12:01:00Z", validated_at="2025-04-02T12:02:00Z")
    receipts.append((parse_synthetic_guidance(raised.raw_bytes, SyntheticGuidanceContext.from_dict(context)), False))
    return ProviderLineage(tuple(sorted(receipts, key=lambda item: item[0].validated_at)))


class IntegrationReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lineage = delayed_fixture_lineage()
        manifest = source_manifest()
        with patch("research.guidance_revision_drift.integration.source_manifest", return_value=manifest):
            with TemporaryDirectory(prefix="gdr-receipt-baseline-") as directory:
                cls.baseline = run_integrated_fixture(Path(directory))
            with TemporaryDirectory(prefix="gdr-receipt-order-") as directory, patch(
                    "research.guidance_revision_drift.integration.fixture_lineage", return_value=cls.lineage):
                cls.report = run_integrated_fixture(Path(directory))
                store = LocalJournal.open(Path(directory),
                    expected_genesis_sha256=cls.report["state"]["genesis_sha256"])
                cls.commands = tuple(row.to_dict() for row in store.read(
                    expected_head=cls.report["journal_head_sha256"]).records)

    def test_first_available_decision_not_publication_date_controls_durable_order(self):
        # The next close proves which decision iteration wrote each event;
        # this checks the durable command chain, not a mocked execute call.
        observed = []
        for index, command in enumerate(self.commands):
            if command["operation"] == "event_ingest":
                next_close = next(row for row in self.commands[index + 1:] if row["operation"] == "close_session")
                observed.append((command["arguments"]["record"]["disclosure_id"],
                                 next_close["arguments"]["session"]))
        self.assertEqual(observed, [
            ("SYN-OLD", "2025-03-03"),
            ("SYN-NIGHT", "2025-03-10"),
            ("SYN-WEEKEND", "2025-03-10"),
            ("SYN-DELAYED", "2025-03-10"),
            ("SYN-TIED", "2025-03-10"),
            ("SYN-AFTER-DECISION", "2025-03-11"),
            ("SYN-RAISE", "2025-04-01"),
        ])

    def test_archive_exactly_matches_visible_first_receipts_without_duplicates_or_future_events(self):
        last_decision = fixture_instant(example_corpus().schedule.sessions[-1].session_date, 10)
        expected = self.lineage.as_of(last_decision).archive
        ingested = [row for row in self.commands if row["operation"] == "event_ingest"]
        self.assertEqual(len(ingested), 7)
        self.assertEqual([row["result"]["observations"] for row in ingested], list(range(1, 8)))
        self.assertEqual([(row["arguments"]["record"], row["arguments"]["bootstrap"]) for row in ingested],
                         [(record.to_dict(), bootstrap) for record, bootstrap in expected.entries])
        self.assertEqual(self.report["state"]["event_count"], 7)
        self.assertEqual(self.report["state"]["archive_head"], expected.head_sha256)
        self.assertEqual(len(self.report["provider_observation_hashes"]), 9)
        self.assertEqual(self.report["command_count"], self.baseline["command_count"] + 5)
        self.assertTrue(self.report["midrun_recovery_performed"])
        self.assertTrue(self.report["final_recovery_exact"])

    def test_original_daytime_actions_economics_and_calendar_are_unchanged(self):
        for name in ("strategy", "comparator"):
            self.assertEqual(self.report["state"][name], self.baseline["state"][name])
        self.assertEqual(self.report["paired_daily_nav"], self.baseline["paired_daily_nav"])
        self.assertEqual(self.report["eligibility_session"], "2025-04-04")
        self.assertEqual(len(self.report["paired_daily_nav"]), 93)
        self.assertEqual(len(self.report["state"]["strategy"]["fills"]), 3)
        self.assertFalse(self.report["state"]["strategy"]["completion_blocked"])
        self.assertFalse(self.report["state"]["comparator"]["study_completion_blocked"])


if __name__ == "__main__":
    unittest.main()
