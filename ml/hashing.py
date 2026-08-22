"""Compatibility facade for the product-neutral hashing contract."""

from data.hashing import HashingError, canonical_json, hash_bytes, hash_payload

__all__ = ["HashingError", "canonical_json", "hash_bytes", "hash_payload"]
