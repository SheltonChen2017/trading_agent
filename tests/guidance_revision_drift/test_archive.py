"""Synthetic archive identity/tamper tests, never real capture or availability."""
from __future__ import annotations

import copy
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.archive import ArchiveError, FixtureArchive
from research.guidance_revision_drift.events import NormalizedDisclosure


def disclosure(identity="SYN-D1", *, day="2025-01-02", revenue="100", eps="1", **changes):
    values = {"schema": "gdr.synthetic.disclosure.v1", "issuer_id": "SYN-ISSUER-A",
        "disclosure_id": identity, "version": 1, "kind": "disclosure", "published_at": f"{day}T12:00:00Z",
        "received_at": f"{day}T12:01:00Z", "validated_at": f"{day}T12:02:00Z", "supersedes": None,
        "release_type": "official", "positioning": "primary", "metadata": "synthetic example only",
        "periods": [{"fiscal_year": 2025, "fiscal_start": "2025-01-01", "fiscal_end": "2025-12-31",
            "period": "FY", "currency": "USD", "revenue_units": "USD_millions", "eps_units": "USD_per_share",
            "revenue_basis": "gaap", "eps_basis": "adj", "adjustment_definition": "adj-v1",
            "share_basis": "shares-v1", "scope": "organic-v1",
            "revenue": {"lower": revenue, "upper": revenue, "kind": "point"},
            "eps": {"lower": eps, "upper": eps, "kind": "point"}}]}
    values.update(changes)
    return NormalizedDisclosure.from_dict(values)


def archive():
    return FixtureArchive().append(disclosure(), bootstrap=True).append(
        disclosure("SYN-D2", day="2025-02-03", revenue="102", eps="1.05"))


def encoded(values):
    return canonical_json(values).encode("utf-8")


class FixtureArchiveTests(unittest.TestCase):
    def test_empty_and_populated_roundtrip_use_retained_head_checkpoint(self):
        for original in (FixtureArchive(), archive()):
            restored = FixtureArchive.from_bytes(original.to_bytes(), expected_head=original.head_sha256)
            self.assertEqual(restored, original)
            self.assertEqual(restored.to_bytes(), original.to_bytes())
        self.assertEqual(archive().book.decisions[-1].disposition, "candidate")

    def test_append_preserves_old_value_and_returns_hash_chained_new_value(self):
        first = FixtureArchive().append(disclosure(), bootstrap=True)
        old_bytes, old_head = first.to_bytes(), first.head_sha256
        second = first.append(disclosure("SYN-D2", day="2025-02-03", revenue="102", eps="1.05"))
        self.assertEqual(first.to_bytes(), old_bytes)
        self.assertEqual(second.to_dict()["entries"][1]["previous_sha256"], old_head)
        self.assertNotEqual(first.head_sha256, second.head_sha256)

    def test_duplicates_are_idempotent_but_cannot_change_bootstrap_role(self):
        original = archive()
        self.assertEqual(original.append(original.entries[-1][0]), original)
        self.assertEqual(original.append(original.entries[0][0], bootstrap=True), original)
        with self.assertRaisesRegex(ArchiveError, "bootstrap"):
            original.append(original.entries[0][0], bootstrap=False)
        with self.assertRaisesRegex(ArchiveError, "duplicate"):
            FixtureArchive(original.entries + (original.entries[-1],))

    def test_conflicting_record_is_retained_and_replayed_as_quarantine(self):
        original = archive()
        changed = original.append(disclosure("SYN-D2", day="2025-02-03", revenue="103", eps="1.1"))
        self.assertEqual(len(changed.entries), 3)
        restored = FixtureArchive.from_bytes(changed.to_bytes(), expected_head=changed.head_sha256)
        self.assertEqual(restored.book.decisions[-1].disposition, "quarantined")
        self.assertEqual(restored.book.decisions[-1].invalidated_disclosure_ids, ("SYN-D2",))

    def test_payload_chain_sequence_and_metadata_tampering_refuse(self):
        original = archive()
        for edit in (
            lambda values: values["entries"][0]["record"].update(metadata="modified"),
            lambda values: values["entries"][0].update(record_sha256="0" * 64),
            lambda values: values["entries"][1].update(previous_sha256="0" * 64),
            lambda values: values["entries"][1].update(sequence=3),
            lambda values: values["entries"][0].update(sequence=True),
            lambda values: values["entries"][0].update(bootstrap=False),
            lambda values: values["entries"][0].update(entry_sha256="0" * 64),
            lambda values: values.update(head_sha256="0" * 64),
        ):
            values = original.to_dict()
            edit(values)
            with self.subTest(values=values), self.assertRaises(ArchiveError):
                FixtureArchive.from_bytes(encoded(values), expected_head=original.head_sha256)

    def test_truncation_is_detected_even_with_recomputed_internal_head(self):
        original = archive()
        truncated = original.to_dict()
        truncated["entries"].pop()
        truncated["head_sha256"] = truncated["entries"][-1]["entry_sha256"]
        with self.assertRaisesRegex(ArchiveError, "checkpoint"):
            FixtureArchive.from_bytes(encoded(truncated), expected_head=original.head_sha256)

    def test_reordering_and_duplicate_entry_cannot_replay(self):
        original = archive()
        for changes in (list(reversed(original.to_dict()["entries"])),
                        original.to_dict()["entries"] + original.to_dict()["entries"][-1:]):
            values = original.to_dict()
            values["entries"] = changes
            with self.assertRaises(ArchiveError):
                FixtureArchive.from_bytes(encoded(values), expected_head=original.head_sha256)

    def test_rechained_duplicate_payload_is_rejected(self):
        original = archive()
        values = original.to_dict()
        duplicate = copy.deepcopy(values["entries"][-1])
        duplicate.update(sequence=3, previous_sha256=values["head_sha256"])
        del duplicate["entry_sha256"]
        duplicate["entry_sha256"] = hash_bytes(encoded(duplicate))
        values["entries"].append(duplicate)
        values["head_sha256"] = duplicate["entry_sha256"]
        with self.assertRaisesRegex(ArchiveError, "duplicate"):
            FixtureArchive.from_bytes(encoded(values), expected_head=values["head_sha256"])

    def test_unknown_fields_authority_provenance_and_types_refuse(self):
        original = archive()
        for edit in (
            lambda values: values.update(point_in_time_data=True),
            lambda values: values.update(provenance="verified_prospective"),
            lambda values: values.update(schema="gdr.real.archive.v1"),
            lambda values: values["entries"][0].update(approved=True),
            lambda values: values["entries"][0].update(bootstrap=1),
            lambda values: values.update(entries={}),
        ):
            values = original.to_dict()
            edit(values)
            with self.subTest(values=values), self.assertRaises(ArchiveError):
                FixtureArchive.from_bytes(encoded(values), expected_head=original.head_sha256)

    def test_malformed_json_and_hash_resource_limits_refuse(self):
        for raw in (b'{"schema":1,"schema":2}', b'{"n":1.0}', b'{"n":Infinity}', b"\xff", b"x" * 8_388_609,
                    b"[" * 2000 + b"]" * 2000, bytearray(b"{}")):
            with self.subTest(kind=type(raw)), self.assertRaises(ArchiveError):
                FixtureArchive.from_bytes(raw, expected_head="0" * 64)
        for head in (None, True, "ABC", "A" * 64):
            with self.subTest(head=head), self.assertRaises(ArchiveError):
                FixtureArchive.from_bytes(archive().to_bytes(), expected_head=head)

    def test_caller_projection_and_record_mutation_cannot_change_archive(self):
        original = disclosure()
        result = FixtureArchive().append(original, bootstrap=True)
        raw = result.to_bytes()
        object.__setattr__(original, "canonical_bytes", b"{}")
        projection = result.to_dict()
        projection["entries"].clear()
        self.assertEqual(result.to_bytes(), raw)
        with self.assertRaises(FrozenInstanceError):
            result.entries = ()
        with self.assertRaises(ArchiveError):
            result.append(original)

    def test_forged_archive_revalidates_before_every_output(self):
        result = archive()
        object.__setattr__(result, "entries", ((disclosure(), "yes"),))
        for action in (result.to_bytes, result.to_dict, lambda: result.head_sha256,
                       lambda: result.append(disclosure())):
            with self.subTest(action=action), self.assertRaises(ArchiveError):
                action()

    def test_resource_limit_and_bad_input_types_refuse(self):
        with self.assertRaises(ArchiveError):
            FixtureArchive(tuple((disclosure(), True) for _ in range(257)))
        for wrong in (None, {}, b"{}"):
            with self.assertRaises(ArchiveError):
                FixtureArchive().append(wrong)
        with self.assertRaises(ArchiveError):
            FixtureArchive().append(disclosure(), bootstrap=1)

    def test_pure_archive_roundtrip_does_not_access_files_environment_or_network(self):
        original = archive()
        with patch("builtins.open", side_effect=AssertionError("file access")), \
             patch("os.getenv", side_effect=AssertionError("environment")), \
             patch("socket.socket", side_effect=AssertionError("network")):
            restored = FixtureArchive.from_bytes(original.to_bytes(), expected_head=original.head_sha256)
        self.assertEqual(restored, original)


if __name__ == "__main__":
    unittest.main()
