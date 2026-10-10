"""Native-only preparation boundaries, not a native SDK execution test."""
from io import BytesIO
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift import bundle, native_bundle, qc_project
from research.guidance_revision_drift.lean_bridge import fixture_stream
from research.guidance_revision_drift.reporting import source_manifest
from tests.guidance_revision_drift.test_bundle import repack


class NativeBundleTests(unittest.TestCase):
    def test_exact_closure_not_whole_review_bundle_and_notebook_headroom(self):
        raw = native_bundle.build_native_bundle()
        verified = native_bundle.verify_native_bundle(raw, expected_sha256=hash_bytes(raw))
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(set(archive.namelist()), native_bundle.SOURCE_PATHS | {bundle.MANIFEST_PATH, bundle.SIDECAR_PATH})
            self.assertEqual(archive.read(bundle.SIDECAR_PATH), fixture_stream())
            self.assertNotIn("research/guidance_revision_drift/evaluation_cycle.py", archive.namelist())
            for path in native_bundle.SOURCE_PATHS:
                self.assertEqual(archive.read(path), (native_bundle.ROOT / path).read_bytes())
        self.assertIs(verified["manifest"]["qc_upload_allowed"], False)
        project = qc_project.qc_project_manifest()
        self.assertLess(project["bundle_bytes"], native_bundle.MAX_NATIVE_BUNDLE_BYTES)
        self.assertLessEqual(project["project_files_with_reserved_notebook"], 25)
        self.assertEqual(project["reserved_project_files"], 1)
        self.assertEqual(project["source_manifest_sha256"], hash_payload(source_manifest()))
        self.assertEqual(project["runtime_source_sha256"], verified["manifest"]["source_manifest_sha256"])

    def test_omission_extra_changed_content_and_noncanonical_bytes_refuse(self):
        raw = native_bundle.build_native_bundle()
        path = native_bundle.ENTRYPOINT
        def change(info, content):
            return info, content + b"\n" if info.filename == path else content
        for bad in (repack(raw, omit=(path,)), repack(raw, extra=(("evil.py", b"pass"),)),
                    repack(raw, change=change), repack(raw, reverse=True), raw + b"suffix"):
            with self.subTest(anchor=hash_bytes(bad)), self.assertRaises(bundle.BundleError):
                native_bundle.verify_native_bundle(bad, expected_sha256=hash_bytes(bad))
        with self.assertRaises(bundle.BundleError):
            native_bundle.verify_native_bundle(raw, expected_sha256="0" * 64)

    def test_all_syntactic_import_edges_and_dynamic_calls_are_checked(self):
        members, _ = native_bundle._snapshot()
        for bad in (b"\nimport requests\n", b"\nfrom research.guidance_revision_drift.evaluation import CandidateBinding\n",
                    b"\nif False:\n    from . import bad\n", b"\n__import__('requests')\n",
                    b"\nfrom AlgorithmImports import QCAlgorithm\n",
                    b"\nfrom importlib import import_module as hidden_loader\nif False:\n    hidden_loader('requests')\n",
                    b"\nimport builtins as hidden\n", b"\nloader = exec\n"):
            # AlgorithmImports is permitted ONLY in the actual entrypoint.
            path = "research/guidance_revision_drift/contracts.py"
            with self.subTest(bad=bad), self.assertRaises(bundle.BundleError):
                native_bundle._import_closure(members | {path: members[path] + bad})
        changed = members | {native_bundle.ENTRYPOINT: b"pass\n"}
        with self.assertRaises(bundle.BundleError):
            native_bundle._import_closure(changed)

    def test_offline_only_review_change_does_not_change_runtime_payload(self):
        raw = native_bundle.build_native_bundle()
        full = source_manifest()
        changed = full | {"research/guidance_revision_drift/evaluation_cycle.py": "0" * 64}
        with patch.object(native_bundle, "source_manifest", return_value=changed):
            self.assertEqual(native_bundle.build_native_bundle(), raw)
        self.assertNotEqual(hash_payload(full), hash_payload(changed))

    def test_preparation_detects_source_epoch_change_not_just_runtime_change(self):
        full = source_manifest()
        changed = full | {"research/guidance_revision_drift/evaluation_cycle.py": "0" * 64}
        with patch.object(native_bundle, "source_manifest", side_effect=[full, changed]), self.assertRaises(bundle.BundleError):
            native_bundle.build_native_bundle()


if __name__ == "__main__":
    unittest.main()
