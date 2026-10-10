"""Pinned draft integrity tests; no provider or empirical data is accessed."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from research.guidance_revision_drift import contracts
from research.guidance_revision_drift.contracts import (
    CANDIDATE_SHA256,
    MAX_CANDIDATE_BYTES,
    MAX_SOURCE_DOCUMENT_BYTES,
    Candidate,
    CandidateError,
    load_candidate,
    verify_source_documents,
)
from research.guidance_revision_drift.formulas import (
    PROPOSED_EPS_RAISE,
    PROPOSED_PRIOR_EPS_MIDPOINT_FLOOR,
    PROPOSED_REVENUE_RAISE,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPOSITORY_ROOT / "research/guidance_revision_drift/specs/gdr0a.draft.json"


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def nodes(value: object, path: tuple = ()):
    """Walk every JSON node, including containers nested in arrays."""
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from nodes(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from nodes(child, path + (index,))


def at_path(value: object, path: tuple):
    for key in path:
        value = value[key]
    return value


class CandidateContractTests(unittest.TestCase):
    def setUp(self):
        self.candidate = load_candidate()
        self.body = self.candidate.to_dict()

    def test_packaged_candidate_is_full_pinned_unreviewed_draft(self):
        self.assertEqual(self.body["schema"], "gdr.candidate.v1")
        self.assertEqual(self.body["candidate_id"], "gdr-1.0-draft")
        self.assertEqual(self.body["milestone"], "GDR-0A")
        self.assertEqual(self.body["status"], "draft_unreviewed")
        self.assertEqual(set(self.body), {
            "schema", "candidate_id", "milestone", "status", "source_documents",
            "signal", "universe", "timing", "portfolio", "execution", "exits",
            "evidence", "statistics", "unresolved", "authority",
        })
        canonical = json.dumps(
            self.body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(self.candidate.canonical_bytes, canonical)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), CANDIDATE_SHA256)
        self.assertEqual(self.candidate.sha256, CANDIDATE_SHA256)
        self.assertEqual(Candidate.from_bytes(SPEC_PATH.read_bytes()), self.candidate)
        self.assertFalse(canonical.endswith(b"\n"))

    def test_whitespace_key_order_and_unicode_escapes_do_not_change_identity(self):
        def reverse_keys(value):
            if isinstance(value, dict):
                return {key: reverse_keys(child) for key, child in reversed(list(value.items()))}
            if isinstance(value, list):
                return [reverse_keys(child) for child in value]
            return value

        for raw in (
            b" \r\n\t" + encoded(reverse_keys(self.body)) + b"\n\t",
            json.dumps(self.body, indent=4).encode("utf-8"),
            self.candidate.canonical_bytes.replace(b"gdr.candidate.v1", b"gdr.\\u0063andidate.v1"),
        ):
            with self.subTest(raw_start=raw[:50]):
                self.assertEqual(Candidate.from_bytes(raw), self.candidate)

    def test_direct_construction_requires_canonical_immutable_bytes(self):
        self.assertEqual(Candidate(self.candidate.canonical_bytes), self.candidate)
        for raw in (encoded(self.body), self.candidate.canonical_bytes + b"\n"):
            with self.subTest(raw_start=raw[:50]):
                with self.assertRaises(CandidateError):
                    Candidate(raw)
        with self.assertRaises(FrozenInstanceError):
            self.candidate.canonical_bytes = b"{}"
        self.assertFalse(hasattr(self.candidate, "__dict__"))

    def test_projection_mutations_cannot_rewrite_candidate_or_other_projection(self):
        first = self.candidate.to_dict()
        second = self.candidate.to_dict()
        first["source_documents"][0]["sha256"] = "0" * 64
        first["signal"]["release_types"].append("invented")
        first["authority"]["live_orders"] = True
        first["unresolved"].clear()
        self.assertEqual(second, self.body)
        self.assertEqual(self.candidate.to_dict(), self.body)
        self.assertEqual(self.candidate.sha256, CANDIDATE_SHA256)

    def test_every_field_is_required_and_every_object_rejects_unknown_fields(self):
        for path, value in nodes(self.body):
            if not isinstance(value, dict):
                continue
            with self.subTest(path=path, mutation="unknown"):
                changed = copy.deepcopy(self.body)
                at_path(changed, path)["unexpected"] = None
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(encoded(changed))
            for key in value:
                with self.subTest(path=path + (key,), mutation="missing"):
                    changed = copy.deepcopy(self.body)
                    del at_path(changed, path)[key]
                    with self.assertRaises(CandidateError):
                        Candidate.from_bytes(encoded(changed))

    def test_every_scalar_semantic_change_is_rejected(self):
        for path, value in nodes(self.body):
            if isinstance(value, (dict, list)):
                continue
            replacement = (
                not value if type(value) is bool else
                value + 1 if type(value) is int else
                value + "_changed" if type(value) is str else
                "caller_approved"
            )
            with self.subTest(path=path):
                changed = copy.deepcopy(self.body)
                at_path(changed, path[:-1])[path[-1]] = replacement
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(encoded(changed))

    def test_arrays_reject_missing_extra_and_reordered_items(self):
        for path, value in nodes(self.body):
            if not isinstance(value, list):
                continue
            for replacement in ([], value + ["unexpected"], list(reversed(value))):
                if replacement == value:
                    continue
                with self.subTest(path=path, replacement=replacement):
                    changed = copy.deepcopy(self.body)
                    at_path(changed, path[:-1])[path[-1]] = replacement
                    with self.assertRaises(CandidateError):
                        Candidate.from_bytes(encoded(changed))

    def test_integer_fields_reject_boolean_string_and_float_coercions(self):
        for path, value in nodes(self.body):
            if type(value) is not int:
                continue
            for replacement in (True, False, str(value), float(value)):
                with self.subTest(path=path, replacement=replacement):
                    changed = copy.deepcopy(self.body)
                    at_path(changed, path[:-1])[path[-1]] = replacement
                    with self.assertRaises(CandidateError):
                        Candidate.from_bytes(encoded(changed))

    def test_boolean_fields_reject_integer_substitutes(self):
        for path, value in nodes(self.body):
            if type(value) is not bool:
                continue
            with self.subTest(path=path):
                changed = copy.deepcopy(self.body)
                at_path(changed, path[:-1])[path[-1]] = int(value)
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(encoded(changed))

    def test_floats_nonfinite_and_giant_integers_are_rejected(self):
        for number in (b"0.0", b"1e0", b"1e999", b"NaN", b"Infinity", b"-Infinity", b"9" * 5000):
            with self.subTest(number=number[:30]):
                raw = self.candidate.canonical_bytes.replace(b'"research_looks":0', b'"research_looks":' + number)
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(raw)

    def test_duplicate_keys_rejected_even_when_same_value(self):
        for raw in (
            b'{"schema":"gdr.candidate.v1",' + self.candidate.canonical_bytes[1:],
            self.candidate.canonical_bytes.replace(b'"research_looks":0', b'"research_looks":0,"research_looks":0'),
            self.candidate.canonical_bytes.replace(b'"provider_access":false', b'"provider_access":true,"provider_access":false'),
            self.candidate.canonical_bytes.replace(b'"provider_access":false', b'"provider_access":false,"provider_access":true'),
        ):
            with self.subTest(raw_start=raw[:90]):
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(raw)

    def test_invalid_encoding_root_type_size_and_depth_fail_closed(self):
        for raw in (
            b"", "{}", bytearray(b"{}"), memoryview(b"{}"), None,
            b"\xff", b"\xef\xbb\xbf" + self.candidate.canonical_bytes,
            encoded(self.body).decode("utf-8").encode("utf-16"),
            b"[]", b"null", b"true", b"1", b'"text"',
            b"{", b"{} trailing", b'{"bad":"\\ud800"}',
            b" " * (MAX_CANDIDATE_BYTES + 1),
            b'{"deep":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}",
        ):
            with self.subTest(raw_type=type(raw).__name__, prefix=repr(raw)[:50]):
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(raw)

    def test_every_authority_is_zero_and_cannot_be_escalated(self):
        authority = self.body["authority"]
        self.assertEqual(set(authority), {
            "provider_access", "source_audit", "prospective_capture", "outcome_access",
            "research_looks", "qc_upload", "qc_processing", "qc_launch", "scheduler",
            "broker", "operator_database", "paper_orders", "live_orders", "capital",
            "inherit_sibling_permissions",
        })
        for key, value in authority.items():
            with self.subTest(authority=key):
                self.assertIs(value, 0 if key == "research_looks" else False)
                changed = copy.deepcopy(self.body)
                changed["authority"][key] = 1 if key == "research_looks" else True
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(encoded(changed))

    def test_reviews_hashes_rights_and_pit_cannot_be_caller_asserted(self):
        for field in ("sha256", "candidate_sha256", "reviewed", "owner_approved", "point_in_time_data", "rights_verified"):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.body)
                changed[field] = CANDIDATE_SHA256 if "sha256" in field else True
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(encoded(changed))
        for key, value in self.body["unresolved"].items():
            with self.subTest(unresolved=key):
                self.assertIsNone(value)
                changed = copy.deepcopy(self.body)
                changed["unresolved"][key] = {"approved": True, "sha256": CANDIDATE_SHA256}
                with self.assertRaises(CandidateError):
                    Candidate.from_bytes(encoded(changed))
        changed = copy.deepcopy(self.body)
        changed["evidence"]["historical_reconstruction_point_in_time"] = True
        with self.assertRaises(CandidateError):
            Candidate.from_bytes(encoded(changed))
        with self.assertRaises(TypeError):
            Candidate(self.candidate.canonical_bytes, sha256=CANDIDATE_SHA256)

    def test_packaged_load_missing_corrupt_and_oversized_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.json"
            with patch.object(contracts, "_SPEC_PATH", path):
                with self.assertRaises(CandidateError):
                    load_candidate()
                for raw in (b"{}", b" " * (MAX_CANDIDATE_BYTES + 1)):
                    path.write_bytes(raw)
                    with self.assertRaises(CandidateError):
                        load_candidate()
                path.write_bytes(self.candidate.canonical_bytes)
                self.assertEqual(load_candidate(), self.candidate)

    def _assert_rejected_without_open(self, callback, target):
        """Guard both current and legacy opens so FIFO regressions cannot hang."""
        original_os_open = os.open
        original_path_open = Path.open

        def guarded_os_open(path, *args, **kwargs):
            if Path(path) == target:
                raise AssertionError("invalid input must be rejected before open")
            return original_os_open(path, *args, **kwargs)

        def guarded_path_open(path, *args, **kwargs):
            if path == target:
                raise AssertionError("legacy open would consume invalid input")
            return original_path_open(path, *args, **kwargs)

        with patch.object(os, "open", side_effect=guarded_os_open), patch.object(
            Path, "open", autospec=True, side_effect=guarded_path_open,
        ):
            with self.assertRaises(CandidateError):
                callback()

    def _copy_source_documents(self, root):
        for document in self.body["source_documents"]:
            target = root / document["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPOSITORY_ROOT / document["path"]).read_bytes())

    def _assert_leaf_symlink_rejected_without_open(self, callback, target):
        # Windows may require privileges to create a native symlink. Simulate
        # its lstat mode only; still assert that neither reader opens the leaf.
        original_lstat = Path.lstat

        def symlink_lstat(path, *args, **kwargs):
            actual = original_lstat(path, *args, **kwargs)
            if path != target:
                return actual
            fields = list(actual)
            fields[0] = stat.S_IFLNK | 0o777
            return os.stat_result(fields)

        with patch.object(Path, "lstat", autospec=True, side_effect=symlink_lstat):
            self._assert_rejected_without_open(callback, target)

    def test_candidate_rejects_leaf_symlink_directory_and_oversize_before_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            targets = [root / name for name in ("symlink.json", "directory.json", "oversized.json")]
            targets[0].write_bytes(self.candidate.canonical_bytes)
            targets[1].mkdir()
            with targets[2].open("wb") as stream:
                stream.truncate(MAX_CANDIDATE_BYTES + 1)
            for target in targets:
                with self.subTest(target=target.name), patch.object(contracts, "_SPEC_PATH", target):
                    if target == targets[0]:
                        self._assert_leaf_symlink_rejected_without_open(load_candidate, target)
                    else:
                        self._assert_rejected_without_open(load_candidate, target)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "platform has no FIFO creation API")
    def test_candidate_rejects_fifo_without_blocking_open(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "candidate.fifo"
            os.mkfifo(target)
            with patch.object(contracts, "_SPEC_PATH", target):
                self._assert_rejected_without_open(load_candidate, target)

    def test_candidate_exact_size_limit_still_accepts_valid_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "candidate.json"
            target.write_bytes(self.candidate.canonical_bytes.ljust(MAX_CANDIDATE_BYTES, b" "))
            with patch.object(contracts, "_SPEC_PATH", target):
                self.assertEqual(load_candidate(), self.candidate)

    def test_both_source_documents_reject_symlink_directory_and_oversize_before_open(self):
        self.assertEqual(MAX_SOURCE_DOCUMENT_BYTES, 1_048_576)
        for document in self.body["source_documents"]:
            for kind in ("symlink", "directory", "oversized"):
                with self.subTest(document=document["path"], kind=kind), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self._copy_source_documents(root)
                    target = root / document["path"]
                    original = target.read_bytes()
                    target.unlink()
                    if kind == "symlink":
                        target.write_bytes(original)
                    elif kind == "directory":
                        target.mkdir()
                    else:
                        with target.open("wb") as stream:
                            stream.truncate(MAX_SOURCE_DOCUMENT_BYTES + 1)
                    check = (
                        self._assert_leaf_symlink_rejected_without_open if kind == "symlink"
                        else self._assert_rejected_without_open
                    )
                    check(
                        lambda: verify_source_documents(self.candidate, root), target,
                    )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "platform has no FIFO creation API")
    def test_both_source_documents_reject_fifo_without_blocking_open(self):
        for document in self.body["source_documents"]:
            with self.subTest(document=document["path"]), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._copy_source_documents(root)
                target = root / document["path"]
                target.unlink()
                os.mkfifo(target)
                self._assert_rejected_without_open(
                    lambda: verify_source_documents(self.candidate, root), target,
                )

    def test_opened_descriptor_rechecks_mode_size_and_identity_before_read(self):
        original_fstat, original_read, original_close = os.fstat, os.read, os.close
        for source_index in (None, 0, 1):
            for defect in ("nonregular", "oversized", "inode", "device"):
                with self.subTest(source_index=source_index, defect=defect), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    self._copy_source_documents(root)
                    if source_index is None:
                        target = root / "candidate.json"
                        target.write_bytes(self.candidate.canonical_bytes)
                        limit = MAX_CANDIDATE_BYTES
                    else:
                        target = root / self.body["source_documents"][source_index]["path"]
                        limit = MAX_SOURCE_DOCUMENT_BYTES
                    identity = target.stat()
                    rejected_descriptors = []

                    def altered_fstat(descriptor):
                        actual = original_fstat(descriptor)
                        if (actual.st_dev, actual.st_ino) != (identity.st_dev, identity.st_ino):
                            return actual
                        rejected_descriptors.append(descriptor)
                        fields = list(actual)
                        if defect == "nonregular":
                            fields[0] = stat.S_IFIFO | 0o600
                        elif defect == "oversized":
                            fields[6] = limit + 1
                        elif defect == "inode":
                            fields[1] += 1
                        else:
                            fields[2] += 1
                        return os.stat_result(fields)

                    def guarded_read(descriptor, length):
                        if descriptor in rejected_descriptors:
                            raise AssertionError("invalid opened descriptor must not be consumed")
                        return original_read(descriptor, length)

                    with patch.object(contracts, "_SPEC_PATH", target), patch.object(
                        os, "fstat", side_effect=altered_fstat,
                    ), patch.object(os, "read", side_effect=guarded_read), patch.object(
                        os, "close", wraps=original_close,
                    ) as closed:
                        with self.assertRaises(CandidateError):
                            if source_index is None:
                                load_candidate()
                            else:
                                verify_source_documents(self.candidate, root)
                        self.assertEqual(len(rejected_descriptors), 1)
                        closed.assert_any_call(rejected_descriptors[0])

    def test_growth_after_stat_reads_at_most_limit_plus_one_and_refuses(self):
        original_fstat, original_read, original_close = os.fstat, os.read, os.close
        for source_index in (None, 0, 1):
            with self.subTest(source_index=source_index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._copy_source_documents(root)
                if source_index is None:
                    target = root / "candidate.json"
                    target.write_bytes(self.candidate.canonical_bytes)
                    limit = MAX_CANDIDATE_BYTES
                else:
                    target = root / self.body["source_documents"][source_index]["path"]
                    limit = MAX_SOURCE_DOCUMENT_BYTES
                identity = target.stat()
                read_requests = []

                def growing_read(descriptor, length):
                    actual = original_fstat(descriptor)
                    if (actual.st_dev, actual.st_ino) != (identity.st_dev, identity.st_ino):
                        return original_read(descriptor, length)
                    read_requests.append((descriptor, length))
                    self.assertEqual(len(read_requests), 1, "must not keep reading after limit+1 bytes")
                    self.assertEqual(length, limit + 1)
                    return b" " * (limit + 1)

                with patch.object(contracts, "_SPEC_PATH", target), patch.object(
                    os, "read", side_effect=growing_read,
                ), patch.object(os, "close", wraps=original_close) as closed:
                    with self.assertRaises(CandidateError):
                        if source_index is None:
                            load_candidate()
                        else:
                            verify_source_documents(self.candidate, root)
                    self.assertEqual(len(read_requests), 1)
                    closed.assert_any_call(read_requests[0][0])

    def test_reader_regressions_detect_mocked_legacy_open_without_hanging(self):
        def legacy_reader(path, limit):
            return path.read_bytes()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_source_documents(root)
            target = root / "candidate.json"
            target.write_bytes(b" " * (MAX_CANDIDATE_BYTES + 1))
            with patch.object(contracts, "_SPEC_PATH", target), patch.object(
                contracts, "_read_regular_file", side_effect=legacy_reader,
            ):
                with self.assertRaisesRegex(AssertionError, "legacy open"):
                    self._assert_rejected_without_open(load_candidate, target)
            target = root / self.body["source_documents"][0]["path"]
            target.write_bytes(b" " * (MAX_SOURCE_DOCUMENT_BYTES + 1))
            with patch.object(contracts, "_read_regular_file", side_effect=legacy_reader):
                with self.assertRaisesRegex(AssertionError, "legacy open"):
                    self._assert_rejected_without_open(
                        lambda: verify_source_documents(self.candidate, root), target,
                    )

    def test_source_document_hashes_match_actual_plan_and_pdf(self):
        self.assertEqual(len(self.body["source_documents"]), 2)
        self.assertEqual({Path(item["path"]).suffix for item in self.body["source_documents"]}, {".md", ".pdf"})
        verify_source_documents(self.candidate, REPOSITORY_ROOT)
        for item in self.body["source_documents"]:
            raw = (REPOSITORY_ROOT / item["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])

    def test_source_document_tamper_and_missing_documents_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for document in self.body["source_documents"]:
                target = root / document["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REPOSITORY_ROOT / document["path"]).read_bytes())
            verify_source_documents(self.candidate, root)
            for document in self.body["source_documents"]:
                target = root / document["path"]
                original = target.read_bytes()
                target.write_bytes(original + b"tampered")
                with self.assertRaises(CandidateError):
                    verify_source_documents(self.candidate, root)
                target.unlink()
                with self.assertRaises(CandidateError):
                    verify_source_documents(self.candidate, root)
                target.write_bytes(original)

    def test_source_verification_rejects_duck_type_and_revalidates_bypassed_freeze(self):
        with self.assertRaises(CandidateError):
            verify_source_documents(self.body, REPOSITORY_ROOT)
        candidate = load_candidate()
        object.__setattr__(candidate, "canonical_bytes", b"{}")
        with self.assertRaises(CandidateError):
            verify_source_documents(candidate, REPOSITORY_ROOT)

    def test_spec_thresholds_match_formula_constants_and_internal_relations(self):
        signal = self.body["signal"]
        self.assertEqual(Decimal(signal["revenue_revision_min"]), PROPOSED_REVENUE_RAISE)
        self.assertEqual(Decimal(signal["eps_revision_min"]), PROPOSED_EPS_RAISE)
        self.assertEqual(Decimal(signal["prior_eps_midpoint_min_usd"]), PROPOSED_PRIOR_EPS_MIDPOINT_FLOOR)
        timing = self.body["timing"]
        self.assertEqual(timing["scheduled_exit_session_number"] - timing["entry_session_number"], timing["holding_session_intervals"])
        self.assertLess(timing["entry_time"], timing["cancel_entry_remainder_time"])
        self.assertEqual(self.body["execution"]["evaluation"], "order_based")
        self.assertEqual(self.body["execution"]["max_unsuccessful_qc_attempts_per_candidate"], 3)
        self.assertEqual(self.body["statistics"]["maximum_base_drawdown"], self.body["exits"]["close_based_program_drawdown_fraction"])
        self.assertLessEqual(Decimal(self.body["portfolio"]["position_fraction_max"]), Decimal(self.body["portfolio"]["sector_fraction_max"]))
        self.assertLessEqual(Decimal(self.body["portfolio"]["sector_fraction_max"]), Decimal(self.body["portfolio"]["gross_fraction_max"]))


if __name__ == "__main__":
    unittest.main()
