from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, localcontext

import pytest

from data.financial_primitives import (
    decimal_effective_scale,
    decimal_text,
    deterministic_decimal_divide,
    deterministic_decimal_quantize,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
    exact_decimal_sum,
)


@pytest.mark.parametrize(
    ("value", "expected_text", "expected_scale"),
    (
        (Decimal("-0E-999"), "0", 0),
        (Decimal("1.23000"), "1.23", 2),
        (Decimal("1.23000E+5"), "123000", 0),
        (Decimal("1.23000E-5"), "0.0000123", 7),
        (Decimal("-1E+3"), "-1000", 0),
    ),
)
def test_decimal_tuple_projection_is_context_free_and_canonical(
    value, expected_text, expected_scale
) -> None:
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        assert decimal_text(value) == expected_text
        assert decimal_effective_scale(value) == expected_scale


def test_exact_arithmetic_is_independent_of_ambient_decimal_context() -> None:
    left = Decimal("1234567890123456789012345678.91")
    right = Decimal("0.09")

    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        assert exact_decimal_add(left, right) == Decimal(
            "1234567890123456789012345679.00"
        )
        assert exact_decimal_subtract(left, right) == Decimal(
            "1234567890123456789012345678.82"
        )
        assert exact_decimal_multiply(
            Decimal("1000000000000000000000000000.01"),
            Decimal("0.03"),
        ) == Decimal("30000000000000000000000000.0003")
        assert exact_decimal_sum((left, right, Decimal("1"))) == Decimal(
            "1234567890123456789012345680.00"
        )


def test_deterministic_projections_ignore_ambient_precision_and_rounding() -> None:
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        assert deterministic_decimal_divide(Decimal("1"), Decimal("3")) == Decimal(
            "0.3333333333333333333333333333"
        )
        assert deterministic_decimal_quantize(
            Decimal("9.995"), Decimal("0.01")
        ) == Decimal("10.00")


@pytest.mark.parametrize(
    "operation",
    (
        lambda: exact_decimal_add(Decimal("1" * 4097), Decimal("1")),
        lambda: exact_decimal_multiply(Decimal("1e1000000"), Decimal("1")),
        lambda: deterministic_decimal_divide(Decimal("1"), Decimal("0")),
        lambda: deterministic_decimal_quantize(Decimal("1"), Decimal("0")),
    ),
)
def test_decimal_primitives_refuse_unsafe_or_undefined_inputs(operation) -> None:
    with pytest.raises(ValueError):
        operation()


def test_deterministic_division_refuses_silent_underflow() -> None:
    with pytest.raises(ValueError, match="deterministically"):
        deterministic_decimal_divide(
            Decimal("1e-999999"),
            Decimal("1e999999"),
        )
