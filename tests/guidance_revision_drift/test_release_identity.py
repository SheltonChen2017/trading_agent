"""Unit-isolated identity policy using the retained reviewed release as content.

test_release.py owns actual current-source/report reconstruction. These tests
avoid rerunning seven integration recipes for each one-field hostile mutation.
"""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift import release
from research.guidance_revision_drift.contracts import _decode


class ReleaseIdentityTests(unittest.TestCase):
    def setUp(self):
        anchor = "fccbef76a0921015e120dbaa73cf09f07ef6d20ac8d42839c7d4f47bce79f305"
        path = Path(__file__).resolve().parents[2] / "research/guidance_revision_drift/releases" / (anchor + ".json")
        raw = path.read_bytes()
        self.assertEqual(hash_bytes(raw), anchor)
        self.body = _decode(raw)
        self.body["schema"] = "gdr.synthetic.review-release.v2"
        self.body["identities"] = release._identities(self.body)

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
