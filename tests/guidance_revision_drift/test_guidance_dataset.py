"""Invented disclosure sources exercise dataset custody, never market signals."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift import guidance_dataset
from research.guidance_revision_drift.guidance_dataset import (
    GuidanceDataset, GuidanceDatasetError, GuidanceSourceProfile, SourceCapture,
    compile_guidance_dataset,
)
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes


def source(identity="fixture-d1", captured="2026-01-01T00:00:00Z"):
    return SourceCapture(identity, "https://example.invalid/" + identity,
                         captured, ("invented original " + identity).encode())


def profile(identity="fixture-d1", published="2025-01-02", predecessor=None, **changes):
    capture = source(identity)
    values = {"schema": "gdr.guidance-source-profile.v1", "profile_id": identity,
        "predecessor_profile_id": predecessor, "issuer_id": "fixture-issuer",
        "security_id": "fixture-common", "period": "FY", "fiscal_year": 2025,
        "fiscal_start": "2025-01-01", "fiscal_end": "2025-12-31", "currency": "USD",
        "revenue_units": "USD_millions", "eps_units": "USD_per_share",
        "revenue_basis": "gaap", "eps_basis": "adj",
        "adjustment_definition": "fixture-adjustments-v1", "share_basis": "fixture-diluted-v1",
        "scope": "fixture-consolidated-v1", "revenue": {"lower": "100", "upper": "110", "kind": "range"},
        "eps": {"lower": "1", "upper": "2", "kind": "range"}, "kind": "disclosure", "supersedes": None,
        "published_date": published, "published_at": None, "captured_at": capture.captured_at,
        "source_uri": capture.source_uri, "source_sha256": capture.metadata()["sha256"],
        "bindings": [], "issues": []}
    values.update(changes)
    bind(values)
    return GuidanceSourceProfile.from_dict(values)


def bind(values):
    nonsemantic = {"schema", "profile_id", "predecessor_profile_id", "captured_at",
                   "source_uri", "source_sha256", "bindings", "issues"}
    values["bindings"] = [{"field": name, "source_sha256": values["source_sha256"],
        "locator": "invented source field " + name,
        "value_sha256": hash_bytes(canonical_bytes({"value": value}))}
        for name, value in sorted(values.items()) if name not in nonsemantic and value is not None]


def scope(ids=("fixture-d1", "fixture-d2"), **changes):
    values = {"schema": "gdr.guidance-dataset-scope.v1", "scope_id": "fixture-audit",
        "publication_start": "2025-01-01", "publication_end": "2025-12-31",
        "issuer_ids": ["fixture-issuer"], "fiscal_years": [2025], "expected_profile_ids": list(ids)}
    values.update(changes)
    return values


def build(profiles=None, captures=None, scoped=None):
    rows = profiles or (profile(), profile("fixture-d2", "2025-02-02", "fixture-d1"))
    sources = captures or tuple(source(row.to_dict()["profile_id"]) for row in rows)
    return compile_guidance_dataset(scope=scoped or scope(), profiles=rows, captures=sources)


class GuidanceDatasetTests(unittest.TestCase):
    def test_unchanged_ranges_form_structural_pair_without_strategy_arithmetic(self):
        with patch("research.guidance_revision_drift.formulas.evaluate_range_revisions", side_effect=AssertionError("strategy maths called")):
            result = build()
        self.assertEqual([row["disposition"] for row in result.to_dict()["decisions"]], ["baseline", "comparable_pair"])
        self.assertEqual(result.safe_summary()["dispositions"], {"baseline": 1, "comparable_pair": 1})
        self.assertTrue(all(value is False for value in result.to_dict()["gates"].values()))
        self.assertNotEqual(result.safe_summary().get("revenue"), "100")
        self.assertNotIn("revenue", result.safe_summary())

    def test_canonical_detached_round_trip_retains_expected_hash(self):
        supplied = profile().to_dict()
        checked = GuidanceSourceProfile.from_dict(supplied)
        supplied["revenue"]["lower"] = "999"
        self.assertEqual(checked.to_dict()["revenue"]["lower"], "100")
        result = build((checked, profile("fixture-d2", "2025-02-02", "fixture-d1")))
        retained = GuidanceDataset.from_bytes(result.canonical_bytes, expected_sha256=result.sha256)
        self.assertEqual(retained.sha256, result.sha256)
        result.to_dict()["profiles"][0]["revenue"]["lower"] = "999"
        self.assertEqual(result.sha256, retained.sha256)
        with self.assertRaises(FrozenInstanceError):
            checked.canonical_bytes = b"{}"
        with self.assertRaises(InputError):
            GuidanceDataset.from_bytes(result.canonical_bytes + b"\n", expected_sha256=result.sha256)

    def test_source_content_clock_uri_and_binding_mutations_refuse(self):
        good = source()
        for changed in (SourceCapture(good.source_id, good.source_uri, good.captured_at, b"different"),
                        source(captured="2026-01-02T00:00:00Z"),
                        SourceCapture(good.source_id, good.source_uri + "/other", good.captured_at, good.raw_bytes)):
            with self.subTest(source=changed.source_id), self.assertRaises(InputError):
                build(captures=(changed, source("fixture-d2")))
        supplied = profile().to_dict()
        supplied["revenue"]["lower"] = "101"
        with self.assertRaisesRegex(InputError, "binding_value_hash"):
            GuidanceSourceProfile.from_dict(supplied)
        supplied = profile().to_dict()
        supplied["bindings"][0]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(InputError, "source_bytes_missing"):
            build((GuidanceSourceProfile.from_dict(supplied), profile("fixture-d2", "2025-02-02", "fixture-d1")))

    def test_local_source_byte_caps_accept_exact_boundary_and_refuse_overflow(self):
        self.assertEqual(guidance_dataset.MAX_SOURCE_BYTES, 32 * 1024 * 1024)
        self.assertEqual(guidance_dataset.MAX_TOTAL_SOURCE_BYTES, 96 * 1024 * 1024)
        self.assertEqual(guidance_dataset.MAX_DATASET_BYTES, 4 * 1024 * 1024)
        with patch.object(guidance_dataset, "MAX_SOURCE_BYTES", 8):
            exact = SourceCapture("fixture", "https://example.invalid/fixture",
                                  "2026-01-01T00:00:00Z", b"invented")
            self.assertEqual(exact.metadata()["byte_count"], 8)
            with self.assertRaisesRegex(InputError, "bounded_source_capture_bytes"):
                SourceCapture("fixture", "https://example.invalid/fixture",
                              "2026-01-01T00:00:00Z", b"invented+")
        captures = (source(), source("fixture-d2"))
        total = sum(len(row.raw_bytes) for row in captures)
        original = build(captures=captures)
        with patch.object(guidance_dataset, "MAX_TOTAL_SOURCE_BYTES", total):
            self.assertEqual(build(captures=captures).sha256, original.sha256)
        with patch.object(guidance_dataset, "MAX_TOTAL_SOURCE_BYTES", total - 1):
            with self.assertRaisesRegex(InputError, "total_source_capture_byte_limit"):
                build(captures=captures)
            with self.assertRaisesRegex(InputError, "total_source_capture_byte_limit"):
                GuidanceDataset(original.canonical_bytes)

    def test_unknown_authority_fields_missing_fields_and_bad_numeric_bounds_refuse(self):
        good = profile().to_dict()
        for name in good:
            changed = deepcopy(good)
            del changed[name]
            with self.subTest(missing=name), self.assertRaises(InputError):
                GuidanceSourceProfile.from_dict(changed)
        for extra in ("approved", "point_in_time_data", "qc_allowed", "rights_verified"):
            with self.subTest(extra=extra), self.assertRaises(InputError):
                GuidanceSourceProfile.from_dict({**good, extra: True})
        for value in ("NaN", "Infinity", "1e2", True, 1.0):
            changed = deepcopy(good)
            changed["eps"]["lower"] = value
            with self.subTest(value=value), self.assertRaises(InputError):
                bind(changed)
                GuidanceSourceProfile.from_dict(changed)
        for value in ({"lower": "2", "upper": "1", "kind": "range"},
                      {"lower": "1", "upper": "1", "kind": "range"},
                      {"lower": "1", "upper": "2", "kind": "point"}):
            with self.subTest(value=value), self.assertRaises(InputError):
                profile(eps=value)

    def test_same_labels_do_not_hide_changed_fiscal_share_scope_or_adjustment_basis(self):
        for changes, refusal in (({"fiscal_start": "2024-12-31"}, "changed_fiscal_start"),
                                 ({"share_basis": "fixture-split-v2"}, "changed_share_basis"),
                                 ({"scope": "fixture-acquisition-v2"}, "changed_scope"),
                                 ({"adjustment_definition": "fixture-adjustments-v2"}, "changed_adjustment_definition"),
                                 ({"currency": "EUR"}, "changed_currency"),
                                 ({"security_id": "fixture-new-common"}, "changed_security_id"),
                                 ({"period": "Q1"}, "full_year_guidance_required")):
            changed = profile("fixture-d2", "2025-02-02", "fixture-d1", **changes)
            decision = build((profile(), changed)).to_dict()["decisions"][1]
            with self.subTest(changes=changes):
                self.assertEqual(decision["disposition"], "refused")
                self.assertIn(refusal, decision["refusal_reasons"])

    def test_explicit_unknowns_remain_visible_and_cannot_be_skipped_as_predecessors(self):
        missing = profile("fixture-d2", "2025-02-02", "fixture-d1", eps=None, currency=None)
        current = profile("fixture-d3", "2025-03-02", "fixture-d2")
        result = build((profile(), missing, current), scoped=scope(("fixture-d1", "fixture-d2", "fixture-d3")))
        decision = result.to_dict()["decisions"][2]
        self.assertEqual(decision["predecessor_profile_id"], "fixture-d2")
        self.assertIn("predecessor_missing_eps", decision["refusal_reasons"])
        self.assertIn("predecessor_missing_currency", decision["refusal_reasons"])
        skipped = profile("fixture-d3", "2025-03-02", "fixture-d1")
        decision = build((profile(), missing, skipped), scoped=scope(("fixture-d1", "fixture-d2", "fixture-d3"))).to_dict()["decisions"][2]
        self.assertIn("declared_predecessor_is_not_immediate_supplied_profile", decision["refusal_reasons"])

    def test_missing_declared_release_blocks_pairs_instead_of_certifying_a_gap(self):
        result = build(scoped=scope(("fixture-d1", "fixture-d2", "fixture-missing")))
        self.assertEqual(result.to_dict()["missing_profile_ids"], ["fixture-missing"])
        self.assertNotIn("comparable_pair", result.safe_summary()["dispositions"])
        self.assertIn("incomplete_declared_inventory", result.to_dict()["decisions"][1]["refusal_reasons"])

    def test_control_event_cannot_form_pair_or_be_bypassed(self):
        for kind in ("correction", "withdrawal"):
            control = profile("fixture-d2", "2025-02-02", "fixture-d1", kind=kind,
                              supersedes="fixture-d1", revenue=None, eps=None)
            new = profile("fixture-d3", "2025-03-02", "fixture-d2")
            result = build((profile(), control, new), scoped=scope(("fixture-d1", "fixture-d2", "fixture-d3")))
            self.assertEqual(result.to_dict()["decisions"][1]["disposition"], "control_event")
            self.assertIn("immediate_predecessor_is_control_event", result.to_dict()["decisions"][2]["refusal_reasons"])
        control = profile("fixture-d2", "2025-02-02", "fixture-d1", kind="correction", supersedes="fixture-unknown")
        self.assertIn("unknown_or_wrong_identity_control_target", build((profile(), control)).to_dict()["decisions"][1]["refusal_reasons"])

    def test_date_only_clocks_are_retained_and_ambiguous_same_day_refuses(self):
        result = build()
        self.assertEqual(result.to_dict()["decisions"][1]["publication_clock_precision"], "date")
        self.assertIsNone(result.to_dict()["profiles"][0]["published_at"])
        equal_day = profile("fixture-d2", "2025-01-02", "fixture-d1")
        self.assertIn("ambiguous_publication_order", build((profile(), equal_day)).to_dict()["decisions"][1]["refusal_reasons"])
        with self.assertRaises(InputError):
            profile(published_at="2025-01-02T12:00:00")
        with self.assertRaises(InputError):
            profile(published_at="2025-01-03T12:00:00Z")
        with self.assertRaises(InputError):
            profile(captured_at="2024-01-01T00:00:00Z")

    def test_fiscal_year_label_is_independent_of_calendar_end_year(self):
        old = profile(fiscal_year=2026)
        new = profile("fixture-d2", "2025-02-02", "fixture-d1",
                      fiscal_year=2026)
        self.assertEqual(build((old, new), scoped=scope(fiscal_years=[2026])).safe_summary()["dispositions"]["comparable_pair"], 1)

    def test_expired_fiscal_guidance_is_retained_but_cannot_form_pair(self):
        old = profile(fiscal_start="2024-01-01", fiscal_end="2024-12-31")
        new = profile("fixture-d2", "2025-02-02", "fixture-d1",
                      fiscal_start="2024-01-01", fiscal_end="2024-12-31")
        result = build((old, new))
        self.assertNotIn("comparable_pair", result.safe_summary()["dispositions"])
        self.assertIn("fiscal_year_expired_at_publication", result.to_dict()["decisions"][1]["refusal_reasons"])

    def test_fractional_publication_instants_sort_by_time_not_text(self):
        old = profile(published_at="2025-01-02T12:00:00Z")
        new = profile("fixture-d2", "2025-01-02", "fixture-d1",
                      published_at="2025-01-02T12:00:00.1Z")
        result = build((old, new)).to_dict()["decisions"]
        self.assertEqual(result[0]["disposition"], "baseline")
        self.assertEqual(result[1]["disposition"], "comparable_pair")

    def test_equal_instants_with_different_fractional_spellings_are_ambiguous(self):
        old = profile(published_at="2025-01-02T12:00:00Z")
        new = profile("fixture-d2", "2025-01-02", "fixture-d1",
                      published_at="2025-01-02T12:00:00.0Z")
        result = build((old, new))
        self.assertNotIn("comparable_pair", result.safe_summary()["dispositions"])
        self.assertTrue(all("ambiguous_publication_order" in row["refusal_reasons"] for row in result.to_dict()["decisions"]))

    def test_profile_scope_duplicate_identity_and_unresolved_identity_cannot_escape(self):
        for changes in ({"issuer_id": "fixture-other"}, {"fiscal_year": 2024}, {"published_date": "2024-12-31"}):
            with self.subTest(changes=changes), self.assertRaises(InputError):
                build((profile(**changes), profile("fixture-d2", "2025-02-02", "fixture-d1")))
        with self.assertRaises(InputError):
            build((profile(), profile()))
        unknown = profile("fixture-d2", "2025-02-02", "fixture-d1", issuer_id=None)
        result = build((profile(), unknown))
        self.assertNotIn("comparable_pair", result.safe_summary()["dispositions"])
        self.assertIn("unresolved_profile_identity_or_fiscal_year", result.safe_summary()["refusal_counts"])

    def test_public_dataset_constructor_rejects_forged_inventory_and_decisions(self):
        original = build().to_dict()
        mutations = []
        for name, value in (("sources", []), ("profiles", []), ("gates", {"execution_ready": True})):
            mutations.append({**original, name: value})
        duplicate = deepcopy(original)
        duplicate["profiles"].append(deepcopy(duplicate["profiles"][0]))
        mutations.append(duplicate)
        missing = deepcopy(original)
        missing["sources"].pop(0)
        mutations.append(missing)
        malformed = deepcopy(original)
        malformed["sources"][0]["byte_count"] = True
        mutations.append(malformed)
        outside = deepcopy(original)
        outside["scope"]["publication_end"] = "2025-01-31"
        mutations.append(outside)
        forged_decision = deepcopy(original)
        forged_decision["decisions"][1]["disposition"] = "approved"
        mutations.append(forged_decision)
        numeric_false = deepcopy(original)
        numeric_false["gates"]["execution_ready"] = 0
        mutations.append(numeric_false)
        for changed in mutations:
            with self.subTest(keys=list(changed)), self.assertRaises(InputError):
                GuidanceDataset(canonical_bytes(changed))

    def test_tampering_frozen_object_is_rechecked_before_summary_or_compile(self):
        document = profile()
        object.__setattr__(document, "canonical_bytes", b"{}")
        with self.assertRaises(InputError):
            build((document, profile("fixture-d2", "2025-02-02", "fixture-d1")))
        dataset = build()
        object.__setattr__(dataset, "canonical_bytes", b"{}")
        with self.assertRaises(InputError):
            dataset.safe_summary()
        capture = source()
        object.__setattr__(capture, "captured_at", "yesterday")
        with self.assertRaises(InputError):
            build(captures=(capture, source("fixture-d2")))

    def test_credential_bearing_source_uris_and_unknown_bindings_refuse(self):
        for uri in ("https://example.invalid/source?api_key=secret", "https://user:secret@example.invalid/a",
                    "http://example.invalid/a", "https://example.invalid/a#secret"):
            with self.subTest(uri=uri), self.assertRaises(InputError):
                SourceCapture("fixture", uri, "2026-01-01T00:00:00Z", b"invented")
        supplied = profile().to_dict()
        supplied["bindings"][0]["field"] = "approved"
        with self.assertRaises(InputError):
            GuidanceSourceProfile.from_dict(supplied)


if __name__ == "__main__":
    unittest.main()
