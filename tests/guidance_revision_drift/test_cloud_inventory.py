"""Complete invented cloud maps; opaque files never become accepted source."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from data.hashing import hash_payload
from research.guidance_revision_drift import cloud_inventory as module


def expected():
    return {"main.py": b"# invented unchanged economics\n", "gdr_payload_000.py": b"_GDR_B64='AA=='\n"}


def expected_anchor(files):
    return hash_payload({name: {key: row[key] for key in ("bytes", "sha256")}
                         for name, row in module.cloud_file_inventory(files).items()})


class CloudInventoryTests(unittest.TestCase):
    def compare(self, supplied=None, *, local=None, before=None, after=None):
        retained = expected() if local is None else local
        returned = retained if supplied is None else supplied
        return module.compare_cloud_inventory(retained, returned,
            expected_project_sha256=expected_anchor(retained) if before is None else before,
            expected_returned_sha256=module.cloud_inventory_anchor(returned) if after is None else after)

    def test_exact_python_and_complete_opaque_notebook_inventory_are_distinct(self):
        report = self.compare()
        self.assertTrue(report["python_byte_identical"])
        self.assertFalse(report["quarantined"])
        for key in ("current_local_content_checked", "external_provenance_verified", "automatic_port_allowed",
                    "economic_acceptance", "qc_launch_allowed", "market_evidence"):
            self.assertIs(report[key], False)
        returned = expected() | {"research.ipynb": b"\x00\xffopaque notebook; do not parse",
                                 "neighbor.bin": b"\x80\x04not a pickle to load"}
        with patch("json.loads", side_effect=AssertionError("opaque files not parsed")), \
             patch("pickle.loads", side_effect=AssertionError("opaque files not loaded")):
            report = self.compare(returned)
        self.assertTrue(report["python_byte_identical"])
        self.assertTrue(report["quarantined"])
        self.assertEqual(report["opaque_quarantine"], ["neighbor.bin", "research.ipynb"])
        self.assertEqual(set(report["returned_files"]), set(returned))
        self.assertEqual(report["returned_files"]["research.ipynb"]["classification"], "quarantined_notebook")
        self.assertEqual(report["returned_inventory_sha256"], module.cloud_inventory_anchor(returned))
        self.assertNotEqual(module.cloud_inventory_anchor(expected()), report["returned_inventory_sha256"])

    def test_every_missing_extra_changed_python_file_and_diff_is_retained(self):
        returned = {"main.py": b"# altered economics quarantine\n", "unreviewed.py": b"raise RuntimeError('never run')\n",
                    "research.ipynb": b"not JSON"}
        report = self.compare(returned)
        self.assertEqual(report["python_changes"], ["gdr_payload_000.py", "main.py", "unreviewed.py"])
        by_name = {row["name"]: row for row in report["changes"]}
        self.assertEqual(by_name["gdr_payload_000.py"]["status"], "missing")
        self.assertEqual(by_name["unreviewed.py"]["status"], "extra")
        self.assertEqual(by_name["main.py"]["status"], "changed")
        self.assertIn("-# invented unchanged economics", by_name["main.py"]["unified_diff"])
        self.assertIn("+# altered economics quarantine", by_name["main.py"]["unified_diff"])
        self.assertEqual(report["change_manifest_sha256"], hash_payload(report["changes"]))
        self.assertTrue(report["quarantined"])

    def test_invalid_utf8_and_oversized_python_retain_raw_review_requirement(self):
        for raw, status in ((b"\xff", "invalid_utf8_python"), (b"x" * (module.MAX_TEXT_DIFF_BYTES + 1), "oversized_python")):
            with self.subTest(size=len(raw)):
                report = self.compare(expected() | {"main.py": raw})
                changed = next(row for row in report["changes"] if row["name"] == "main.py")
                self.assertTrue(changed["diff_status"].startswith(status))
                self.assertNotIn("unified_diff", changed)
                self.assertTrue(report["quarantined"])
                self.assertEqual(changed["returned"]["bytes"], len(raw))

    def test_text_diff_prefix_and_line_budgets_never_claim_complete_content(self):
        local = {"main.py": b"a" * 30_000 + b"\n"}
        supplied = {"main.py": b"b" * 30_000 + b"\n"}
        report = self.compare(supplied, local=local)
        changed = report["changes"][0]
        self.assertFalse(changed["diff_complete"])
        self.assertLessEqual(len(changed["unified_diff"]), module.MAX_DIFF_CHARS)
        self.assertIn("raw_review_required", changed["diff_status"])
        self.assertEqual(changed["returned"]["bytes"], len(supplied["main.py"]))
        supplied = expected() | {"main.py": b"x\n" * (module.MAX_DIFF_LINES + 1)}
        changed = next(row for row in self.compare(supplied)["changes"] if row["name"] == "main.py")
        self.assertNotIn("unified_diff", changed)
        self.assertIn("too_many_python_lines", changed["diff_status"])

    def test_unsafe_paths_aliases_types_count_size_and_aggregate_bound_refuse(self):
        for name in ("../outside.py", "/outside.py", "a//b.py", "a/./b.py", "a/../b.py", "a\\b.py", "a\n.py", "é.py", "x" * 257):
            with self.subTest(name=name), self.assertRaises(module.CloudInventoryError):
                self.compare(expected() | {name: b"x"})
        for supplied in (expected() | {"MAIN.PY": b"x"}, expected() | {"x.bin": bytearray(b"x")},
                         {1: b"x"}, {f"f{i}.bin": b"x" for i in range(module.MAX_FILES + 1)},
                         {"x.bin": b"x" * (module.MAX_FILE_BYTES + 1)},
                         {f"f{i}.bin": b"x" * module.MAX_FILE_BYTES for i in range(5)}):
            with self.subTest(kind=len(supplied)), self.assertRaises(module.CloudInventoryError):
                self.compare(supplied)
        with self.assertRaises(module.CloudInventoryError):
            module.cloud_file_inventory([])

    def test_retained_anchors_and_strict_expected_python_carrier_refuse(self):
        with self.assertRaisesRegex(module.CloudInventoryError, "retained"):
            self.compare(before="0" * 64)
        with self.assertRaisesRegex(module.CloudInventoryError, "retained"):
            self.compare(after="0" * 64)
        for local in ({}, {"main.py": b""}, expected() | {"research.ipynb": b"opaque"},
                      {"main.py": b"x" * module.MAX_EXPECTED_PYTHON_BYTES}):
            with self.subTest(kind=len(local)), self.assertRaises(module.CloudInventoryError):
                self.compare(local=local)

    def test_private_byte_snapshots_survive_caller_mutation_during_hashing(self):
        retained, returned = expected(), expected() | {"research.ipynb": b"opaque"}
        before, after = expected_anchor(retained), module.cloud_inventory_anchor(returned)
        original = module.hash_payload
        def mutate(value):
            retained.clear()
            returned.clear()
            returned["main.py"] = b"unrelated caller mutation"
            return original(value)
        with patch.object(module, "hash_payload", side_effect=mutate):
            report = module.compare_cloud_inventory(retained, returned,
                expected_project_sha256=before, expected_returned_sha256=after)
        self.assertEqual(set(report["returned_files"]), set(expected()) | {"research.ipynb"})
        self.assertTrue(report["python_byte_identical"])
        self.assertEqual(report["returned_inventory_sha256"], after)
        report["returned_files"].clear()
        fresh = self.compare(expected() | {"research.ipynb": b"opaque"})
        self.assertEqual(len(fresh["returned_files"]), 3)

    def test_inventory_order_is_deterministic_and_no_external_actions_occur(self):
        supplied = expected() | {"research.ipynb": b"opaque"}
        reversed_map = dict(reversed(list(supplied.items())))
        with patch("socket.create_connection", side_effect=AssertionError("no network")), \
             patch("subprocess.run", side_effect=AssertionError("no process")):
            self.assertEqual(module.cloud_file_inventory(supplied), module.cloud_file_inventory(reversed_map))
            self.assertEqual(self.compare(supplied), self.compare(reversed_map))
