"""Deterministic hashing for manifests, datasets, and artifacts.

Reuses the canonical-JSON-then-sha256 convention already established by
backtest/research_report.py's `_series_digest`/parameter hash and
assistant/llm/committee_service.py's `_input_hash` -- same
`json.dumps(..., sort_keys=True, default=str, separators=(",", ":"))`
shape, so a manifest hashed here and a report/committee-input hashed
elsewhere are trustworthy in exactly the same way.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


class HashingError(ValueError):
    """A payload cannot be represented as canonical, standards-compliant JSON."""


def _normalize_json_value(value: Any, *, path: str = "payload") -> Any:
    """Reject values that ``json.dumps(default=str)`` would silently coerce.

    Artifact and lineage hashes must describe the value itself, not an
    implementation-specific ``str(object)`` representation (which can include
    memory addresses), and RFC JSON does not contain NaN or infinity.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise HashingError(f"{path} is not finite: {value!r}")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise HashingError(
                    f"{path} contains non-string JSON key {key!r}"
                )
            result[key] = _normalize_json_value(item, path=f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [
            _normalize_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise HashingError(
        f"{path} contains unsupported JSON value of type {type(value).__name__}"
    )


def canonical_json(payload: Any) -> str:
    normalized = _normalize_json_value(payload)
    try:
        return json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise HashingError(f"payload is not canonical JSON: {exc}") from exc


def hash_payload(payload: Any) -> str:
    """Deterministic sha256 hex digest of any JSON-serializable structure."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    """sha256 hex digest of raw bytes (artifact files)."""
    return hashlib.sha256(data).hexdigest()
