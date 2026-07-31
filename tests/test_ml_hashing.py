"""Tests for ml/hashing.py."""
from __future__ import annotations

from ml.hashing import hash_bytes, hash_payload


def test_hash_payload_is_deterministic_for_identical_input():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert hash_payload(a) == hash_payload(b)


def test_hash_payload_changes_for_any_value_change():
    assert hash_payload({"a": 1}) != hash_payload({"a": 2})


def test_hash_payload_returns_hex_sha256_digest():
    digest = hash_payload({"a": 1})
    assert len(digest) == 64
    int(digest, 16)  # raises ValueError if not valid hex


def test_hash_bytes_matches_hashlib_sha256():
    import hashlib

    data = b"some artifact bytes"
    assert hash_bytes(data) == hashlib.sha256(data).hexdigest()
