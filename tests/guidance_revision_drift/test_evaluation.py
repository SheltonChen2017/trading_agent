"""Invented passive job observations; no platform or external provenance."""
from copy import deepcopy
from dataclasses import replace
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift import evaluation
from research.guidance_revision_drift.evaluation import (
    CandidateBinding, CompileReceipt, RunReceipt, ReceiptJournal, EvaluationError,
    FIXTURE_SHA256, compare_cloud_source, project_file_inventory,
    validate_journal_projection,
)
from research.guidance_revision_drift.persistence import (
    JournalError, JournalConflict, PublicationUncertain, canonical_object,
)


def binding():
    return CandidateBinding("a" * 64, "b" * 64, "c" * 64, FIXTURE_SHA256,
                            "d" * 40, "e" * 40, "f" * 64)


def at(minute):
    return f"2025-01-02T00:{minute:02d}:00+00:00"


def compiled(candidate, attempt="SYN-QC-one", *, status="compiled", compile_id="SYN_compile_1", minute=1):
    return CompileReceipt(candidate.sha256, attempt, 123, compile_id, at(minute), at(minute + 1),
                          status, "LEAN-SYN-1", "SDK-SYN-1", "1" * 64)


def ran(candidate, attempt="SYN-QC-one", *, status="completed", compile_id="SYN_compile_1", minute=3):
    return RunReceipt(candidate.sha256, attempt, 123, compile_id, "SYN_run_1", at(minute), at(minute + 1),
                      status, "LEAN-SYN-1", "SDK-SYN-1", "2" * 64)


def files():
    return {"main.py": b"# invented source\n", "gdr_payload_000.py": b"_GDR_B64 = 'AA=='\n"}


def anchor(value):
    return hash_payload(project_file_inventory(value))


class EvaluationTests(unittest.TestCase):
    def test_binding_and_receipts_are_exact_immutable_observations(self):
        candidate = binding()
        self.assertEqual(candidate.sha256, hash_payload(candidate.to_dict()))
        projected = candidate.to_dict()
        projected["source_sha256"] = "9" * 64
        self.assertNotEqual(projected, candidate.to_dict())
        for changes in ({"candidate_sha256": "9" * 64}, {"fixture_sha256": "9" * 64},
                        {"review_commit": "HEAD"}, {"source_sha256": True}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                replace(candidate, **changes)
        for changes in ({"project_id": True}, {"project_id": float("nan")}, {"compile_id": None},
                        {"engine": False}, {"binding_sha256": "real"}, {"status": "Completed"},
                        {"requested_at": "2025-01-02T00:01:00"}, {"completed_at": at(0)}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                replace(compiled(candidate), **changes)
        for changes in ({"run_id": ""}, {"status": "running"}, {"started_at": at(5)}):
            with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                replace(ran(candidate), **changes)

    def test_pending_and_ambiguity_survive_restart_and_no_renaming_reset(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            genesis = journal.head_sha256
            journal.record_intent(expected_head=genesis, attempt_id="SYN-QC-one", at=at(0))
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     at=at(1), output_sha256="3" * 64)
            head = journal.head_sha256
            recovered = ReceiptJournal.open(Path(directory), binding=candidate, expected_head=head)
            self.assertEqual(recovered.to_dict()["pending_attempts"], 1)
            self.assertEqual(recovered.to_dict()["attempts"][0]["status"], "ambiguous")
            with self.assertRaisesRegex(EvaluationError, "pending"):
                recovered.record_intent(expected_head=head, attempt_id="SYN-QC-renamed", at=at(2))
            with self.assertRaises(JournalError):
                ReceiptJournal.create(Path(directory), replace(candidate, project_sha256="8" * 64))
            self.assertEqual(ReceiptJournal.create(Path(directory), candidate).head_sha256, head)
            recovered.record_compile(expected_head=head, receipt=compiled(candidate, minute=1))
            self.assertEqual(recovered.to_dict()["attempts"][0]["status"], "compiled")

    def test_complete_compile_run_lineage_is_passive_and_detached(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", at=at(0))
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate))
            before = journal.head_sha256
            for changes in ({"binding_sha256": "8" * 64}, {"project_id": 124}, {"compile_id": "wrong"},
                            {"engine": "wrong"}, {"binding_version": "wrong"}, {"started_at": at(1)}):
                with self.subTest(changes=changes), self.assertRaises(EvaluationError):
                    journal.record_run(expected_head=before, receipt=replace(ran(candidate), **changes))
                self.assertEqual(journal.head_sha256, before)
            result = journal.record_run(expected_head=before, receipt=ran(candidate))
            self.assertTrue(result["completed_observed"])
            for flag in ("external_provenance_verified", "native_runtime_verified", "qc_launch_allowed",
                         "economic_acceptance", "market_evidence"):
                self.assertIs(result[flag], False)
            result["attempts"][0]["run"]["run_id"] = "mutated"
            self.assertEqual(journal.to_dict()["attempts"][0]["run"]["run_id"], "SYN_run_1")
            with self.assertRaises(EvaluationError):
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-two", at=at(5))

    def test_all_terminal_failure_classes_count_once_and_third_stops(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", at=at(0))
            first = compiled(candidate, status="compile_failed")
            journal.record_compile(expected_head=journal.head_sha256, receipt=first)
            head = journal.head_sha256
            journal.record_compile(expected_head=head, receipt=first)
            self.assertEqual(journal.head_sha256, head)
            journal.record_intent(expected_head=head, attempt_id="SYN-QC-two", at=at(5))
            journal.record_compile(expected_head=journal.head_sha256,
                receipt=compiled(candidate, "SYN-QC-two", compile_id="SYN_compile_2", minute=6))
            journal.record_run(expected_head=journal.head_sha256,
                receipt=ran(candidate, "SYN-QC-two", status="runtime_error", compile_id="SYN_compile_2", minute=8))
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-three", at=at(10))
            journal.record_failure(expected_head=journal.head_sha256, attempt_id="SYN-QC-three",
                                    at=at(11), output_sha256="5" * 64)
            final = journal.to_dict()
            self.assertEqual((final["launch_intents"], final["unsuccessful_attempts"]), (3, 3))
            self.assertIn("Mia", final["next_action"])
            with self.assertRaisesRegex(EvaluationError, "maximum three"):
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-four", at=at(12))
            self.assertEqual(ReceiptJournal.open(Path(directory), binding=candidate,
                expected_head=journal.head_sha256).to_dict(), final)

    def test_stale_conflicts_truncation_and_identity_reuse_refuse(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            genesis = journal.head_sha256
            journal.record_intent(expected_head=genesis, attempt_id="SYN-QC-one", at=at(0))
            with self.assertRaises(JournalConflict):
                journal.record_intent(expected_head=genesis, attempt_id="SYN-QC-one", at=at(1))
            with self.assertRaises(JournalConflict):
                journal.record_compile(expected_head=genesis, receipt=compiled(candidate))
            journal.record_compile(expected_head=journal.head_sha256,
                                   receipt=compiled(candidate, status="compile_failed"))
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-two", at=at(5))
            with self.assertRaisesRegex(EvaluationError, "compile ID"):
                journal.record_compile(expected_head=journal.head_sha256,
                    receipt=compiled(candidate, "SYN-QC-two", minute=6))
            with self.assertRaisesRegex(EvaluationError, "project changed"):
                journal.record_compile(expected_head=journal.head_sha256,
                    receipt=replace(compiled(candidate, "SYN-QC-two", compile_id="SYN_compile_2", minute=6), project_id=124))
            head = journal.head_sha256
            Path(directory, "evaluation-000003.json").unlink()
            with self.assertRaisesRegex(EvaluationError, "truncation"):
                ReceiptJournal.open(Path(directory), binding=candidate, expected_head=head)

    def test_other_run_failures_and_reused_run_id_cannot_create_success(self):
        candidate = binding()
        for status in ("cancelled", "other_failed"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                journal = ReceiptJournal.create(Path(directory), candidate)
                with self.assertRaises(EvaluationError):
                    journal.record_run(expected_head=journal.head_sha256, receipt=ran(candidate))
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", at=at(0))
                with self.assertRaises(EvaluationError):
                    journal.record_run(expected_head=journal.head_sha256, receipt=ran(candidate))
                journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate))
                journal.record_run(expected_head=journal.head_sha256, receipt=ran(candidate, status=status))
                self.assertEqual(journal.to_dict()["unsuccessful_attempts"], 1)
                self.assertFalse(journal.to_dict()["completed_observed"])
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-two", at=at(5))
                journal.record_compile(expected_head=journal.head_sha256,
                    receipt=compiled(candidate, "SYN-QC-two", compile_id="SYN_compile_2", minute=6))
                before = journal.head_sha256
                with self.assertRaisesRegex(EvaluationError, "run ID reused"):
                    journal.record_run(expected_head=before,
                        receipt=ran(candidate, "SYN-QC-two", compile_id="SYN_compile_2", minute=8))
                self.assertEqual(journal.head_sha256, before)

    def test_terminal_observations_cannot_backdate_later_ambiguity(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", at=at(0))
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     at=at(20), output_sha256="3" * 64)
            before = journal.head_sha256
            for operation in (lambda: journal.record_failure(expected_head=before,
                    attempt_id="SYN-QC-one", at=at(1), output_sha256="4" * 64),
                    lambda: journal.record_compile(expected_head=before, receipt=compiled(candidate))):
                with self.assertRaises(EvaluationError):
                    operation()
                self.assertEqual(journal.head_sha256, before)
            self.assertEqual(journal.to_dict()["pending_attempts"], 1)
            with self.assertRaises(EvaluationError):
                journal.record_intent(expected_head=before, attempt_id="SYN-QC-two", at=at(2))
            # An earlier request is allowed, but its supplied terminal clock
            # must not predate the most recent uncertainty observation.
            compilation = replace(compiled(candidate), completed_at=at(21))
            journal.record_compile(expected_head=before, receipt=compilation)
            journal.record_run(expected_head=journal.head_sha256,
                receipt=replace(ran(candidate, status="runtime_error"), started_at=at(22), completed_at=at(23)))
            self.assertEqual(journal.to_dict()["unsuccessful_attempts"], 1)
            with self.assertRaises(EvaluationError):
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-two", at=at(22))
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-two", at=at(24))
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", at=at(0))
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate))
            before = journal.head_sha256
            with self.assertRaises(EvaluationError):
                journal.record_ambiguous(expected_head=before, attempt_id="SYN-QC-one",
                                         at=at(1), output_sha256="3" * 64)
            journal.record_ambiguous(expected_head=before, attempt_id="SYN-QC-one",
                                     at=at(20), output_sha256="3" * 64)
            before = journal.head_sha256
            with self.assertRaises(EvaluationError):
                journal.record_run(expected_head=before, receipt=ran(candidate, status="runtime_error"))
            self.assertEqual(journal.head_sha256, before)
            journal.record_run(expected_head=before,
                receipt=replace(ran(candidate, status="runtime_error"), completed_at=at(21)))
            self.assertEqual(journal.to_dict()["unsuccessful_attempts"], 1)

    def test_reload_refuses_a_chained_second_observation_of_one_kind_for_one_attempt(self):
        # The writer refuses a different second "ambiguous" record for one
        # attempt. A correctly chained one written straight to disk must also
        # be refused on reload; otherwise replay would silently overwrite the
        # first ambiguity's retained output evidence with the second.
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ReceiptJournal.create(root, candidate)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", at=at(0))
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                     at=at(1), output_sha256="3" * 64)
            head = journal.head_sha256
            forged = {"schema": "gdr.synthetic.evaluation-record.v1", "sequence": 3,
                      "previous_sha256": head, "binding_sha256": candidate.sha256,
                      "operation": "ambiguous",
                      "payload": {"attempt_id": "SYN-QC-one", "at": at(2), "output_sha256": "4" * 64}}
            (root / "evaluation-000003.json").write_bytes(canonical_object(forged))
            with self.assertRaisesRegex(EvaluationError, "reused evaluation observation identity"):
                ReceiptJournal.open(root, binding=candidate, expected_head=head)

    def test_create_refuses_wrong_binding_without_invoking_caller_methods(self):
        class Forged:
            def to_dict(self):
                raise AssertionError("untrusted method invoked")
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(EvaluationError):
            ReceiptJournal.create(Path(directory), Forged())

    def test_journal_wrong_binding_symlink_foreign_entry_and_mutation_refuse(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            with self.assertRaises(EvaluationError):
                ReceiptJournal.open(Path(directory), binding=replace(candidate, source_sha256="9" * 64),
                                    expected_head=journal.head_sha256)
            old = journal.binding
            journal.binding = replace(candidate, project_sha256="9" * 64)
            with self.assertRaisesRegex(EvaluationError, "binding changed"):
                journal.to_dict()
            journal.binding = old
            Path(directory, "foreign.py").touch()
            with self.assertRaisesRegex(EvaluationError, "unexpected"):
                journal.to_dict()
            Path(directory, "foreign.py").unlink()
            original = Path(directory, "evaluation-genesis.json")
            copied = original.read_bytes()
            original.unlink()
            replacement = Path(directory, "replacement.json")
            replacement.write_bytes(copied)
            original.symlink_to(replacement)
            with self.assertRaises(JournalError):
                journal.to_dict()

    def test_uncertain_publication_recovery_does_not_forget_intent(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            previous = journal.head_sha256
            original = evaluation._publish
            def uncertain(*args):
                original(*args)
                raise PublicationUncertain("invented barrier loss")
            with patch.object(evaluation, "_publish", uncertain), self.assertRaises(PublicationUncertain):
                journal.record_intent(expected_head=previous, attempt_id="SYN-QC-one", at=at(0))
            recovered = ReceiptJournal.open(Path(directory), binding=candidate, expected_head=previous)
            self.assertEqual(recovered.to_dict()["pending_attempts"], 1)
            recovered.record_intent(expected_head=previous, attempt_id="SYN-QC-one", at=at(0))
            self.assertEqual(recovered.to_dict()["launch_intents"], 1)

    def test_full_projection_replay_refuses_false_summary_aliases_and_changed_chain(self):
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), candidate)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", at=at(0))
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled(candidate))
            journal.record_run(expected_head=journal.head_sha256, receipt=ran(candidate))
            snapshot, head = journal.to_dict(), journal.head_sha256
            verified = validate_journal_projection(snapshot, binding=candidate, expected_head_sha256=head)
            self.assertEqual(verified, snapshot)
            verified["attempts"][0]["status"] = "forged"
            self.assertEqual(journal.to_dict()["attempts"][0]["status"], "completed")
            mutations = [lambda body: body.update(unsuccessful_attempts=0, native_runtime_verified=True),
                         lambda body: body.update(unsuccessful_attempts=False),
                         lambda body: body["attempts"][0].update(status="failed"),
                         lambda body: body["binding"].update(source_sha256="8" * 64),
                         lambda body: body["records"][0]["payload"].update(at=at(5)),
                         lambda body: body.update(records=body["records"][:-1]),
                         lambda body: body.update(extra=True)]
            for mutate in mutations:
                body = deepcopy(snapshot)
                mutate(body)
                with self.subTest(mutation=mutate), self.assertRaises((EvaluationError, JournalError)):
                    validate_journal_projection(body, binding=candidate, expected_head_sha256=head)
            with self.assertRaises(EvaluationError):
                validate_journal_projection(snapshot, binding=candidate, expected_head_sha256="9" * 64)

    def test_complete_cloud_map_reports_every_missing_extra_changed_identity(self):
        expected = files()
        returned = {"main.py": b"# altered economic code\n", "extra.py": b"# not accepted\n"}
        result = compare_cloud_source(expected, returned, expected_project_sha256=anchor(expected),
                                      expected_returned_sha256=anchor(returned))
        self.assertEqual({row["name"]: row["status"] for row in result["changes"]},
                         {"extra.py": "extra", "gdr_payload_000.py": "missing", "main.py": "changed"})
        self.assertTrue(result["quarantined"])
        self.assertEqual(result["change_manifest_sha256"], hash_payload(result["changes"]))
        same = compare_cloud_source(expected, expected, expected_project_sha256=anchor(expected),
                                    expected_returned_sha256=anchor(expected))
        self.assertFalse(same["quarantined"])
        for flag in ("external_provenance_verified", "automatic_port_allowed", "economic_acceptance", "qc_launch_allowed"):
            self.assertIs(same[flag], False)

    def test_cloud_map_hostile_containers_and_retained_anchors_refuse(self):
        expected = files()
        for returned in ({"../main.py": b"x"}, {"x.py": bytearray(b"x")},
                         {"x.py": b"x" * 32000}, {True: b"x"},
                         {f"x{i}.py": b"x" for i in range(65)}):
            with self.subTest(returned=tuple(returned)), self.assertRaises(EvaluationError):
                compare_cloud_source(expected, returned, expected_project_sha256=anchor(expected),
                                     expected_returned_sha256="a" * 64)
        for first, second in (("9" * 64, anchor(expected)), (anchor(expected), "9" * 64)):
            with self.assertRaisesRegex(EvaluationError, "retained"):
                compare_cloud_source(expected, expected, expected_project_sha256=first,
                                     expected_returned_sha256=second)
        with self.assertRaises(EvaluationError):
            compare_cloud_source({"main.py": b"x"}, expected, expected_project_sha256="9" * 64,
                                 expected_returned_sha256=anchor(expected))

    def test_cloud_map_snapshot_cannot_change_during_current_verification(self):
        expected, returned = files(), files()
        expected["main.py"] = b"# retained altered root\n"
        before = anchor(expected)
        def change_caller(*args, **kwargs):
            expected.clear()
            expected.update(returned)
        with patch("research.guidance_revision_drift.qc_project.verify_qc_project", side_effect=change_caller):
            result = compare_cloud_source(expected, returned, expected_project_sha256=before,
                                          expected_returned_sha256=anchor(returned), verify_current=True)
        self.assertTrue(result["quarantined"])
        self.assertEqual(result["expected_project_sha256"], before)
        self.assertEqual(next(row for row in result["changes"] if row["name"] == "main.py")["status"], "changed")

    def test_load_bearing_attempt_ceiling_and_anchor_mutants_are_caught(self):
        source = inspect.getsource(evaluation._apply)
        mutant = source.replace("if len(attempts) >= 3 or sum(row[\"status\"] == \"failed\" for row in attempts) >= 3:", "if False:")
        self.assertNotEqual(source, mutant)
        namespace = dict(evaluation.__dict__)
        exec(compile(mutant, "<attempt-ceiling-mutant>", "exec"), namespace)
        candidate = binding()
        with tempfile.TemporaryDirectory() as directory, patch.object(evaluation, "_apply", namespace["_apply"]):
            journal = ReceiptJournal.create(Path(directory), candidate)
            for number in range(3):
                name = f"SYN-QC-{number}"
                journal.record_intent(expected_head=journal.head_sha256, attempt_id=name, at=at(number * 2))
                journal.record_failure(expected_head=journal.head_sha256, attempt_id=name,
                                       at=at(number * 2 + 1), output_sha256="5" * 64)
            with self.assertRaises(AssertionError):
                with self.assertRaises(EvaluationError):
                    journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-four", at=at(8))
        source = inspect.getsource(evaluation.compare_cloud_source)
        guard = 'if (hash_payload(before) != _hash(expected_project_sha256)\n            or hash_payload(after) != _hash(expected_returned_sha256)):'
        mutant = source.replace(guard, "if False:")
        self.assertNotEqual(source, mutant)
        namespace = dict(evaluation.__dict__)
        exec(compile(mutant, "<cloud-anchor-mutant>", "exec"), namespace)
        with patch.object(evaluation, "compare_cloud_source", namespace["compare_cloud_source"]):
            with self.assertRaises(AssertionError):
                with self.assertRaises(EvaluationError):
                    evaluation.compare_cloud_source(files(), files(), expected_project_sha256="9" * 64,
                                                    expected_returned_sha256=anchor(files()))


if __name__ == "__main__":
    unittest.main()
