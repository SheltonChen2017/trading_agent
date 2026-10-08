"""Unit-isolated identity policy using an explicit representative content body.

test_release.py owns actual current-source/report reconstruction. These tests
avoid rerunning seven integration recipes for each one-field hostile mutation.
The policy body is not a release artifact or evidence of engine execution.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift import release


class ReleaseIdentityTests(unittest.TestCase):
    def setUp(self):
        # Include every field mutated below, with the same scalar types as an
        # actual release. The separate reconstruction tests own release shape,
        # source/report contents and historical artifact availability.
        self.body = {
            "schema": "gdr.synthetic.review-release.v2",
            "engine": {"python_implementation": "CPython", "python_version": "3.12.14",
                       "LEAN_version": None, "SDK_binding_verified": False, "QC_completed": False,
                       "native_settlement": "immediate_cash_envelope_not_equity_cash_account_parity"},
            "preflight": {"qc_attempts": 0, "empirical_looks": 0, "qc_upload_allowed": False,
                          "qc_launch_allowed": False, "provider_access_allowed": False,
                          "paper_live_allowed": False},
            "calendar": {"session_count": 93, "audited_exchange_calendar": False},
            "reports": {"integration_sha256": "1" * 64},
            "source_manifest": {"research/guidance_revision_drift/lean/main.py": "2" * 64},
            "market_evidence": False, "point_in_time_evidence": False,
            "independent_review_complete": False,
        }
        self.body["identities"] = release._identities(self.body)

    def test_policy_fixture_needs_no_release_file_and_preserves_scalar_types(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("fixture file read forbidden")), \
             patch.object(Path, "read_text", side_effect=AssertionError("fixture file read forbidden")):
            self.setUp()
            self.assertIs(self.body["engine"]["QC_completed"], False)
            self.assertIs(type(self.body["preflight"]["qc_attempts"]), int)
            with patch.object(release, "build_release", return_value=self.body):
                self.assertTrue(self.verify(self.body)["environment_matches"])
                # Python compares these pairs equal, but their canonical JSON
                # types must remain distinct after rehashing hostile input.
                for section, key, alias in (("engine", "QC_completed", 0),
                                            ("preflight", "qc_attempts", False)):
                    body = deepcopy(self.body)
                    self.assertEqual(body[section][key], alias)
                    self.assertIsNot(type(body[section][key]), type(alias))
                    body[section][key] = alias
                    body["identities"] = release._identities(body)
                    with self.subTest(section=section, key=key), self.assertRaisesRegex(ValueError, "reproduce"):
                        self.verify(body)

    def verify(self, body):
        raw = canonical_json(body).encode()
        return release.verify_release_content(raw, expected_sha256=hash_bytes(raw),
            expected_content_sha256=body["identities"]["portable_content_sha256"])

    def test_interpreter_difference_has_portable_identity_but_fails_exact_verification(self):
        other = deepcopy(self.body)
        other["engine"]["python_version"] = "3.13.15"
        other["identities"] = release._identities(other)
        self.assertEqual(other["identities"]["portable_content_sha256"],
                         self.body["identities"]["portable_content_sha256"])
        self.assertNotEqual(other["identities"]["environment_sha256"],
                            self.body["identities"]["environment_sha256"])
        with patch.object(release, "build_release", return_value=other):
            report = self.verify(self.body)
            self.assertFalse(report["environment_matches"])
            self.assertFalse(report["runtime_parity_verified"])
            raw = canonical_json(self.body).encode()
            with self.assertRaisesRegex(ValueError, "reproduce"):
                release.verify_release(raw, expected_sha256=hash_bytes(raw))

    def test_same_environment_identity_is_not_native_or_cloud_acceptance(self):
        with patch.object(release, "build_release", return_value=self.body):
            report = self.verify(self.body)
        self.assertTrue(report["environment_matches"])
        for key in ("runtime_parity_verified", "qc_launch_allowed", "market_evidence"):
            self.assertIs(report[key], False)

    def test_rehashed_changes_outside_two_labels_never_self_certify(self):
        changes = [("engine", "LEAN_version", "changed"),
                   ("engine", "SDK_binding_verified", True),
                   ("engine", "native_settlement", "changed"),
                   ("engine", "QC_completed", 0),
                   ("preflight", "qc_attempts", False),
                   ("calendar", "session_count", 94),
                   ("reports", "integration_sha256", "a" * 64),
                   ("source_manifest", "research/guidance_revision_drift/lean/main.py", "b" * 64)]
        with patch.object(release, "build_release", return_value=self.body):
            for section, key, value in changes:
                body = deepcopy(self.body)
                body[section][key] = value
                body["identities"] = release._identities(body)
                with self.subTest(section=section, key=key), self.assertRaisesRegex(ValueError, "reproduce"):
                    self.verify(body)

    def test_both_retained_anchors_and_identity_fields_are_checked(self):
        raw = canonical_json(self.body).encode()
        with self.assertRaisesRegex(ValueError, "anchor"):
            release.verify_release_content(raw, expected_sha256="0" * 64,
                expected_content_sha256=self.body["identities"]["portable_content_sha256"])
        with self.assertRaisesRegex(ValueError, "anchor"):
            release.verify_release_content(raw, expected_sha256=hash_bytes(raw), expected_content_sha256="0" * 64)
        for key in ("portable_content_sha256", "environment_sha256", "extra"):
            body = deepcopy(self.body)
            body["identities"][key] = "f" * 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "identity"):
                self.verify(body)

    def test_malformed_labels_and_noncanonical_input_refuse(self):
        for value in (False, 31214, "", "3.12\n", "a" * 65):
            body = deepcopy(self.body)
            body["engine"]["python_version"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.verify(body)
        raw = canonical_json(self.body).encode() + b"\n"
        with self.assertRaisesRegex(ValueError, "canonical"):
            release.verify_release_content(raw, expected_sha256=hash_bytes(raw),
                expected_content_sha256=self.body["identities"]["portable_content_sha256"])


if __name__ == "__main__":
    unittest.main()
