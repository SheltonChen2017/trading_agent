"""Complete invented trace custody/replay, not a native engine certification."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.financial_primitives import exact_decimal_sum
from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift import completion_evidence as evidence_module
from research.guidance_revision_drift.completion_evidence import (
    EvidenceError, TraceEvidence, export_trace, replay_completion, completion_dossier, completion_output,
)
from research.guidance_revision_drift.evaluation import CandidateBinding, CompileReceipt, RunReceipt, ReceiptJournal
from research.guidance_revision_drift.lean_bridge import SyntheticOrderBridge, fixture_frames
from research.guidance_revision_drift.qc_project import qc_project_manifest


def raw(body):
    return canonical_json(body).encode()


def drive(mode="base", checkpoints=True):
    bridge, bindings, events = SyntheticOrderBridge(mode), {}, {}
    for frame in fixture_frames():
        state = bridge.engine.snapshot()
        account = dict(native_quantity=Decimal(sum(p["quantity"] for p in state["positions"])),
            native_cash=exact_decimal_sum((Decimal(state["settled_cash"]),
                *(Decimal(r["amount"]) for r in state["receivables"])))) if checkpoints else {}
        actions = bridge.step(frame, **account)
        for order in actions["submit"]:
            native = 11 + 12 * len(bindings)  # IDs are not assumed to be 1/2.
            bridge.bind(order.order_id, native)
            bindings[order.order_id], events[native] = native, 0
            bridge.order_event(native_id=native, event_id=0, status="submitted", at=bridge.current_at,
                               quantity=0, price=Decimal(0), fee=Decimal(0))
        for order_id, native in bindings.items():
            fill = bridge.issue_fill(native, bridge.current_at)
            if fill is None:
                continue
            remaining = next(o.remaining for o in bridge.engine.orders if o.order_id == order_id)
            events[native] += 1
            bridge.order_event(native_id=native, event_id=events[native],
                status="filled" if remaining == 0 else "partially_filled", at=fill.at,
                quantity=fill.quantity if fill.side == "buy" else -fill.quantity, price=fill.price, fee=fill.fee)
        for order_id in actions["cancel"]:
            native = bindings[order_id]
            for status in ("cancel_pending", "canceled"):
                events[native] += 1
                bridge.order_event(native_id=native, event_id=events[native], status=status,
                    at=bridge.current_at, quantity=0, price=Decimal(0), fee=Decimal(0))
    bridge.finish()
    return bridge


def rechain(original, change):
    records = [json.loads(row) for row in original.records]
    change(records)
    prior, result = hash_bytes(original.genesis), []
    for sequence, row in enumerate(records):
        row.update(sequence=sequence, previous_sha256=prior)
        result.append(raw(row))
        prior = hash_bytes(result[-1])
    return TraceEvidence(original.genesis, tuple(result), prior)


class CompletionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = drive()
        cls.evidence = export_trace(cls.bridge)

    def test_complete_trace_chunk_roundtrip_and_replay_preserve_economics(self):
        evidence = self.evidence
        self.assertEqual(len(evidence.records), 752)
        chunks = evidence.to_chunks()
        self.assertTrue(all(len(chunk) <= 65536 for chunk in chunks))
        recovered = TraceEvidence.from_chunks(chunks, expected_sha256=evidence.sha256)
        self.assertEqual(recovered, evidence)
        report = replay_completion(recovered, expected_sha256=evidence.sha256)
        self.assertEqual(report["account_checkpoints"], 372)
        self.assertEqual(report["strategy"], self.bridge.finish()["strategy"])
        for flag in ("native_runtime_verified", "cloud_completed", "external_provenance_verified",
                     "empirical_evidence", "settlement_parity_verified"):
            self.assertIs(report[flag], False)
        projection = self.bridge.protocol_trace()
        copied = TraceEvidence.from_trace(projection)
        projection["records"][0]["payload"]["quantity"] = "100"
        self.assertEqual(copied, evidence)

    def test_missing_reordered_extra_noncanonical_or_wrong_anchor_chunks_refuse(self):
        chunks = self.evidence.to_chunks()
        for changed in (chunks[:-1], chunks[::-1], chunks + (chunks[-1],),
                        (chunks[0] + b" ",) + chunks[1:]):
            with self.subTest(kind=len(changed)), self.assertRaises(EvidenceError):
                TraceEvidence.from_chunks(changed, expected_sha256=self.evidence.sha256)
        with self.assertRaises(EvidenceError):
            TraceEvidence.from_chunks(chunks, expected_sha256="f" * 64)
        with self.assertRaises(EvidenceError):
            replay_completion(self.evidence, expected_sha256="f" * 64)

    def test_changed_but_rehashed_transient_account_and_economics_still_refuse(self):
        def changed(records, kind, field, value):
            next(row for row in records if row["kind"] == kind)["payload"][field] = value
        for kind, field, value in (("account_checkpoint", "immediate_cash", "100001"),
                ("account_checkpoint", "quantity", "1"), ("acknowledgement", "fee", "1"),
                ("binding", "side_quantity_limit", ["buy", 1, "1"])):
            altered = rechain(self.evidence, lambda rows: changed(rows, kind, field, value))
            with self.subTest(kind=kind, field=field), self.assertRaises(EvidenceError):
                replay_completion(altered, expected_sha256=altered.sha256)

    def test_missing_checkpoint_missing_ack_duplicate_ack_and_incomplete_calendar_refuse(self):
        for change in (lambda rows: rows.pop(0),
                       lambda rows: rows.pop(next(i for i, row in enumerate(rows) if row["kind"] == "acknowledgement")),
                       lambda rows: rows.insert(5, deepcopy(next(row for row in rows if row["kind"] == "acknowledgement"))),
                       lambda rows: rows.pop()):
            altered = rechain(self.evidence, change)
            with self.assertRaises(EvidenceError):
                replay_completion(altered, expected_sha256=altered.sha256)

    def test_scalar_aliases_structure_and_caller_allocation_bounds_refuse(self):
        projection = self.bridge.protocol_trace()
        for changes in ({"count": True}, {"native_runtime_verified": True},
                        {"records": [{}] * 1025, "count": 1025}):
            with self.subTest(changes=list(changes)), self.assertRaises(EvidenceError):
                TraceEvidence.from_trace(projection | changes)
        for malformed in (b'{"x":1,"x":2}', b'{"x":1.0}', b'{"x":NaN}'):
            with self.assertRaises(EvidenceError):
                TraceEvidence.from_chunks((malformed,), expected_sha256=self.evidence.sha256)
        cyclic = {}
        cyclic["cycle"] = cyclic
        for value in (cyclic, {"huge": "x" * 65537}, ["x" * 40000] * 2,
                      {"int": 2 ** 129}, {"float": 1.0}, {"unicode": "\ud800"}):
            with self.assertRaises(EvidenceError):
                evidence_module._raw(value)
        first = json.loads(self.evidence.records[0])
        first["sequence"] = False
        with self.assertRaises(EvidenceError):
            TraceEvidence(self.evidence.genesis, (raw(first),), hash_bytes(raw(first)))

    def test_dossier_links_exact_local_epoch_and_whole_passive_attempt_chain(self):
        current = qc_project_manifest()
        binding = CandidateBinding(current["source_manifest_sha256"], current["project_sha256"],
            current["bundle_sha256"], current["fixture_sha256"], "d" * 40, "e" * 40, "f" * 64)
        compiled = CompileReceipt(binding.sha256, "SYN-QC-one", 123, "SYN_compile_1",
            "2025-01-02T00:01:00+00:00", "2025-01-02T00:02:00+00:00", "compiled",
            "LEAN-SYN-1", "SDK-SYN-1", "1" * 64)
        output = completion_output(self.evidence, binding_sha256=binding.sha256)
        ran = RunReceipt(binding.sha256, "SYN-QC-one", 123, "SYN_compile_1", "SYN_run_1",
            "2025-01-02T00:03:00+00:00", "2025-01-02T00:04:00+00:00", "completed",
            "LEAN-SYN-1", "SDK-SYN-1", hash_bytes(output))
        with tempfile.TemporaryDirectory() as directory:
            journal = ReceiptJournal.create(Path(directory), binding)
            journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                  at="2025-01-02T00:00:00+00:00")
            journal.record_compile(expected_head=journal.head_sha256, receipt=compiled)
            journal.record_run(expected_head=journal.head_sha256, receipt=ran)
            arguments = dict(expected_sha256=self.evidence.sha256, binding=binding,
                compile_receipt=compiled, run_receipt=ran, run_output=output, journal_snapshot=journal.to_dict(),
                expected_journal_head_sha256=journal.head_sha256)
            report = completion_dossier(self.evidence, **arguments)
            self.assertEqual(report["platform_status_observed"], "completed")
            for flag in ("external_provenance_verified", "native_runtime_verified", "cloud_completed",
                         "empirical_backtest_ready", "qc_upload_allowed", "qc_launch_allowed"):
                self.assertIs(report[flag], False)
            forged = deepcopy(journal.to_dict())
            forged["records"] = []
            for changes in ({"binding": replace(binding, source_sha256="0" * 64)},
                    {"run_receipt": replace(ran, run_id="wrong")},
                    {"compile_receipt": replace(compiled, status="compile_failed")},
                    {"run_receipt": replace(ran, output_sha256="2" * 64)},
                    {"run_output": output + b" "},
                    {"run_output": completion_output(self.evidence, binding_sha256="0" * 64)},
                    {"journal_snapshot": forged}, {"expected_journal_head_sha256": "0" * 64}):
                with self.subTest(changes=list(changes)), self.assertRaises(EvidenceError):
                    completion_dossier(self.evidence, **(arguments | changes))
            stress = export_trace(drive("stress"))
            with self.assertRaisesRegex(EvidenceError, "base"):
                completion_dossier(stress, **(arguments | {"expected_sha256": stress.sha256}))

    def test_dossier_refuses_consistently_receipted_output_for_another_binding_or_trace(self):
        # GDR-CCR22-004's scenario: the run receipt, its journal entry and the
        # supplied output all agree on the output hash, but the output bytes
        # describe a different binding or trace. Only the content binding of
        # the output to this trace and binding can refuse it; the one-argument
        # cases above are all refused earlier by the receipt-hash comparison.
        current = qc_project_manifest()
        binding = CandidateBinding(current["source_manifest_sha256"], current["project_sha256"],
            current["bundle_sha256"], current["fixture_sha256"], "d" * 40, "e" * 40, "f" * 64)
        compiled = CompileReceipt(binding.sha256, "SYN-QC-one", 123, "SYN_compile_1",
            "2025-01-02T00:01:00+00:00", "2025-01-02T00:02:00+00:00", "compiled",
            "LEAN-SYN-1", "SDK-SYN-1", "1" * 64)
        stress = export_trace(drive("stress"))
        for label, unrelated in (
                ("other_binding", completion_output(self.evidence, binding_sha256="0" * 64)),
                ("other_trace", completion_output(stress, binding_sha256=binding.sha256))):
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                ran = RunReceipt(binding.sha256, "SYN-QC-one", 123, "SYN_compile_1", "SYN_run_1",
                    "2025-01-02T00:03:00+00:00", "2025-01-02T00:04:00+00:00", "completed",
                    "LEAN-SYN-1", "SDK-SYN-1", hash_bytes(unrelated))
                journal = ReceiptJournal.create(Path(directory), binding)
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                      at="2025-01-02T00:00:00+00:00")
                journal.record_compile(expected_head=journal.head_sha256, receipt=compiled)
                journal.record_run(expected_head=journal.head_sha256, receipt=ran)
                with self.assertRaisesRegex(EvidenceError, "run output differs"):
                    completion_dossier(self.evidence, expected_sha256=self.evidence.sha256,
                        binding=binding, compile_receipt=compiled, run_receipt=ran,
                        run_output=unrelated, journal_snapshot=journal.to_dict(),
                        expected_journal_head_sha256=journal.head_sha256)

    def test_dossier_refuses_a_fully_consistent_chain_bound_to_an_older_source_epoch(self):
        # Receipts, journal and output all consistently name one binding, but
        # that binding's source/project/bundle identities are not the current
        # carrier's: evidence from an earlier epoch cannot certify this source.
        # The one-argument stale-binding case above is refused earlier, by the
        # receipts' binding hash, so it never reaches the current-source check.
        current = qc_project_manifest()
        for field in ("source_sha256", "project_sha256", "bundle_sha256"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                values = {"source_sha256": current["source_manifest_sha256"],
                          "project_sha256": current["project_sha256"],
                          "bundle_sha256": current["bundle_sha256"]}
                values[field] = "0" * 64
                stale = CandidateBinding(values["source_sha256"], values["project_sha256"],
                    values["bundle_sha256"], current["fixture_sha256"], "d" * 40, "e" * 40, "f" * 64)
                compiled = CompileReceipt(stale.sha256, "SYN-QC-one", 123, "SYN_compile_1",
                    "2025-01-02T00:01:00+00:00", "2025-01-02T00:02:00+00:00", "compiled",
                    "LEAN-SYN-1", "SDK-SYN-1", "1" * 64)
                output = completion_output(self.evidence, binding_sha256=stale.sha256)
                ran = RunReceipt(stale.sha256, "SYN-QC-one", 123, "SYN_compile_1", "SYN_run_1",
                    "2025-01-02T00:03:00+00:00", "2025-01-02T00:04:00+00:00", "completed",
                    "LEAN-SYN-1", "SDK-SYN-1", hash_bytes(output))
                journal = ReceiptJournal.create(Path(directory), stale)
                journal.record_intent(expected_head=journal.head_sha256, attempt_id="SYN-QC-one",
                                      at="2025-01-02T00:00:00+00:00")
                journal.record_compile(expected_head=journal.head_sha256, receipt=compiled)
                journal.record_run(expected_head=journal.head_sha256, receipt=ran)
                with self.assertRaisesRegex(EvidenceError, "not bound to current exact source"):
                    completion_dossier(self.evidence, expected_sha256=self.evidence.sha256,
                        binding=stale, compile_receipt=compiled, run_receipt=ran,
                        run_output=output, journal_snapshot=journal.to_dict(),
                        expected_journal_head_sha256=journal.head_sha256)

    def test_two_load_bearing_guard_mutants_are_caught_and_restored(self):
        first = json.loads(self.evidence.records[0])
        first["sequence"] = False
        alias = raw(first)
        with self.assertRaises(EvidenceError):
            TraceEvidence(self.evidence.genesis, (alias,), hash_bytes(alias))
        with patch.object(TraceEvidence, "__post_init__", lambda value: None):
            self.assertEqual(TraceEvidence(self.evidence.genesis, (alias,), hash_bytes(alias)).records, (alias,))
        with self.assertRaises(EvidenceError):
            TraceEvidence(self.evidence.genesis, (alias,), hash_bytes(alias))
        identity, original = self.evidence.sha256, evidence_module._digest
        with patch.object(evidence_module, "_digest", lambda value: identity if value == "f" * 64 else original(value)):
            self.assertTrue(replay_completion(self.evidence, expected_sha256="f" * 64)["protocol_reconciled"])
        with self.assertRaises(EvidenceError):
            replay_completion(self.evidence, expected_sha256="f" * 64)
