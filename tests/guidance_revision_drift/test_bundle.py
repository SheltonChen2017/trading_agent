"""Bounded offline archive preparation; no extraction, engine or cloud run."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import stat
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift import bundle
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.lean_bridge import fixture_stream


def repack(raw, *, change=None, omit=(), extra=(), reverse=False, compression=None):
    """Deliberately manufacture untrusted archives, without extracting them."""
    target = BytesIO()
    with ZipFile(BytesIO(raw)) as source, ZipFile(target, "w", allowZip64=False) as output:
        infos = source.infolist()
        if reverse:
            infos.reverse()
        for original in infos:
            if original.filename in omit:
                continue
            info = deepcopy(original)
            data = source.read(original)
            if change:
                info, data = change(info, data)
            if compression is not None:
                info.compress_type = compression
            output.writestr(info, data)
        for name, data in extra:
            info = ZipInfo(name, date_time=bundle._DATE)
            info.create_system = 3
            info.external_attr = bundle._FILE_MODE
            output.writestr(info, data)
    return target.getvalue()


class BundleTests(unittest.TestCase):
    def setUp(self):
        # Each test pins one actual source snapshot while other agents may be
        # editing unrelated lane files. The separate roundtrip test below does
        # not mock source reconstruction; the parent reruns after source freeze.
        members, manifest = bundle._snapshot()
        self.members = members
        self.manifest = manifest
        self.snapshot = patch.object(bundle, "_snapshot", side_effect=lambda: (
            dict(self.members), deepcopy(self.manifest)))
        self.snapshot.start()
        self.addCleanup(self.snapshot.stop)
        self.raw = bundle.build_bundle()

    def assert_refused(self, raw):
        with self.assertRaises(bundle.BundleError):
            bundle.verify_bundle(raw, expected_sha256=hash_bytes(raw))

    def test_actual_current_source_reconstructs_deterministically(self):
        self.snapshot.stop()
        raw = bundle.build_bundle()
        self.assertEqual(bundle.build_bundle(), raw)
        receipt = bundle.verify_bundle(raw, expected_sha256=hash_bytes(raw))
        self.assertEqual(receipt["manifest"]["candidate_sha256"], CANDIDATE_SHA256)
        self.assertEqual(receipt["manifest"], bundle.bundle_manifest())
        self.assertEqual(receipt["bytes"], len(raw))
        for field in ("qc_upload_allowed", "qc_launch_allowed", "native_runtime_verified", "market_evidence"):
            self.assertIs(receipt[field], False)
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(archive.read(bundle.SIDECAR_PATH), fixture_stream())
            self.assertEqual(set(archive.namelist()), bundle._SOURCE_PATHS | {
                bundle.SIDECAR_PATH, bundle.MANIFEST_PATH})
            for info in archive.infolist():
                self.assertEqual(info.compress_type, ZIP_STORED)
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.external_attr >> 16, stat.S_IFREG | 0o444)
        self.assertNotIn("python_version", receipt["manifest"])
        self.assertFalse(receipt["manifest"]["SDK_included"])
        self.assertFalse(receipt["manifest"]["planning_documents_included"])

    def test_wrong_anchor_refuses_before_source_reconstruction(self):
        with patch.object(bundle, "_snapshot", side_effect=AssertionError("must not read")):
            for anchor in ("0" * 64, "F" * 64, "", None, 123):
                with self.subTest(anchor=anchor), self.assertRaisesRegex(bundle.BundleError, "anchor"):
                    bundle.verify_bundle(self.raw, expected_sha256=anchor)

    def test_type_empty_and_oversize_refuse(self):
        for raw in (None, bytearray(self.raw), "zip", b"", b"x" * (bundle.MAX_BUNDLE_BYTES + 1)):
            with self.subTest(kind=type(raw)), self.assertRaises(bundle.BundleError):
                bundle.verify_bundle(raw, expected_sha256="0" * 64)

    def test_missing_extra_duplicate_and_reordered_members_refuse(self):
        bad = [repack(self.raw, omit=(bundle.SIDECAR_PATH,)),
               repack(self.raw, extra=(("extra.py", b"pass"),)),
               repack(self.raw, reverse=True)]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            bad.append(repack(self.raw, extra=((bundle.SIDECAR_PATH, b"duplicate"),)))
        for raw in bad:
            with self.subTest(sha=hash_bytes(raw)):
                self.assert_refused(raw)

    def test_traversal_absolute_windows_and_backslash_names_refuse(self):
        for name in ("../outside.py", "/outside.py", "C:/outside.py", "x\\outside.py",
                     "x//outside.py", "x/./outside.py"):
            with self.subTest(name=name):
                self.assert_refused(repack(self.raw, extra=((name, b"unsafe"),)))

    def test_compression_and_oversized_advertised_member_refuse_before_read(self):
        compressed = repack(self.raw, compression=ZIP_DEFLATED)
        def enlarge(info, raw):
            if info.filename == bundle.SIDECAR_PATH:
                raw = b"x" * (bundle.MAX_SOURCE_DOCUMENT_BYTES + 1)
            return info, raw
        oversized = repack(self.raw, change=enlarge)
        for raw in (compressed, oversized):
            with self.subTest(sha=hash_bytes(raw)), patch.object(
                    ZipFile, "read", side_effect=AssertionError("unsafe members must not be read")):
                self.assert_refused(raw)

    def test_symlink_and_noncanonical_metadata_refuse(self):
        for attribute, value in (("external_attr", (stat.S_IFLNK | 0o777) << 16),
                                 ("date_time", (2025, 1, 1, 0, 0, 0)),
                                 ("comment", b"hidden"), ("extra", b"\x01\x00\x00\x00"),
                                 ("create_system", 0), ("internal_attr", 1)):
            def change(info, raw):
                if info.filename == bundle.SIDECAR_PATH:
                    setattr(info, attribute, value)
                return info, raw
            with self.subTest(attribute=attribute):
                self.assert_refused(repack(self.raw, change=change))

    def test_altered_source_and_sidecar_cannot_self_certify(self):
        for path in ("research/guidance_revision_drift/lean/main.py", bundle.SIDECAR_PATH):
            def alter(info, raw):
                if info.filename == path:
                    raw += b"\n# forged bytes"
                return info, raw
            with self.subTest(path=path):
                self.assert_refused(repack(self.raw, change=alter))

    def test_rehashed_consistent_member_manifest_forgery_refuses(self):
        forged = dict(self.members)
        forged[bundle.SIDECAR_PATH] = b"forged\n"
        manifest = deepcopy(self.manifest)
        manifest["members"][bundle.SIDECAR_PATH] = {
            "sha256": hash_bytes(forged[bundle.SIDECAR_PATH]), "bytes": len(forged[bundle.SIDECAR_PATH])}
        forged[bundle.MANIFEST_PATH] = canonical_json(manifest).encode()
        self.assert_refused(bundle._archive(forged))

    def test_manifest_unknown_authority_boolean_alias_and_noncanonical_bytes_refuse(self):
        bad = []
        for field, value in (("qc_launch_allowed", True), ("qc_launch_allowed", 0),
                             ("unknown", "extra"), ("candidate_sha256", "a" * 64)):
            manifest = deepcopy(self.manifest)
            manifest[field] = value
            bad.append(canonical_json(manifest).encode())
        canonical = canonical_json(self.manifest).encode()
        bad += [canonical + b"\n", b'{"schema":"x","schema":"x"}', b'{"x":NaN}']
        for altered in bad:
            def change(info, raw):
                return info, altered if info.filename == bundle.MANIFEST_PATH else raw
            with self.subTest(altered=altered[:50]):
                self.assert_refused(repack(self.raw, change=change))

    def test_nonzip_prefix_suffix_and_corrupted_member_refuse(self):
        bad = [b"not an archive", b"prefix" + self.raw, self.raw + b"suffix"]
        damaged = bytearray(self.raw)
        with ZipFile(BytesIO(self.raw)) as archive:
            info = archive.getinfo(bundle.SIDECAR_PATH)
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        damaged[offset] ^= 1
        bad.append(bytes(damaged))
        for raw in bad:
            with self.subTest(sha=hash_bytes(raw)):
                self.assert_refused(raw)

    def test_malformed_filename_and_parser_errors_have_bounded_refusal(self):
        malformed = bytearray(self.raw)
        # Claim UTF-8 while supplying an invalid byte in both local/central
        # names. The standard library raises UnicodeDecodeError on opening.
        for signature, flags_offset, name_offset in ((b"PK\x03\x04", 6, 30), (b"PK\x01\x02", 8, 46)):
            offset = malformed.index(signature)
            flags = int.from_bytes(malformed[offset + flags_offset:offset + flags_offset + 2], "little") | 0x800
            malformed[offset + flags_offset:offset + flags_offset + 2] = flags.to_bytes(2, "little")
            malformed[offset + name_offset] = 0xff
        self.assert_refused(bytes(malformed))
        for error in (struct.error("bad header"), ValueError("bad metadata"), EOFError("truncated")):
            with self.subTest(error=type(error)), patch.object(bundle, "ZipFile", side_effect=error):
                self.assert_refused(self.raw)

    def test_source_inventory_extension_or_changed_source_epoch_refuses(self):
        self.snapshot.stop()
        real_manifest = bundle.source_manifest()
        with patch.object(bundle, "source_manifest", return_value=real_manifest | {"secret.py": "a" * 64}):
            with self.assertRaisesRegex(bundle.BundleError, "inventory"):
                bundle.build_bundle()
        changed = dict(real_manifest)
        changed["research/guidance_revision_drift/lean/main.py"] = "a" * 64
        with patch.object(bundle, "source_manifest", side_effect=[real_manifest, changed]):
            with self.assertRaisesRegex(bundle.BundleError, "source changed"):
                bundle.build_bundle()
        with patch.object(bundle, "source_manifest", return_value=changed):
            with self.assertRaisesRegex(bundle.BundleError, "source changed"):
                bundle.build_bundle()

    def test_publication_idempotent_atomic_and_no_staging_remains(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = bundle.publish_bundle(root, self.raw)
            self.assertEqual(path.name, hash_bytes(self.raw) + ".zip")
            self.assertEqual(path.read_bytes(), self.raw)
            self.assertEqual(bundle.publish_bundle(root, self.raw), path)
            self.assertEqual(list(root.iterdir()), [path])

    def test_publication_concurrent_identical_calls_are_idempotent(self):
        with TemporaryDirectory() as temporary, ThreadPoolExecutor(max_workers=4) as pool:
            root = Path(temporary).resolve()
            paths = list(pool.map(lambda _: bundle.publish_bundle(root, self.raw), range(8)))
            self.assertEqual(len(set(paths)), 1)
            self.assertEqual(paths[0].read_bytes(), self.raw)
            self.assertEqual(list(root.iterdir()), [paths[0]])

    def test_tampered_existing_bundle_never_overwritten(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = bundle.publish_bundle(root, self.raw)
            path.write_bytes(b"tampered")
            with self.assertRaises(bundle.BundleError):
                bundle.publish_bundle(root, self.raw)
            self.assertEqual(path.read_bytes(), b"tampered")
            self.assertEqual(list(root.iterdir()), [path])

    def test_missing_nondirectory_symlink_directory_and_leaf_refuse(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaises(bundle.BundleError):
                bundle.publish_bundle(root / "missing", self.raw)
            directory = root / "real"
            directory.mkdir()
            redirect = root / "redirect"
            redirect.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(bundle.BundleError):
                bundle.publish_bundle(redirect, self.raw)
            target = root / "target.zip"
            target.write_bytes(self.raw)
            with self.assertRaises(bundle.BundleError):
                bundle.publish_bundle(target, self.raw)
            destination = directory / (hash_bytes(self.raw) + ".zip")
            destination.symlink_to(target)
            with self.assertRaises(bundle.BundleError):
                bundle.publish_bundle(directory, self.raw)
            self.assertTrue(destination.is_symlink())
            self.assertEqual(target.read_bytes(), self.raw)
            destination.unlink()
            destination.mkdir()
            with self.assertRaises(bundle.BundleError):
                bundle.publish_bundle(directory, self.raw)
            self.assertTrue(destination.is_dir())

    def test_invalid_archive_refused_before_creating_staging_file(self):
        with TemporaryDirectory() as temporary:
            with patch.object(bundle.tempfile, "mkstemp", side_effect=AssertionError("must not stage")):
                with self.assertRaises(bundle.BundleError):
                    bundle.publish_bundle(Path(temporary), b"bad")
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_file_sync_failure_has_no_publication(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(bundle.os, "fsync", side_effect=OSError("synthetic failed file sync")):
                with self.assertRaises(bundle.BundleError) as caught:
                    bundle.publish_bundle(root, self.raw)
            self.assertNotIsInstance(caught.exception, bundle.BundlePublicationUncertain)
            self.assertEqual(list(root.iterdir()), [])

    def test_postlink_sync_failure_is_ambiguous_and_identical_retry_recovers(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(bundle, "_sync_directory", side_effect=OSError("synthetic lost acknowledgement")):
                with self.assertRaises(bundle.BundlePublicationUncertain):
                    bundle.publish_bundle(root, self.raw)
            destination = root / (hash_bytes(self.raw) + ".zip")
            self.assertEqual(destination.read_bytes(), self.raw)
            self.assertEqual(list(root.iterdir()), [destination])
            self.assertEqual(bundle.publish_bundle(root, self.raw), destination)

    def test_failed_staging_cleanup_does_not_misreport_synced_publication(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(Path, "unlink", side_effect=OSError("synthetic cleanup failure")):
                path = bundle.publish_bundle(root, self.raw)
            self.assertEqual(path.read_bytes(), self.raw)
            remnants = [item for item in root.iterdir() if item != path]
            self.assertEqual(len(remnants), 1)
            self.assertTrue(remnants[0].name.startswith(".gdr-bundle-"))
            self.assertTrue(remnants[0].name.endswith(".staging"))
            self.assertEqual(bundle.publish_bundle(root, self.raw), path)


if __name__ == "__main__":
    unittest.main()
