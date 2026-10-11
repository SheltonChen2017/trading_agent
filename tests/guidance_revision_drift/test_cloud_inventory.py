"""Complete invented cloud maps; opaque files never become accepted source."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from data.hashing import hash_payload
from research.guidance_revision_drift import cloud_inventory as module


def expected():
    # Generic readable comparison input; actual candidate verification is separate.
    return {"main.py": b"# invented unchanged economics\n", "support.py": b"# invented readable helper\n"}


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
        self.assertEqual(report["python_changes"], ["main.py", "support.py", "unreviewed.py"])
        by_name = {row["name"]: row for row in report["changes"]}
        self.assertEqual(by_name["support.py"]["status"], "missing")
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
                      {"main.py": b"x" * module.MAX_EXPECTED_PYTHON_BYTES},
                      expected() | {"support.py": b""}, expected() | {"data/not__init__.py": b""}):
            with self.subTest(kind=len(local)), self.assertRaises(module.CloudInventoryError):
                self.compare(local=local)

    def test_readable_native_source_and_empty_initializer_fit_without_platform_claims(self):
        source = Path(__file__).resolve().parents[2] / "research/guidance_revision_drift/simulation.py"
        native = source.read_bytes()
        self.assertGreater(len(native), 32_000)
        local = expected() | {"research/guidance_revision_drift/simulation.py": native, "data/__init__.py": b""}
        returned = local | {"research.ipynb": b"opaque notebook"}
        report = self.compare(returned, local=local)
        self.assertTrue(report["python_byte_identical"])
        self.assertTrue(report["quarantined"])
        self.assertEqual(report["opaque_quarantine"], ["research.ipynb"])
        self.assertEqual(report["expected_files"]["data/__init__.py"]["bytes"], 0)
        self.assertEqual(report["expected_files"]["research/guidance_revision_drift/simulation.py"]["bytes"], len(native))
        self.assertIs(report["current_local_content_checked"], False)
        self.assertIs(report["economic_acceptance"], False)

    def test_current_verified_readable_project_and_opaque_notebook_compose(self):
        from research.guidance_revision_drift.qc_project import (
            build_qc_project, qc_project_manifest, verify_qc_project,
        )
        local = build_qc_project()
        verified = verify_qc_project(local, expected_sha256=expected_anchor(local))
        current = qc_project_manifest()
        self.assertEqual(current["schema"], "gdr.synthetic.python-project.v3")
        self.assertEqual(verified["project_sha256"], expected_anchor(local))
        self.assertEqual(local["data/__init__.py"], b"")
        self.assertEqual(local["research/__init__.py"], b"")
        self.assertGreater(len(local["research/guidance_revision_drift/simulation.py"]), 32_000)
        returned = local | {"research.ipynb": b"opaque default notebook, never parsed"}
        report = self.compare(returned, local=local)
        self.assertEqual(report["expected_project_sha256"], verified["project_sha256"])
        self.assertEqual(set(report["returned_files"]), set(returned))
        self.assertTrue(report["python_byte_identical"])
        self.assertEqual(report["opaque_quarantine"], ["research.ipynb"])
        self.assertIs(report["current_local_content_checked"], False)
        self.assertIs(report["external_provenance_verified"], False)
        self.assertIs(report["economic_acceptance"], False)

    def test_researcher_expected_project_reserves_notebook_and_strict_byte_headroom(self):
        self.assertEqual(module.MAX_FILES, 50)
        self.assertEqual(module.MAX_EXPECTED_FILES, 49)
        self.assertEqual(module.MAX_EXPECTED_PYTHON_BYTES, 64_000)
        local = {"main.py": b"# root\n"} | {f"support_{index}.py": b"# readable\n" for index in range(48)}
        local["support_0.py"] = b"x" * 63_999
        self.assertTrue(self.compare(local=local)["python_byte_identical"])
        self.assertEqual(len(self.compare(local | {"research.ipynb": b"opaque"}, local=local)["returned_files"]), 50)
        for bad in (local | {"support_extra.py": b"x"}, local | {"support_0.py": b"x" * 64_000}):
            with self.subTest(count=len(bad)), self.assertRaises(module.CloudInventoryError):
                self.compare(local=bad)

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
