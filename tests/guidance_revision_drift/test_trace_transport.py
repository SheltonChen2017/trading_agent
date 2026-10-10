"""Lossless supplied log reconstruction; never a QC runtime test."""
from copy import deepcopy
import base64
import inspect
import json
import unittest
from unittest.mock import patch
import zlib

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift import trace_transport as module
from research.guidance_revision_drift.completion_evidence import TraceEvidence, replay_completion
from tests.guidance_revision_drift.test_completion_evidence import drive


def context():
    return {"runtime_source_sha256": "a" * 64, "bundle_sha256": "b" * 64,
            "candidate_sha256": module.CANDIDATE_SHA256, "fixture_sha256": module.FIXTURE_SHA256}


def wrap(packed):
    encoded = base64.b64encode(packed)
    count = (len(encoded) + module.PAYLOAD_CHARS - 1) // module.PAYLOAD_CHARS
    prior, result = module._START, []
    for sequence in range(count):
        part = encoded[sequence * module.PAYLOAD_CHARS:(sequence + 1) * module.PAYLOAD_CHARS]
        raw = f"GDRT1|{sequence:05d}|{count:05d}|{prior}|".encode() + part
        result.append(raw)
        prior = hash_bytes(raw)
    anchor = hash_payload([hash_bytes(raw) for raw in result])
    return tuple(result) + (f"GDRT1|END|{count:05d}|{prior}|{anchor}".encode(),)


def envelope(fragments):
    encoded = b"".join(raw.split(b"|", 4)[4] for raw in fragments[:-1])
    return json.loads(zlib.decompress(base64.b64decode(encoded)))


class TraceTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = drive().protocol_trace()
        cls.extra = {"status": "complete", "observations": {"python_version": "invented-shim",
            "native_runtime_verified": False}, "valuations": [{"frame": i, "raw_mark": "50"} for i in range(372)]}
        cls.fragments = module.export_trace_fragments(cls.trace, runtime_context=context(), metadata=cls.extra)

    def reconstruct(self, fragments=None, **kwargs):
        supplied = self.fragments if fragments is None else fragments
        return module.reconstruct_trace_fragments(supplied,
            expected_sha256=kwargs.get("anchor", module.trace_fragment_anchor(supplied)),
            expected_runtime_context=kwargs.get("runtime_context", context()))

    def test_complete_exact_trace_roundtrip_reaches_existing_replay_without_authority(self):
        recovered = self.reconstruct()
        self.assertEqual(recovered["trace"], self.trace)
        self.assertEqual(recovered["metadata"], self.extra)
        self.assertEqual(recovered["runtime_context"], context())
        evidence = TraceEvidence.from_trace(recovered["trace"])
        replay = replay_completion(evidence, expected_sha256=evidence.sha256)
        self.assertEqual(replay["account_checkpoints"], 372)
        for key in ("external_provenance_verified", "native_runtime_verified", "cloud_completed"):
            self.assertIs(recovered[key], False)
        manifest = module.transport_manifest(self.fragments)
        self.assertEqual(manifest["fragment_hashes"], [hash_bytes(raw) for raw in self.fragments])
        self.assertEqual(manifest["sha256"], module.trace_fragment_anchor(self.fragments))
        self.assertLessEqual(manifest["max_line_bytes"], 200)
        self.assertEqual(manifest["route"], "log")
        self.assertIs(manifest["quota_verified"], False)
        self.assertEqual(manifest["log_bytes_including_lf"], sum(len(raw) + 1 for raw in self.fragments))
        self.assertEqual(len(set(self.fragments)), len(self.fragments))

    def test_lossless_compact_wire_omits_only_validated_derivable_chain_fields(self):
        body = envelope(self.fragments)
        self.assertEqual(body["trace_sha256"], hash_payload(self.trace))
        for original, wire in zip(self.trace["records"], body["trace"]["records"]):
            self.assertEqual(wire, {key: original[key] for key in ("kind", "payload")})
        altered = deepcopy(self.trace)
        altered["records"][10]["previous_sha256"] = "0" * 64
        with self.assertRaisesRegex(module.TraceTransportError, "chain"):
            module.export_trace_fragments(altered, runtime_context=context())
        altered = deepcopy(self.trace)
        altered["records"][0]["sequence"] = False
        with self.assertRaisesRegex(module.TraceTransportError, "chain"):
            module.export_trace_fragments(altered, runtime_context=context())

    def test_missing_duplicate_reordered_corrupt_unrelated_or_terminal_only_refuse(self):
        changed = list(self.fragments)
        changed[2] = changed[2][:-1] + (b"A" if changed[2][-1:] != b"A" else b"B")
        cases = (self.fragments[:-1], self.fragments[:2] + self.fragments[3:],
                 self.fragments[:2] + (self.fragments[1],) + self.fragments[2:],
                 (self.fragments[1], self.fragments[0]) + self.fragments[2:],
                 tuple(changed), self.fragments + (b"unrelated line",))
        for index, supplied in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(module.TraceTransportError):
                self.reconstruct(supplied)
        with self.assertRaises(module.TraceTransportError):
            self.reconstruct((self.fragments[-1],))
        with self.assertRaisesRegex(module.TraceTransportError, "retained anchor"):
            self.reconstruct(anchor="f" * 64)
        with self.assertRaisesRegex(module.TraceTransportError, "runtime context"):
            self.reconstruct(runtime_context=context() | {"runtime_source_sha256": "f" * 64})

    def test_fully_reanchored_changed_payload_or_original_head_refuses(self):
        for change in (lambda body: body["trace"]["records"][0]["payload"].update(immediate_cash="100001"),
                       lambda body: body["trace"].update(head_sha256="0" * 64),
                       lambda body: body.update(trace_sha256="0" * 64)):
            body = envelope(self.fragments)
            change(body)
            supplied = wrap(zlib.compress(canonical_json(body).encode(), 9))
            with self.subTest(change=change), self.assertRaises(module.TraceTransportError):
                self.reconstruct(supplied)

    def test_oversized_trailing_truncated_or_duplicate_compression_refuses_before_json(self):
        packed = zlib.compress(canonical_json(envelope(self.fragments)).encode(), 9)
        for changed in (packed + b"tail", packed + packed, packed[:-1],
                        zlib.compress(b"A" * (module.MAX_RAW_BYTES + 1), 9)):
            supplied = wrap(changed)
            with self.subTest(bytes=len(changed)), patch.object(module, "_object", side_effect=AssertionError("no JSON")), \
                 self.assertRaisesRegex(module.TraceTransportError, "compressed transport"):
                self.reconstruct(supplied)

    def test_partial_failed_trace_retains_actual_observations_never_full_completion(self):
        partial = deepcopy(self.trace)
        partial["records"] = partial["records"][:7]
        partial["count"] = 7
        partial["head_sha256"] = hash_payload(partial["records"][-1])
        failed = {"status": "failed", "diagnostics": {"stage": "receipt", "pending_native_ids": [11]}}
        supplied = module.export_trace_fragments(partial, runtime_context=context(), metadata=failed)
        recovered = self.reconstruct(supplied)
        self.assertEqual(recovered["trace"], partial)
        self.assertEqual(recovered["metadata"], failed)
        with self.assertRaisesRegex(module.TraceTransportError, "all accepted records"):
            module.export_trace_fragments(partial, runtime_context=context())
        with self.assertRaises(ValueError):
            replay_completion(TraceEvidence.from_trace(partial), expected_sha256=TraceEvidence.from_trace(partial).sha256)

    def test_complete_stress_mode_refuses_on_producer_and_reconstructor(self):
        stress = drive("stress").protocol_trace()
        with self.assertRaisesRegex(module.TraceTransportError, "fixed base candidate"):
            module.export_trace_fragments(stress, runtime_context=context())
        failed = module.export_trace_fragments(stress, runtime_context=context(), metadata={"status": "failed"})
        changed = envelope(failed)
        changed["metadata"]["status"] = "complete"
        supplied = wrap(zlib.compress(canonical_json(changed).encode(), 9))
        with self.assertRaisesRegex(module.TraceTransportError, "fixed base candidate"):
            self.reconstruct(supplied)

    def test_strict_bounds_types_context_metadata_and_no_source_side_effects(self):
        for supplied in (list(self.fragments), (b"x" * 201, self.fragments[-1]),
                         (True, self.fragments[-1]), self.fragments * 4):
            with self.subTest(kind=type(supplied)), self.assertRaises(module.TraceTransportError):
                self.reconstruct(supplied)
        for metadata in ([], {"status": "unknown"}, {"status": "complete", "qc_launch_allowed": True},
                         {"status": "complete", "observations": {"cloud_completed": True}},
                         {"status": "complete", "value": float("nan")},
                         {"status": "complete", "text": "x" * (module.MAX_METADATA_BYTES + 1)}):
            with self.subTest(metadata=type(metadata)), self.assertRaises(module.TraceTransportError):
                module.export_trace_fragments(self.trace, runtime_context=context(), metadata=metadata)
        for changed in (context() | {"extra": "x"}, context() | {"fixture_sha256": "0" * 64},
                        context() | {"candidate_sha256": "0" * 64}, context() | {"bundle_sha256": True}):
            with self.subTest(context=changed), self.assertRaises(module.TraceTransportError):
                module.export_trace_fragments(self.trace, runtime_context=changed)
        source = inspect.getsource(module)
        for forbidden in ("completion_evidence", "AlgorithmImports", "subprocess", "socket", "requests", "open("):
            self.assertNotIn(forbidden, source)
        with patch("socket.create_connection", side_effect=AssertionError("no network")), \
             patch("subprocess.run", side_effect=AssertionError("no process")):
            self.assertEqual(module.export_trace_fragments(self.trace, runtime_context=context(), metadata=self.extra), self.fragments)

    def test_input_and_returned_projections_are_detached(self):
        trace, extra, ctx = deepcopy(self.trace), deepcopy(self.extra), context()
        prepared = module.export_trace_fragments(trace, runtime_context=ctx, metadata=extra)
        trace["records"].clear()
        extra["valuations"].clear()
        ctx["bundle_sha256"] = "0" * 64
        first = self.reconstruct(prepared)
        first["trace"]["records"].clear()
        first["metadata"]["valuations"].clear()
        self.assertEqual(self.reconstruct(prepared)["trace"], self.trace)
        self.assertEqual(self.reconstruct(prepared)["metadata"], self.extra)
