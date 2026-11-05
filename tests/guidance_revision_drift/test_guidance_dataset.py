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

def rebound(**changes):
    values = profile().to_dict()
    values.update(changes)
    bind(values)
    return values


def forged(original, mutate):
    changed = deepcopy(original)
    mutate(changed)
    return GuidanceDataset(canonical_bytes(changed))


def extra_source(**changes):
    return {"source_id": "zz-extra", "source_uri": "https://example.invalid/extra",
            "captured_at": "2026-01-01T00:00:00Z", "sha256": "0" * 64, "byte_count": 1} | changes


class ReviewCorrectionTests(unittest.TestCase):
    """GDR-CR65 corrections; each case fails on the source Codex published."""

    def test_malformed_locations_refuse_statically_without_echoing_the_location(self):
        for uri in ("https://[bad", "https://[::1/x", "https://exa℀mple.invalid/x", "https://example.invalid/\x7f"):
            with self.subTest(uri=uri), self.assertRaises(GuidanceDatasetError) as caught:
                SourceCapture("fixture", uri, "2026-01-01T00:00:00Z", b"invented")
            self.assertEqual(str(caught.exception), "credential_free_https_source_uri_required")

    def test_unhashable_binding_field_is_a_static_refusal(self):
        for name in ([], {}):
            values = profile().to_dict()
            values["bindings"][0]["field"] = name
            with self.subTest(name=name), self.assertRaises(GuidanceDatasetError):
                GuidanceSourceProfile.from_dict(values)

    def test_scope_at_the_declared_inventory_limit_compiles(self):
        ids = sorted(["fixture-d1", "fixture-d2"] + [f"fixture-z{index:04d}-{'x' * 100}" for index in range(1022)])
        self.assertGreater(len(canonical_bytes(scope(ids))), 65536)
        result = build(scoped=scope(ids))
        self.assertEqual(len(result.to_dict()["missing_profile_ids"]), 1022)
        self.assertEqual(GuidanceDataset(result.canonical_bytes).sha256, result.sha256)

    def test_neighbouring_date_only_and_instant_rows_do_not_establish_order(self):
        for published, instant in (("2025-01-03", "2025-01-03T00:30:00Z"),
                                   ("2025-01-02", "2025-01-02T12:00:00Z"),
                                   ("2025-01-01", "2025-01-01T23:30:00Z")):
            new = profile("fixture-d2", published, None if published == "2025-01-01" else "fixture-d1", published_at=instant)
            old = profile(predecessor="fixture-d2") if published == "2025-01-01" else profile()
            result = build((old, new), scoped=scope(publication_start="2024-12-01")).to_dict()["decisions"]
            with self.subTest(instant=instant):
                self.assertTrue(all("ambiguous_publication_order" in row["refusal_reasons"] for row in result))
                self.assertTrue(all(row["disposition"] == "refused" for row in result))
        # Two clear days between the clocks settle the order under any US issuer date.
        for old, new in ((profile(), profile("fixture-d2", "2025-01-04", "fixture-d1", published_at="2025-01-04T00:30:00Z")),
                         (profile(published_at="2025-01-02T12:00:00Z"), profile("fixture-d2", "2025-01-04", "fixture-d1"))):
            self.assertEqual(build((old, new)).safe_summary()["dispositions"], {"baseline": 1, "comparable_pair": 1})


class EdgePinTests(unittest.TestCase):
    """Boundaries the original methods left unpinned."""

    def test_source_location_rules_are_each_enforced(self):
        for uri in (1, None, "https://example.invalid/" + "a" * 2048, "https:///a", "https://user@example.invalid/a",
                    "https://:secret@example.invalid/a", "https://example.invalid/a b", "https://example.invalid/a\nb"):
            with self.subTest(uri=repr(uri)[:40]), self.assertRaises(InputError):
                SourceCapture("fixture", uri, "2026-01-01T00:00:00Z", b"invented")
        exact = "https://example.invalid/" + "a" * (2048 - len("https://example.invalid/"))
        self.assertEqual(SourceCapture("fixture", exact, "2026-01-01T00:00:00Z", b"invented").source_uri, exact)
        for args in (("bad id", "https://example.invalid/a", "2026-01-01T00:00:00Z", b"x"),
                     ("fixture", "https://example.invalid/a", "2026-01-01", b"x"),
                     ("fixture", "https://example.invalid/a", "2026-01-01T00:00:00Z", b""),
                     ("fixture", "https://example.invalid/a", "2026-01-01T00:00:00Z", "x")):
            with self.subTest(args=args[0::2]), self.assertRaises(InputError):
                SourceCapture(*args)

    def test_profile_fields_refuse_each_invalid_value(self):
        good = profile().to_dict()
        for changes in ({"schema": "gdr.other.v1"}, {"profile_id": "bad id"}, {"predecessor_profile_id": "bad id"},
                        {"source_sha256": "A" * 64}, {"source_uri": "http://example.invalid/a"},
                        {"issues": "x"}, {"issues": [f"code-{index:02d}" for index in range(65)]}, {"issues": ["bad code"]},
                        {"issues": ["b", "a"]}, {"issues": ["a", "a"]}, {"bindings": "x"}):
            with self.subTest(changes=str(changes)[:40]), self.assertRaises(InputError):
                GuidanceSourceProfile.from_dict({**good, **changes})
        for changes in ({"supersedes": "bad id", "kind": "correction"}, {"kind": "guess", "supersedes": "fixture-d0"},
                        {"kind": "disclosure", "supersedes": "fixture-d0"}, {"kind": "correction", "supersedes": None},
                        {"kind": "withdrawal", "supersedes": None}, {"fiscal_year": "2025"}, {"fiscal_year": 1899},
                        {"fiscal_year": 2201}, {"fiscal_year": True}, {"fiscal_end": "2025-10-27"}, {"fiscal_end": "2026-02-06"},
                        {"currency": "bad code"}, {"revenue": {"lower": 1, "upper": 2, "kind": "range"}},
                        {"revenue": {"lower": "1", "upper": "2", "kind": "guess"}},
                        {"published_date": "2026-01-01", "published_at": "2026-01-01T00:00:01Z"}):
            with self.subTest(changes=str(changes)[:60]), self.assertRaises(InputError):
                GuidanceSourceProfile.from_dict(rebound(**changes))
        for changes in ({"fiscal_end": "2025-10-28"}, {"fiscal_end": "2026-02-05"}, {"fiscal_year": 1900}, {"fiscal_year": 2200},
                        {"fiscal_end": None}, {"fiscal_start": None}, {"fiscal_year": None}, {"predecessor_profile_id": "fixture-d0"},
                        {"revenue": {"lower": "1", "upper": "1", "kind": "point"}},
                        {"published_date": "2026-01-01", "published_at": "2026-01-01T00:00:00Z"}):
            with self.subTest(accepted=str(changes)[:60]):
                self.assertEqual(GuidanceSourceProfile.from_dict(rebound(**changes)).to_dict()["schema"],
                                 "gdr.guidance-source-profile.v1")

    def test_every_nonnull_semantic_field_needs_one_valid_binding(self):
        good = profile().to_dict()
        def changed(mutate):
            values = deepcopy(good)
            mutate(values)
            return values
        by_field = {row["field"]: index for index, row in enumerate(good["bindings"])}
        cases = {
            "unbound": lambda v: v["bindings"].pop(by_field["revenue"]),
            "duplicate": lambda v: v["bindings"].append(deepcopy(v["bindings"][0])),
            "bad source": lambda v: v["bindings"][0].update(source_sha256="A" * 64),
            "bad value hash": lambda v: v["bindings"][0].update(value_sha256="A" * 64),
            "empty locator": lambda v: v["bindings"][0].update(locator=""),
            "long locator": lambda v: v["bindings"][0].update(locator="a" * 513),
            "control locator": lambda v: v["bindings"][0].update(locator="a\nb"),
            "numeric locator": lambda v: v["bindings"][0].update(locator=1),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), self.assertRaises(InputError):
                GuidanceSourceProfile.from_dict(changed(mutate))
        def null_binding(values):
            binding = deepcopy(values["bindings"][by_field["eps"]])
            values["eps"] = None
            binding["value_sha256"] = hash_bytes(canonical_bytes({"value": None}))
            values["bindings"][by_field["eps"]] = binding
        with self.assertRaisesRegex(InputError, "semantic_field_binding"):
            GuidanceSourceProfile.from_dict(changed(null_binding))
        exact = changed(lambda v: v["bindings"][0].update(locator="a" * 512))
        self.assertEqual(GuidanceSourceProfile.from_dict(exact).to_dict()["bindings"][0]["locator"], "a" * 512)

    def test_noncanonical_profile_and_dataset_bytes_refuse(self):
        raw = profile().canonical_bytes
        with self.assertRaisesRegex(InputError, "canonical_guidance_profile"):
            GuidanceSourceProfile(b" " + raw)
        dataset = build().canonical_bytes
        with self.assertRaisesRegex(InputError, "canonical_guidance_dataset"):
            GuidanceDataset(b" " + dataset)

    def test_scope_refuses_each_invalid_inventory(self):
        for changes in ({"schema": "gdr.other.v1"}, {"scope_id": "bad id"},
                        {"publication_start": "2026-01-01"}, {"issuer_ids": "fixture-issuer"}, {"issuer_ids": []},
                        {"issuer_ids": ["bad id", "fixture-issuer"]}, {"issuer_ids": ["fixture-issuer", "a"]},
                        {"issuer_ids": ["fixture-issuer", "fixture-issuer"]},
                        {"expected_profile_ids": []}, {"expected_profile_ids": ["bad id", "fixture-d1", "fixture-d2"]},
                        {"expected_profile_ids": ["fixture-d2", "fixture-d1"]}, {"fiscal_years": 2025}, {"fiscal_years": []},
                        {"fiscal_years": list(range(1993, 2026))}, {"fiscal_years": [1899, 2025]}, {"fiscal_years": [2025, 2201]},
                        {"fiscal_years": [True]}, {"fiscal_years": [2026, 2025]}, {"fiscal_years": [2025, 2025]}):
            with self.subTest(changes=str(changes)[:40]), self.assertRaises(InputError):
                build(scoped=scope(**changes))
        with patch.object(guidance_dataset, "MAX_PROFILES", 1), self.assertRaisesRegex(InputError, "scope_inventory"):
            build((profile(),), (source(),), scope(("fixture-d1", "fixture-d2")))
        self.assertEqual(build(scoped=scope(fiscal_years=list(range(1994, 2026)))).safe_summary()["profile_count"], 2)

    def test_profiles_outside_the_declared_inventory_refuse(self):
        with self.assertRaisesRegex(InputError, "outside_declared"):
            build(scoped=scope(("fixture-d2", "fixture-d3")))
        for start, end in (("2025-01-03", "2025-12-31"), ("2025-01-01", "2025-02-01")):
            with self.subTest(start=start), self.assertRaisesRegex(InputError, "outside_declared"):
                build(scoped=scope(publication_start=start, publication_end=end))
        self.assertEqual(build(scoped=scope(publication_start="2025-01-02", publication_end="2025-02-02")).safe_summary()["profile_count"], 2)

    def test_public_dataset_rechecks_each_source_and_profile_row(self):
        original = build().to_dict()
        def add(**changes):
            return lambda value: value["sources"].append(extra_source(**changes))
        cases = {
            "source id": add(source_id="zz bad"), "source uri": add(source_uri="http://example.invalid/a"),
            "source clock": add(captured_at="2026-01-01"), "source hash": add(sha256="A" * 64),
            "zero bytes": add(byte_count=0), "too many bytes": add(byte_count=guidance_dataset.MAX_SOURCE_BYTES + 1),
            "source fields": lambda value: value["sources"].append({"source_id": "zz-extra"}),
            "duplicate source": lambda value: value["sources"].append(deepcopy(value["sources"][-1])),
            "unsorted sources": lambda value: value["sources"].reverse(),
            "unsorted profiles": lambda value: value["profiles"].reverse(),
            "unbound profile": lambda value: value["profiles"][0].update(bindings=[]),
            "schema": lambda value: value.update(schema="gdr.other.v1"),
            "missing gate": lambda value: value["gates"].pop("execution_ready"),
            "extra gate": lambda value: value["gates"].update(extra=False),
            "gates type": lambda value: value.update(gates=[]),
            "missing ids": lambda value: value.update(missing_profile_ids=["fixture-zz"]),
            "profile list": lambda value: value.update(profiles={}),
            "source list": lambda value: value.update(sources={}),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), self.assertRaises(InputError):
                forged(original, mutate)
        accepted = forged(original, lambda value: value["sources"].append(extra_source()))
        self.assertEqual(accepted.safe_summary()["source_count"], 3)

    def test_retained_bytes_require_their_own_hash(self):
        result = build()
        self.assertEqual(GuidanceDataset.from_bytes(result.canonical_bytes, expected_sha256=result.sha256).sha256, result.sha256)
        for expected in ("0" * 64, "A" * 64):
            with self.subTest(expected=expected[:1]), self.assertRaisesRegex(InputError, "hash_mismatch|SHA256"):
                GuidanceDataset.from_bytes(result.canonical_bytes, expected_sha256=expected)
        with self.assertRaisesRegex(InputError, "hash_mismatch"):
            GuidanceDataset.from_bytes(bytearray(result.canonical_bytes), expected_sha256=result.sha256)

    def test_exact_decisions_and_summary_without_financial_values(self):
        result = build()
        self.assertEqual(result.to_dict()["decisions"], [
            {"profile_id": "fixture-d1", "predecessor_profile_id": None, "disposition": "baseline",
             "refusal_reasons": [], "publication_clock_precision": "date"},
            {"profile_id": "fixture-d2", "predecessor_profile_id": "fixture-d1", "disposition": "comparable_pair",
             "refusal_reasons": [], "publication_clock_precision": "date"}])
        self.assertEqual(result.safe_summary(), {"schema": "gdr.guidance-dataset-summary.v1", "dataset_sha256": result.sha256,
            "source_count": 2, "profile_count": 2, "missing_profile_count": 0,
            "dispositions": {"baseline": 1, "comparable_pair": 1}, "refusal_counts": {},
            "gates": {"point_in_time_data": False, "historical_availability_verified": False,
                      "source_completeness_verified": False, "source_authenticity_verified": False,
                      "rights_verified": False, "approved_strategy_input": False, "execution_ready": False}})
        gapped = build(scoped=scope(("fixture-d1", "fixture-d2", "fixture-d3", "fixture-d4")))
        self.assertEqual(gapped.safe_summary()["missing_profile_count"], 2)
        timed = build((profile(published_at="2025-01-02T12:00:00Z"),
                       profile("fixture-d2", "2025-02-02", "fixture-d1", published_at="2025-02-02T12:00:00Z")))
        self.assertEqual({row["publication_clock_precision"] for row in timed.to_dict()["decisions"]}, {"instant"})

    def test_decisions_sort_by_identity_and_chains_are_per_issuer_and_year(self):
        later = profile("fixture-a-later", "2025-03-02", "fixture-z-earlier")
        earlier = profile("fixture-z-earlier", "2025-01-02")
        decisions = build((later, earlier), captures=(source("fixture-a-later"), source("fixture-z-earlier")),
                          scoped=scope(("fixture-a-later", "fixture-z-earlier"))).to_dict()["decisions"]
        self.assertEqual([row["profile_id"] for row in decisions], ["fixture-a-later", "fixture-z-earlier"])
        self.assertEqual([row["disposition"] for row in decisions], ["comparable_pair", "baseline"])
        ids = ("fixture-d1", "fixture-d2")
        other_year = profile("fixture-d2", "2025-02-02", fiscal_year=2026, fiscal_start="2026-01-01", fiscal_end="2026-12-31")
        self.assertEqual(build((profile(), other_year), scoped=scope(ids, fiscal_years=[2025, 2026])).safe_summary()["dispositions"], {"baseline": 2})
        other_issuer = profile("fixture-d2", "2025-02-02", issuer_id="fixture-other")
        self.assertEqual(build((profile(), other_issuer), scoped=scope(ids, issuer_ids=["fixture-issuer", "fixture-other"])).safe_summary()["dispositions"], {"baseline": 2})
        wrong = profile("fixture-d2", "2025-02-02", fiscal_year=2026, fiscal_start="2026-01-01", fiscal_end="2026-12-31",
                        kind="correction", supersedes="fixture-d1", revenue=None, eps=None)
        decision = build((profile(), wrong), scoped=scope(ids, fiscal_years=[2025, 2026])).to_dict()["decisions"][1]
        self.assertIn("unknown_or_wrong_identity_control_target", decision["refusal_reasons"])

    def test_inputs_compile_to_identical_bytes_in_any_order(self):
        rows = (profile(), profile("fixture-d2", "2025-02-02", "fixture-d1"))
        first, second = source(), source("fixture-d2")
        self.assertEqual(build(rows, (first, second)).sha256, build(rows[::-1], (second, first)).sha256)

    def test_compiler_refuses_wrong_container_and_member_types(self):
        rows, captures = (profile(), profile("fixture-d2", "2025-02-02", "fixture-d1")), (source(), source("fixture-d2"))
        for fields in (dict(profiles=list(rows), captures=captures), dict(profiles=rows, captures=list(captures)),
                       dict(profiles=(), captures=captures), dict(profiles=rows, captures=()),
                       dict(profiles=rows, captures=(object(),)), dict(profiles=(rows[0].to_dict(),), captures=captures),
                       dict(profiles=rows, captures=(source(), source()))):
            with self.subTest(fields=sorted(type(x).__name__ for x in fields.values())), self.assertRaises(InputError):
                compile_guidance_dataset(scope=scope(), **fields)
        with patch.object(guidance_dataset, "MAX_PROFILES", 1), self.assertRaises(InputError):
            compile_guidance_dataset(scope=scope(("fixture-d1",)), profiles=rows, captures=captures[:1])
        with patch.object(guidance_dataset, "MAX_DATASET_BYTES", 2048), self.assertRaisesRegex(InputError, "byte_limit"):
            build()

    def test_control_events_and_predecessor_defects_report_their_named_reasons(self):
        known = profile("fixture-d2", "2025-02-02", "fixture-d1", kind="correction", supersedes="fixture-d1")
        decision = build((profile(), known)).to_dict()["decisions"][1]
        self.assertEqual(decision["disposition"], "control_event")
        self.assertEqual(decision["refusal_reasons"], ["control_event_cannot_create_comparable_pair"])
        flagged = profile(issues=["fixture-table-unreadable"])
        decisions = build((flagged, profile("fixture-d2", "2025-02-02", "fixture-d1"))).to_dict()["decisions"]
        self.assertEqual(decisions[0]["refusal_reasons"], ["fixture-table-unreadable"])
        self.assertEqual(decisions[0]["disposition"], "refused")
        self.assertEqual(decisions[1]["refusal_reasons"], ["predecessor_issue_fixture-table-unreadable"])
        current_flag = profile("fixture-d2", "2025-02-02", "fixture-d1", issues=["fixture-table-unreadable"])
        self.assertEqual(build((profile(), current_flag)).to_dict()["decisions"][1]["refusal_reasons"], ["fixture-table-unreadable"])
        unknown_year = profile("fixture-d2", "2025-02-02", "fixture-d1", fiscal_year=None)
        self.assertIn("unresolved_profile_identity_or_fiscal_year", build((profile(), unknown_year)).safe_summary()["refusal_counts"])
        missing = profile("fixture-d2", "2025-02-02", "fixture-d1", eps=None)
        reasons = build((profile(), missing)).to_dict()["decisions"][1]["refusal_reasons"]
        self.assertEqual(reasons.count("current_missing_eps"), 1)
        baseline = build((profile(eps=None),), (source(),), scope(("fixture-d1",))).to_dict()["decisions"][0]
        self.assertEqual((baseline["disposition"], baseline["refusal_reasons"]), ("refused", ["current_missing_eps"]))

    def test_unsupported_units_and_bases_are_refused_even_when_unchanged(self):
        for changes, reason in (({"currency": "EUR"}, "unsupported_currency_or_units"),
                                ({"revenue_units": "EUR"}, "unsupported_currency_or_units"),
                                ({"eps_units": "EUR_per_share"}, "unsupported_currency_or_units"),
                                ({"revenue_basis": "non-gaap"}, "unsupported_accounting_basis"),
                                ({"eps_basis": "gaap"}, "unsupported_accounting_basis"),
                                ({"period": "Q1"}, "full_year_guidance_required")):
            old = profile(**changes)
            new = profile("fixture-d2", "2025-02-02", "fixture-d1", **changes)
            with self.subTest(changes=changes):
                self.assertIn(reason, build((old, new)).to_dict()["decisions"][1]["refusal_reasons"])
        for changes, reason in (({"revenue_basis": "non-gaap"}, "unsupported_accounting_basis"),
                                ({"currency": "EUR"}, "unsupported_currency_or_units"),
                                ({"period": "Q1"}, "full_year_guidance_required")):
            with self.subTest(predecessor_only=changes):
                self.assertIn(reason, build((profile(**changes), profile("fixture-d2", "2025-02-02", "fixture-d1"))).to_dict()["decisions"][1]["refusal_reasons"])
        dollars = profile("fixture-d2", "2025-02-02", "fixture-d1", revenue_units="USD")
        self.assertEqual(build((profile(revenue_units="USD"), dollars)).safe_summary()["dispositions"], {"baseline": 1, "comparable_pair": 1})

    def test_publication_on_the_fiscal_end_date_has_not_expired(self):
        old = profile(fiscal_start="2024-02-01", fiscal_end="2025-02-02")
        new = profile("fixture-d2", "2025-02-02", "fixture-d1", fiscal_start="2024-02-01", fiscal_end="2025-02-02")
        self.assertEqual(build((old, new)).safe_summary()["dispositions"], {"baseline": 1, "comparable_pair": 1})

    def test_same_day_date_only_and_instant_rows_sort_without_a_type_error(self):
        old = profile()
        new = profile("fixture-d2", "2025-01-02", "fixture-d1", published_at="2025-01-02T12:00:00Z")
        result = build((old, new)).to_dict()["decisions"]
        self.assertTrue(all("ambiguous_publication_order" in row["refusal_reasons"] for row in result))
        self.assertEqual(result[1]["predecessor_profile_id"], "fixture-d1")


if __name__ == "__main__":
    unittest.main()
