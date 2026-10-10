"""Invented owner-cycle observations only; no platform, SDK or real outcomes."""
from copy import deepcopy
from dataclasses import replace
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift import evaluation_cycle
from research.guidance_revision_drift.evaluation import (
    CandidateBinding, CompileReceipt, RunReceipt, EvaluationError, FIXTURE_SHA256,
)
from research.guidance_revision_drift.evaluation_cycle import (
    OwnerCycle, CycleJournal, content_identity, validate_cycle_projection,
)
from research.guidance_revision_drift.persistence import (
    JournalError, JournalConflict, PublicationUncertain, canonical_object,
)


def binding():
    return CandidateBinding("a" * 64, "b" * 64, "c" * 64, FIXTURE_SHA256,
                            "d" * 40, "e" * 40, "f" * 64)


def at(minute):
    return f"2025-01-02T00:{minute:02d}:00+00:00"


def compiled(candidate, attempt="SYN-QC-one", *, status="compiled", minute=1,
             compile_id="SYN_compile_1"):
    return CompileReceipt(candidate.sha256, attempt, 123, compile_id, at(minute), at(minute + 1),
                          status, "LEAN-SYN-1", "SDK-SYN-1", "1" * 64)


def ran(candidate, attempt="SYN-QC-one", *, status="completed", minute=3,
        compile_id="SYN_compile_1", run_id="SYN_run_1"):
    return RunReceipt(candidate.sha256, attempt, 123, compile_id, run_id, at(minute), at(minute + 1),
                      status, "LEAN-SYN-1", "SDK-SYN-1", "2" * 64)


def inventory(root):
    return {path.name: path.read_bytes() for path in Path(root).iterdir()}


def fresh(root):
    cycle = OwnerCycle("SYN-owner-cycle-20251008")
    return CycleJournal.create(Path(root), cycle, expected_head=cycle.genesis_sha256)


def intent(journal, candidate, *, attempt="SYN-QC-one", minute=0):
    return journal.record_intent(expected_head=journal.head_sha256, attempt_id=attempt,
                                 binding=candidate, at=at(minute), observed_at=at(minute))


class EvaluationCycleTests(unittest.TestCase):
    def test_content_identity_excludes_review_metadata_but_not_byte_changes(self):
        candidate = binding()
        reviewed = replace(candidate, source_commit="1" * 40, review_commit="2" * 40,
                           review_record_sha256="3" * 64)
        self.assertNotEqual(candidate.sha256, reviewed.sha256)
        self.assertEqual(content_identity(candidate), content_identity(reviewed))
        for name in ("source_sha256", "project_sha256", "bundle_sha256"):
            with self.subTest(name=name):
                self.assertNotEqual(content_identity(candidate),
                                    content_identity(replace(candidate, **{name: "4" * 64})))
        with self.assertRaises(EvaluationError):
            content_identity(candidate.to_dict())

    def test_fixed_cycle_refuses_candidate_fixture_mode_replacement(self):
        cycle = OwnerCycle("SYN-one")
        for changes in ({"candidate_sha256": "0" * 64}, {"fixture_sha256": "0" * 64},
                        {"fixture_mode": "split"}, {"fixture_mode": True}, {"cycle_id": ""}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                replace(cycle, **changes)
        projected = cycle.to_dict()
        projected["max_unsuccessful_attempts"] = 99
        self.assertEqual(cycle.to_dict()["max_unsuccessful_attempts"], 3)

    def _assert_budget_persists(self):
        candidate = binding()
        reviewed = replace(candidate, review_commit="1" * 40, review_record_sha256="2" * 64)
        corrected = replace(reviewed, source_sha256="3" * 64, project_sha256="4" * 64,
                            bundle_sha256="5" * 64, source_commit="6" * 40)
        with tempfile.TemporaryDirectory() as root:
            journal = fresh(root)
            intent(journal, candidate)
            first = compiled(candidate, status="compile_failed")
            journal.record_compile(expected_head=journal.head_sha256, receipt=first, observed_at=at(2))
            head = journal.head_sha256
            journal.record_compile(expected_head=head, receipt=first, observed_at=at(2))
            self.assertEqual(journal.head_sha256, head)
            journal = CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=head)
            intent(journal, reviewed, attempt="SYN-QC-two", minute=5)
            journal.record_compile(expected_head=journal.head_sha256,
                receipt=compiled(reviewed, "SYN-QC-two", minute=6, compile_id="SYN_compile_2"),
                observed_at=at(7))
            journal.record_run(expected_head=journal.head_sha256,
                receipt=ran(reviewed, "SYN-QC-two", minute=8, compile_id="SYN_compile_2",
                            status="runtime_error"), observed_at=at(9))
            intent(journal, corrected, attempt="SYN-QC-three", minute=10)
            journal.record_failure(expected_head=journal.head_sha256, attempt_id="SYN-QC-three",
                                   event_at=at(11), observed_at=at(12), output_sha256="7" * 64)
            final = journal.to_dict()
            self.assertEqual((final["launch_intents"], final["unsuccessful_attempts"]), (3, 3))
            self.assertEqual(len(final["content_identities"]), 2)
            self.assertEqual(len(final["review_bindings"]), 3)
            self.assertEqual(final["attempts"][1]["binding"], reviewed.to_dict())
            self.assertEqual(final["attempts"][2]["binding"], corrected.to_dict())
            self.assertIn("Mia", final["next_action"])
            before = inventory(root)
            with self.assertRaisesRegex(EvaluationError, "maximum three"):
                intent(journal, replace(corrected, review_commit="8" * 40),
                       attempt="SYN-QC-four", minute=13)
            self.assertEqual(inventory(root), before)
            self.assertEqual(CycleJournal.open(Path(root), cycle=journal.cycle,
                expected_head=journal.head_sha256).to_dict(), final)

    def test_budget_continues_across_review_metadata_and_corrected_content(self):
        self._assert_budget_persists()

    def test_late_true_terminal_clears_ambiguity_without_rewriting_event_times(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as root:
            journal = fresh(root)
            intent(journal, candidate)
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate),
                                   observed_at=at(2))
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     observed_at=at(5), output_sha256="3" * 64)
            head = journal.head_sha256
            recovered = CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=head)
            with self.assertRaisesRegex(EvaluationError, "unresolved"):
                intent(recovered, candidate, attempt="SYN-QC-two", minute=6)
            terminal = ran(candidate)
            result = recovered.record_run(expected_head=head, receipt=terminal, observed_at=at(7))
            row = result["attempts"][0]
            self.assertEqual(row["run"], terminal.to_dict())
            self.assertEqual((row["terminal_event_at"], row["terminal_observed_at"]), (at(4), at(7)))
            self.assertEqual(row["ambiguity"]["observed_at"], at(5))
            self.assertEqual(result["last_observed_at"], at(7))
            self.assertEqual((result["pending_attempts"], result["unsuccessful_attempts"]), (0, 0))
            self.assertTrue(result["completed_observed"])
            self.assertEqual(validate_cycle_projection(result, cycle=journal.cycle,
                expected_head_sha256=recovered.head_sha256), result)
            for flag in ("external_provenance_verified", "native_runtime_verified", "qc_launch_allowed",
                         "economic_acceptance", "market_evidence"):
                self.assertIs(result[flag], False)
            with self.assertRaisesRegex(EvaluationError, "completed"):
                intent(recovered, candidate, attempt="SYN-QC-two", minute=8)

    def test_earlier_compile_can_be_retrieved_after_ambiguity_then_terminal_run(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as root:
            journal = fresh(root)
            intent(journal, candidate)
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     observed_at=at(5), output_sha256="3" * 64)
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate),
                                   observed_at=at(6))
            journal.record_run(expected_head=journal.head_sha256, receipt=ran(candidate), observed_at=at(7))
            row = journal.to_dict()["attempts"][0]
            self.assertEqual(row["compile"]["completed_at"], at(2))
            self.assertEqual(row["compile_observed_at"], at(6))
            self.assertIsNotNone(row["ambiguity"])

    def _assert_observation_floor(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, journal = binding(), fresh(root)
            intent(journal, candidate)
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate),
                                   observed_at=at(2))
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     observed_at=at(5), output_sha256="3" * 64)
            before = inventory(root)
            with self.assertRaisesRegex(EvaluationError, "regressed"):
                journal.record_run(expected_head=journal.head_sha256, receipt=ran(candidate),
                                   observed_at=at(4))
            self.assertEqual(inventory(root), before)

    def test_observation_floor_regression_is_atomic(self):
        self._assert_observation_floor()

    def test_wrong_lineage_and_future_event_refuse_atomically(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as root:
            journal = fresh(root)
            intent(journal, candidate)
            for receipt, observed in ((replace(compiled(candidate), requested_at=at(0)), at(1)),
                                      (replace(compiled(candidate), binding_sha256="0" * 64), at(2))):
                before = inventory(root)
                with self.assertRaises(EvaluationError):
                    journal.record_compile(expected_head=journal.head_sha256, receipt=receipt,
                                           observed_at=observed)
                self.assertEqual(inventory(root), before)
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate),
                                   observed_at=at(2))
            reviewed = replace(candidate, review_commit="8" * 40)
            for changes in ({"binding_sha256": reviewed.sha256}, {"project_id": 124},
                            {"compile_id": "wrong"}, {"engine": "wrong"},
                            {"binding_version": "wrong"}, {"started_at": at(1)},
                            {"completed_at": at(9)}):
                before = inventory(root)
                with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                    journal.record_run(expected_head=journal.head_sha256,
                        receipt=replace(ran(candidate), **changes), observed_at=at(8))
                self.assertEqual(inventory(root), before)

    def test_failed_old_event_recovery_retains_count_and_prevents_backdated_next_intent(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as root:
            journal = fresh(root)
            intent(journal, candidate)
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     observed_at=at(5), output_sha256="3" * 64)
            result = journal.record_failure(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                event_at=at(1), observed_at=at(7), output_sha256="4" * 64)
            self.assertEqual(result["unsuccessful_attempts"], 1)
            self.assertEqual(result["attempts"][0]["terminal_event_at"], at(1))
            with self.assertRaisesRegex(EvaluationError, "prior observation"):
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-two",
                                      binding=candidate, at=at(6), observed_at=at(8))
            intent(journal, candidate, attempt="SYN-QC-two", minute=8)
            before = inventory(root)
            with self.assertRaisesRegex(EvaluationError, "precedes"):
                journal.record_failure(expected_head=journal.head_sha256, attempt_id="SYN-QC-two",
                    event_at=at(7), observed_at=at(9), output_sha256="4" * 64)
            self.assertEqual(inventory(root), before)

    def test_create_replacement_and_reopen_require_retained_heads(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as lost:
            journal = fresh(root)
            intent(journal, binding())
            head = journal.head_sha256
            for cycle in (journal.cycle, OwnerCycle("SYN-replacement-cycle")):
                with self.subTest(cycle=cycle), self.assertRaisesRegex(EvaluationError, "genesis"):
                    CycleJournal.create(Path(lost), cycle, expected_head=head)
                self.assertEqual(inventory(lost), {})
            with self.assertRaises(JournalError):
                CycleJournal.open(Path(lost), cycle=journal.cycle, expected_head=head)
            with self.assertRaises(TypeError):
                CycleJournal.create(Path(lost), journal.cycle)
            with self.assertRaises(TypeError):
                CycleJournal.open(Path(root), cycle=journal.cycle)
            with self.assertRaises(EvaluationError):
                CycleJournal.open(Path(root), cycle=OwnerCycle("SYN-replacement-cycle"), expected_head=head)
            self.assertEqual(CycleJournal.create(Path(root), journal.cycle,
                expected_head=journal.cycle.genesis_sha256).head_sha256, head)

    def test_full_projection_refuses_lossy_forged_extra_and_old_head_views(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, journal = binding(), fresh(root)
            genesis = journal.head_sha256
            intent(journal, candidate)
            result = journal.to_dict()
            mutations = []
            for field, value in (("launch_intents", 0), ("qc_launch_allowed", True),
                                 ("content_identities", []), ("last_observed_at", at(1)),
                                 ("extra", False)):
                mutated = deepcopy(result)
                mutated[field] = value
                mutations.append(mutated)
            lossy = deepcopy(result)
            del lossy["attempts"][0]["binding"]
            mutations.append(lossy)
            for mutation in mutations:
                with self.subTest(keys=mutation.keys()), self.assertRaises(EvaluationError):
                    validate_cycle_projection(mutation, cycle=journal.cycle,
                                              expected_head_sha256=journal.head_sha256)
            with self.assertRaises(EvaluationError):
                validate_cycle_projection(result, cycle=journal.cycle, expected_head_sha256=genesis)
            self.assertEqual(validate_cycle_projection(result, cycle=journal.cycle,
                expected_head_sha256=journal.head_sha256), result)

    def test_duplicate_replay_conflict_stale_writer_and_detached_views(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, journal = binding(), fresh(root)
            genesis = journal.head_sha256
            result = intent(journal, candidate)
            head = journal.head_sha256
            journal.record_intent(expected_head=genesis, attempt_id="SYN-QC-one", binding=candidate,
                                  at=at(0), observed_at=at(0))
            self.assertEqual(journal.head_sha256, head)
            with self.assertRaises(JournalConflict):
                journal.record_intent(expected_head=head, attempt_id="SYN-QC-one", binding=candidate,
                                      at=at(0), observed_at=at(1))
            with self.assertRaises(JournalConflict):
                journal.record_compile(expected_head=genesis, receipt=compiled(candidate), observed_at=at(2))
            result["attempts"][0]["binding"]["source_sha256"] = "0" * 64
            self.assertEqual(journal.to_dict()["attempts"][0]["binding"], candidate.to_dict())

    def test_terminal_classes_and_reused_platform_ids(self):
        candidate = binding()
        for status in ("cancelled", "other_failed", "runtime_error"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as root:
                journal = fresh(root)
                intent(journal, candidate)
                journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate),
                                       observed_at=at(2))
                journal.record_run(expected_head=journal.head_sha256,
                                   receipt=ran(candidate, status=status), observed_at=at(4))
                self.assertEqual(journal.to_dict()["unsuccessful_attempts"], 1)
                intent(journal, candidate, attempt="SYN-QC-two", minute=5)
                for changes in ({"compile_id": "SYN_compile_1"}, {"project_id": 124}):
                    with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                        journal.record_compile(expected_head=journal.head_sha256,
                            receipt=replace(compiled(candidate, "SYN-QC-two", minute=6,
                                                    compile_id="SYN_compile_2"), **changes), observed_at=at(7))
                journal.record_compile(expected_head=journal.head_sha256,
                    receipt=compiled(candidate, "SYN-QC-two", minute=6, compile_id="SYN_compile_2"),
                    observed_at=at(7))
                with self.assertRaisesRegex(EvaluationError, "run ID reused"):
                    journal.record_run(expected_head=journal.head_sha256,
                        receipt=ran(candidate, "SYN-QC-two", minute=8, compile_id="SYN_compile_2"),
                        observed_at=at(9))

    def test_hash_tamper_holes_truncation_and_duplicate_records_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            journal = fresh(root)
            intent(journal, binding())
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     observed_at=at(5), output_sha256="3" * 64)
            original = inventory(root)
            head = journal.head_sha256
            path = Path(root, "evaluation-cycle-000002.json")
            path.unlink()
            with self.assertRaisesRegex(EvaluationError, "truncation"):
                CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=head)
            path.write_bytes(original[path.name])
            first = Path(root, "evaluation-cycle-000001.json")
            first.unlink()
            with self.assertRaisesRegex(EvaluationError, "sequence"):
                CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=head)
            first.write_bytes(original[first.name])
            changed = journal.to_dict()["records"][-1]
            changed["observed_at"] = at(6)
            path.write_bytes(canonical_object(changed))
            with self.assertRaisesRegex(EvaluationError, "changed history"):
                CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=head)
            path.write_bytes(original[path.name])
            changed = journal.to_dict()["records"][-1]
            changed["extra"] = False
            path.write_bytes(canonical_object(changed))
            with self.assertRaisesRegex(EvaluationError, "unknown"):
                CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=head)
            path.write_bytes(original[path.name])
            body = journal.to_dict()["records"][-1]
            body.update(sequence=3, previous_sha256=head, observed_at=at(6))
            raw = canonical_object(body)
            Path(root, "evaluation-cycle-000003.json").write_bytes(raw)
            with self.assertRaisesRegex(EvaluationError, "reused"):
                CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=hash_bytes(raw))

    def test_uncertain_publication_recovers_exact_tail_and_retained_ancestor(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, journal = binding(), fresh(root)
            head = journal.head_sha256
            original = evaluation_cycle._publish

            def uncertain(*args):
                original(*args)
                raise PublicationUncertain("invented acknowledgment loss")

            with patch.object(evaluation_cycle, "_publish", uncertain), self.assertRaises(PublicationUncertain):
                intent(journal, candidate)
            recovered = CycleJournal.open(Path(root), cycle=journal.cycle, expected_head=head)
            self.assertEqual(recovered.to_dict()["launch_intents"], 1)
            recovered.record_intent(expected_head=head, attempt_id="SYN-QC-one", binding=candidate,
                                    at=at(0), observed_at=at(0))
            self.assertEqual(recovered.to_dict()["launch_intents"], 1)

    def test_invalid_clock_and_new_directory_contents_refuse_before_publication(self):
        with tempfile.TemporaryDirectory() as root:
            journal = fresh(root)
            for value in (None, True, "2025-01-02T00:00:00", "2025-01-02T00:00:00Z"):
                before = inventory(root)
                with self.subTest(value=value), self.assertRaises(EvaluationError):
                    journal.record_intent(expected_head=journal.head_sha256, binding=binding(),
                        attempt_id="SYN-QC-one", at=at(0), observed_at=value)
                self.assertEqual(inventory(root), before)
        with tempfile.TemporaryDirectory() as root:
            Path(root, "unrelated.txt").write_bytes(b"invented")
            cycle = OwnerCycle("SYN-one")
            before = inventory(root)
            with self.assertRaises(EvaluationError):
                CycleJournal.create(Path(root), cycle, expected_head=cycle.genesis_sha256)
            self.assertEqual(inventory(root), before)

    def test_naive_event_unknown_intent_fields_and_mutated_cycle_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, journal = binding(), fresh(root)
            before = inventory(root)
            with self.assertRaises(EvaluationError):
                journal.record_intent(expected_head=journal.head_sha256, binding=candidate,
                    attempt_id="SYN-QC-one", at="2025-01-02T00:00:00", observed_at=at(0))
            self.assertEqual(inventory(root), before)
            payload = {"attempt_id": "SYN-QC-one", "at": at(0), "binding": candidate.to_dict(),
                       "binding_sha256": candidate.sha256, "content_sha256": content_identity(candidate),
                       "extra": True}
            with self.assertRaises(EvaluationError):
                journal._append(journal.head_sha256, "intent", payload, at(0))
            self.assertEqual(inventory(root), before)
            object.__setattr__(journal.cycle, "cycle_id", "SYN-replaced-after-construction")
            with self.assertRaisesRegex(EvaluationError, "changed"):
                journal.to_dict()
            self.assertEqual(inventory(root), before)

    def test_two_guard_removal_mutants_fail_and_original_is_restored(self):
        original = evaluation_cycle._apply
        source = inspect.getsource(original)
        mutants = (("if len(attempts) >= 3:", "if False:", self._assert_budget_persists),
                   ("observed < _clock(previous_observed_at)", "False", self._assert_observation_floor))
        for before, after, assertion in mutants:
            with self.subTest(guard=before):
                self.assertIn(before, source)
                namespace = dict(vars(evaluation_cycle))
                exec(compile(source.replace(before, after, 1), "<cycle-guard-mutant>", "exec"), namespace)
                with patch.object(evaluation_cycle, "_apply", namespace["_apply"]):
                    with self.assertRaises(AssertionError):
                        assertion()
                self.assertIs(evaluation_cycle._apply, original)
                assertion()


if __name__ == "__main__":
    unittest.main()
