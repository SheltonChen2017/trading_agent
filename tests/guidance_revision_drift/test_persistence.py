"""Focused synthetic journal corruption, CAS and crash-boundary tests."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.persistence import (
    JournalConflict, JournalError, LocalJournal, PublicationUncertain, canonical_object,
)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # The storage layer keeps genesis opaque; RecoveryEngine validates its
        # domain/session semantics before execution.
        self.genesis = canonical_object({"schema": "gdr.synthetic.recovery-genesis.v1", "fixture": "SYN-STORE"})
        self.store = LocalJournal.create(self.root, self.genesis)
        self.head = hash_bytes(self.genesis)

    def append(self, *, store=None, head=None, identity="SYN-C1", value=1):
        return (store or self.store).append(expected_head=head or self.head, command_id=identity,
            operation="advance", arguments={"fixture": value}, result=None, post_state_sha256="a" * 64)

    def test_append_reopen_and_exact_duplicate_are_immutable(self):
        first = self.append()
        self.assertEqual(self.append(), first)
        opened = LocalJournal.open(self.root, expected_genesis_sha256=self.head)
        self.assertEqual(opened.read(expected_head=first.sha256).records, (first,))
        projection = first.to_dict()
        projection["arguments"]["fixture"] = 3
        self.assertEqual(first.to_dict()["arguments"], {"fixture": 1})
        self.assertEqual(len(list(self.root.glob("command-*.json"))), 1)

    def test_stale_writer_and_conflicting_command_identity_refuse(self):
        first = self.append()
        with self.assertRaises(JournalConflict):
            self.append(identity="SYN-C2")
        with self.assertRaises(JournalConflict):
            self.append(value=2)
        second = self.append(head=first.sha256, identity="SYN-C2")
        self.assertEqual(self.store.read(expected_head=first.sha256).head_sha256, second.sha256)

    def test_concurrent_sequence_claim_has_one_winner_without_overwrite(self):
        barrier = threading.Barrier(2)
        from research.guidance_revision_drift import persistence
        real = persistence._publish

        def synchronize(directory, name, raw):
            if name.startswith("command-"):
                barrier.wait(timeout=5)
            return real(directory, name, raw)

        def attempt(identity):
            try:
                return self.append(identity=identity)
            except JournalConflict:
                return None

        with patch.object(persistence, "_publish", synchronize), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ("SYN-A", "SYN-B")))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(len(self.store.read(expected_head=self.head).records), 1)

    def test_failed_write_or_link_never_commits_partial_command(self):
        for target in ("os.write", "os.link"):
            with self.subTest(target=target), patch(target, side_effect=OSError("fixture interruption")):
                with self.assertRaises(JournalError):
                    self.append()
            self.assertEqual(self.store.read(expected_head=self.head).records, ())
            self.assertEqual(list(self.root.glob(".gdr-journal-*")), [])

    def test_file_fsync_failure_is_before_publication(self):
        with patch("os.fsync", side_effect=OSError("fixture failure")):
            with self.assertRaises(JournalError) as caught:
                self.append()
        self.assertNotIsInstance(caught.exception, PublicationUncertain)
        self.assertEqual(self.store.read(expected_head=self.head).records, ())

    def test_directory_sync_failure_is_explicitly_ambiguous_and_reloadable(self):
        with patch("research.guidance_revision_drift.persistence._sync_directory", side_effect=OSError("fixture crash")):
            with self.assertRaises(PublicationUncertain):
                self.append()
        view = self.store.read(expected_head=self.head)
        self.assertEqual(len(view.records), 1)
        with patch("research.guidance_revision_drift.persistence._sync_directory", side_effect=OSError("still unavailable")):
            with self.assertRaises(PublicationUncertain):
                self.append()
        self.assertEqual(self.append(), view.records[0])
        self.assertEqual(len(self.store.read(expected_head=self.head).records), 1)

    def test_lost_link_acknowledgment_is_ambiguous_not_a_false_rejection(self):
        real_link = os.link

        def lost_ack(source, destination):
            real_link(source, destination)
            raise OSError("synthetic interruption after successful link")

        with patch("os.link", lost_ack), self.assertRaises(PublicationUncertain):
            self.append()
        self.assertEqual(len(self.store.read(expected_head=self.head).records), 1)
        self.append()
        self.assertEqual(len(self.store.read(expected_head=self.head).records), 1)

    def test_genesis_and_command_tampering_refuse_without_overwrite(self):
        first = self.append()
        path = self.root / "command-000001.json"
        path.write_bytes(b"damaged")
        with self.assertRaises(JournalError):
            self.store.read(expected_head=first.sha256)
        with self.assertRaises(JournalError):
            self.append()
        self.assertEqual(path.read_bytes(), b"damaged")
        (self.root / "genesis.json").write_bytes(b"damaged genesis")
        with self.assertRaises(JournalError):
            LocalJournal.open(self.root, expected_genesis_sha256=self.head)

    def test_missing_middle_and_truncated_tail_detected_against_retained_anchor(self):
        first = self.append()
        second = self.append(head=first.sha256, identity="SYN-C2")
        path = self.root / "command-000001.json"
        raw = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(JournalError, "sequence"):
            self.store.read(expected_head=second.sha256)
        path.write_bytes(raw)
        (self.root / "command-000002.json").unlink()
        with self.assertRaisesRegex(JournalError, "retained head"):
            self.store.read(expected_head=second.sha256)
        self.assertEqual(self.store.read(expected_head=first.sha256).head_sha256, first.sha256)

    def test_wrong_chain_epoch_sequence_and_result_hash_refuse(self):
        record = self.append()
        path = self.root / "command-000001.json"
        for field, value in (("previous_sha256", "b" * 64), ("genesis_sha256", "b" * 64),
                             ("sequence", True), ("result_sha256", "c" * 64)):
            body = record.to_dict()
            body[field] = value
            path.write_bytes(canonical_object(body))
            with self.subTest(field=field), self.assertRaises(JournalError):
                self.store.read(expected_head=self.head)
        path.write_bytes(record.canonical_bytes)

    def test_checkpoint_content_and_sequence_are_verified(self):
        first = self.append()
        checkpoint = self.store.checkpoint(expected_head=first.sha256, state_sha256="a" * 64)
        self.assertEqual(self.store.read_checkpoint(checkpoint)["head_sha256"], first.sha256)
        with self.assertRaises(JournalError):
            self.store.checkpoint(expected_head=first.sha256, state_sha256="b" * 64)
        path = self.root / f"checkpoint-{checkpoint}.json"
        path.write_bytes(b"damaged")
        with self.assertRaises(JournalError):
            self.store.read_checkpoint(checkpoint)

    def test_nonregular_unknown_and_excessive_input_refuses(self):
        for args in ({"float": 1.0}, {"oversize": "x" * 65536}):
            with self.assertRaises(JournalError):
                self.store.append(expected_head=self.head, command_id="SYN-X", operation="advance",
                                  arguments=args, result=None, post_state_sha256="a" * 64)
        self.assertEqual(self.store.read(expected_head=self.head).records, ())
        path = self.root / "command-000001.json"
        path.symlink_to(self.root / "genesis.json")
        with self.assertRaises(JournalError):
            self.store.read(expected_head=self.head)
        path.unlink()
        (self.root / "unexpected").write_bytes(b"x")
        with self.assertRaises(JournalError):
            self.store.read(expected_head=self.head)

    def test_strict_canonical_json_and_invalid_genesis(self):
        for raw in (b'{"schema":1,"schema":2}', b'{"n":NaN}', b'{"n":1.0}', b'{}'):
            with self.assertRaises(JournalError):
                LocalJournal.create(self.root, raw)
        with self.assertRaises(JournalConflict):
            LocalJournal.create(self.root, canonical_object({"schema": "gdr.synthetic.recovery-genesis.v1", "changed": True}))


if __name__ == "__main__":
    unittest.main()
