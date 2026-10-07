"""Readiness and CLI tests: an intact draft never grants research authority."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from research.guidance_revision_drift import __main__ as cli
from research.guidance_revision_drift import contracts
from research.guidance_revision_drift.contracts import Candidate, CandidateError, load_candidate
from research.guidance_revision_drift.readiness import ReadinessReport, preflight


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.candidate = load_candidate()

    def test_valid_draft_is_blocked_with_every_unresolved_gate(self):
        body = self.candidate.to_dict()
        report = preflight(self.candidate).to_dict()
        self.assertEqual(report["schema"], "gdr.readiness.v1")
        self.assertEqual(report["candidate_id"], body["candidate_id"])
        self.assertEqual(report["candidate_sha256"], self.candidate.sha256)
        self.assertIs(report["draft_valid"], True)
        self.assertEqual(report["status"], "blocked")
        self.assertIs(report["ready_for_data_or_outcomes"], False)
        self.assertIs(report["ready_for_orders"], False)
        self.assertIs(report["point_in_time_evidence_verified"], False)
        self.assertEqual(report["blockers"], sorted(body["unresolved"]))
        self.assertEqual(len(report["blockers"]), 11)
        self.assertTrue(all(value is None for value in body["unresolved"].values()))
        self.assertEqual(report["authority"], body["authority"])
        self.assertFalse(any(report["authority"].values()))
        self.assertIn("not approved", report["note"])

    def test_reports_are_immutable_and_projections_are_isolated(self):
        report = preflight(self.candidate)
        with self.assertRaises(FrozenInstanceError):
            report.candidate = None
        first = report.to_dict()
        expected = report.to_dict()
        first["authority"]["qc_launch"] = True
        first["blockers"].clear()
        first["ready_for_orders"] = True
        self.assertEqual(report.to_dict(), expected)
        self.assertEqual(preflight(self.candidate).to_dict(), expected)

    def test_readiness_accepts_no_approval_or_pit_keywords(self):
        for keyword in ("approved", "owner_approved", "reviewed", "point_in_time_data", "candidate_sha256", "authority"):
            for call in (preflight, ReadinessReport):
                with self.subTest(keyword=keyword, call=call.__name__):
                    with self.assertRaises(TypeError):
                        call(self.candidate, **{keyword: True})

    def test_wrong_types_and_candidate_subclasses_are_rejected(self):
        class Impostor:
            canonical_bytes = self.candidate.canonical_bytes

        class DerivedCandidate(Candidate):
            pass

        for candidate in (None, self.candidate.to_dict(), self.candidate.canonical_bytes, Impostor(), DerivedCandidate(self.candidate.canonical_bytes)):
            with self.subTest(candidate_type=type(candidate).__name__):
                with self.assertRaises(CandidateError):
                    preflight(candidate)

    def test_candidate_is_revalidated_before_report_and_projection(self):
        candidate = load_candidate()
        report = preflight(candidate)
        object.__setattr__(candidate, "canonical_bytes", b"{}")
        with self.assertRaises(CandidateError):
            preflight(candidate)
        with self.assertRaises(CandidateError):
            report.to_dict()


class ReadOnlyCliTests(unittest.TestCase):
    def setUp(self):
        self.candidate = load_candidate()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.spec = self.root / "research/guidance_revision_drift/specs/gdr0a.draft.json"
        self.spec.parent.mkdir(parents=True)
        self.spec.write_bytes(self.candidate.canonical_bytes)
        for document in self.candidate.to_dict()["source_documents"]:
            target = self.root / document["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPOSITORY_ROOT / document["path"]).read_bytes())
        self.spec_patch = patch.object(contracts, "_SPEC_PATH", self.spec)
        self.spec_patch.start()
        self.addCleanup(self.spec_patch.stop)
        self.root_patch = patch.object(cli, "__file__", str(self.root / "research/guidance_revision_drift/__main__.py"))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def invoke(self, command):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = cli.main(command)
        return status, stdout.getvalue(), stderr.getvalue()

    def snapshot(self):
        return {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def test_show_candidate_exits_zero_and_does_not_write(self):
        before = self.snapshot()
        status, stdout, stderr = self.invoke(["show-candidate"])
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), self.candidate.to_dict())
        self.assertEqual(stdout.encode("utf-8"), self.candidate.canonical_bytes + b"\n")
        self.assertEqual(self.snapshot(), before)

    def test_preflight_exits_two_with_valid_but_blocked_report_and_does_not_write(self):
        before = self.snapshot()
        status, stdout, stderr = self.invoke(["preflight"])
        self.assertEqual(status, 2)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), preflight(self.candidate).to_dict())
        self.assertEqual(self.snapshot(), before)

    def test_invalid_candidate_exits_one_without_plausible_readiness_output(self):
        for raw in (b"{}", b"bad json", self.candidate.canonical_bytes.replace(b'"qc_launch":false', b'"qc_launch":true')):
            for command in ("preflight", "show-candidate"):
                with self.subTest(raw_start=raw[:30], command=command):
                    self.spec.write_bytes(raw)
                    before = self.snapshot()
                    status, stdout, stderr = self.invoke([command])
                    self.assertEqual(status, 1)
                    self.assertEqual(stdout, "")
                    self.assertEqual(json.loads(stderr)["status"], "invalid_candidate")
                    self.assertEqual(self.snapshot(), before)

    def test_missing_candidate_exits_one(self):
        self.spec.unlink()
        status, stdout, stderr = self.invoke(["preflight"])
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["status"], "invalid_candidate")

    def test_tampered_source_document_exits_one_for_both_commands(self):
        for document in self.candidate.to_dict()["source_documents"]:
            target = self.root / document["path"]
            original = target.read_bytes()
            target.write_bytes(original + b"tampered")
            for command in ("preflight", "show-candidate"):
                with self.subTest(document=document["path"], command=command):
                    status, stdout, stderr = self.invoke([command])
                    self.assertEqual(status, 1)
                    self.assertEqual(stdout, "")
                    self.assertEqual(json.loads(stderr)["status"], "invalid_candidate")
            target.write_bytes(original)

    def test_unknown_or_missing_command_exits_two_before_loading(self):
        with patch.object(cli, "load_candidate", side_effect=AssertionError("must not load")):
            for arguments in ([], ["launch"], ["download"], ["approve"], ["capture"], ["paper"], ["preflight", "--approved"]):
                with self.subTest(arguments=arguments):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as raised:
                            cli.main(arguments)
                    self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
