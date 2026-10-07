from dataclasses import FrozenInstanceError
from unittest.mock import patch
import unittest

from research.guidance_revision_drift.contracts import CandidateError, load_candidate
from research.guidance_revision_drift.specification import ExecutableSpecification, check_proposed_semantics


class SpecificationTests(unittest.TestCase):
    def test_exact_boundaries_execute(self):
        self.assertEqual(len(check_proposed_semantics()), 6)

    def test_all_rights_stay_closed_and_decisions_unresolved(self):
        spec = ExecutableSpecification(load_candidate())
        body = spec.to_dict()
        self.assertEqual(len(body["owner_decisions"]), 11)
        self.assertTrue(all(row["approval"] is None for row in body["owner_decisions"]))
        self.assertTrue(all(row["allowed"] is False for row in body["decision_rights"]))
        self.assertEqual(body["readiness"]["status"], "blocked")
        self.assertEqual((body["research_looks"], body["qc_attempts"]), (0, 0))
        self.assertFalse(body["point_in_time_data"])

    def test_canonical_identity_and_defensive_projections(self):
        spec = ExecutableSpecification(load_candidate())
        before = spec.to_bytes()
        body = spec.to_dict()
        body["parameters"]["portfolio"]["position_fraction_max"] = "1"
        body["owner_decisions"][0]["approval"] = "fake"
        self.assertEqual(spec.to_bytes(), before)
        self.assertEqual(spec.sha256, ExecutableSpecification(load_candidate()).sha256)
        with self.assertRaises(FrozenInstanceError):
            spec.candidate = None

    def test_forged_candidate_and_changed_semantics_refuse(self):
        with self.assertRaises(CandidateError):
            ExecutableSpecification({})
        spec = ExecutableSpecification(load_candidate())
        object.__setattr__(spec.candidate, "canonical_bytes", b"{}")
        with self.assertRaises(CandidateError):
            spec.to_dict()
        with patch("research.guidance_revision_drift.specification.time_exit_session", return_value=None):
            with self.assertRaisesRegex(CandidateError, "twenty_session_intervals"):
                check_proposed_semantics()

    def test_proposed_semantics_explicitly_preserve_open_choices(self):
        body = ExecutableSpecification(load_candidate()).to_dict()
        self.assertEqual(body["status"], "proposed_not_owner_frozen")
        self.assertIn("corrected_predecessor", body["semantics"]["explicit_correction"])
        self.assertIn("none", body["semantics"]["trim_tolerance"])
        self.assertIn("real_contract_unresolved", body["semantics"]["settlement"])


if __name__ == "__main__":
    unittest.main()
