"""Strict primitives for local GDR structural inputs, not provenance or access.

Kept separate from the frozen SYN-only parsers. These functions perform no
file, clock, environment, provider or SDK access. Numeric provider tokens are
decoded to Decimal directly; canonical normalized amounts must be explicit.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, DecimalException
import json
import re

from data.hashing import canonical_json


class InputError(ValueError):
    """A local input violates the structural contract; never echo source data."""


def keys(value: object, expected: set | frozenset) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise InputError("missing or unknown input fields")
    return value


def identifier(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}", value) is None:
        raise InputError("bounded input identifier required")
    return value


def digest(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InputError("lowercase SHA256 input anchor required")
    return value


def utc(value: object) -> datetime:
    if (type(value) is not str
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value) is None):
        raise InputError("explicit canonical UTC input instant required")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InputError("invalid UTC input instant") from exc


def day(value: object) -> date:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise InputError("canonical input date required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError("invalid input date") from exc


def amount(value: object, *, nonnegative: bool = False, positive: bool = False) -> Decimal:
    if type(nonnegative) is not bool or type(positive) is not bool:
        raise InputError("strict numeric validation options required")
    if type(value) is str:
        if len(value) > 100 or re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is None:
            raise InputError("bounded plain decimal input text required")
        result = Decimal(value)
    elif type(value) in (int, Decimal):
        if type(value) is int and (value.bit_length() > 213 or len(str(abs(value))) > 64):
            raise InputError("input integer magnitude exceeded")
        result = Decimal(value)
    else:
        raise InputError("exact decimal input required; no float or bool")
    if (not result.is_finite() or len(result.as_tuple().digits) > 64
            or abs(result.as_tuple().exponent) > 32):
        raise InputError("input decimal magnitude or precision exceeded")
    if (nonnegative and result < 0) or (positive and result <= 0):
        raise InputError("input decimal sign refused")
    return result


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate input JSON field")
        result[key] = value
    return result


def _integer(token: str) -> int:
    if len(token) > 65:
        raise InputError("input integer token exceeded")
    return int(token)


def _decimal(token: str) -> Decimal:
    if len(token) > 128:
        raise InputError("input decimal token exceeded")
    try:
        return amount(Decimal(token))
    except DecimalException as exc:
        raise InputError("invalid provider decimal token") from exc


def _forbidden_number(token: str) -> None:
    raise InputError("input float or nonfinite token refused")


def decode_object(raw: bytes, maximum: int = 65536, *, provider_numbers: bool = False) -> dict:
    if (type(raw) is not bytes or type(maximum) is not int or not 1 <= maximum <= 4 * 1024 * 1024
            or not raw or len(raw) > maximum or type(provider_numbers) is not bool):
        raise InputError("bounded local input bytes required")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_int=_integer,
                            parse_float=_decimal if provider_numbers else _forbidden_number,
                            parse_constant=_forbidden_number)
    except InputError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError("invalid strict input JSON") from exc
    if type(result) is not dict:
        raise InputError("local input object required")
    return result


def canonical_bytes(value: dict) -> bytes:
    if type(value) is not dict:
        raise InputError("normalized input object required")
    try:
        # Decimal cannot be silently stringified here. Normalizers must name
        # amount units and serialize their exact values explicitly themselves.
        raw = canonical_json(value).encode("utf-8")
        decode_object(raw, 4 * 1024 * 1024)
        return raw
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise InputError("input projection is not canonical JSON") from exc
