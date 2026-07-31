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
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def hash_payload(payload: Any) -> str:
    """Deterministic sha256 hex digest of any JSON-serializable structure."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    """sha256 hex digest of raw bytes (artifact files)."""
    return hashlib.sha256(data).hexdigest()
