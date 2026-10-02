"""Focused authority tests for the physical historical pre-open adapter."""
from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from research.analyst_revisions_v2_qc import historical_preopen_input_adapter as adapter
from research.analyst_revisions_v2_qc.physical_historical_preopen_bridge import (
    build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed,
)
from scripts import build_arv2_historical_preopen_bridge as historical
from tests.analyst_revisions_v2 import (
    test_physical_historical_preopen_bridge as fixture,
)


def _bridge(monkeypatch, tmp_path):
    discovery, _massive, _c1, _sharadar, seed, _legacy = fixture._sources(
        monkeypatch, tmp_path
    )
    return build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
        discovery, seed, tmp_path / "physical-historical-preopen"
    )


def test_adapter_reconstructs_every_exact_descriptor_payload_and_order(
    monkeypatch, tmp_path
):
    bridge = _bridge(monkeypatch, tmp_path)
    value = adapter.build_authenticated_historical_preopen_inputs(bridge)
    assert adapter.require_authenticated_historical_preopen_inputs(value) is value
    manifest = json.loads(value.closed_input_manifest_bytes)
    assert [item.descriptor() for item in value.input_shards] == manifest["shards"]
    assert tuple(item.role for item in value.input_shards) == tuple(
        descriptor["role"] for descriptor in manifest["shards"]
    )
    source = list(historical.iter_reviewed_historical_preopen_input_shards(bridge))
    assert [item.payload for item in value.input_shards] == [
        item.payload for item in source
    ]
    assert value.input_source_inventory_sha256 == hashlib.sha256(
        adapter.canonical_json_bytes(manifest["shards"])
    ).hexdigest()
    assert manifest["resource_census"][
        "host_manifest_projection_retains_all_compressed_input_payloads"
    ] is False


def test_adapter_refuses_rebound_physical_iterator_before_hostile_callback(
    monkeypatch, tmp_path
):
    bridge = _bridge(monkeypatch, tmp_path)
    callbacks = []

    def hostile(_value):
        callbacks.append(_value)
        raise AssertionError("hostile iterator executed")

    monkeypatch.setattr(
        historical, "iter_reviewed_historical_preopen_input_shards", hostile
    )
    with pytest.raises(
        adapter.HistoricalPreopenInputAdapterError,
        match="dependency authority changed",
    ):
        adapter.build_authenticated_historical_preopen_inputs(bridge)
    assert callbacks == []


def test_adapter_refuses_retained_payload_mutation_on_reauthentication(
    monkeypatch, tmp_path
):
    bridge = _bridge(monkeypatch, tmp_path)
    value = adapter.build_authenticated_historical_preopen_inputs(bridge)
    first = value.input_shards[0]
    changed = dataclasses.replace(
        first,
        payload=first.payload + b"changed",
        compressed_byte_count=first.compressed_byte_count + 7,
        compressed_sha256=hashlib.sha256(first.payload + b"changed").hexdigest(),
    )
    object.__setattr__(value, "input_shards", (changed, *value.input_shards[1:]))
    with pytest.raises(
        adapter.HistoricalPreopenInputAdapterError,
        match="authenticated historical pre-open input changed",
    ):
        adapter.require_authenticated_historical_preopen_inputs(value)


def test_adapter_refuses_forged_unregistered_projection(monkeypatch, tmp_path):
    bridge = _bridge(monkeypatch, tmp_path)
    value = adapter.build_authenticated_historical_preopen_inputs(bridge)
    forged = dataclasses.replace(value)
    with pytest.raises(
        adapter.HistoricalPreopenInputAdapterError,
        match="lacks builder authority",
    ):
        adapter.require_authenticated_historical_preopen_inputs(forged)


def test_adapter_refuses_rebound_manifest_or_canonicalizer_before_callback(
    monkeypatch, tmp_path
):
    bridge = _bridge(monkeypatch, tmp_path)
    callbacks = []

    def hostile(**_values):
        callbacks.append(True)
        return bridge.closed_input_manifest_bytes

    monkeypatch.setattr(adapter, "build_preopen_input_manifest_bytes", hostile)
    with pytest.raises(
        adapter.HistoricalPreopenInputAdapterError,
        match="dependency authority changed",
    ):
        adapter.build_authenticated_historical_preopen_inputs(bridge)
    assert callbacks == []
    monkeypatch.setattr(
        adapter,
        "build_preopen_input_manifest_bytes",
        adapter._PINNED_BUILD_MANIFEST,
    )
    monkeypatch.setattr(adapter, "canonical_json_bytes", hostile)
    with pytest.raises(
        adapter.HistoricalPreopenInputAdapterError,
        match="dependency authority changed",
    ):
        adapter.build_authenticated_historical_preopen_inputs(bridge)
    assert callbacks == []
