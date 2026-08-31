"""Strict canonical JSON and immutable-value helpers for TPR evidence."""

# TPR-CCR5-001: tracked LF migration marker for existing Windows worktrees.
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Mapping


class CanonicalContractError(ValueError):
    """Persisted TPR authority is not in the one accepted representation."""


_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")
_UTC_INSTANT_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
)


def sha256_bytes(payload: bytes) -> str:
    if type(payload) is not bytes:
        raise CanonicalContractError("SHA-256 input must be exact bytes")
    return hashlib.sha256(payload).hexdigest()


def require_sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CanonicalContractError(
            f"{name} must be a lowercase 64-character SHA-256 digest"
        )
    return value


def require_git_commit(value: object, name: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT_RE.fullmatch(value) is None:
        raise CanonicalContractError(
            f"{name} must be a lowercase 40-character Git commit"
        )
    return value


def require_identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise CanonicalContractError(f"{name} must be a canonical identifier")
    return value


def require_text(value: object, name: str, *, maximum_length: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum_length
        or any(unicodedata.category(character) in {"Cc", "Cs"} for character in value)
    ):
        raise CanonicalContractError(
            f"{name} must be trimmed non-control text of at most "
            f"{maximum_length} characters"
        )
    return value


def require_exact_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise CanonicalContractError(f"{name} must be an exact JSON boolean")
    return value


def require_int(
    value: object,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise CanonicalContractError(f"{name} must be an exact integer")
    if minimum is not None and value < minimum:
        raise CanonicalContractError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise CanonicalContractError(f"{name} must be at most {maximum}")
    return value


def require_decimal_text(
    value: object,
    name: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CanonicalContractError(f"{name} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CanonicalContractError(f"{name} must be a finite decimal string") from exc
    if not parsed.is_finite():
        raise CanonicalContractError(f"{name} must be a canonical finite decimal string")
    canonical = "0" if parsed.is_zero() else format(parsed.normalize(), "f")
    if value != canonical:
        raise CanonicalContractError(
            f"{name} must use one canonical plain-decimal spelling"
        )
    if minimum is not None and parsed < minimum:
        raise CanonicalContractError(f"{name} is below its minimum")
    if maximum is not None and parsed > maximum:
        raise CanonicalContractError(f"{name} exceeds its maximum")
    return parsed


def require_date(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise CanonicalContractError(f"{name} must use canonical YYYY-MM-DD form")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CanonicalContractError(f"{name} must be a real YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise CanonicalContractError(f"{name} must use canonical YYYY-MM-DD form")
    return parsed


def require_aware_instant(value: object, name: str) -> str:
    if not isinstance(value, str) or _UTC_INSTANT_RE.fullmatch(value) is None:
        raise CanonicalContractError(
            f"{name} must use exact UTC YYYY-MM-DDTHH:MM:SSZ form"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CanonicalContractError(
            f"{name} must be a real exact UTC instant"
        ) from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
        or parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") != value
    ):
        raise CanonicalContractError(
            f"{name} must round-trip in exact UTC YYYY-MM-DDTHH:MM:SSZ form"
        )
    return value


def require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], name: str
) -> None:
    if not isinstance(value, Mapping):
        raise CanonicalContractError(f"{name} must be a JSON object")
    actual = set(value)
    if actual != set(expected):
        raise CanonicalContractError(
            f"{name} keys are not exact; missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}"
        )


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalContractError(f"duplicate JSON key is forbidden: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise CanonicalContractError(f"non-finite JSON number is forbidden: {token}")


def _reject_binary_float(token: str) -> None:
    raise CanonicalContractError(
        f"binary floating-point JSON numbers are forbidden; use a decimal string: {token}"
    )


def strict_json_loads(text: str, name: str) -> Any:
    if not isinstance(text, str):
        raise CanonicalContractError(f"{name} must be text")
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_nonfinite,
            parse_float=_reject_binary_float,
        )
    except CanonicalContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CanonicalContractError(f"{name} is not strict JSON") from exc


def decode_utf8(payload: bytes, name: str) -> str:
    if type(payload) is not bytes:
        raise CanonicalContractError(f"{name} must be exact bytes")
    if payload.startswith(b"\xef\xbb\xbf"):
        raise CanonicalContractError(f"{name} must not contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CanonicalContractError(f"{name} is not strict UTF-8") from exc


def _require_json_value(value: object, path: str = "value") -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if isinstance(value, float) or isinstance(value, Decimal):
        raise CanonicalContractError(
            f"{path} cannot contain binary floating-point or JSON decimal numbers"
        )
    if isinstance(value, list) or isinstance(value, tuple):
        for index, item in enumerate(value):
            _require_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise CanonicalContractError(f"{path} keys must be non-empty strings")
            _require_json_value(item, f"{path}.{key}")
        return
    raise CanonicalContractError(f"{path} contains a non-JSON value")


def _json_materialize(value: object) -> object:
    """Turn frozen Mapping/tuple containers back into detached JSON containers."""
    if isinstance(value, Mapping):
        return {key: _json_materialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_materialize(item) for item in value]
    return value


def canonical_json_bytes(value: Any, *, trailing_lf: bool = False) -> bytes:
    _require_json_value(value)
    try:
        rendered = json.dumps(
            _json_materialize(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalContractError("value is not canonically JSON serializable") from exc
    return (rendered + ("\n" if trailing_lf else "")).encode("utf-8")


def require_canonical_json_bytes(payload: bytes, name: str) -> Any:
    value = strict_json_loads(decode_utf8(payload, name), name)
    if canonical_json_bytes(value, trailing_lf=True) != payload:
        raise CanonicalContractError(
            f"{name} is not canonical minified JSON with exactly one LF terminator"
        )
    return value


def deep_freeze(value: object) -> object:
    """Detach JSON containers and recursively make their contents immutable."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    return value


def authority_value(value: object) -> object:
    """Return a stable hashable representation of an already-frozen value."""
    if isinstance(value, Mapping):
        return tuple((key, authority_value(item)) for key, item in sorted(value.items()))
    if isinstance(value, tuple):
        return tuple(authority_value(item) for item in value)
    return value
