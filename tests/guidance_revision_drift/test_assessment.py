from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
import unittest

from research.guidance_revision_drift.assessment import assess_candidate
from research.guidance_revision_drift.events import NormalizedDisclosure
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant
from research.guidance_revision_drift.timing import Availability


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.corpus = example_corpus()
        self.at = fixture_instant(date(2025, 4, 4), 10)

    def assess(self, **changes):
        args = dict(book=self.corpus.archive.book, disclosure_id="SYN-RAISE", as_of=self.at,
            schedule=self.corpus.schedule, permanent_security_id="SYN-SEC-A",
            references=self.corpus.references, bars=self.corpus.bars)
        args.update(changes)
        return assess_candidate(**args)

    def test_composed_event_clock_universe_passes_only_first_opportunity(self):
        result = self.assess()
        self.assertEqual(result.eligible_session, date(2025, 4, 4))
        self.assertEqual(result.adv20, Decimal("25000000"))
        self.assertEqual(result.candidate.disclosure_id, "SYN-RAISE")
        later = self.assess(as_of=fixture_instant(date(2025, 4, 7), 10))
        self.assertIsNone(later.eligible_session)
        self.assertIn("earlier_eligible_opportunity_was_missed", later.refusals[-1][1])

    def test_future_bar_and_reference_revisions_cannot_change_past_assessment(self):
        original = self.assess()
        future = self.at + timedelta(days=10)
        availability = Availability("history", future, future, future)
        prior = next(b for b in self.corpus.bars if b.session_date == date(2025, 4, 3))
        revision = replace(prior, raw_close=Decimal("1"), availability=availability)
        mapping = replace(self.corpus.references[0], issuer_id="SYN-OTHER", availability=availability)
        result = self.assess(bars=self.corpus.bars + (revision,), references=self.corpus.references + (mapping,))
        self.assertEqual(result, original)

    def test_future_withdrawal_is_not_seen_early_but_invalidates_after_receipt(self):
        body = self.corpus.archive.entries[-1][0].to_dict()
        body.update(disclosure_id="SYN-WITHDRAW", kind="withdrawal", supersedes="SYN-RAISE",
                    published_at="2025-04-07T12:00:00Z", received_at="2025-04-07T12:01:00Z",
                    validated_at="2025-04-07T12:02:00Z", periods=[])
        book = self.corpus.archive.book.ingest(NormalizedDisclosure.from_dict(body))
        self.assertEqual(self.assess(book=book), self.assess())
        self.assertIsNone(self.assess(book=book, as_of=fixture_instant(date(2025, 4, 7), 10)).candidate)

    def test_wrong_identity_missing_bar_and_late_receipt_are_retained(self):
        mapping = replace(self.corpus.references[0], issuer_id="SYN-OTHER")
        result = self.assess(references=(mapping,))
        self.assertIn("event_security_issuer_mismatch", result.refusals[0][1])
        bars = tuple(b for b in self.corpus.bars if b.session_date != date(2025, 4, 3))
        self.assertIsNone(self.assess(bars=bars).eligible_session)
        bars = tuple(replace(b, availability=Availability("history", b.availability.published_at,
            self.at, self.at)) if b.session_date == date(2025, 4, 3) else b for b in self.corpus.bars)
        self.assertIsNone(self.assess(bars=bars).eligible_session)

    def test_before_event_or_entry_no_backdating_and_corpus_hash_stable(self):
        self.assertIsNone(self.assess(as_of=fixture_instant(date(2025, 3, 31), 10)).candidate)
        self.assertIsNone(self.assess(as_of=fixture_instant(date(2025, 4, 3), 10)).eligible_session)
        self.assertEqual(self.corpus.sha256, example_corpus().sha256)


if __name__ == "__main__":
    unittest.main()
