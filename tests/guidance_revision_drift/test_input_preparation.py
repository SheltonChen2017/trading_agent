"""Invented named files prove preparation without any real-data or QC run."""
from __future__ import annotations

import contextlib
from datetime import timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import load_candidate
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes, utc
from research.guidance_revision_drift.input_preparation import prepare_inputs, inspect_local_inputs, main
from research.guidance_revision_drift.guidance_inputs import GuidanceLedger
from tests.guidance_revision_drift.test_guidance_inputs import receipt, raised
from tests.guidance_revision_drift.test_historical_market import market_body


def fixture_set(candidate):
    old, new = receipt(), raised()
    stock = market_body()
    stock["security_id"] = "fixture-security"
    spy = market_body()
    spy.update(security_id="fixture-spy", symbol="SPY", role="benchmark")
    files = {"old-raw.json": old.raw_bytes, "old-doc.json": old.document.canonical_bytes,
             "new-raw.json": new.raw_bytes, "new-doc.json": new.document.canonical_bytes,
             "stock.json": canonical_bytes(stock), "spy.json": canonical_bytes(spy)}
    manifest = {"schema": "gdr.local-input-manifest.v1", "candidate_sha256": candidate.sha256,
        "data_class": "invented_fixture", "owner_scope_reference": None, "source_rights_reference": None,
        "calendar_sha256": hash_bytes(b"invented-calendar-not-verified"),
        "files": {name: hash_bytes(raw) for name, raw in files.items()},
        "guidance_receipts": [
            {"raw_file": "old-raw.json", "document_file": "old-doc.json",
             "received_at": old.received_at, "validated_at": old.validated_at},
            {"raw_file": "new-raw.json", "document_file": "new-doc.json",
             "received_at": new.received_at, "validated_at": new.validated_at}],
        "stock_market_file": "stock.json", "benchmark_market_file": "spy.json",
        "decision_at": "2025-04-04T14:00:00Z", "submitted_at": "2025-04-04T14:00:00Z",
        "callback_at": "2025-04-04T14:01:00Z"}
    return manifest, files


class InputPreparationTests(unittest.TestCase):
    def setUp(self):
        self.candidate = load_candidate()
        self.manifest, self.files = fixture_set(self.candidate)

    def run_preparation(self):
        raw = canonical_bytes(self.manifest)
        return prepare_inputs(self.candidate, raw, self.files, expected_manifest_sha256=hash_bytes(raw))

    def replace_file(self, name, values):
        raw = canonical_bytes(values)
        self.files[name] = raw
        self.manifest["files"][name] = hash_bytes(raw)

    def test_paired_preparation_binds_both_sources_without_authority_or_source_rows(self):
        result = self.run_preparation()
        self.assertEqual(result["status"], "structurally_prepared")
        self.assertEqual(result["guidance"]["qualifying_arithmetic_comparisons"], 1)
        self.assertEqual([row["role"] for row in result["market"]], ["stock", "benchmark"])
        self.assertTrue(all(row["status"] == "structurally_prepared" for row in result["market"]))
        for key in ("backtest_ready", "point_in_time_data", "source_rights_verified", "source_completeness_verified",
                    "calendar_and_mapping_verified", "common_history_verified", "data_class_verified", "orders_allowed",
                    "qc_access_allowed", "outcome_evaluation_allowed"):
            self.assertIs(result[key], False)
        encoded = canonical_bytes(result)
        for private in (b"raw_hex", b"bid_price", b"eps", b"revenue", b"invented_source"):
            self.assertNotIn(private, encoded)
        self.assertEqual(result["file_sha256s"], self.manifest["files"])

    def test_exact_inventory_hashes_and_roles_refuse_missing_extra_or_reused_inputs(self):
        for name in tuple(self.files):
            original = self.files.pop(name)
            with self.subTest(name=name), self.assertRaises(InputError):
                self.run_preparation()
            self.files[name] = original
        self.files["extra.json"] = b"{}"
        with self.assertRaises(InputError):
            self.run_preparation()
        del self.files["extra.json"]
        self.files["old-raw.json"] = b"altered"
        with patch("research.guidance_revision_drift.input_preparation.GuidanceLedger", side_effect=AssertionError("parsed before hashes")), \
             self.assertRaises(InputError):
            self.run_preparation()
        self.manifest["benchmark_market_file"] = "stock.json"
        with self.assertRaises(InputError):
            self.run_preparation()

    def test_stock_spy_identity_and_session_must_match_without_aliasing(self):
        spy = json.loads(self.files["spy.json"])
        spy["security_id"] = "fixture-security"
        self.replace_file("spy.json", spy)
        with self.assertRaises(InputError):
            self.run_preparation()
        self.manifest, self.files = fixture_set(self.candidate)
        spy = json.loads(self.files["spy.json"])
        spy["role"] = "stock"
        self.replace_file("spy.json", spy)
        with self.assertRaises(InputError):
            self.run_preparation()
        self.manifest, self.files = fixture_set(self.candidate)
        doc = json.loads(self.files["new-doc.json"])
        doc["security_id"] = "other-security"
        self.replace_file("new-doc.json", doc)
        with self.assertRaises(InputError):
            self.run_preparation()

    def test_bad_quote_retains_both_legs_and_a_named_refusal(self):
        stock = json.loads(self.files["stock.json"])
        stock["quotes"][0]["bid_price"] = "100"
        self.replace_file("stock.json", stock)
        report = self.run_preparation()
        self.assertEqual(report["status"], "structurally_blocked")
        self.assertEqual(report["market"][0]["status"], "refused")
        self.assertEqual(report["market"][1]["status"], "structurally_prepared")
        self.assertFalse(report["backtest_ready"])

    def test_single_provider_issuer_epoch_and_identical_paired_session_are_isolated(self):
        for field in ("provider", "issuer_id"):
            doc = json.loads(self.files["new-doc.json"])
            doc[field] = "different-identity"
            self.replace_file("new-doc.json", doc)
            with self.subTest(field=field), self.assertRaisesRegex(InputError, "single issuer and provider"):
                self.run_preparation()
            self.manifest, self.files = fixture_set(self.candidate)
        # The shifted benchmark is internally valid; only cross-leg equality
        # can refuse it, rather than a malformed individual quote/session.
        spy = json.loads(self.files["spy.json"])
        spy["session_date"] = "2025-04-07"
        for key in ("session_open_utc", "session_close_utc"):
            spy[key] = (utc(spy[key]) + timedelta(days=3)).isoformat().replace("+00:00", "Z")
        for quote in spy["quotes"]:
            for key in ("sip_timestamp", "participant_timestamp"):
                quote[key] += 3 * 86400 * 1_000_000_000
        for minute in spy["minutes"]:
            minute["t"] += 3 * 86400 * 1000
        self.replace_file("spy.json", spy)
        with self.assertRaisesRegex(InputError, "session bounds differ"):
            self.run_preparation()

    def test_zero_qualifying_comparisons_is_structural_only_never_strategy_readiness(self):
        self.manifest["guidance_receipts"].pop()
        for name in ("new-raw.json", "new-doc.json"):
            del self.files[name]
            del self.manifest["files"][name]
        result = self.run_preparation()
        self.assertEqual(result["status"], "structurally_prepared")
        self.assertEqual(result["guidance"]["qualifying_arithmetic_comparisons"], 0)
        self.assertEqual(result["guidance"]["observations"][0]["status"], "baseline")
        self.assertFalse(result["backtest_ready"])
        self.assertFalse(result["outcome_evaluation_allowed"])

    def test_no_future_volume_or_wrong_clock_order(self):
        self.manifest["submitted_at"] = "2025-04-04T14:00:00.000001Z"
        result = self.run_preparation()
        self.assertEqual(result["status"], "structurally_blocked")
        self.assertTrue(all(row["status"] == "refused" for row in result["market"]))
        self.manifest["callback_at"] = "2025-04-04T13:59:00Z"
        with self.assertRaises(InputError):
            self.run_preparation()

    def test_historical_references_never_verify_rights_and_protected_dates_refuse(self):
        self.manifest["data_class"] = "historical_reconstruction"
        with self.assertRaises(InputError):
            self.run_preparation()
        self.manifest["owner_scope_reference"] = "0" * 64
        self.manifest["source_rights_reference"] = "1" * 64
        result = self.run_preparation()
        self.assertFalse(result["source_rights_verified"])
        self.assertFalse(result["outcome_evaluation_allowed"])
        self.manifest["callback_at"] = "2026-09-01T14:01:00Z"
        with self.assertRaises(InputError):
            self.run_preparation()

    def test_fixture_label_does_not_bypass_protected_callback_or_market_session(self):
        self.manifest["callback_at"] = "2026-09-01T14:01:00Z"
        with self.assertRaisesRegex(InputError, "protected-date input"):
            self.run_preparation()
        self.manifest, self.files = fixture_set(self.candidate)
        for name in ("stock.json", "spy.json"):
            market = json.loads(self.files[name])
            shift = utc("2026-09-01T13:30:00Z") - utc(market["session_open_utc"])
            market["session_date"] = "2026-09-01"
            for key in ("session_open_utc", "session_close_utc"):
                market[key] = (utc(market[key]) + shift).isoformat().replace("+00:00", "Z")
            seconds = shift.days * 86400 + shift.seconds
            for quote in market["quotes"]:
                for key in ("sip_timestamp", "participant_timestamp"):
                    quote[key] += seconds * 1_000_000_000
            for minute in market["minutes"]:
                minute["t"] += seconds * 1000
            self.replace_file(name, market)
        with self.assertRaisesRegex(InputError, "market file contains protected-date input"):
            self.run_preparation()

    def test_manifest_rejects_unknown_authority_fields_paths_and_bad_retained_hash(self):
        for name in ("../private", "/private", "https://provider/data", "folder/data", ".env"):
            with self.subTest(name=name):
                self.manifest["files"] = {name: "0" * 64}
                with self.assertRaises(InputError):
                    self.run_preparation()
        self.manifest, self.files = fixture_set(self.candidate)
        for key in ("approved", "point_in_time_data", "ready_for_backtesting", "api_key"):
            self.manifest[key] = True
            with self.subTest(key=key), self.assertRaises(InputError):
                self.run_preparation()
            del self.manifest[key]
        with self.assertRaises(InputError):
            prepare_inputs(self.candidate, canonical_bytes(self.manifest), self.files,
                           expected_manifest_sha256="0" * 64)

    def test_projections_are_detached_and_preparation_is_pure(self):
        expected = canonical_bytes(self.run_preparation())
        report = self.run_preparation()
        report["file_sha256s"].clear()
        report["market"].clear()
        with patch("builtins.open", side_effect=AssertionError("file forbidden")), \
             patch("os.getenv", side_effect=AssertionError("environment forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("subprocess.run", side_effect=AssertionError("process forbidden")):
            self.assertEqual(canonical_bytes(self.run_preparation()), expected)

    def test_caller_cannot_replace_named_bytes_after_hash_verification(self):
        expected = canonical_bytes(self.run_preparation())

        def replace_caller_map():
            self.files["old-doc.json"] = b"UNVERIFIED-PRIVATE-CONTENT"
            self.files["stock.json"] = b"UNVERIFIED-PRIVATE-CONTENT"
            return GuidanceLedger()

        with patch("research.guidance_revision_drift.input_preparation.GuidanceLedger",
                   side_effect=replace_caller_map):
            self.assertEqual(canonical_bytes(self.run_preparation()), expected)

    def test_named_regular_files_cli_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, raw in self.files.items():
                (root / name).write_bytes(raw)
            raw_manifest = canonical_bytes(self.manifest)
            manifest = root / "manifest.json"
            manifest.write_bytes(raw_manifest)
            expected = self.run_preparation()
            self.assertEqual(inspect_local_inputs(self.candidate, manifest,
                expected_manifest_sha256=hash_bytes(raw_manifest)), expected)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--manifest", str(manifest), "--sha256", hash_bytes(raw_manifest)]), 0)
            self.assertEqual(json.loads(output.getvalue()), expected)
            (root / "old-raw.json").unlink()
            (root / "old-raw.json").symlink_to(root / "new-raw.json")
            with self.assertRaises(InputError):
                inspect_local_inputs(self.candidate, manifest, expected_manifest_sha256=hash_bytes(raw_manifest))

    def test_cli_error_never_echoes_private_content_or_traceback(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(["--manifest", "/nonexistent/SECRET.json", "--sha256", "0" * 64])
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())


if __name__ == "__main__":
    unittest.main()
