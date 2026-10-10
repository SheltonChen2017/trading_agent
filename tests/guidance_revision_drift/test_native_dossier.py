"""Offline composition of invented retrieved logs, cycle and carrier custody."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from data.financial_primitives import decimal_text, exact_decimal_multiply, exact_decimal_sum
from data.hashing import hash_bytes
from research.guidance_revision_drift.completion_evidence import EvidenceError, native_completion_dossier
from research.guidance_revision_drift.cloud_inventory import cloud_inventory_anchor, compare_cloud_inventory
from research.guidance_revision_drift.evaluation import CandidateBinding, CompileReceipt, RunReceipt
from research.guidance_revision_drift.evaluation_cycle import OwnerCycle, CycleJournal
from research.guidance_revision_drift.native_observation import observe_runtime
from research.guidance_revision_drift.qc_project import build_qc_project, qc_project_manifest, verify_qc_project
from research.guidance_revision_drift.trace_transport import export_trace_fragments, trace_fragment_anchor
from tests.guidance_revision_drift.test_completion_evidence import drive


def metadata(trace):
    checkpoints = [row["payload"] for row in trace["records"] if row["kind"] == "account_checkpoint"]
    values = [[row["before_frame_index"], "50", decimal_text(exact_decimal_sum((
        Decimal(row["immediate_cash"]), exact_decimal_multiply(Decimal(row["quantity"]), Decimal(50)))))]
        for row in checkpoints]
    observations = observe_runtime(NS(time_zone=NS(id="UTC")), NS(symbol="SYN-GDR"))
    return {"status": "complete", "terminal": {"native_quantity": "0",
        "native_cash": checkpoints[-1]["immediate_cash"], "native_price": "50", "native_nav": values[-1][2]},
        "valuation_schema": "gdr-native-price-nav-v1", "valuation_rows": values, "observations": observations}


class NativeDossierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = drive().protocol_trace()

    def setUp(self):
        current = qc_project_manifest()
        self.binding = CandidateBinding(current["source_manifest_sha256"], current["project_sha256"],
            current["bundle_sha256"], current["fixture_sha256"], "d" * 40, "e" * 40, "f" * 64)
        self.context = current["runtime_context"]
        self.fragments = export_trace_fragments(self.trace, runtime_context=self.context, metadata=metadata(self.trace))

    def dossier(self, fragments=None, *, binding=None, run_hash=None):
        fragments = self.fragments if fragments is None else fragments
        binding = self.binding if binding is None else binding
        cycle = OwnerCycle("SYN-dossier-only")
        compiled = CompileReceipt(binding.sha256, "SYN-QC-one", 123, "SYN_compile_1",
            "2025-01-02T00:01:00+00:00", "2025-01-02T00:02:00+00:00", "compiled",
            "SYN-LEAN", "SYN-PythonBinding", "1" * 64)
        output_hash = hash_bytes(b"\n".join(fragments) + b"\n") if run_hash is None else run_hash
        ran = RunReceipt(binding.sha256, "SYN-QC-one", 123, "SYN_compile_1", "SYN_run_1",
            "2025-01-02T00:03:00+00:00", "2025-01-02T00:04:00+00:00", "completed",
            "SYN-LEAN", "SYN-PythonBinding", output_hash)
        with TemporaryDirectory() as root:
            journal = CycleJournal.create(Path(root), cycle, expected_head=cycle.genesis_sha256)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one", binding=binding,
                at="2025-01-02T00:00:00+00:00", observed_at="2025-01-02T00:00:00+00:00")
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled, observed_at=compiled.completed_at)
            journal.record_ambiguous(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                observed_at="2025-01-02T00:05:00+00:00", output_sha256="2" * 64)
            journal.record_run(expected_head=journal.head_sha256, receipt=ran, observed_at="2025-01-02T00:07:00+00:00")
            return native_completion_dossier(fragments, expected_fragment_sha256=trace_fragment_anchor(fragments),
                binding=binding, cycle=cycle, compile_receipt=compiled, run_receipt=ran,
                cycle_snapshot=journal.to_dict(), expected_cycle_head_sha256=journal.head_sha256)

    def test_actual_supplied_trace_raw_output_valuation_cycle_and_current_carrier_compose(self):
        report = self.dossier()
        self.assertEqual(report["replay"]["account_checkpoints"], 372)
        self.assertEqual(report["replay"]["record_count"], 752)
        self.assertEqual(report["raw_output_sha256"], hash_bytes(b"\n".join(self.fragments) + b"\n"))
        self.assertNotEqual(report["raw_output_sha256"], report["fragment_sha256"])
        for flag in ("native_runtime_verified", "cloud_completed", "external_provenance_verified", "empirical_backtest_ready"):
            self.assertIs(report[flag], False)
        files = build_qc_project()
        verified = verify_qc_project(files, expected_sha256=self.binding.project_sha256)
        returned = files | {"research.ipynb": b"notebook bytes retained, never parsed"}
        custody = compare_cloud_inventory(files, returned, expected_project_sha256=verified["project_sha256"],
                                          expected_returned_sha256=cloud_inventory_anchor(returned))
        self.assertTrue(custody["python_byte_identical"])
        self.assertEqual(custody["opaque_quarantine"], ["research.ipynb"])
        self.assertIs(custody["economic_acceptance"], False)

    def test_consistent_receipts_for_wrong_raw_output_or_source_epoch_refuse(self):
        with self.assertRaisesRegex(EvidenceError, "raw trace messages"):
            self.dossier(run_hash="0" * 64)
        for name in ("source_sha256", "project_sha256", "bundle_sha256"):
            with self.subTest(name=name), self.assertRaisesRegex(EvidenceError, "current candidate"):
                self.dossier(binding=replace(self.binding, **{name: "0" * 64}))

    def test_rehashed_wrong_runtime_context_refuses(self):
        for name in ("runtime_source_sha256", "bundle_sha256"):
            fragments = export_trace_fragments(self.trace, runtime_context=self.context | {name: "0" * 64},
                                               metadata=metadata(self.trace))
            with self.subTest(name=name), self.assertRaises(EvidenceError):
                self.dossier(fragments)

    def test_consistently_receipted_incomplete_or_changed_native_valuation_refuses(self):
        for change in ("missing", "changed", "promotion"):
            extra = metadata(self.trace)
            if change == "missing":
                extra["valuation_rows"].pop()
            elif change == "changed":
                extra["valuation_rows"][20][2] = "1"
            else:
                extra["observations"]["configuration_verified"] = True
            fragments = export_trace_fragments(self.trace, runtime_context=self.context, metadata=extra)
            with self.subTest(change=change), self.assertRaises(EvidenceError):
                self.dossier(fragments)


if __name__ == "__main__":
    unittest.main()
