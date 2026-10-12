"""Readable invented commitments/replay, never a native or QC execution test."""
import ast
from copy import deepcopy
import inspect
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift import readable_transport as module
from research.guidance_revision_drift.completion_evidence import TraceEvidence, replay_completion
from research.guidance_revision_drift.native_observation import failure_diagnostics
from tests.guidance_revision_drift.test_completion_evidence import drive
from tests.guidance_revision_drift.test_native_dossier import metadata, failed_metadata


def context():
    return {"runtime_source_sha256": "a" * 64, "bundle_sha256": "b" * 64,
            "candidate_sha256": module.CANDIDATE_SHA256, "fixture_sha256": module.FIXTURE_SHA256}


def alter(lines, change):
    """Re-anchor deliberate changed supplied content; not fake authentication."""
    bodies = [json.loads(raw) for raw in lines[:-1]]
    change(bodies)
    result = tuple(canonical_json(row).encode("ascii") for row in bodies)
    return result + (canonical_json({"end": module.SCHEMA, "line_count": len(result),
        "sha256": hash_payload([hash_bytes(raw) for raw in result])}).encode("ascii"),)


def remap(trace):
    body, prior = deepcopy(trace), trace["genesis_sha256"]
    for row in body["records"]:
        payload = row["payload"]
        if "native_id" in payload:
            payload["native_id"] += 1_234_567_000
        if "event_id" in payload:
            payload["event_id"] += 17
        row["previous_sha256"] = prior
        prior = hash_bytes(canonical_json(row).encode())
    body["head_sha256"] = prior
    return body


class ReadableTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = remap(drive().protocol_trace())
        cls.extra = metadata(cls.trace)
        cls.lines = module.export_readable_evidence(cls.trace, runtime_context=context(), metadata=cls.extra)

    def reconstruct(self, lines=None, expected_context=None):
        lines = self.lines if lines is None else lines
        return module.reconstruct_readable_evidence(lines, expected_sha256=module.readable_evidence_anchor(lines),
            expected_runtime_context=context() if expected_context is None else expected_context)

    def test_readable_atomic_values_and_exact_752_record_372_checkpoint_replay(self):
        recovered = self.reconstruct()
        self.assertEqual(recovered["trace"], self.trace)
        self.assertEqual(recovered["metadata"], self.extra)
        evidence = TraceEvidence.from_trace(recovered["trace"])
        replay = replay_completion(evidence, expected_sha256=evidence.sha256)
        self.assertEqual((replay["record_count"], replay["account_checkpoints"]), (752, 372))
        self.assertEqual(recovered["evidence_provenance"], "digest-reconciled local reconstruction")
        manifest = module.readable_transport_manifest(self.lines)
        self.assertLess(manifest["log_bytes_including_lf"], 100_000)
        self.assertLessEqual(manifest["line_count"], 1025)
        self.assertLessEqual(manifest["max_line_bytes"], 200)
        self.assertEqual(manifest["sha256"], module.readable_evidence_anchor(self.lines))
        rows = [json.loads(line) for line in self.lines]
        self.assertEqual(sum("record" in row for row in rows), 752)
        self.assertEqual(sum("valuation" in row for row in rows), 372)
        supplied = [row["value"] for row in rows if row.get("path") == ["native_id"]]
        self.assertTrue(supplied and min(supplied) > 1_234_567_000)
        for result in (recovered, manifest):
            for name in ("external_provenance_verified", "native_runtime_verified", "cloud_completed",
                         "empirical_backtest_ready", "qc_upload_allowed", "qc_launch_allowed", "raw_transcript_transported"):
                self.assertIs(result[name], False)

    def test_missing_extra_reordered_changed_records_and_metadata_refuse_even_reanchored(self):
        def drop(rows):
            del rows[10]
        def extra(rows):
            rows.insert(10, deepcopy(rows[10]))
        def reorder(rows):
            rows[10], rows[11] = rows[11], rows[10]
        def digest(rows):
            rows[10]["sha256"] = "0" * 64
        def receipt(rows):
            next(row for row in rows if row.get("path") == ["native_id"])["value"] += 1
        def bad_value(rows):
            next(row for row in rows if "valuation" in row)["valuation"][2] = "1"
        def context_row(rows):
            next(row for row in rows if row.get("context") == "runtime_source_sha256")["sha256"] = "0" * 64
        def metadata_field(rows):
            next(row for row in rows if row.get("metadata") == ["terminal", "native_cash"])["value"] = "1"
        def field_order(rows):
            a = next(index for index, row in enumerate(rows) if "metadata" in row)
            rows[a], rows[a + 1] = rows[a + 1], rows[a]
        def duplicate_field(rows):
            rows.append(deepcopy(next(row for row in rows if "metadata" in row)))
        def promotion(rows):
            next(row for row in rows if row.get("metadata") == ["observations", "native_binding_verified"])["value"] = True
        for change in (drop, extra, reorder, digest, receipt, bad_value, context_row,
                       metadata_field, field_order, duplicate_field, promotion):
            with self.subTest(change=change.__name__), self.assertRaises(module.ReadableTransportError):
                self.reconstruct(alter(self.lines, change))

    def test_retained_anchor_noncanonical_duplicate_json_and_type_confusion_refuse(self):
        with self.assertRaises(module.ReadableTransportError):
            module.reconstruct_readable_evidence(self.lines, expected_sha256="0" * 64,
                                                expected_runtime_context=context())
        for raw in (b'{"x":1,"x":2}', b'{"x":1.0}', b'{"x":NaN}', b'{"x": 1}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(module.ReadableTransportError):
                module.readable_evidence_anchor((raw,) * 7)
        for name in ("status", "record_count"):
            with self.subTest(field=name), self.assertRaises(module.ReadableTransportError):
                self.reconstruct(alter(self.lines, lambda rows: rows[0].update({name: []})))
        with self.assertRaises(module.ReadableTransportError):
            self.reconstruct(expected_context=context() | {"bundle_sha256": "0" * 64})

    def test_failed_complete_and_partial_prefix_remain_failed_and_do_not_finish(self):
        failed = module.export_readable_evidence(self.trace, runtime_context=context(), metadata=failed_metadata(self.trace))
        with patch.object(module.SyntheticOrderBridge, "finish", side_effect=AssertionError("failed is not completion")):
            recovered = self.reconstruct(failed)
        self.assertEqual(recovered["metadata"]["status"], "failed")
        partial = deepcopy(self.trace)
        partial["records"] = partial["records"][:10]
        partial["count"] = 10
        partial["head_sha256"] = hash_bytes(canonical_json(partial["records"][-1]).encode())
        extra = failed_metadata(self.trace)
        extra["valuation_rows"] = extra["valuation_rows"][:5]
        bridge = NS(_bindings={}, _pending={}, _cancels={}, protocol_trace=lambda: partial)
        extra["diagnostics"] = failure_diagnostics("on_data", RuntimeError(), bridge, None)
        lines = module.export_readable_evidence(partial, runtime_context=context(), metadata=extra)
        with patch.object(module.SyntheticOrderBridge, "finish", side_effect=AssertionError("partial is not completion")):
            restored = self.reconstruct(lines)
        self.assertEqual(restored["trace"], partial)
        self.assertEqual(restored["metadata"]["status"], "failed")
        with self.assertRaises(module.ReadableTransportError):
            self.reconstruct(alter(lines, lambda rows: rows[0].update(status="complete")))

    def test_budget_bounds_and_oversize_atomic_failed_diagnostic_refuse_without_truncation(self):
        short = canonical_json({"x": "y"}).encode()
        module.readable_evidence_anchor((short,) * 1025)
        with self.assertRaises(module.ReadableTransportError):
            module.readable_evidence_anchor((short,) * 1026)
        line = canonical_json({"x": "y" * 192}).encode()
        self.assertEqual(len(line), 200)
        module.readable_evidence_anchor((line,) * 497)
        with self.assertRaises(module.ReadableTransportError):
            module.readable_evidence_anchor((line,) * 498)
        with self.assertRaises(module.ReadableTransportError):
            module.readable_evidence_anchor((line + b" ",) * 7)
        failed = failed_metadata(self.trace)
        failed["diagnostics"]["error_type"] = "SYN-" + "x" * 245
        before = deepcopy(failed)
        with self.assertRaises(module.ReadableTransportError):
            module.export_readable_evidence(self.trace, runtime_context=context(), metadata=failed)
        self.assertEqual(failed, before)

    def test_no_opaque_codec_or_offline_completion_dependency_in_native_transport(self):
        tree = ast.parse(inspect.getsource(module))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
        for forbidden in ("base64", "zlib", "zipfile", "research.guidance_revision_drift.trace_transport",
                          "research.guidance_revision_drift.completion_evidence"):
            self.assertNotIn(forbidden, imports)

    def test_repeated_text_is_refused_before_canonical_serializer_allocates_output(self):
        with patch.object(module, "canonical_json", side_effect=AssertionError("serializer must not run")):
            for limit, body in ((200, {"a": "x" * 120, "b": "x" * 120}),
                                (65_536, {"a": ["x" * 32_768] * 3})):
                with self.subTest(limit=limit), self.assertRaisesRegex(module.ReadableTransportError, "aggregate readable text"):
                    module._raw(body, limit)


    def test_non_ascii_values_refuse_at_export_and_reconstruction(self):
        # GDR-CR31-006: canonical_json keeps non-ASCII text, so only the two
        # ASCII checks keep the readable route plain ASCII; no case had any.
        label = ["observations", "objects", "algorithm", "python_type"]
        extra = deepcopy(self.extra)
        extra["observations"]["objects"]["algorithm"]["python_type"] = "SYN.Algorithm\u00e9"
        with self.assertRaises(module.ReadableTransportError):
            module.export_readable_evidence(self.trace, runtime_context=context(), metadata=extra)
        bodies = [json.loads(raw) for raw in self.lines[:-1]]
        target = next(row for row in bodies if row.get("metadata") == label)
        target["value"] += "\u00e9"
        result = tuple(canonical_json(row).encode("utf-8") for row in bodies)
        lines = result + (canonical_json({"end": module.SCHEMA, "line_count": len(result),
            "sha256": hash_payload([hash_bytes(raw) for raw in result])}).encode("ascii"),)
        self.assertTrue(any(not raw.isascii() for raw in lines))
        with self.assertRaises(module.ReadableTransportError):
            self.reconstruct(lines)


if __name__ == "__main__":
    unittest.main()
