from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.guidance_revision_drift.artifacts import (
    FixtureArtifactError, publish_fixture, read_fixture,
)
from research.guidance_revision_drift.controls import FixtureEpoch, FixtureLedger


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.raw = FixtureLedger(FixtureEpoch("a" * 64, "b" * 64, "c" * 64)).to_bytes()

    def test_immutable_idempotent_roundtrip_no_staging_left(self):
        path = publish_fixture(self.root, self.raw)
        self.assertEqual(read_fixture(path), self.raw)
        self.assertEqual(publish_fixture(self.root, self.raw), path)
        self.assertEqual([item.resolve() for item in self.root.iterdir()], [path])

    def test_concurrent_identical_publication(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths = list(pool.map(lambda _: publish_fixture(self.root, self.raw), range(8)))
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(read_fixture(paths[0]), self.raw)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_tampered_existing_is_never_overwritten(self):
        path = publish_fixture(self.root, self.raw)
        path.write_bytes(b"tampered")
        with self.assertRaises(FixtureArtifactError):
            publish_fixture(self.root, self.raw)
        self.assertEqual(path.read_bytes(), b"tampered")
        with self.assertRaises(FixtureArtifactError):
            read_fixture(path)

    def test_failed_link_does_not_publish_partial_file(self):
        with patch("os.link", side_effect=OSError("synthetic failure")):
            with self.assertRaises(FixtureArtifactError):
                publish_fixture(self.root, self.raw)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_schemas_duplicate_float_and_oversize_refuse_before_write(self):
        for raw in (b'{"schema":"real"}', b'{"schema":"gdr.synthetic.x","a":1.0}',
                    b'{"schema":"gdr.synthetic.x","a":1,"a":2}', b" " * 65537, "{}"):
            with self.subTest(raw=repr(raw)[:50]), self.assertRaises(FixtureArtifactError):
                publish_fixture(self.root, raw)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_directory_or_nonregular_target_refuses(self):
        with self.assertRaises(FixtureArtifactError):
            publish_fixture(self.root / "absent", self.raw)
        path = publish_fixture(self.root, self.raw)
        path.unlink()
        path.mkdir()
        with self.assertRaises(FixtureArtifactError):
            publish_fixture(self.root, self.raw)


if __name__ == "__main__":
    unittest.main()
