"""Synthetic arithmetic tests, without provider, outcome, or order evidence."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal, Inexact, Rounded, localcontext

from research.guidance_revision_drift.formulas import (
    GuidanceArithmeticError,
    GuidanceRange,
    evaluate_range_revisions,
)


def interval(lower: str, upper: str | None = None) -> GuidanceRange:
    return GuidanceRange(Decimal(lower), Decimal(lower if upper is None else upper))


def evaluate(**changes):
    values = {
        "previous_revenue": interval("100"),
        "current_revenue": interval("102"),
        "previous_eps": interval("1"),
        "current_eps": interval("1.05"),
    }
    values.update(changes)
    return evaluate_range_revisions(**values)


class GuidanceRangeArithmeticTests(unittest.TestCase):
    def test_exact_thresholds_pass_arithmetic(self):
        result = evaluate()
        self.assertTrue(result.passes_arithmetic)
        self.assertEqual(result.revenue_revision_fraction, Decimal("0.02"))
        self.assertEqual(result.eps_revision_fraction, Decimal("0.05"))
        self.assertEqual(result.refusal_reasons, ())

    def test_just_below_revenue_threshold_refuses_even_if_display_rounds_up(self):
        result = evaluate(current_revenue=interval("101.999999999999999999999999999999"))
        self.assertEqual(result.revenue_revision_fraction, Decimal("0.02"))
        self.assertFalse(result.revenue_raise_threshold_met)
        self.assertFalse(result.passes_arithmetic)

    def test_just_below_eps_threshold_refuses_even_if_display_rounds_up(self):
        result = evaluate(current_eps=interval("1.04999999999999999999999999999999"))
        self.assertEqual(result.eps_revision_fraction, Decimal("0.05"))
        self.assertFalse(result.eps_raise_threshold_met)
        self.assertFalse(result.passes_arithmetic)

    def test_each_lower_cut_refuses_despite_large_midpoint_raise(self):
        for changes, reason in (
            ({"current_revenue": interval("99", "120")}, "revenue_lower_bound_reduced"),
            ({"current_eps": interval("0.99", "1.5")}, "eps_lower_bound_reduced"),
        ):
            with self.subTest(reason=reason):
                result = evaluate(**changes)
                self.assertTrue(result.revenue_raise_threshold_met)
                self.assertTrue(result.eps_raise_threshold_met)
                self.assertFalse(result.passes_arithmetic)
                self.assertIn(reason, result.refusal_reasons)

    def test_unchanged_lows_and_higher_uppers_are_permitted(self):
        result = evaluate(current_revenue=interval("100", "104"), current_eps=interval("1", "1.1"))
        self.assertTrue(result.passes_arithmetic)

    def test_eps_floor_is_inclusive_on_midpoint_not_lower_bound(self):
        result = evaluate(previous_eps=interval("0.2", "0.3"), current_eps=interval("0.225", "0.3"))
        self.assertEqual(result.previous_eps_midpoint, Decimal("0.25"))
        self.assertTrue(result.passes_arithmetic)

    def test_eps_prior_below_floor_zero_and_negative_are_unavailable(self):
        for prior in ("0.24999999999999999999999999999999", "0", "-1"):
            with self.subTest(prior=prior):
                result = evaluate(previous_eps=interval(prior))
                self.assertFalse(result.previous_eps_floor_met)
                self.assertFalse(result.eps_raise_threshold_met)
                self.assertIsNone(result.eps_revision_fraction)
                self.assertFalse(result.passes_arithmetic)

    def test_nonpositive_prior_revenue_has_no_revision_fraction(self):
        for prior in (interval("0"), interval("-1"), interval("-1", "1")):
            with self.subTest(prior=prior):
                result = evaluate(previous_revenue=prior)
                self.assertFalse(result.previous_revenue_positive)
                self.assertIsNone(result.revenue_revision_fraction)
                self.assertFalse(result.passes_arithmetic)

    def test_invalid_endpoint_types_and_nonfinite_values_refuse(self):
        for bad in (1.0, 1, True, False, "1", None, Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity")):
            for lower, upper in ((bad, Decimal("2")), (Decimal("1"), bad)):
                with self.subTest(lower=lower, upper=upper):
                    with self.assertRaises(GuidanceArithmeticError):
                        GuidanceRange(lower, upper)

    def test_inverted_range_refuses(self):
        with self.assertRaisesRegex(GuidanceArithmeticError, "exceed upper"):
            interval("2", "1")

    def test_resource_bounds_cover_large_coefficients_exponents_and_zero(self):
        for bad in (Decimal("1" * 129), Decimal("1e129"), Decimal("1e-129"), Decimal("0e-999999"), Decimal("9" * 128 + "e128")):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(GuidanceArithmeticError, "resource bounds"):
                    GuidanceRange(bad, bad)

    def test_extreme_permitted_alignment_remains_exact(self):
        result = evaluate(
            previous_revenue=interval("1e-128", "1e128"),
            current_revenue=interval("1e-128", "1e128"),
        )
        self.assertEqual(result.revenue_revision_fraction, Decimal("0"))
        self.assertFalse(result.revenue_raise_threshold_met)

    def test_ambient_decimal_precision_traps_and_exponent_limits_do_not_change_results(self):
        arguments = {
            "previous_revenue": interval("980", "1020"),
            "current_revenue": interval("1030", "1070"),
            "previous_eps": interval("2", "2.2"),
            "current_eps": interval("2.2", "2.4"),
        }
        expected = evaluate(**arguments)
        with localcontext() as context:
            context.prec = 2
            context.Emax = 2
            context.Emin = -2
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            actual = evaluate(**arguments)
        self.assertEqual(actual, expected)
        self.assertEqual(actual.current_eps_midpoint, Decimal("2.3"))
        self.assertEqual(actual.eps_revision_fraction, Decimal("0.09523809523809523809523809524"))
        self.assertTrue(actual.passes_arithmetic)

    def test_ranges_and_results_are_frozen_without_stored_mutable_containers(self):
        prior = interval("100")
        result = evaluate(previous_revenue=prior)
        with self.assertRaises(FrozenInstanceError):
            prior.lower = Decimal("0")
        with self.assertRaises(FrozenInstanceError):
            result.refusal_reasons = ("forged",)
        self.assertIsInstance(result.refusal_reasons, tuple)
        self.assertFalse(hasattr(result, "__dict__"))

    def test_forged_range_is_revalidated_at_evaluation(self):
        prior = interval("100")
        object.__setattr__(prior, "lower", Decimal("NaN"))
        with self.assertRaises(GuidanceArithmeticError):
            evaluate(previous_revenue=prior)
        with self.assertRaises(GuidanceArithmeticError):
            evaluate(previous_revenue={"lower": Decimal("100"), "upper": Decimal("100")})


if __name__ == "__main__":
    unittest.main()
