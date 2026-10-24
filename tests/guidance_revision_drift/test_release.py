"""Release reconstruction and authority refusal, with invented inputs only."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift import release
from research.guidance_revision_drift.__main__ import main
from research.guidance_revision_drift.contracts import load_candidate
from research.guidance_revision_drift.lean_bridge import fixture_stream


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = release.build_release()
        cls.raw = canonical_json(cls.report).encode()

    def test_actual_release_reconstructs_and_retains_every_gate_closed(self):
        verified = release.verify_release(self.raw, expected_sha256=hash_bytes(self.raw))
        self.assertFalse(verified["qc_launch_allowed"])
        self.assertFalse(verified["market_evidence"])
        self.assertEqual(self.report["candidate_sha256"], load_candidate().sha256)
        self.assertEqual(self.report["calendar"]["session_count"], 93)
        self.assertEqual(self.report["engine"]["synthetic_sidecar_sha256"], hash_bytes(fixture_stream()))
        self.assertIsNone(self.report["engine"]["LEAN_version"])
        self.assertFalse(self.report["engine"]["SDK_binding_verified"])
        self.assertFalse(self.report["engine"]["QC_completed"])
        self.assertEqual(len(self.report["reports"]["integration"]["runs"]), 7)
        self.assertEqual(len(self.report["preflight"]["original_candidate_blockers"]), 11)
        self.assertFalse(self.report["independent_review_complete"])

    def test_rehashed_forgery_omitted_manifest_or_changed_epoch_cannot_self_certify(self):
        mutated = []
        forged = deepcopy(self.report)
        forged["preflight"]["qc_launch_allowed"] = True
        mutated.append(forged)
        omitted = deepcopy(self.report)
        del omitted["source_manifest"]["research/guidance_revision_drift/lean/main.py"]
        mutated.append(omitted)
        epoch = deepcopy(self.report)
        epoch["calendar"]["sha256"] = "f" * 64
        mutated.append(epoch)
        outcome = deepcopy(self.report)
        outcome["reports"]["integration_sha256"] = "e" * 64
        mutated.append(outcome)
        boolean_alias = deepcopy(self.report)
        boolean_alias["preflight"]["qc_launch_allowed"] = 0
        mutated.append(boolean_alias)
        integer_alias = deepcopy(self.report)
        integer_alias["preflight"]["qc_attempts"] = False
        mutated.append(integer_alias)
        # Unit-isolate the verifier comparison against the actually built
        # local report. The previous test performs a second full reconstruction.
        with patch.object(release, "build_release", return_value=self.report):
            for body in mutated:
                raw = canonical_json(body).encode()
                with self.subTest(body=body["code_sha256"]), self.assertRaisesRegex(ValueError, "reproduce"):
                    release.verify_release(raw, expected_sha256=hash_bytes(raw))

    def test_actual_cli_publication_is_content_addressed_and_idempotent(self):
        with TemporaryDirectory(prefix="gdr-release-test-") as directory, \
             patch.object(release, "build_release", return_value=self.report):
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(["review-release", "--output-dir", directory]), 0)
                receipt = json.loads(output.getvalue())
                self.assertEqual(Path(receipt["artifact"]).read_bytes(), self.raw)
                self.assertFalse(receipt["external_authority"])
            self.assertEqual(len(tuple(Path(directory).iterdir())), 1)

    def test_content_anchor_and_strict_canonical_json_required(self):
        with self.assertRaisesRegex(ValueError, "anchor"):
            release.verify_release(self.raw, expected_sha256="0" * 64)
        whitespace = self.raw + b"\n"
        with self.assertRaisesRegex(ValueError, "canonical"):
            release.verify_release(whitespace, expected_sha256=hash_bytes(whitespace))
        duplicate = b'{"schema":1,"schema":2}'
        with self.assertRaises(ValueError):
            release.verify_release(duplicate, expected_sha256=hash_bytes(duplicate))

    def test_manifest_covers_nested_algorithm_and_candidate_actual_bytes(self):
        manifest = self.report["source_manifest"]
        for name in ("research/guidance_revision_drift/lean/main.py",
                     "research/guidance_revision_drift/specs/gdr0a.draft.json",
                     "research/guidance_revision_drift/recovery.py", "data/__init__.py"):
            self.assertIn(name, manifest)
            self.assertEqual(manifest[name], hash_bytes((Path(__file__).resolve().parents[2] / name).read_bytes()))

    def test_preflight_cli_never_launches_and_rejects_approval_flags(self):
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("launch forbidden")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["launch-preflight"]), 2)
        self.assertIn('"qc_launch_allowed":false', output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["launch-preflight", "--approved"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
