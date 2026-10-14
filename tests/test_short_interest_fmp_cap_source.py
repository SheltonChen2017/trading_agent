"""Fabricated exact cap tokens and protected-date boundaries only."""
from fractions import Fraction

import pytest

from research.short_interest_etf import fmp_cap_source as source


def token(raw):
    rows = source.preflight_scope(raw)
    return rows[0].values("marketCap")[0]


def test_cap_parser_preserves_exact_token_without_asserting_USD_or_shares():
    result = source._cap(token(b'[{"date":"2023-01-13","marketCap":9007199254740993.125}]'))
    assert result["lexical"] == "9007199254740993.125"
    assert Fraction(int(result["numerator"]), int(result["denominator"])) == Fraction("9007199254740993.125")
    assert result["unit"] == "trading_currency_amount_independent_dated_binding_required"


@pytest.mark.parametrize("value", [b"true", b'"10"', b"0", b"-1", b"NaN", b"1e65", b"1e31"])
def test_bad_cap_quantity_is_not_finite_positive_issuer_size(value):
    raw = b'[{"date":"2023-01-13","marketCap":' + value + b'}]'
    with pytest.raises(source.FmpCapError):
        source._cap(token(raw))


@pytest.mark.parametrize("raw", [
    b'[{"date":"2023-01-13","date":"2026-09-01","marketCap":1}]',
    b'[{"date":"2023-01-13suffix","marketCap":1}]',
    b'[{"date":"2022-01-02","marketCap":1}]',
    b'[{"marketCap":1}]',
])
def test_every_date_token_must_be_in_the_frozen_source_window(raw):
    with pytest.raises(source.FmpCapError):
        source.preflight_scope(raw)
