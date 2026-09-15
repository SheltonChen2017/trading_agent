"""Authenticate the physical historical bridge as exact pre-open input.

The compatibility adapter restores descriptor fields already committed by the
closed manifest and constructs the tuple expected by older fixture boundaries.
That tuple can retain up to the full one-GiB compressed-input allowance, so it
is not the production upload path.  The streaming authority and iterator below
retain no shard payload and yield one exact ``PreopenInputShard`` at a time.

No caller-supplied descriptor, payload, order, or authority assertion is
accepted.  The returned projection retains the reviewed bridge so later use
also reauthenticates the immutable physical archive.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import threading
import weakref
from typing import Iterator, Mapping

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    INPUT_SHARD_SCHEMA,
    MAX_COMPRESSED_SHARD_BYTES,
    MAX_RETAINED_INPUT_COMPRESSED_BYTES,
    PreopenInputShard,
    build_preopen_input_manifest_bytes,
)
from scripts import build_arv2_historical_preopen_bridge as historical


class HistoricalPreopenInputAdapterError(ValueError):
    """The reviewed historical bridge cannot be used as exact QC input."""


ADAPTER_SCHEMA = "arv2-authenticated-historical-preopen-input-projection-v1"
STREAM_SCHEMA = "arv2-authenticated-historical-preopen-input-stream-v1"

_PINNED_REQUIRE_BRIDGE = (
    historical.require_reviewed_historical_universe_to_preopen_bridge
)
_PINNED_CANONICAL_JSON_BYTES = canonical_json_bytes
_PINNED_ITER_SHARDS = historical.iter_reviewed_historical_preopen_input_shards
_PINNED_SOURCE_SHARD_CLASS = historical.ReviewedHistoricalPreopenInputShard
_PINNED_BUILD_MANIFEST = build_preopen_input_manifest_bytes
_PINNED_PREOPEN_SHARD_CLASS = PreopenInputShard
_PINNED_PREOPEN_DESCRIPTOR = PreopenInputShard.descriptor
_PINNED_MAX_COMPRESSED_SHARD_BYTES = MAX_COMPRESSED_SHARD_BYTES
_PINNED_MAX_RETAINED_INPUT_COMPRESSED_BYTES = (
    MAX_RETAINED_INPUT_COMPRESSED_BYTES
)
_PINNED_MAX_ARCHIVE_SHARD_COUNT = historical.MAX_ARCHIVE_SHARD_COUNT


def _require_dependency_authority() -> None:
    if (
        historical.require_reviewed_historical_universe_to_preopen_bridge
        is not _PINNED_REQUIRE_BRIDGE
        or canonical_json_bytes is not _PINNED_CANONICAL_JSON_BYTES
        or historical.iter_reviewed_historical_preopen_input_shards
        is not _PINNED_ITER_SHARDS
        or historical.ReviewedHistoricalPreopenInputShard
        is not _PINNED_SOURCE_SHARD_CLASS
        or build_preopen_input_manifest_bytes is not _PINNED_BUILD_MANIFEST
        or PreopenInputShard is not _PINNED_PREOPEN_SHARD_CLASS
        or PreopenInputShard.descriptor is not _PINNED_PREOPEN_DESCRIPTOR
        or MAX_COMPRESSED_SHARD_BYTES
        is not _PINNED_MAX_COMPRESSED_SHARD_BYTES
        or MAX_RETAINED_INPUT_COMPRESSED_BYTES
        is not _PINNED_MAX_RETAINED_INPUT_COMPRESSED_BYTES
        or historical.MAX_ARCHIVE_SHARD_COUNT
        is not _PINNED_MAX_ARCHIVE_SHARD_COUNT
        or globals().get("_converted_shard") is not _PINNED_CONVERTED_SHARD
        or (
            "_stream_record" in globals()
            and globals().get("_stream_record") is not _PINNED_STREAM_RECORD
        )
    ):
        raise HistoricalPreopenInputAdapterError(
            "historical pre-open adapter dependency authority changed"
        )


def _strict_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise HistoricalPreopenInputAdapterError(f"{name} is not exact bytes")

    def pairs(items):
        result: dict[str, object] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise HistoricalPreopenInputAdapterError(
                    f"{name} has duplicate or non-string keys"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                HistoricalPreopenInputAdapterError(f"{name} contains a float")
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                HistoricalPreopenInputAdapterError(
                    f"{name} contains a non-finite value"
                )
            ),
        )
    except HistoricalPreopenInputAdapterError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise HistoricalPreopenInputAdapterError(
            f"{name} is not strict canonical JSON"
        ) from exc
    if type(value) is not dict or _PINNED_CANONICAL_JSON_BYTES(value) != payload:
        raise HistoricalPreopenInputAdapterError(
            f"{name} is not one canonical JSON object"
        )
    return value


def _rebuild_exact_manifest(
    *, manifest: Mapping[str, object], shards: tuple[PreopenInputShard, ...]
) -> bytes:
    try:
        source_policy = manifest["source_policy"]
        universe = manifest["eligible_universe_source"]
        truth = manifest["truth_source_bindings"]
        if (
            type(source_policy) is not dict
            or type(universe) is not dict
            or type(truth) is not list
        ):
            raise HistoricalPreopenInputAdapterError(
                "historical pre-open manifest parent fields changed"
            )
        rebuilt_bytes = _PINNED_BUILD_MANIFEST(
            shards=shards,
            benchmark_security_id=manifest["benchmark_security_id"],
            benchmark_ticker=manifest["benchmark_ticker"],
            first_session=manifest["first_session"],
            last_session=manifest["last_session"],
            calculation_session=manifest["calculation_session"],
            rating_source_complete=source_policy["rating_source_complete"],
            earnings_source_complete=source_policy["earnings_source_complete"],
            guidance_source_complete=source_policy["guidance_source_complete"],
            earnings_pit_policy_id=source_policy["earnings_pit_policy_id"],
            guidance_clock_policy_id=source_policy["guidance_clock_policy_id"],
            eligible_universe_artifact_id=universe["artifact_id"],
            eligible_universe_artifact_sha256=universe["artifact_sha256"],
            eligible_universe_artifact_byte_count=universe["byte_count"],
            truth_source_bindings=tuple(truth),
        )
    except HistoricalPreopenInputAdapterError:
        raise
    except Exception as exc:
        raise HistoricalPreopenInputAdapterError(
            "historical pre-open manifest cannot be revalidated"
        ) from exc
    rebuilt = _strict_object(rebuilt_bytes, "rebuilt pre-open manifest")
    rebuilt_census = rebuilt.get("resource_census")
    source_census = manifest.get("resource_census")
    if (
        type(rebuilt_census) is not dict
        or type(source_census) is not dict
        or rebuilt_census.get(
            "host_manifest_projection_retains_all_compressed_input_payloads"
        )
        is not True
        or source_census.get(
            "host_manifest_projection_retains_all_compressed_input_payloads"
        )
        is not False
    ):
        raise HistoricalPreopenInputAdapterError(
            "historical host-retention disclosure changed"
        )
    rebuilt_census[
        "host_manifest_projection_retains_all_compressed_input_payloads"
    ] = False
    rebuilt["resource_census"] = rebuilt_census
    return _PINNED_CANONICAL_JSON_BYTES(rebuilt)


def _converted_shard(source: object, descriptor: object) -> PreopenInputShard:
    if (
        type(source) is not _PINNED_SOURCE_SHARD_CLASS
        or type(descriptor) is not dict
        or descriptor.get("schema") != INPUT_SHARD_SCHEMA
        or source.role != descriptor.get("role")
        or source.security_batch_ordinal
        != descriptor.get("security_batch_ordinal")
        or source.ordinal != descriptor.get("ordinal")
        or source.object_store_key != descriptor.get("object_store_key")
        or source.compressed_sha256 != descriptor.get("compressed_sha256")
        or source.compressed_byte_count
        != descriptor.get("compressed_byte_count")
        or source.payload.__class__ is not bytes
    ):
        raise HistoricalPreopenInputAdapterError(
            "historical shard and closed descriptor differ"
        )
    shard = _PINNED_PREOPEN_SHARD_CLASS(
        role=descriptor["role"],
        security_batch_ordinal=descriptor["security_batch_ordinal"],
        ordinal=descriptor["ordinal"],
        partition_first_session=descriptor["partition_first_session"],
        partition_last_session=descriptor["partition_last_session"],
        object_store_key=descriptor["object_store_key"],
        compressed_sha256=descriptor["compressed_sha256"],
        compressed_byte_count=descriptor["compressed_byte_count"],
        uncompressed_sha256=descriptor["uncompressed_sha256"],
        uncompressed_byte_count=descriptor["uncompressed_byte_count"],
        row_count=descriptor["row_count"],
        payload=source.payload,
    )
    if _PINNED_PREOPEN_DESCRIPTOR(shard) != descriptor:
        raise HistoricalPreopenInputAdapterError(
            "converted pre-open shard descriptor changed"
        )
    return shard


_PINNED_CONVERTED_SHARD = _converted_shard


def _converted_shards(
    bridge: historical.ReviewedHistoricalUniverseToPreopenBridge,
    manifest: Mapping[str, object],
) -> tuple[PreopenInputShard, ...]:
    descriptors = manifest.get("shards")
    if type(descriptors) is not list or not descriptors:
        raise HistoricalPreopenInputAdapterError(
            "historical pre-open descriptor inventory is empty"
        )
    try:
        source_shards = _PINNED_ITER_SHARDS(bridge)
        converted: list[PreopenInputShard] = []
        for source, descriptor in zip(source_shards, descriptors, strict=True):
            _PINNED_REQUIRE_BRIDGE(bridge)
            converted.append(_PINNED_CONVERTED_SHARD(source, descriptor))
    except HistoricalPreopenInputAdapterError:
        raise
    except Exception as exc:
        raise HistoricalPreopenInputAdapterError(
            "historical pre-open shard authority changed"
        ) from exc
    result = tuple(converted)
    if (
        len(result) != bridge.input_shard_count
        or [_PINNED_PREOPEN_DESCRIPTOR(item) for item in result] != descriptors
        or tuple(item.role for item in result)
        != tuple(item["role"] for item in descriptors)
    ):
        raise HistoricalPreopenInputAdapterError(
            "converted pre-open shard order or census changed"
        )
    return result


def _stream_record(
    bridge: historical.ReviewedHistoricalUniverseToPreopenBridge,
) -> dict[str, object]:
    manifest_bytes = bridge.closed_input_manifest_bytes
    manifest = _strict_object(manifest_bytes, "closed pre-open manifest")
    descriptors = manifest.get("shards")
    if (
        type(descriptors) is not list
        or not descriptors
        or len(descriptors) != bridge.input_shard_count
        or len(descriptors) > _PINNED_MAX_ARCHIVE_SHARD_COUNT
        or manifest.get("input_source_inventory_sha256")
        != hashlib.sha256(
            _PINNED_CANONICAL_JSON_BYTES(descriptors)
        ).hexdigest()
        or bridge.closed_input_manifest_sha256
        != hashlib.sha256(manifest_bytes).hexdigest()
        or bridge.closed_input_manifest_byte_count != len(manifest_bytes)
    ):
        raise HistoricalPreopenInputAdapterError(
            "historical streaming descriptor inventory changed"
        )
    compressed_counts = [
        item.get("compressed_byte_count")
        if type(item) is dict else None
        for item in descriptors
    ]
    if (
        any(
            type(count) is not int
            or not 0 < count <= _PINNED_MAX_COMPRESSED_SHARD_BYTES
            for count in compressed_counts
        )
        or sum(compressed_counts)
        > _PINNED_MAX_RETAINED_INPUT_COMPRESSED_BYTES
    ):
        raise HistoricalPreopenInputAdapterError(
            "historical streaming input exceeds its closed capacity"
        )
    return {
        "schema": STREAM_SCHEMA,
        "source_bridge_id": bridge.bridge_id,
        "source_bridge_sha256": bridge.bridge_sha256,
        "closed_input_manifest_sha256": hashlib.sha256(
            manifest_bytes
        ).hexdigest(),
        "closed_input_manifest_byte_count": len(manifest_bytes),
        "input_source_inventory_sha256": manifest[
            "input_source_inventory_sha256"
        ],
        "input_shard_count": len(descriptors),
        "total_compressed_input_byte_count": sum(compressed_counts),
        "maximum_shard_compressed_byte_count": max(compressed_counts),
        "retains_compressed_input_payloads": False,
    }


_PINNED_STREAM_RECORD = _stream_record


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AuthenticatedHistoricalPreopenInputStream:
    schema: str
    stream_id: str
    stream_sha256: str
    source_bridge_id: str
    source_bridge_sha256: str
    closed_input_manifest_sha256: str
    closed_input_manifest_byte_count: int
    input_source_inventory_sha256: str
    input_shard_count: int
    total_compressed_input_byte_count: int
    maximum_shard_compressed_byte_count: int
    retains_compressed_input_payloads: bool
    closed_input_manifest_bytes: bytes = dataclasses.field(repr=False)
    _source_bridge: historical.ReviewedHistoricalUniverseToPreopenBridge = (
        dataclasses.field(repr=False)
    )


_STREAM_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[AuthenticatedHistoricalPreopenInputStream],
        str,
        int,
    ],
] = {}
_STREAM_AUTHORITY_LOCK = threading.RLock()
_STREAM_AUTHORITY_PID = os.getpid()


def _stream_fingerprint(
    value: AuthenticatedHistoricalPreopenInputStream,
) -> str:
    return hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES({
        **_PINNED_STREAM_RECORD(value._source_bridge),
        "stream_id": value.stream_id,
        "stream_sha256": value.stream_sha256,
        "closed_input_manifest_payload_sha256": hashlib.sha256(
            value.closed_input_manifest_bytes
        ).hexdigest(),
    })).hexdigest()


def build_authenticated_historical_preopen_input_stream(
    bridge: historical.ReviewedHistoricalUniverseToPreopenBridge,
) -> AuthenticatedHistoricalPreopenInputStream:
    """Bind the physical archive without retaining compressed shard payloads."""

    try:
        _require_dependency_authority()
        bridge = _PINNED_REQUIRE_BRIDGE(bridge)
        record = _PINNED_STREAM_RECORD(bridge)
        digest = hashlib.sha256(
            _PINNED_CANONICAL_JSON_BYTES(record)
        ).hexdigest()
    except HistoricalPreopenInputAdapterError:
        raise
    except Exception as exc:
        raise HistoricalPreopenInputAdapterError(
            "historical streaming authority cannot be built"
        ) from exc
    value = AuthenticatedHistoricalPreopenInputStream(
        **record,
        stream_id="arv2-authenticated-historical-preopen-stream-"
        + digest[:24],
        stream_sha256=digest,
        closed_input_manifest_bytes=bridge.closed_input_manifest_bytes,
        _source_bridge=bridge,
    )
    reference = weakref.ref(
        value,
        lambda _ref, key=id(value): _STREAM_AUTHORITIES.pop(key, None),
    )
    with _STREAM_AUTHORITY_LOCK:
        _STREAM_AUTHORITIES[id(value)] = (
            reference,
            _stream_fingerprint(value),
            os.getpid(),
        )
    return require_authenticated_historical_preopen_input_stream(value)


def require_authenticated_historical_preopen_input_stream(
    value: AuthenticatedHistoricalPreopenInputStream,
) -> AuthenticatedHistoricalPreopenInputStream:
    """Reauthenticate the payload-free stream authority and physical parent."""

    if type(value) is not AuthenticatedHistoricalPreopenInputStream:
        raise HistoricalPreopenInputAdapterError(
            "authenticated historical pre-open stream type changed"
        )
    with _STREAM_AUTHORITY_LOCK:
        registered = _STREAM_AUTHORITIES.get(id(value))
    if (
        os.getpid() != _STREAM_AUTHORITY_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise HistoricalPreopenInputAdapterError(
            "authenticated historical pre-open stream lacks builder authority"
        )
    try:
        _require_dependency_authority()
        bridge = _PINNED_REQUIRE_BRIDGE(value._source_bridge)
        record = _PINNED_STREAM_RECORD(bridge)
        digest = hashlib.sha256(
            _PINNED_CANONICAL_JSON_BYTES(record)
        ).hexdigest()
        if (
            value.schema != STREAM_SCHEMA
            or value.stream_id
            != "arv2-authenticated-historical-preopen-stream-" + digest[:24]
            or value.stream_sha256 != digest
            or any(getattr(value, name) != item for name, item in record.items())
            or value.closed_input_manifest_bytes
            != bridge.closed_input_manifest_bytes
            or registered[1] != _stream_fingerprint(value)
        ):
            raise HistoricalPreopenInputAdapterError(
                "authenticated historical pre-open stream changed"
            )
    except HistoricalPreopenInputAdapterError:
        raise
    except Exception as exc:
        raise HistoricalPreopenInputAdapterError(
            "authenticated historical pre-open stream cannot be revalidated"
        ) from exc
    return value


_PINNED_REQUIRE_STREAM = require_authenticated_historical_preopen_input_stream


def iter_authenticated_historical_preopen_input_shards(
    value: AuthenticatedHistoricalPreopenInputStream,
) -> Iterator[PreopenInputShard]:
    """Yield one descriptor-authenticated shard and release it before the next."""

    value = _PINNED_REQUIRE_STREAM(value)
    manifest = _strict_object(
        value.closed_input_manifest_bytes, "closed pre-open manifest"
    )
    descriptors = manifest["shards"]
    try:
        sources = _PINNED_ITER_SHARDS(value._source_bridge)
        observed_count = 0
        for source, descriptor in zip(sources, descriptors, strict=True):
            value = _PINNED_REQUIRE_STREAM(value)
            shard = _PINNED_CONVERTED_SHARD(source, descriptor)
            observed_count += 1
            yield shard
            del shard, source
        if observed_count != value.input_shard_count:
            raise HistoricalPreopenInputAdapterError(
                "historical streaming shard census changed"
            )
        _PINNED_REQUIRE_STREAM(value)
    except HistoricalPreopenInputAdapterError:
        raise
    except Exception as exc:
        raise HistoricalPreopenInputAdapterError(
            "historical streaming shard iteration changed"
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AuthenticatedHistoricalPreopenInputs:
    schema: str
    projection_id: str
    projection_sha256: str
    source_bridge_id: str
    source_bridge_sha256: str
    closed_input_manifest_sha256: str
    closed_input_manifest_byte_count: int
    input_source_inventory_sha256: str
    input_shard_count: int
    closed_input_manifest_bytes: bytes = dataclasses.field(repr=False)
    input_shards: tuple[PreopenInputShard, ...] = dataclasses.field(repr=False)
    _source_bridge: historical.ReviewedHistoricalUniverseToPreopenBridge = (
        dataclasses.field(repr=False)
    )


_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[AuthenticatedHistoricalPreopenInputs], str, int]
] = {}
_AUTHORITY_LOCK = threading.RLock()
_AUTHORITY_PID = os.getpid()


def _record(
    bridge: historical.ReviewedHistoricalUniverseToPreopenBridge,
    manifest_bytes: bytes,
    shards: tuple[PreopenInputShard, ...],
) -> dict[str, object]:
    manifest = _strict_object(manifest_bytes, "closed pre-open manifest")
    return {
        "schema": ADAPTER_SCHEMA,
        "source_bridge_id": bridge.bridge_id,
        "source_bridge_sha256": bridge.bridge_sha256,
        "closed_input_manifest_sha256": hashlib.sha256(
            manifest_bytes
        ).hexdigest(),
        "closed_input_manifest_byte_count": len(manifest_bytes),
        "input_source_inventory_sha256": manifest[
            "input_source_inventory_sha256"
        ],
        "input_shard_count": len(shards),
    }


def _fingerprint(value: AuthenticatedHistoricalPreopenInputs) -> str:
    return hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES({
        **_record(
            value._source_bridge,
            value.closed_input_manifest_bytes,
            value.input_shards,
        ),
        "projection_id": value.projection_id,
        "projection_sha256": value.projection_sha256,
        "descriptors": [
            _PINNED_PREOPEN_DESCRIPTOR(item) for item in value.input_shards
        ],
        "payload_sha256": [
            hashlib.sha256(item.payload).hexdigest()
            for item in value.input_shards
        ],
    })).hexdigest()


def build_authenticated_historical_preopen_inputs(
    bridge: historical.ReviewedHistoricalUniverseToPreopenBridge,
) -> AuthenticatedHistoricalPreopenInputs:
    """Convert one reviewed physical bridge without accepting caller material."""

    try:
        _require_dependency_authority()
        bridge = _PINNED_REQUIRE_BRIDGE(bridge)
        manifest_bytes = bridge.closed_input_manifest_bytes
        manifest = _strict_object(manifest_bytes, "closed pre-open manifest")
        shards = _converted_shards(bridge, manifest)
        if _rebuild_exact_manifest(manifest=manifest, shards=shards) != manifest_bytes:
            raise HistoricalPreopenInputAdapterError(
                "converted shards do not reproduce the closed manifest"
            )
        _PINNED_REQUIRE_BRIDGE(bridge)
    except HistoricalPreopenInputAdapterError:
        raise
    except Exception as exc:
        raise HistoricalPreopenInputAdapterError(
            "historical pre-open bridge authority changed"
        ) from exc
    record = _record(bridge, manifest_bytes, shards)
    digest = hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES(record)).hexdigest()
    value = AuthenticatedHistoricalPreopenInputs(
        **record,
        projection_id="arv2-authenticated-historical-preopen-" + digest[:24],
        projection_sha256=digest,
        closed_input_manifest_bytes=manifest_bytes,
        input_shards=shards,
        _source_bridge=bridge,
    )
    reference = weakref.ref(
        value, lambda _ref, key=id(value): _AUTHORITIES.pop(key, None)
    )
    with _AUTHORITY_LOCK:
        _AUTHORITIES[id(value)] = (reference, _fingerprint(value), os.getpid())
    return require_authenticated_historical_preopen_inputs(value)


def require_authenticated_historical_preopen_inputs(
    value: AuthenticatedHistoricalPreopenInputs,
) -> AuthenticatedHistoricalPreopenInputs:
    """Reauthenticate the projection, retained bytes, and physical parent."""

    if type(value) is not AuthenticatedHistoricalPreopenInputs:
        raise HistoricalPreopenInputAdapterError(
            "authenticated historical pre-open input type changed"
        )
    with _AUTHORITY_LOCK:
        registered = _AUTHORITIES.get(id(value))
    if (
        os.getpid() != _AUTHORITY_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise HistoricalPreopenInputAdapterError(
            "authenticated historical pre-open input lacks builder authority"
        )
    try:
        _require_dependency_authority()
        bridge = _PINNED_REQUIRE_BRIDGE(value._source_bridge)
        manifest = _strict_object(
            value.closed_input_manifest_bytes, "closed pre-open manifest"
        )
        record = _record(
            bridge, value.closed_input_manifest_bytes, value.input_shards
        )
        digest = hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES(record)).hexdigest()
        if (
            value.schema != ADAPTER_SCHEMA
            or value.source_bridge_id != bridge.bridge_id
            or value.source_bridge_sha256 != bridge.bridge_sha256
            or value.projection_id
            != "arv2-authenticated-historical-preopen-" + digest[:24]
            or value.projection_sha256 != digest
            or any(getattr(value, name) != item for name, item in record.items())
            or type(value.input_shards) is not tuple
            or any(type(item) is not PreopenInputShard for item in value.input_shards)
            or [
                _PINNED_PREOPEN_DESCRIPTOR(item) for item in value.input_shards
            ]
            != manifest.get("shards")
            or _rebuild_exact_manifest(
                manifest=manifest, shards=value.input_shards
            )
            != value.closed_input_manifest_bytes
            or registered[1] != _fingerprint(value)
        ):
            raise HistoricalPreopenInputAdapterError(
                "authenticated historical pre-open input changed"
            )
    except HistoricalPreopenInputAdapterError:
        raise
    except Exception as exc:
        raise HistoricalPreopenInputAdapterError(
            "authenticated historical pre-open input cannot be revalidated"
        ) from exc
    return value


__all__ = (
    "ADAPTER_SCHEMA",
    "AuthenticatedHistoricalPreopenInputs",
    "AuthenticatedHistoricalPreopenInputStream",
    "HistoricalPreopenInputAdapterError",
    "STREAM_SCHEMA",
    "build_authenticated_historical_preopen_input_stream",
    "build_authenticated_historical_preopen_inputs",
    "iter_authenticated_historical_preopen_input_shards",
    "require_authenticated_historical_preopen_input_stream",
    "require_authenticated_historical_preopen_inputs",
)
