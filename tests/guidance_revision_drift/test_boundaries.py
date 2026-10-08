"""Lane-local dependency and side-effect checks, runnable without operator fixtures."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from research.guidance_revision_drift.__main__ import main
from research.guidance_revision_drift.contracts import load_candidate


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "research" / "guidance_revision_drift"
NEUTRAL_MODULES = {"data.hashing", "data.financial_primitives"}


class GuidanceBoundaryTests(unittest.TestCase):
    def test_transitive_local_dependencies_are_only_lane_and_neutral_primitives(self):
        pending = list(PACKAGE.rglob("*.py"))
        pending.extend([ROOT / "research/__init__.py", ROOT / "data/__init__.py"])
        visited = set()
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    self.assertEqual(node.level, 0, "relative edges need an explicit reviewed resolver")
                    names = [node.module]
                else:
                    continue
                for name in names:
                    if name == "AlgorithmImports" and path == PACKAGE / "lean/main.py":
                        continue  # isolated unexecuted SDK source, no core edge
                    if name == "__future__" or name.split(".")[0] in sys.stdlib_module_names:
                        continue
                    self.assertTrue(
                        name in NEUTRAL_MODULES or name.startswith("research.guidance_revision_drift."),
                        f"unapproved local/third-party dependency from {path.name}: {name}",
                    )
                    dependency = ROOT.joinpath(*name.split(".")).with_suffix(".py")
                    self.assertNotEqual(dependency, PACKAGE / "lean/main.py", "offline core must not load SDK")
                    self.assertTrue(dependency.is_file(), name)
                    pending.append(dependency)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    called = node.func.id if isinstance(node.func, ast.Name) else (
                        node.func.attr if isinstance(node.func, ast.Attribute) else None
                    )
                    self.assertNotIn(called, {"__import__", "import_module", "eval", "exec"})
        self.assertIn(ROOT / "data/hashing.py", visited)
        self.assertIn(ROOT / "data/financial_primitives.py", visited)

    def test_fresh_process_imports_no_execution_or_provider_package(self):
        code = """
import json, sys
import research.guidance_revision_drift.contracts
import research.guidance_revision_drift.formulas
import research.guidance_revision_drift.readiness
import research.guidance_revision_drift.__main__
import research.guidance_revision_drift.archive
import research.guidance_revision_drift.artifacts
import research.guidance_revision_drift.assessment
import research.guidance_revision_drift.comparison
import research.guidance_revision_drift.controls
import research.guidance_revision_drift.events
import research.guidance_revision_drift.fixtures
import research.guidance_revision_drift.qc_adapter
import research.guidance_revision_drift.reporting
import research.guidance_revision_drift.scenario
import research.guidance_revision_drift.simulation
import research.guidance_revision_drift.timing
import research.guidance_revision_drift.universe
import research.guidance_revision_drift.specification
import research.guidance_revision_drift.vendor_payloads
import research.guidance_revision_drift.lineage
import research.guidance_revision_drift.market_inputs
import research.guidance_revision_drift.corporate_actions
import research.guidance_revision_drift.persistence
import research.guidance_revision_drift.recovery
import research.guidance_revision_drift.lean_bridge
import research.guidance_revision_drift.integration
import research.guidance_revision_drift.release
blocked = {'assistant', 'risk', 'execution', 'ml', 'config', 'requests', 'httpx', 'alpaca', 'quantconnect'}
blocked.update({'AlgorithmImports', 'clr', 'QuantConnect'})
print(json.dumps(sorted(name for name in sys.modules if name.split('.')[0] in blocked)))
"""
        completed = subprocess.run(
            [sys.executable, "-B", "-c", code], cwd=ROOT,
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(completed.stdout), [])
        self.assertEqual(completed.stderr, "")

    def test_inspection_has_only_expected_read_only_file_access(self):
        allowed = {
            PACKAGE / "specs/gdr0a.draft.json",
            ROOT / "docs/Plan/GUIDANCE_REVISION_DRIFT_RESEARCH_PLAN_2026-10-06.md",
            ROOT / "output/pdf/GUIDANCE_REVISION_DRIFT_RESEARCH_PLAN_2026-10-06.pdf",
        }
        observed = []
        original_open = os.open

        def guarded_open(path, flags, *args, **kwargs):
            path = Path(path)
            self.assertEqual(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND), 0)
            self.assertIn(path.resolve(), allowed)
            observed.append(path.resolve())
            return original_open(path, flags, *args, **kwargs)

        with patch.object(os, "open", guarded_open), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("network forbidden")), \
             patch("os.getenv", side_effect=AssertionError("environment access forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process launch forbidden")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["preflight"]), 2)
        self.assertEqual(set(observed), allowed)
        self.assertFalse(json.loads(output.getvalue())["ready_for_orders"])

    def test_proposal_has_no_access_to_four_lane_budget_or_protected_dates(self):
        body = load_candidate().to_dict()
        self.assertIsNone(body["unresolved"]["research_family_id"])
        self.assertIsNone(body["unresolved"]["family_allocation"])
        self.assertIsNone(body["unresolved"]["authorized_evidence_windows"])
        self.assertFalse(body["authority"]["inherit_sibling_permissions"])
        self.assertEqual(body["authority"]["research_looks"], 0)
        self.assertEqual(body["evidence"]["outcome_quarantine_from"], "2026-09-01")
        self.assertEqual(body["evidence"]["existing_shared_holdout_start"], "2027-09-01")
        self.assertEqual(body["evidence"]["existing_shared_holdout_end"], "2029-08-31")

    def test_source_byte_contract_has_lane_scoped_eol_rules(self):
        attributes = (PACKAGE / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.json -text", attributes)
        attributes = (ROOT / "docs/Plan/.gitattributes").read_text(encoding="utf-8")
        self.assertIn("GUIDANCE_REVISION_DRIFT_RESEARCH_PLAN_2026-10-06.md text eol=lf", attributes)

    def test_active_document_references_agree_on_lane_and_draft_sources(self):
        record_path = "docs/Strategy Description/GUIDANCE_REVISION_DRIFT_IMPLEMENTATION_RECORD.md"
        record = (ROOT / record_path).read_text(encoding="utf-8")
        for path in (ROOT / "docs/ACTION_PLAN_2026-08-20.md", PACKAGE / "README.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn(record_path, text)
            self.assertIn("GDR-0A", text)
        self.assertIn("codex/strategy-guidance-revision-drift", record)
        # Review-state phrase: rotate it in the same commit as each new review
        # or counter-review section so the status block cannot go stale.
        self.assertIn("Section 16 counter-review accepted after correction", record.split("## 1.", 1)[0])
        self.assertIn("does not mark GDR-0 complete", record)
        # Shared handoff size belongs to the project-wide active-document
        # guard, not this lane's contract/source consistency check.
        candidate = load_candidate()
        self.assertIn(candidate.sha256, record)
        for document in candidate.to_dict()["source_documents"]:
            self.assertIn(document["path"], record)
            self.assertIn(document["sha256"], record)
        self.assertIn(
            "GUIDANCE_REVISION_DRIFT_RESEARCH_PLAN_2026-10-06.md",
            (ROOT / "docs/Plan/README.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
