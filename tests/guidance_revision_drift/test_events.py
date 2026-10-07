"""Synthetic 2024/2025 guidance replay; no provider data or return evidence."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal

from research.guidance_revision_drift.events import (
    EventBook, EventCandidate, EventDecision, EventError, NormalizedDisclosure,
)


def period(revenue="100", eps="1", *, year=2025, **changes):
    values = {"fiscal_year": year, "fiscal_start": f"{year}-01-01", "fiscal_end": f"{year}-12-31",
        "period": "FY", "currency": "USD", "revenue_units": "USD_millions", "eps_units": "USD_per_share",
        "revenue_basis": "gaap", "eps_basis": "adj", "adjustment_definition": "adj-v1",
        "share_basis": "shares-v1", "scope": "organic-v1",
        "revenue": {"lower": revenue, "upper": revenue, "kind": "point"},
        "eps": {"lower": eps, "upper": eps, "kind": "point"}}
    values.update(changes)
    return values


def payload(identity="SYN-D1", *, day="2025-01-02", revenue="100", eps="1", **changes):
    values = {"schema": "gdr.synthetic.disclosure.v1", "issuer_id": "SYN-ISSUER-A",
        "disclosure_id": identity, "version": 1, "kind": "disclosure", "published_at": f"{day}T12:00:00Z",
        "received_at": f"{day}T12:01:00Z", "validated_at": f"{day}T12:02:00Z", "supersedes": None,
        "release_type": "official", "positioning": "primary", "periods": [period(revenue, eps)],
        "metadata": "synthetic example only"}
    values.update(changes)
    return values


def record(*args, **kwargs):
    return NormalizedDisclosure.from_dict(payload(*args, **kwargs))


def raised_book():
    return EventBook().ingest(record(), bootstrap=True).ingest(
        record("SYN-D2", day="2025-02-03", revenue="102", eps="1.05"))


class NormalizedDisclosureTests(unittest.TestCase):
    def test_roundtrip_and_caller_mutation_cannot_change_bytes(self):
        values = payload()
        normalized = NormalizedDisclosure.from_dict(values)
        original = normalized.canonical_bytes
        values["periods"][0]["revenue"]["lower"] = "0"
        projection = normalized.to_dict()
        projection["periods"].clear()
        self.assertEqual(normalized.canonical_bytes, original)
        self.assertEqual(NormalizedDisclosure.from_bytes(original), normalized)
        with self.assertRaises(FrozenInstanceError):
            normalized.canonical_bytes = b"{}"

    def test_unknown_approval_pit_and_non_synthetic_identity_refuse(self):
        for changes in ({"approved": True}, {"point_in_time_data": True}, {"issuer_id": "AAPL"},
                        {"schema": "gdr.real.disclosure.v1"}, {"version": True}, {"version": 1.0}):
            with self.subTest(changes=changes), self.assertRaises(EventError):
                record(**changes)

    def test_clock_order_timezone_canonicality_and_protected_dates_refuse(self):
        for value in ("2025-01-02", "2025-01-02T12:00:00", "2025-01-02T12:00:00+00:00",
                      "2025-02-30T12:00:00Z", "2026-09-01T12:00:00Z", True):
            with self.subTest(value=value), self.assertRaises(EventError):
                record(published_at=value)
        for changes in ({"received_at": "2025-01-02T11:00:00Z"},
                        {"validated_at": "2025-01-02T12:00:30Z"}):
            with self.subTest(changes=changes), self.assertRaises(EventError):
                record(**changes)

    def test_strict_json_duplicate_float_encoding_and_resource_refusals(self):
        for raw in (b'{"schema":1,"schema":2}', b'{"version":1.0}', b'{"bad":NaN}', b"\xff", b"{}" * 20_000,
                    b"[" * 2000 + b"]" * 2000, bytearray(b"{}"), b"\xef\xbb\xbf{}"):
            with self.subTest(raw_type=type(raw)), self.assertRaises(EventError):
                NormalizedDisclosure.from_bytes(raw)

    def test_missing_inverted_nonfinite_unbounded_and_implicit_point_ranges_refuse(self):
        for interval in ({"lower": "1", "upper": "1", "kind": "range"},
                         {"lower": "1", "upper": "2", "kind": "point"},
                         {"lower": "2", "upper": "1", "kind": "range"},
                         {"lower": "1", "kind": "point"},
                         {"lower": "NaN", "upper": "1", "kind": "range"},
                         {"lower": 1.0, "upper": "2", "kind": "range"},
                         {"lower": "1e100", "upper": "1e100", "kind": "point"},
                         {"lower": "1" * 129, "upper": "1" * 129, "kind": "point"}):
            with self.subTest(interval=interval), self.assertRaises(EventError):
                current = period()
                current["revenue"] = interval
                record(periods=[current])

    def test_period_duplicate_identity_bad_dates_unknown_fields_and_boolean_year_refuse(self):
        for periods in ([period(), period()], [period(year=True)],
                        [period(fiscal_start="2025-12-31")], [period(extra="bad")]):
            with self.subTest(periods=periods), self.assertRaises(EventError):
                record(periods=periods)

    def test_forged_objects_are_revalidated_and_nested_objects_are_copied(self):
        original = record()
        book = EventBook().ingest(original, bootstrap=True)
        object.__setattr__(original, "canonical_bytes", b"{}")
        self.assertEqual(book.decisions[0].disposition, "bootstrap")
        with self.assertRaises(EventError):
            book.ingest(original)
        forged = raised_book()
        object.__setattr__(forged, "entries", ((record(), 1),))
        with self.assertRaises(EventError):
            _ = forged.decisions


class EventReplayTests(unittest.TestCase):
    def test_bootstrap_then_exact_boundary_creates_only_synthetic_candidate(self):
        book = raised_book()
        self.assertEqual([item.disposition for item in book.decisions], ["bootstrap", "candidate"])
        candidate = book.decisions[-1].candidate
        self.assertEqual(candidate.disclosure_id, "SYN-D2")
        self.assertEqual(candidate.issuer_id, "SYN-ISSUER-A")
        self.assertEqual(candidate.arithmetic.revenue_revision_fraction, Decimal("0.02"))
        self.assertTrue(candidate.arithmetic.passes_arithmetic)
        self.assertFalse(hasattr(candidate, "order_authorized"))
        self.assertEqual(candidate.previous_period.revenue.lower, Decimal("100"))

    def test_explicit_two_ended_ranges_match_synthetic_plan_example(self):
        old, new = period(), period()
        old.update(revenue={"lower": "980", "upper": "1020", "kind": "range"},
                   eps={"lower": "2", "upper": "2.2", "kind": "range"})
        new.update(revenue={"lower": "1030", "upper": "1070", "kind": "range"},
                   eps={"lower": "2.2", "upper": "2.4", "kind": "range"})
        result = EventBook().ingest(record(periods=[old]), bootstrap=True).ingest(
            record("SYN-D2", day="2025-02-03", periods=[new])).decisions[-1]
        self.assertTrue(result.candidate.arithmetic.passes_arithmetic)
        self.assertEqual(result.candidate.arithmetic.revenue_revision_fraction, Decimal("0.05"))

    def test_decision_fields_are_strict_deep_immutable_and_source_bound(self):
        decision = raised_book().decisions[-1]
        candidate = decision.candidate
        copied = EventDecision(decision.record_sha256, "candidate", candidate=candidate)
        object.__setattr__(candidate, "current", record())
        self.assertEqual(copied.candidate.disclosure_id, "SYN-D2")
        for arguments in (
            {"record_sha256": "bad", "disposition": "refused"},
            {"record_sha256": "0" * 64, "disposition": "refused", "refusal_reasons": []},
            {"record_sha256": "0" * 64, "disposition": "refused", "invalidated_disclosure_ids": ["SYN-D2"]},
            {"record_sha256": "0" * 64, "disposition": "candidate", "candidate": copied.candidate},
            {"record_sha256": "0" * 64, "disposition": "candidate"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(EventError):
                EventDecision(**arguments)

    def test_initial_corpus_cannot_manufacture_new_signals(self):
        book = EventBook().ingest(record(), bootstrap=True).ingest(
            record("SYN-D2", day="2025-02-03", revenue="200", eps="2"), bootstrap=True)
        self.assertTrue(all(item.candidate is None for item in book.decisions))
        with self.assertRaisesRegex(EventError, "initial contiguous"):
            raised_book().ingest(record("SYN-D3", day="2025-03-03"), bootstrap=True)

    def test_duplicate_and_metadata_versions_do_not_create_second_candidate(self):
        book = raised_book()
        raised = book.entries[-1][0]
        duplicated = book.ingest(raised)
        self.assertEqual(duplicated.decisions[-1].disposition, "duplicate")
        metadata = raised.to_dict()
        metadata.update(version=2, metadata="updated descriptive note", received_at="2025-02-04T12:00:00Z",
                        validated_at="2025-02-04T12:01:00Z")
        edited = duplicated.ingest(NormalizedDisclosure.from_dict(metadata))
        self.assertEqual(edited.decisions[-1].disposition, "metadata_edit")
        self.assertEqual(sum(item.candidate is not None for item in edited.decisions), 1)

    def test_conflicting_duplicate_quarantines_and_invalidates_without_rewriting(self):
        book = raised_book()
        conflict = record("SYN-D2", day="2025-02-03", revenue="300", eps="3")
        changed = book.ingest(conflict)
        self.assertEqual(changed.decisions[1], book.decisions[1])
        self.assertEqual(changed.decisions[-1].disposition, "quarantined")
        self.assertEqual(changed.decisions[-1].invalidated_disclosure_ids, ("SYN-D2",))
        later = changed.ingest(record("SYN-D3", day="2025-03-03", revenue="400", eps="4"))
        self.assertIn("issuer_quarantined", later.decisions[-1].refusal_reasons)

    def test_unmarked_economic_edit_and_missing_version_quarantine(self):
        for changes in ({"version": 2, "periods": [period("110", "1.1")]}, {"version": 3}):
            values = raised_book().entries[-1][0].to_dict()
            values.update(changes)
            result = raised_book().ingest(NormalizedDisclosure.from_dict(values)).decisions[-1]
            self.assertEqual(result.disposition, "quarantined")

    def test_ticker_like_identity_reuse_cannot_cross_issuers(self):
        book = raised_book()
        values = book.entries[-1][0].to_dict()
        values.update(issuer_id="SYN-ISSUER-B", version=2)
        result = book.ingest(NormalizedDisclosure.from_dict(values)).decisions[-1]
        self.assertEqual(result.disposition, "quarantined")
        self.assertEqual(result.invalidated_disclosure_ids, ("SYN-D2",))
        independent = EventBook().ingest(record(), bootstrap=True).ingest(
            record("SYN-B1", day="2025-02-03", issuer_id="SYN-ISSUER-B", revenue="200", eps="2"))
        self.assertEqual(independent.decisions[-1].disposition, "baseline")

    def test_nearest_unexpired_fy_is_chosen_once(self):
        old = record(day="2024-06-03", periods=[period("100", "1", year=2024), period("100", "1", year=2025)])
        new = record("SYN-D2", day="2024-07-03", periods=[period("102", "1.05", year=2024), period("200", "2", year=2025)])
        result = EventBook().ingest(old, bootstrap=True).ingest(new).decisions[-1]
        self.assertEqual(result.candidate.current_period.fiscal_year, 2024)
        # In 2025 the expired 2024 period is not selected despite a larger raise.
        later = record("SYN-D3", day="2025-01-03", periods=[period("999", "9", year=2024), period("204", "2.1", year=2025)])
        result = EventBook().ingest(old, bootstrap=True).ingest(new).ingest(later).decisions[-1]
        self.assertEqual(result.candidate.current_period.fiscal_year, 2025)

    def test_nearest_fy_failure_does_not_fall_back_to_further_year_success(self):
        old = record(day="2024-06-03", periods=[period(year=2024), period(year=2025)])
        new = record("SYN-D2", day="2024-07-03", periods=[period("101", "1", year=2024), period("200", "2", year=2025)])
        result = EventBook().ingest(old, bootstrap=True).ingest(new).decisions[-1]
        self.assertIsNone(result.candidate)
        self.assertIn("revenue_raise_threshold_not_met", result.refusal_reasons)

    def test_changed_immediate_predecessor_never_cherry_picks_older_comparable(self):
        middle = record("SYN-D2", day="2025-02-03", periods=[period("100", "1", share_basis="split-v2")])
        current = record("SYN-D3", day="2025-03-03", revenue="110", eps="1.1")
        result = EventBook().ingest(record(), bootstrap=True).ingest(middle).ingest(current).decisions[-1]
        self.assertIsNone(result.candidate)
        self.assertIn("changed_share_basis", result.refusal_reasons)

    def test_all_economic_comparability_axes_refuse(self):
        for field, value in (("currency", "EUR"), ("revenue_units", "USD_units"), ("eps_units", "cents"),
                             ("revenue_basis", "non_gaap"), ("eps_basis", "gaap"), ("share_basis", "split-v2"),
                             ("adjustment_definition", "adj-v2"), ("scope", "acquisition-v2"),
                             ("fiscal_start", "2025-01-02"), ("fiscal_end", "2025-12-30")):
            with self.subTest(field=field):
                changed = record("SYN-D2", day="2025-02-03", periods=[period("110", "1.1", **{field: value})])
                result = EventBook().ingest(record(), bootstrap=True).ingest(changed).decisions[-1]
                self.assertIsNone(result.candidate)
                self.assertIn("changed_" + field, result.refusal_reasons)

    def test_unsupported_primary_period_and_fiscal_transition_are_explicit(self):
        for changes, expected in (({"positioning": "secondary"}, "not_primary_guidance"),
                                  ({"periods": [period("110", "1.1", period="Q1")]}, "no_unexpired_full_year"),
                                  ({"periods": [period("110", "1.1", year=2026)]}, "no_same_period_predecessor")):
            result = EventBook().ingest(record(), bootstrap=True).ingest(
                record("SYN-D2", day="2025-02-03", **changes)).decisions[-1]
            self.assertIn(expected, result.refusal_reasons)

    def test_predecessor_recorded_after_publication_is_not_pit_by_assertion(self):
        prior = record(received_at="2025-02-03T12:00:00Z", validated_at="2025-02-03T12:00:00Z")
        result = EventBook().ingest(prior, bootstrap=True).ingest(
            record("SYN-D2", day="2025-02-03", revenue="110", eps="1.1")).decisions[-1]
        self.assertIn("predecessor_not_captured_before_disclosure", result.refusal_reasons)

    def test_late_backfill_does_not_replace_baseline(self):
        late = record("SYN-LATE", day="2025-01-01", revenue="1", eps="0.5",
            received_at="2025-02-04T12:00:00Z", validated_at="2025-02-04T12:01:00Z")
        book = raised_book().ingest(late)
        self.assertIn("simultaneous_or_late_discovered_disclosure", book.decisions[-1].refusal_reasons)
        next_book = book.ingest(record("SYN-D3", day="2025-03-03", revenue="104.04", eps="1.1025"))
        self.assertEqual(next_book.decisions[-1].candidate.previous.disclosure_id, "SYN-D2")

    def test_simultaneous_disclosures_with_distinct_ids_quarantine_first_candidate(self):
        ambiguous = record("SYN-SECOND-ID", day="2025-02-03", revenue="103", eps="1.1",
            received_at="2025-02-04T12:00:00Z", validated_at="2025-02-04T12:01:00Z")
        book = raised_book().ingest(ambiguous)
        self.assertEqual(book.decisions[-1].disposition, "quarantined")
        self.assertEqual(book.decisions[-1].invalidated_disclosure_ids, ("SYN-D2",))
        next_book = book.ingest(record("SYN-D3", day="2025-03-03", revenue="110", eps="1.2"))
        self.assertIn("issuer_quarantined", next_book.decisions[-1].refusal_reasons)

    def test_correction_withdrawal_and_post_cutoff_receipt_only_invalidate(self):
        for kind in ("correction", "withdrawal"):
            changes = {"kind": kind, "supersedes": "SYN-D2", "revenue": "200", "eps": "2"}
            if kind == "withdrawal":
                changes["periods"] = []
            correction = record("SYN-C1", day="2025-02-04", **changes)
            book = raised_book().ingest(correction)
            self.assertEqual(book.decisions[-1].disposition, kind)
            self.assertIsNone(book.decisions[-1].candidate)
            self.assertEqual(book.decisions[-1].invalidated_disclosure_ids, ("SYN-D2",))
            self.assertEqual(book.decisions[1].candidate.disclosure_id, "SYN-D2")

    def test_correction_of_predecessor_cancels_dependent_candidate(self):
        corrected = record("SYN-C1", day="2025-02-04", kind="correction", supersedes="SYN-D1", revenue="200", eps="2")
        result = raised_book().ingest(corrected).decisions[-1]
        self.assertEqual(result.invalidated_disclosure_ids, ("SYN-D2",))

    def test_same_identity_explicit_correction_retains_original_and_never_reissues(self):
        corrected = record("SYN-D2", day="2025-02-04", version=2, kind="correction",
                           supersedes="SYN-D2", revenue="110", eps="1.1")
        book = raised_book().ingest(corrected)
        self.assertEqual(book.decisions[-1].disposition, "correction")
        self.assertIsNone(book.decisions[-1].candidate)
        self.assertEqual(book.decisions[-1].invalidated_disclosure_ids, ("SYN-D2",))
        self.assertEqual(book.decisions[1].candidate.current_period.revenue.lower, Decimal("102"))

    def test_unknown_wrong_issuer_or_prepublication_correction_refuses(self):
        for changes in ({"supersedes": "SYN-NOT-FOUND"}, {"issuer_id": "SYN-OTHER"},
                        {"published_at": "2025-02-03T11:00:00Z"}):
            values = {"kind": "correction", "supersedes": "SYN-D2", **changes}
            result = raised_book().ingest(record("SYN-C1", day="2025-02-04", **values)).decisions[-1]
            self.assertEqual(result.disposition, "refused")
            self.assertEqual(result.invalidated_disclosure_ids, ())

    def test_corrected_predecessor_is_used_and_withdrawn_predecessor_not_skipped(self):
        correction = record("SYN-C1", day="2025-02-04", kind="correction", supersedes="SYN-D2", revenue="110", eps="1.1")
        book = raised_book().ingest(correction).ingest(record("SYN-D3", day="2025-03-03", revenue="112.2", eps="1.155"))
        self.assertEqual(book.decisions[-1].candidate.previous.disclosure_id, "SYN-C1")
        withdrawal = record("SYN-W1", day="2025-02-04", kind="withdrawal", supersedes="SYN-D2", periods=[])
        result = raised_book().ingest(withdrawal).ingest(record("SYN-D3", day="2025-03-03", revenue="200", eps="2")).decisions[-1]
        self.assertIn("immediate_predecessor_withdrawn", result.refusal_reasons)

    def test_comparable_midpoint_cut_invalidates_existing_candidate(self):
        for revenue, eps in (("101", "1.1"), ("103", "1.04")):
            result = raised_book().ingest(record("SYN-D3", day="2025-03-03", revenue=revenue, eps=eps)).decisions[-1]
            self.assertEqual(result.invalidated_disclosure_ids, ("SYN-D2",))
            self.assertIsNone(result.candidate)

    def test_incomparable_entry_predecessor_does_not_suppress_comparable_risk_cut(self):
        middle = record("SYN-D3", day="2025-03-03", periods=[period("105", "1.1", scope="acquisition-v2")])
        later = record("SYN-D4", day="2025-04-03", revenue="101", eps="1.1")
        result = raised_book().ingest(middle).ingest(later).decisions[-1]
        self.assertIn("changed_scope", result.refusal_reasons)
        self.assertEqual(result.invalidated_disclosure_ids, ("SYN-D2",))

    def test_later_published_cut_invalidates_delayed_receipt_raise_without_granting_entry(self):
        raised = record("SYN-D2", day="2025-04-01", revenue="102", eps="1.05",
                        received_at="2025-04-03T12:00:00Z", validated_at="2025-04-03T12:01:00Z")
        cut = record("SYN-D3", day="2025-04-02", revenue="101", eps="1.05",
                     received_at="2025-04-03T13:00:00Z", validated_at="2025-04-03T13:01:00Z")
        book = EventBook().ingest(record(), bootstrap=True).ingest(raised)
        original_decision = book.decisions[-1]
        self.assertEqual(original_decision.disposition, "candidate")
        updated = book.ingest(cut)
        # Publication ordering and economic comparability still apply. But
        # the old raise's delayed capture cannot hide a later known risk cut.
        result = updated.decisions[-1]
        self.assertEqual(result.invalidated_disclosure_ids, ("SYN-D2",))
        self.assertIsNone(result.candidate)
        self.assertIn("predecessor_not_captured_before_disclosure", result.refusal_reasons)
        self.assertEqual(updated.decisions[-2], original_decision)

    def test_fiscal_year_rollover_does_not_suppress_old_period_risk_cut(self):
        old = record(day="2024-06-03", periods=[period(year=2024)])
        raised = record("SYN-D2", day="2024-07-03", periods=[period("102", "1.05", year=2024)])
        rollover = record("SYN-D3", day="2025-01-03", periods=[period("101", "1.05", year=2024), period(year=2025)])
        result = EventBook().ingest(old, bootstrap=True).ingest(raised).ingest(rollover).decisions[-1]
        self.assertEqual(result.disposition, "baseline")
        self.assertEqual(result.invalidated_disclosure_ids, ("SYN-D2",))

    def test_nearest_fy_uses_new_york_announcement_date_not_utc_date(self):
        old = record(day="2024-11-03", periods=[period(year=2024)])
        new = record("SYN-D2", day="2025-01-01", published_at="2025-01-01T01:00:00Z",
            periods=[period("102", "1.05", year=2024), period("200", "2", year=2025)])
        result = EventBook().ingest(old, bootstrap=True).ingest(new).decisions[-1]
        self.assertEqual(result.candidate.current_period.fiscal_year, 2024)

    def test_out_of_order_ingestion_non_boolean_mode_and_direct_invalid_candidate_refuse(self):
        with self.assertRaisesRegex(EventError, "validation instants"):
            raised_book().ingest(record("SYN-OLD", day="2025-01-03"))
        for value in (1, "yes", None):
            with self.assertRaises(EventError):
                EventBook().ingest(record(), bootstrap=value)
        with self.assertRaises(EventError):
            EventCandidate(record(), record("SYN-D2", day="2025-02-03", revenue="101", eps="1.01"))


if __name__ == "__main__":
    unittest.main()
