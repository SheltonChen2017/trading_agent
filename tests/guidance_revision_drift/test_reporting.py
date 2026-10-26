"""Paired synthetic diagnostics retain missing dates and never imply acceptance."""
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift import reporting


D = Decimal
DATES = tuple(date(2025, 1, i) for i in (2, 3, 6))


class ReportingTests(unittest.TestCase):
    def test_arithmetic_excess_and_drawdown_use_whole_sleeves(self):
        result = reporting.paired_nav_diagnostics((
            (date(2025, 1, 2), D(100), D(100)),
            (date(2025, 1, 3), D(110), D(100)),
            (date(2025, 1, 6), D(99), D(90)),
        ), expected_session_dates=DATES)
        self.assertEqual(result["annualized_arithmetic_excess"], "12.6")
        self.assertEqual(result["strategy_max_drawdown"], "0.1")
        self.assertEqual(result["comparator_max_drawdown"], "0.1")
        self.assertEqual(result["return_intervals"], 2)
        self.assertFalse(result["empirical_interpretation_permitted"])
        self.assertFalse(result["sufficient_for_research"])
        self.assertIsNone(result["confidence_interval"])

    def test_idle_dates_count_and_no_roundtrip_summary_substitutes_for_nav(self):
        rows = tuple((date(2025, 1, i), D(100), D(100)) for i in (2, 3, 6))
        result = reporting.paired_nav_diagnostics(rows, expected_session_dates=DATES)
        self.assertEqual(result["calendar_observations"], 3)
        self.assertEqual(result["annualized_arithmetic_excess"], "0")

    def test_missing_on_either_side_blocks_without_dropping_any_date(self):
        rows = ((date(2025, 1, 2), D(100), D(100)),
                (date(2025, 1, 3), None, D(100)),
                (date(2025, 1, 6), None, None))
        result = reporting.paired_nav_diagnostics(rows, expected_session_dates=DATES)
        self.assertEqual(result["calendar_observations"], 3)
        self.assertEqual(result["missing_dates"], ["2025-01-03", "2025-01-06"])
        self.assertEqual(result["status"], "blocked_missing_paired_nav")
        self.assertIsNone(result["annualized_arithmetic_excess"])
        self.assertIsNone(result["strategy_max_drawdown"])

    def test_invalid_numbers_containers_or_calendar_refuse(self):
        good = (date(2025, 1, 2), D(100), D(100))
        for rows in ([], (), (good,), (good, good),
                     ((date(2025, 1, 3), D(100), D(100)), good)):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                reporting.paired_nav_diagnostics(rows, expected_session_dates=DATES)
        for value in (True, 100, 1.0, D(0), D(-1), D("NaN"), D("Infinity"), D("1e33")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reporting.paired_nav_diagnostics((good, (date(2025, 1, 3), value, D(100))), expected_session_dates=DATES[:2])

    def test_omitted_whole_date_cannot_be_treated_as_one_daily_return(self):
        rows = tuple((day, D(100), D(100)) for day in DATES)
        with self.assertRaisesRegex(ValueError, "pinned expected sessions"):
            reporting.paired_nav_diagnostics((rows[0], rows[2]), expected_session_dates=DATES)
        for dates in (list(DATES), DATES[::-1], (DATES[0], DATES[0]), (True, True)):
            with self.subTest(dates=dates), self.assertRaises(ValueError):
                reporting.paired_nav_diagnostics(rows, expected_session_dates=dates)

    def test_decimal_context_does_not_change_diagnostics(self):
        rows = ((date(2025, 1, 2), D("100000.123456789"), D("100000")),
                (date(2025, 1, 3), D("100001.765432198"), D("99999.123456789")))
        expected = reporting.paired_nav_diagnostics(rows, expected_session_dates=DATES[:2])
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(reporting.paired_nav_diagnostics(rows, expected_session_dates=DATES[:2]), expected)

    def test_source_manifest_hashes_actual_local_bytes(self):
        root = Path(__file__).resolve().parents[2]
        manifest = reporting.source_manifest()
        self.assertIn("research/guidance_revision_drift/scenario.py", manifest)
        self.assertIn("data/financial_primitives.py", manifest)
        for name, digest in manifest.items():
            self.assertEqual(digest, hash_bytes((root / name).read_bytes()))
        self.assertEqual(reporting.source_manifest_sha256(), hash_payload(manifest))

    def test_changed_code_bytes_change_epoch_digest(self):
        before = reporting.source_manifest_sha256()
        with patch.object(reporting, "_read_regular_file", return_value=b"changed fixture code"):
            self.assertNotEqual(reporting.source_manifest_sha256(), before)


if __name__ == "__main__":
    unittest.main()
