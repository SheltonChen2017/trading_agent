"""Canonical serialization and scalar validators for ARV2 evidence.

This module deliberately depends only on the Python standard library.  It is
used at every persisted-evidence boundary so the same bytes cannot acquire two
meanings and two different byte streams cannot masquerade as one artifact.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


class CanonicalEvidenceError(ValueError):
    """Persisted evidence is not in the one accepted canonical form."""


_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_OBJECT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_TICKER_RE = re.compile(r"[A-Z][A-Z0-9.-]{0,15}")
_UTC_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"
)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def sha256_bytes(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise CanonicalEvidenceError("sha256 input must be bytes")
    return hashlib.sha256(payload).hexdigest()


def require_sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CanonicalEvidenceError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def require_git_object(value: object, name: str) -> str:
    if not isinstance(value, str) or _GIT_OBJECT_RE.fullmatch(value) is None:
        raise CanonicalEvidenceError(
            f"{name} must be a lowercase 40- or 64-character Git object ID"
        )
    return value


def require_identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise CanonicalEvidenceError(f"{name} is not a canonical identifier")
    return value


def require_ticker(value: object, name: str = "historical_ticker") -> str:
    if not isinstance(value, str) or _TICKER_RE.fullmatch(value) is None:
        raise CanonicalEvidenceError(f"{name} is not a canonical historical ticker")
    return value


def require_text(value: object, name: str, *, maximum_length: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum_length
        or any(unicodedata.category(character) in {"Cc", "Cs"} for character in value)
    ):
        raise CanonicalEvidenceError(
            f"{name} must be trimmed non-control text of at most {maximum_length} characters"
        )
    return value


def require_exact_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise CanonicalEvidenceError(f"{name} must be an exact JSON boolean")
    return value


def require_int(
    value: object,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise CanonicalEvidenceError(f"{name} must be an exact integer")
    if minimum is not None and value < minimum:
        raise CanonicalEvidenceError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise CanonicalEvidenceError(f"{name} must be at most {maximum}")
    return value


def parse_utc_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise CanonicalEvidenceError(
            f"{name} must use canonical UTC YYYY-MM-DDTHH:MM:SS.ffffffZ form"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CanonicalEvidenceError(f"{name} is not a real timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CanonicalEvidenceError(f"{name} must be UTC")
    if format_utc_timestamp(parsed) != value:
        raise CanonicalEvidenceError(f"{name} is not canonical")
    return parsed


def format_utc_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalEvidenceError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def parse_date(value: object, name: str) -> date:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        raise CanonicalEvidenceError(f"{name} must use canonical YYYY-MM-DD form")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise CanonicalEvidenceError(f"{name} is not a real date") from exc
    if parsed.isoformat() != value:
        raise CanonicalEvidenceError(f"{name} is not canonical")
    return parsed


def require_relative_page_path(value: object, name: str = "filename") -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CanonicalEvidenceError(f"{name} must be a canonical POSIX relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
        or not value.startswith("pages/")
        or path.suffix != ".jsonl"
        or str(path) != value
    ):
        raise CanonicalEvidenceError(
            f"{name} must be a canonical pages/.../*.jsonl relative path"
        )
    return value


def resolve_contained(root: Path, relative: str) -> Path:
    root_resolved = root.resolve(strict=True)
    candidate = (root_resolved / Path(*PurePosixPath(relative).parts)).resolve(strict=True)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise CanonicalEvidenceError("artifact path escapes its root") from exc
    return candidate


def require_exact_keys(
    record: Mapping[str, Any], expected: Iterable[str], name: str
) -> None:
    if not isinstance(record, Mapping):
        raise CanonicalEvidenceError(f"{name} must be a JSON object")
    expected_set = set(expected)
    actual = set(record)
    if actual != expected_set:
        missing = sorted(expected_set - actual)
        extra = sorted(actual - expected_set)
        raise CanonicalEvidenceError(
            f"{name} keys are not exact; missing={missing}, extra={extra}"
        )


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalEvidenceError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise CanonicalEvidenceError(f"non-finite JSON number is forbidden: {token}")


def _parse_finite_float(token: str) -> Decimal:
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise CanonicalEvidenceError(f"invalid JSON number: {token}") from exc
    if not value.is_finite():
        raise CanonicalEvidenceError(f"non-finite JSON number is forbidden: {token}")
    return value


def strict_json_loads(text: str, name: str) -> Any:
    if not isinstance(text, str):
        raise CanonicalEvidenceError(f"{name} must be text")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except CanonicalEvidenceError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CanonicalEvidenceError(f"{name} is not strict JSON") from exc


def decode_utf8(payload: bytes, name: str) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise CanonicalEvidenceError(f"{name} must not contain a UTF-8 BOM")
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CanonicalEvidenceError(f"{name} is not strict UTF-8") from exc


def canonical_json_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalEvidenceError("value is not canonically JSON serializable") from exc
    return (rendered + "\n").encode("utf-8")


def require_canonical_json_bytes(payload: bytes, name: str) -> Any:
    text = decode_utf8(payload, name)
    value = strict_json_loads(text, name)
    if canonical_json_bytes(value) != payload:
        raise CanonicalEvidenceError(f"{name} is not canonical JSON with one LF terminator")
    return value
