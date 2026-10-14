"""Exact FMP cap JSON parsing only; no identity or denomination admission.

The source has no stable identifier, currency or availability clock. Context
and exact daily source bindings are separate; no API/credential route is here.
"""
from datetime import date
from fractions import Fraction
import json
import re

ENDPOINT = "https://financialmodelingprep.com/stable/historical-market-capitalization"
FROM, TO, LIMIT = "2022-01-03", "2026-08-31", 5000
MAXIMUM_RESPONSE_BYTES = 8 * 1024 * 1024
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE]([+-]?[0-9]+))?\Z")

class FmpCapError(ValueError):
    """Fixed diagnostics never contain private source values."""


def _require(value, reason):
    if not value:
        raise FmpCapError("REFUSED: " + reason)


def _date(value):
    _require(type(value) is str and len(value) == 10, "canonical_date_required")
    try:
        _require(date.fromisoformat(value).isoformat() == value, "canonical_date_required")
    except ValueError:
        raise FmpCapError("REFUSED: canonical_date_required") from None
    return value


class _Number(str):
    pass


class _Constant(str):
    pass


class _Pairs(list):
    def values(self, key):
        return [value for name, value in self if name == key]


def _decode(raw):
    _require(type(raw) is bytes and len(raw) <= MAXIMUM_RESPONSE_BYTES, "bounded_raw_bytes_required")
    try:
        parsed = json.loads(raw.decode("utf-8"), parse_int=_Number, parse_float=_Number,
                            parse_constant=_Constant, object_pairs_hook=_Pairs)
        def unicode_guard(value):
            if isinstance(value, str):
                value.encode("utf-8")
            elif isinstance(value, list):
                for child in value:
                    if type(child) is tuple:
                        unicode_guard(child[0]); unicode_guard(child[1])
                    else:
                        unicode_guard(child)
        unicode_guard(parsed)
    except (UnicodeError, ValueError, RecursionError):
        raise FmpCapError("REFUSED: source_UTF8_JSON_refused") from None
    _require(type(parsed) is list and len(parsed) <= LIMIT, "single_bounded_array_no_envelope_or_paging")
    return parsed


def preflight_scope(raw):
    """Before raw hash/storage: inspect EVERY supplied date, not a prefix."""
    parsed = _decode(raw)
    for row in parsed:
        _require(type(row) is _Pairs and bool(row.values("date")), "unrecognizable_source_date")
        for value in row.values("date"):
            _require(FROM <= _date(value) <= TO, "outside_frozen_or_protected_date_range")
    return parsed


def _cap(value):
    _require(type(value) is _Number and len(value) <= 128, "cap_requires_exact_JSON_number")
    match = _NUMBER.fullmatch(value)
    _require(match is not None and (match.group(1) is None or abs(int(match.group(1))) <= 64), "bounded_cap_number_required")
    amount = Fraction(value)
    _require(amount > 0 and amount <= 10 ** 30, "positive_bounded_cap_required")
    return {"lexical": str(value), "numerator": str(amount.numerator), "denominator": str(amount.denominator),
            "unit": "trading_currency_amount_independent_dated_binding_required"}
