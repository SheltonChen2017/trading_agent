"""Synthetic logical-layout contract for eventual ARV2 QuantConnect inputs."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest

from research.analyst_revisions_v2_qc import synthetic_input_transport as transport
from research.analyst_revisions_v2_qc.global_input_bundle import (
    SyntheticGlobalInputPartitionPayload,
    collect_synthetic_event_study_from_global_input_bundle,
    load_synthetic_qc_global_input_bundle,
)
from research.analyst_revisions_v2_qc.synthetic_input_transport import (
    CAPABILITIES,
    EXPECTED_OBJECT_COUNT,
    EXTERNAL_BINDINGS,
    FALSE_PROPERTY_NAMES,
    KEY_PREFIX,
    MAX_INDEX_BYTES,
    MAX_JSON_DEPTH,
    MAX_OBJECT_BYTES,
    MAX_TOTAL_BYTES,
    QcSyntheticInputTransportError,
    SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID,
    SCHEMA_SHA256,
    SyntheticObjectStoreEntry,
    SyntheticObjectStoreFixture,
    SyntheticQcTransportLoad,
    build_synthetic_qc_object_store_fixture,
    load_synthetic_qc_global_input_bundle_from_object_store_fixture,
    render_qc_synthetic_input_transport_schema_bytes,
    require_synthetic_qc_transport_load,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import (
    _active_rows,
    _terminal_rows,
    _wire_inputs,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/analyst_revisions_v2_qc/synthetic_input_transport.py"
BUNDLE_MODULE = ROOT / "research/analyst_revisions_v2_qc/global_input_bundle.py"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _inputs(rows=None):
    return _wire_inputs(_active_rows() if rows is None else rows)


def _fixture(rows=None):
    candidate, manifest_bytes, partition_payloads = _inputs(rows)
    fixture = build_synthetic_qc_object_store_fixture(
        run_candidate=candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )
    return candidate, manifest_bytes, partition_payloads, fixture


def _load(rows=None):
    candidate, _, _, fixture = _fixture(rows)
    receipt = load_synthetic_qc_global_input_bundle_from_object_store_fixture(
        run_candidate=candidate,
        object_store=fixture,
        transport_index_key=fixture.transport_index_key,
    )
    return candidate, fixture, receipt


def _replace_entry(
    fixture: SyntheticObjectStoreFixture,
    ordinal: int,
    *,
    key: object | None = None,
    payload: object | None = None,
) -> SyntheticObjectStoreFixture:
    entries = list(fixture.entries)
    old = entries[ordinal]
    entries[ordinal] = SyntheticObjectStoreEntry(
        key=old.key if key is None else key,
        payload=old.payload if payload is None else payload,
    )
    return SyntheticObjectStoreFixture(
        transport_index_key=fixture.transport_index_key,
        entries=tuple(entries),
    )


def _index_document(fixture: SyntheticObjectStoreFixture) -> dict[str, object]:
    return json.loads(fixture.entries[0].payload)


def _replace_index_document(
    fixture: SyntheticObjectStoreFixture,
    document: dict[str, object],
    *,
    reidentify: bool = True,
) -> SyntheticObjectStoreFixture:
    if reidentify:
        seed = dict(document)
        seed["transport_id"] = None
        seed["transport_hash"] = None
        digest = hashlib.sha256(
            transport.TRANSPORT_HASH_DOMAIN.encode("ascii")
            + b"\x00"
            + _canonical(seed)
        ).hexdigest()
        document["transport_id"] = f"arv2-qc-synthetic-transport-{digest[:16]}"
        document["transport_hash"] = digest
    return _replace_entry(fixture, 0, payload=_canonical(document))


def test_transport_schema_is_stable_and_content_addressed():
    payload = render_qc_synthetic_input_transport_schema_bytes()
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert hashlib.sha256(payload).hexdigest() == SCHEMA_ARTIFACT_SHA256
    assert SCHEMA_ID == f"arv2-qc-synthetic-input-transport-schema-{SCHEMA_SHA256[:16]}"
    assert SCHEMA_ID == "arv2-qc-synthetic-input-transport-schema-dc34a225af704e3b"
    assert SCHEMA_SHA256 == "dc34a225af704e3b2a4632108f936a7812d3119ce7b3ce95a3e0f3ea8483c439"
    assert SCHEMA_ARTIFACT_SHA256 == (
        "ff0eed2e87de06729b6a2b3d4a35b2cbecaaab2194d4f4d7e84cda0bb48ebe10"
    )
    assert render_qc_synthetic_input_transport_schema_bytes() == payload


def test_transport_schema_has_no_external_authority():
    document = json.loads(render_qc_synthetic_input_transport_schema_bytes())
    assert all(value is None for value in document["external_bindings"].values())
    assert all(value is False for value in document["capabilities"].values())
    assert document["object_count"] == EXPECTED_OBJECT_COUNT
    assert document["object_order"] == [
        "transport_index",
        "global_input_manifest",
        *transport.ROLE_ORDER,
    ]
    assert document["key_rules"]["scope"] == (
        "logical_relative_suffix_not_a_direct_qc_object_store_key"
    )
    assert document["resource_limits"]["scope"] == (
        "synthetic_fixture_parser_bounds_not_authenticated_qc_quota"
    )


def test_fixture_layout_is_deterministic_and_exactly_nine_objects():
    candidate, manifest_bytes, partition_payloads, first = _fixture()
    second = build_synthetic_qc_object_store_fixture(
        run_candidate=candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )
    assert first == second
    assert len(first.entries) == EXPECTED_OBJECT_COUNT
    assert first.entries[0].key == first.transport_index_key
    assert first.transport_index_key.startswith(
        f"{KEY_PREFIX}/{SCHEMA_SHA256}/{candidate.candidate_hash}/"
    )
    assert len({item.key for item in first.entries}) == EXPECTED_OBJECT_COUNT
    assert all(".." not in item.key.split("/") for item in first.entries)


@pytest.mark.parametrize("rows_factory", (_active_rows, _terminal_rows))
def test_fixture_load_reproduces_direct_bundle_and_event_study(rows_factory):
    rows = rows_factory()
    candidate, manifest_bytes, partition_payloads, fixture = _fixture(rows)
    direct = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )
    receipt = load_synthetic_qc_global_input_bundle_from_object_store_fixture(
        run_candidate=candidate,
        object_store=fixture,
        transport_index_key=fixture.transport_index_key,
    )
    assert receipt.bundle.bundle_id == direct.bundle_id
    assert receipt.bundle.bundle_hash == direct.bundle_hash
    assert receipt.bundle.bundle_artifact_sha256 == direct.bundle_artifact_sha256
    assert (
        collect_synthetic_event_study_from_global_input_bundle(receipt.bundle)
        == collect_synthetic_event_study_from_global_input_bundle(direct)
    )


def test_load_receipt_records_exact_resolution_order_and_closed_authorities():
    _, fixture, receipt = _load()
    assert fixture.qc_object_store_read_available is False
    assert fixture.qc_object_store_write_available is False
    assert receipt.resolved_fixture_keys == tuple(item.key for item in fixture.entries)
    assert receipt.total_object_count == 9
    assert receipt.total_byte_count == sum(len(item.payload) for item in fixture.entries)
    assert receipt.synthetic_fixture_transport_validated is True
    assert receipt.real_qc_object_store_access_performed is False
    assert receipt.external_bindings == EXTERNAL_BINDINGS
    assert receipt.capabilities == CAPABILITIES
    assert all(value is None for _, value in receipt.external_bindings)
    assert all(value is False for _, value in receipt.capabilities)
    assert all(getattr(receipt, name) is False for name in FALSE_PROPERTY_NAMES)


def test_load_receipt_reauthenticates_without_changing_identity():
    _, _, receipt = _load()
    assert require_synthetic_qc_transport_load(receipt) is receipt


def test_transport_index_binds_parent_source_and_bundle_schema():
    _, _, _, fixture = _fixture()
    document = _index_document(fixture)
    binding = document["bundle_contract_binding"]
    assert binding["schema_id"] == transport.BUNDLE_SCHEMA_ID
    assert binding["schema_sha256"] == transport.BUNDLE_SCHEMA_SHA256
    assert binding["schema_artifact_sha256"] == transport.BUNDLE_SCHEMA_ARTIFACT_SHA256
    source = BUNDLE_MODULE.read_bytes().replace(b"\r\n", b"\n")
    assert len(source) == transport.BUNDLE_SOURCE_BYTE_COUNT
    assert hashlib.sha256(source).hexdigest() == transport.BUNDLE_SOURCE_SHA256


def test_transport_index_partition_bindings_match_every_fixture_payload():
    _, _, _, fixture = _fixture()
    document = _index_document(fixture)
    for descriptor, entry in zip(document["partitions"], fixture.entries[2:], strict=True):
        assert descriptor["key"] == entry.key
        assert descriptor["byte_count"] == len(entry.payload)
        assert descriptor["artifact_sha256"] == hashlib.sha256(entry.payload).hexdigest()


class _HostileStore:
    calls = 0

    def __getattribute__(self, name):
        type(self).calls += 1
        return object.__getattribute__(self, name)


def test_lookalike_external_store_is_rejected_before_any_callback():
    candidate, _, _, fixture = _fixture()
    _HostileStore.calls = 0
    with pytest.raises(
        QcSyntheticInputTransportError,
        match="only the exact synthetic Object Store fixture",
    ):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=_HostileStore(),
            transport_index_key=fixture.transport_index_key,
        )
    assert _HostileStore.calls == 0


def test_fixture_subclass_is_not_an_external_store_escape():
    class DerivedFixture(SyntheticObjectStoreFixture):
        pass

    candidate, _, _, fixture = _fixture()
    derived = DerivedFixture(
        transport_index_key=fixture.transport_index_key,
        entries=fixture.entries,
    )
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=derived,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize(
    "bad_key",
    (
        "",
        "/absolute/key",
        "a/../b",
        "a/./b",
        "a//b",
        "a\\b",
        "C:/drive/key",
        "https://example.test/key",
        "a/",
        "a" * 513,
    ),
)
def test_unsafe_object_keys_are_refused(bad_key: str):
    candidate, _, _, fixture = _fixture()
    changed = _replace_entry(fixture, 2, key=bad_key)
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_safe_key_accepts_the_declared_512_character_boundary():
    assert transport._require_safe_key("a" * 512, "boundary key") == "a" * 512


def test_coherently_reidentified_safe_relocation_is_refused():
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    index_key = "alternate/safe/layout/transport-index.json"
    manifest_key = "alternate/safe/layout/manifest.json"
    partition_keys = tuple(
        f"alternate/safe/layout/{ordinal:02d}-{descriptor['role']}.jsonl"
        for ordinal, descriptor in enumerate(document["partitions"], start=1)
    )
    document["layout"]["index_key"] = index_key
    document["manifest_binding"]["key"] = manifest_key
    for descriptor, key in zip(document["partitions"], partition_keys, strict=True):
        descriptor["key"] = key
    reidentified = _replace_index_document(fixture, document)
    changed = SyntheticObjectStoreFixture(
        transport_index_key=index_key,
        entries=(
            SyntheticObjectStoreEntry(key=index_key, payload=reidentified.entries[0].payload),
            SyntheticObjectStoreEntry(key=manifest_key, payload=fixture.entries[1].payload),
            *(
                SyntheticObjectStoreEntry(key=key, payload=entry.payload)
                for key, entry in zip(
                    partition_keys,
                    fixture.entries[2:],
                    strict=True,
                )
            ),
        ),
    )
    with pytest.raises(QcSyntheticInputTransportError, match="content-addressed layout"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=index_key,
        )


@pytest.mark.parametrize("mode", ("missing", "extra", "duplicate", "reordered"))
def test_fixture_inventory_must_be_complete_unique_and_ordered(mode: str):
    candidate, _, _, fixture = _fixture()
    entries = list(fixture.entries)
    if mode == "missing":
        entries.pop()
    elif mode == "extra":
        entries.append(SyntheticObjectStoreEntry(key="extra/object", payload=b"x"))
    elif mode == "duplicate":
        entries[-1] = dataclasses.replace(entries[-1], key=entries[-2].key)
    else:
        entries[-1], entries[-2] = entries[-2], entries[-1]
    changed = SyntheticObjectStoreFixture(
        transport_index_key=fixture.transport_index_key,
        entries=tuple(entries),
    )
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_transport_index_key_is_an_exact_argument_binding():
    candidate, _, _, fixture = _fixture()
    with pytest.raises(QcSyntheticInputTransportError, match="index key changed"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=fixture,
            transport_index_key="other/safe/index.json",
        )


def test_nonbytes_fixture_payload_is_refused_before_parsing():
    candidate, _, _, fixture = _fixture()
    changed = _replace_entry(fixture, 2, payload="not-bytes")
    with pytest.raises(QcSyntheticInputTransportError, match="exact bytes"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_oversized_transport_index_is_refused():
    candidate, _, _, fixture = _fixture()
    changed = _replace_entry(fixture, 0, payload=b"x" * (MAX_INDEX_BYTES + 1))
    with pytest.raises(QcSyntheticInputTransportError, match="index is too large"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_oversized_fixture_object_is_refused_before_parsing():
    candidate, _, _, fixture = _fixture()
    changed = _replace_entry(fixture, 2, payload=b"x" * (MAX_OBJECT_BYTES + 1))
    with pytest.raises(QcSyntheticInputTransportError, match="object is too large"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_total_fixture_bound_is_enforced_without_nine_distinct_allocations():
    candidate, _, _, fixture = _fixture()
    shared_payload = b"x" * ((MAX_TOTAL_BYTES // EXPECTED_OBJECT_COUNT) + 1)
    changed = SyntheticObjectStoreFixture(
        transport_index_key="synthetic/object-0",
        entries=tuple(
            SyntheticObjectStoreEntry(
                key=f"synthetic/object-{ordinal}",
                payload=shared_payload,
            )
            for ordinal in range(EXPECTED_OBJECT_COUNT)
        ),
    )
    with pytest.raises(QcSyntheticInputTransportError, match="total byte limit"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=changed.transport_index_key,
        )


def test_transport_index_json_depth_bound_is_enforced():
    candidate, _, _, fixture = _fixture()
    depth = MAX_JSON_DEPTH + 2
    payload = (b"[" * depth) + b"0" + (b"]" * depth) + b"\n"
    changed = _replace_entry(fixture, 0, payload=payload)
    with pytest.raises(QcSyntheticInputTransportError, match="maximum JSON depth"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize(
    "mutator",
    (
        lambda payload: b"\xef\xbb\xbf" + payload,
        lambda payload: payload.replace(b"\n", b"\r\n"),
        lambda payload: payload.rstrip(b"\n"),
        lambda payload: payload + b"\n",
        lambda payload: b"\xff\n",
    ),
)
def test_noncanonical_transport_index_encodings_are_refused(mutator):
    candidate, _, _, fixture = _fixture()
    changed = _replace_entry(fixture, 0, payload=mutator(fixture.entries[0].payload))
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_duplicate_json_key_and_float_are_refused():
    candidate, _, _, fixture = _fixture()
    original = fixture.entries[0].payload
    duplicate = original.replace(b'{"authority":', b'{"authority":"x","authority":', 1)
    floating = original.replace(b'"object_count":8', b'"object_count":8.0', 1)
    for payload in (duplicate, floating):
        changed = _replace_entry(fixture, 0, payload=payload)
        with pytest.raises(QcSyntheticInputTransportError):
            load_synthetic_qc_global_input_bundle_from_object_store_fixture(
                run_candidate=candidate,
                object_store=changed,
                transport_index_key=fixture.transport_index_key,
            )


def test_oversized_json_integer_is_normalized_to_the_lane_error():
    candidate, _, _, fixture = _fixture()
    payload = fixture.entries[0].payload.replace(
        b'"object_count":8',
        b'"object_count":' + (b"9" * 5_000),
        1,
    )
    assert len(payload) <= MAX_INDEX_BYTES
    changed = _replace_entry(fixture, 0, payload=payload)
    with pytest.raises(
        QcSyntheticInputTransportError,
        match="not valid bounded canonical JSON",
    ):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize(
    "field,value",
    (
        ("schema", "different-schema"),
        ("status", "production"),
        ("authority", "run_anything"),
        ("transport_hash", "0" * 64),
    ),
)
def test_transport_root_authority_and_identity_mutations_refuse(field, value):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document[field] = value
    changed = _replace_index_document(
        fixture,
        document,
        reidentify=field != "transport_hash",
    )
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_object_order_mutation_is_refused_after_coherent_reidentification():
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document["layout"]["object_order"][1:3] = reversed(
        document["layout"]["object_order"][1:3]
    )
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError, match="object order changed"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize(
    "field,value",
    (
        ("object_count", 7),
        ("partition_count", 6),
        ("total_byte_count", 0),
    ),
)
def test_referenced_census_guards_are_independently_load_bearing(field, value):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document["referenced_census"][field] = value
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError, match="transport census changed"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize(
    "section,field,value,error",
    (
        ("schema_binding", "schema_id", "changed", "schema binding changed"),
        ("schema_binding", "schema_sha256", "0" * 64, "schema binding changed"),
        (
            "schema_binding",
            "schema_artifact_sha256",
            "0" * 64,
            "schema binding changed",
        ),
        (
            "bundle_contract_binding",
            "schema_id",
            "changed",
            "bundle contract binding changed",
        ),
        (
            "bundle_contract_binding",
            "schema_sha256",
            "0" * 64,
            "bundle contract binding changed",
        ),
        (
            "bundle_contract_binding",
            "schema_artifact_sha256",
            "0" * 64,
            "bundle contract binding changed",
        ),
        (
            "bundle_contract_binding",
            "source_sha256",
            "0" * 64,
            "bundle contract binding changed",
        ),
        (
            "bundle_contract_binding",
            "source_byte_count",
            0,
            "bundle contract binding changed",
        ),
    ),
)
def test_schema_and_parent_source_binding_mutations_refuse(
    section,
    field,
    value,
    error,
):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document[section][field] = value
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError, match=error):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize(
    "section,field,value",
    (
        ("run_candidate_binding", "candidate_hash", "0" * 64),
        ("manifest_binding", "manifest_sha256", "0" * 64),
        ("bundle_binding", "bundle_hash", "0" * 64),
        ("referenced_census", "total_row_count", 0),
    ),
)
def test_nested_lineage_census_and_authority_mutations_refuse(section, field, value):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document[section][field] = value
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize(
    "field",
    (
        "synthetic_fixture_transport",
        "real_qc_object_store_access_performed",
        "runtime_code_authenticated",
        "production_truth_authenticated",
        "rights_authenticated",
        "point_in_time_provenance_authenticated",
        "real_outcome_authority",
    ),
)
def test_every_truth_state_gate_is_exact_and_load_bearing(field):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document["truth_state"][field] = not document["truth_state"][field]
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError, match="truth state changed"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize("field", tuple(name for name, _ in CAPABILITIES))
def test_every_capability_gate_is_closed_and_load_bearing(field):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document["capabilities"][field] = True
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError, match="authority changed"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize("field", tuple(name for name, _ in EXTERNAL_BINDINGS))
def test_every_external_authority_binding_is_null_and_load_bearing(field):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document["external_bindings"][field] = "bound"
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError, match="authority changed"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_integer_aliases_cannot_impersonate_boolean_or_ordinal_fields():
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document["partitions"][0]["ordinal"] = True
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )

    document = _index_document(fixture)
    document["truth_state"]["real_qc_object_store_access_performed"] = 0
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )

    document = _index_document(fixture)
    document["capabilities"]["qc_launch"] = 0
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_each_partition_census_is_bound_to_the_authenticated_manifest():
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    assert document["partitions"][0]["row_count"] > 0
    document["partitions"][0]["row_count"] -= 1
    document["partitions"][1]["row_count"] += 1
    changed = _replace_index_document(fixture, document)
    with pytest.raises(QcSyntheticInputTransportError, match="manifest"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


@pytest.mark.parametrize("ordinal", range(2, 9))
def test_each_partition_is_hash_checked_before_bundle_decode(ordinal, monkeypatch):
    candidate, _, _, fixture = _fixture()
    calls = []

    def hostile_loader(**kwargs):
        calls.append(kwargs)
        raise AssertionError("bundle decoder ran before transport hash refusal")

    monkeypatch.setattr(transport, "load_synthetic_qc_global_input_bundle", hostile_loader)
    monkeypatch.setattr(transport, "_PINNED_LOAD_BUNDLE", hostile_loader)
    payload = bytearray(fixture.entries[ordinal].payload)
    if payload:
        payload[0] ^= 1
    else:
        payload.extend(b"x")
    changed = _replace_entry(fixture, ordinal, payload=bytes(payload))
    with pytest.raises(QcSyntheticInputTransportError, match="bytes do not match"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )
    assert calls == []


def test_manifest_is_hash_checked_before_manifest_decode(monkeypatch):
    candidate, _, _, fixture = _fixture()
    calls = []

    def hostile_loader(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("manifest decoder ran before transport hash refusal")

    monkeypatch.setattr(
        transport,
        "load_synthetic_qc_global_input_manifest_bytes",
        hostile_loader,
    )
    monkeypatch.setattr(transport, "_PINNED_LOAD_MANIFEST", hostile_loader)
    payload = bytearray(fixture.entries[1].payload)
    payload[0] ^= 1
    changed = _replace_entry(fixture, 1, payload=bytes(payload))
    with pytest.raises(QcSyntheticInputTransportError, match="manifest bytes"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )
    assert calls == []


def test_swapped_partition_objects_are_refused():
    candidate, _, _, fixture = _fixture()
    entries = list(fixture.entries)
    entries[2], entries[3] = entries[3], entries[2]
    changed = SyntheticObjectStoreFixture(
        transport_index_key=fixture.transport_index_key,
        entries=tuple(entries),
    )
    with pytest.raises(QcSyntheticInputTransportError, match="order or inventory"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
        )


def test_different_valid_candidate_cannot_reuse_a_fixture():
    _, _, _, fixture = _fixture()
    other_candidate, _, _ = _inputs(_terminal_rows())
    with pytest.raises(QcSyntheticInputTransportError, match="lineage changed"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=other_candidate,
            object_store=fixture,
            transport_index_key=fixture.transport_index_key,
        )


def test_original_fixture_mutation_after_load_does_not_change_receipt():
    candidate, _, _, fixture = _fixture()
    receipt = load_synthetic_qc_global_input_bundle_from_object_store_fixture(
        run_candidate=candidate,
        object_store=fixture,
        transport_index_key=fixture.transport_index_key,
    )
    object.__setattr__(fixture.entries[-1], "payload", b"changed")
    assert require_synthetic_qc_transport_load(receipt) is receipt


@pytest.mark.parametrize(
    "field,value",
    (
        ("transport_hash", "0" * 64),
        ("transport_artifact_sha256", "0" * 64),
        ("total_object_count", 8),
        ("total_byte_count", -1),
        ("total_row_count", -1),
        ("synthetic_fixture_transport_validated", False),
        ("real_qc_object_store_access_performed", True),
    ),
)
def test_retained_receipt_scalar_tampering_refuses(field, value):
    _, _, receipt = _load()
    object.__setattr__(receipt, field, value)
    with pytest.raises(QcSyntheticInputTransportError):
        require_synthetic_qc_transport_load(receipt)


def test_retained_fixture_and_bundle_tampering_refuse():
    _, _, receipt = _load()
    bad_fixture = _replace_entry(receipt._fixture, 2, payload=b"changed")
    object.__setattr__(receipt, "_fixture", bad_fixture)
    with pytest.raises(QcSyntheticInputTransportError):
        require_synthetic_qc_transport_load(receipt)

    _, _, receipt = _load()
    object.__setattr__(receipt.bundle, "bundle_hash", "0" * 64)
    with pytest.raises(QcSyntheticInputTransportError):
        require_synthetic_qc_transport_load(receipt)


@pytest.mark.parametrize(
    "name,value",
    (
        ("TRANSPORT_HASH_DOMAIN", "unreviewed-domain"),
        ("KEY_PREFIX", "unreviewed/prefix"),
        ("MAX_OBJECT_BYTES", 49_000_001),
    ),
)
def test_public_operations_refuse_static_contract_mutation(monkeypatch, name, value):
    monkeypatch.setattr(transport, name, value)
    with pytest.raises(QcSyntheticInputTransportError, match="static|resource"):
        render_qc_synthetic_input_transport_schema_bytes()


@pytest.mark.parametrize(
    "value",
    (
        True,
        1,
        type("TextLookalike", (str,), {})(transport.SCHEMA_ARTIFACT_SHA256),
    ),
)
def test_schema_artifact_identity_refuses_scalar_type_aliases(monkeypatch, value):
    monkeypatch.setattr(transport, "SCHEMA_ARTIFACT_SHA256", value)
    with pytest.raises(QcSyntheticInputTransportError, match="static"):
        render_qc_synthetic_input_transport_schema_bytes()


def test_schema_artifact_identity_refuses_before_hostile_equality(monkeypatch):
    class HostileEquality:
        calls = 0

        def __eq__(self, _other):
            type(self).calls += 1
            return True

    monkeypatch.setattr(transport, "SCHEMA_ARTIFACT_SHA256", HostileEquality())
    with pytest.raises(QcSyntheticInputTransportError, match="static"):
        render_qc_synthetic_input_transport_schema_bytes()
    assert HostileEquality.calls == 0


@pytest.mark.parametrize("name", ("_HEX_64", "_SAFE_KEY"))
def test_regex_replacement_refuses_before_hostile_match_callback(monkeypatch, name):
    class HostileMatcher:
        calls = 0

        def fullmatch(self, _value):
            type(self).calls += 1
            return object()

    monkeypatch.setattr(transport, name, HostileMatcher())
    with pytest.raises(QcSyntheticInputTransportError, match="topology"):
        render_qc_synthetic_input_transport_schema_bytes()
    assert HostileMatcher.calls == 0


@pytest.mark.parametrize(
    "name",
    (
        "_CLASS_MEMBERS",
        "_CLASS_FUNCTION_STATES",
        "_FALSE_PROPERTY_TOPOLOGY",
        "_LOCAL_FUNCTION_STATES",
    ),
)
def test_empty_static_snapshot_registry_is_refused(monkeypatch, name):
    monkeypatch.setattr(transport, name, ())
    with pytest.raises(QcSyntheticInputTransportError, match="topology|graph"):
        render_qc_synthetic_input_transport_schema_bytes()


def test_builtin_type_shadow_refuses_external_lookalike_before_callback(monkeypatch):
    candidate, _, _, fixture = _fixture()

    class ExternalLookalike:
        calls = 0

        def __getattribute__(self, name):
            type(self).calls += 1
            return object.__getattribute__(self, name)

    external = ExternalLookalike()
    real_type = type

    def smart_type(value):
        if value is external:
            return SyntheticObjectStoreFixture
        return real_type(value)

    monkeypatch.setattr(transport, "type", smart_type, raising=False)
    with pytest.raises(QcSyntheticInputTransportError, match="builtin topology"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=external,
            transport_index_key=fixture.transport_index_key,
        )
    assert ExternalLookalike.calls == 0


def test_builtin_any_shadow_cannot_hide_authority_bearing_index(monkeypatch):
    candidate, _, _, fixture = _fixture()
    document = _index_document(fixture)
    document["capabilities"]["qc_launch"] = True
    fixture = _replace_index_document(fixture, document)
    assert json.loads(fixture.entries[0].payload)["capabilities"]["qc_launch"] is True

    monkeypatch.setattr(transport, "any", lambda _items: False, raising=False)
    with pytest.raises(QcSyntheticInputTransportError, match="builtin topology"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=fixture,
            transport_index_key=fixture.transport_index_key,
        )


def test_builtin_key_lookalike_refuses_without_equality_callback_subprocess():
    script = r'''
from research.analyst_revisions_v2_qc import synthetic_input_transport as transport

calls = []

class AnyLookalike(str):
    def __eq__(self, other):
        calls.append(other)
        return super().__eq__(other)

    __hash__ = str.__hash__

builtins_dict = transport._BUILTIN_GLOBALS
original = builtins_dict.pop("any")
lookalike = AnyLookalike("any")
builtins_dict[lookalike] = original
try:
    try:
        transport.render_qc_synthetic_input_transport_schema_bytes()
    except transport.QcSyntheticInputTransportError as exc:
        if str(exc) != "synthetic transport builtin topology changed":
            raise AssertionError(f"unexpected refusal: {exc}")
    else:
        raise AssertionError("equal builtin-key lookalike was accepted")
    if calls:
        raise AssertionError(f"hostile equality ran {len(calls)} times")
finally:
    del builtins_dict[lookalike]
    builtins_dict["any"] = original
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "name,delegate",
    (
        ("_PINNED_DICT_ITEMS", dict.items),
        ("_PINNED_DICT_GET", dict.get),
        ("_PINNED_TYPE", type),
        ("_PINNED_LEN", len),
    ),
)
def test_builtin_primitive_alias_replacement_refuses_before_callback(
    monkeypatch,
    name,
    delegate,
):
    calls = []

    def hostile_alias(*args, **kwargs):
        calls.append((args, kwargs))
        return delegate(*args, **kwargs)

    monkeypatch.setattr(transport, name, hostile_alias)
    with pytest.raises(QcSyntheticInputTransportError, match="builtin topology"):
        render_qc_synthetic_input_transport_schema_bytes()
    assert calls == []


@pytest.mark.parametrize(
    "accepted_class,property_name",
    (
        (SyntheticObjectStoreFixture, "qc_object_store_read_available"),
        (SyntheticQcTransportLoad, "launch_available"),
    ),
)
def test_false_authority_property_replacement_is_refused(
    monkeypatch,
    accepted_class,
    property_name,
):
    monkeypatch.setattr(accepted_class, property_name, property(lambda _self: True))
    with pytest.raises(QcSyntheticInputTransportError, match="class topology"):
        render_qc_synthetic_input_transport_schema_bytes()


def test_generated_receipt_constructor_code_mutation_is_refused(monkeypatch):
    original_init = SyntheticQcTransportLoad.__init__
    replacement_code = original_init.__code__.replace(
        co_firstlineno=original_init.__code__.co_firstlineno + 1
    )
    monkeypatch.setattr(original_init, "__code__", replacement_code)
    with pytest.raises(QcSyntheticInputTransportError, match="function state"):
        render_qc_synthetic_input_transport_schema_bytes()


def test_generated_receipt_constructor_closure_mutation_is_refused(monkeypatch):
    candidate, _, _, fixture = _fixture()

    class HostileObject:
        calls = 0

        @staticmethod
        def __setattr__(target, name, value):
            HostileObject.calls += 1
            object.__setattr__(
                target,
                name,
                True if name == "real_qc_object_store_access_performed" else value,
            )

    closure = SyntheticQcTransportLoad.__init__.__closure__
    assert closure is not None
    object_cell = next(cell for cell in closure if cell.cell_contents is object)
    monkeypatch.setattr(object_cell, "cell_contents", HostileObject)
    with pytest.raises(QcSyntheticInputTransportError, match="function state"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=fixture,
            transport_index_key=fixture.transport_index_key,
        )
    assert HostileObject.calls == 0


def test_uninitialized_fixture_and_receipt_shells_raise_lane_error():
    fixture_shell = object.__new__(SyntheticObjectStoreFixture)
    candidate, _, _, _ = _fixture()
    with pytest.raises(QcSyntheticInputTransportError, match="topology"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=fixture_shell,
            transport_index_key="safe/index.json",
        )

    receipt_shell = object.__new__(SyntheticQcTransportLoad)
    with pytest.raises(QcSyntheticInputTransportError, match="topology"):
        require_synthetic_qc_transport_load(receipt_shell)


def test_internal_parser_replacement_is_refused_before_fixture_resolution(monkeypatch):
    candidate, _, _, fixture = _fixture()
    original = transport._parse_transport_contract(fixture.entries[0].payload)
    monkeypatch.setattr(transport, "_parse_transport_contract", lambda _payload: original)
    with pytest.raises(QcSyntheticInputTransportError, match="callable graph"):
        load_synthetic_qc_global_input_bundle_from_object_store_fixture(
            run_candidate=candidate,
            object_store=fixture,
            transport_index_key=fixture.transport_index_key,
        )


def test_public_boundaries_have_value_only_signatures():
    assert tuple(inspect.signature(build_synthetic_qc_object_store_fixture).parameters) == (
        "run_candidate",
        "manifest_bytes",
        "partition_payloads",
    )
    assert tuple(
        inspect.signature(
            load_synthetic_qc_global_input_bundle_from_object_store_fixture
        ).parameters
    ) == ("run_candidate", "object_store", "transport_index_key")
    assert tuple(inspect.signature(require_synthetic_qc_transport_load).parameters) == (
        "value",
    )


def test_transport_module_has_no_external_io_or_qc_runtime_surface():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    forbidden_roots = {
        "builtins",
        "io",
        "os",
        "pathlib",
        "subprocess",
        "requests",
        "urllib",
        "http",
        "socket",
        "quantconnect",
        "algorithmimports",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0].lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0].lower())
    assert imported == {
        "__future__",
        "dataclasses",
        "global_input_bundle",
        "global_input_schema",
        "hashlib",
        "inspect",
        "json",
        "re",
        "run_contract",
    }
    assert imported.isdisjoint(forbidden_roots)
    forbidden_calls = {
        "open",
        "__import__",
        "eval",
        "exec",
        "compile",
        "getenv",
        "put",
        "save",
        "delete",
        "create_project",
        "compile_project",
        "backtest",
        "launch",
        "submit_order",
    }
    assert {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }.isdisjoint(forbidden_calls)
    forbidden_attribute_calls = forbidden_calls | {
        "contains_key",
        "get_file_path",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
    }
    assert {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and not (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re"
            and node.func.attr == "compile"
        )
        and node.func.attr in forbidden_attribute_calls
    } == set()


def test_no_io_ast_guard_detects_an_attribute_call_mutant():
    tree = ast.parse(
        "import builtins\n"
        "def _hidden_read():\n"
        "    return builtins.open('forbidden')\n"
    )
    imported = {
        alias.name.split(".", 1)[0].lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "builtins" in imported
    assert "open" in attribute_calls
    nested = ast.parse(
        "def _hidden_read(self):\n"
        "    return self.object_store.read_bytes('forbidden')\n"
    )
    assert "read_bytes" in {
        node.func.attr
        for node in ast.walk(nested)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def test_no_public_writer_runner_result_or_trading_entrypoint_exists():
    forbidden_fragments = (
        "write",
        "upload",
        "compile",
        "launch",
        "run_backtest",
        "read_result",
        "deploy",
        "order",
        "trade",
    )
    public_callables = {
        name
        for name, value in vars(transport).items()
        if not name.startswith("_") and inspect.isfunction(value)
    }
    assert all(
        fragment not in name
        for name in public_callables
        for fragment in forbidden_fragments
    )
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    assert tuple(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ) == (
        "render_qc_synthetic_input_transport_schema_bytes",
        "build_synthetic_qc_object_store_fixture",
        "load_synthetic_qc_global_input_bundle_from_object_store_fixture",
        "require_synthetic_qc_transport_load",
    )
    allowed_negative_properties = {
        *FALSE_PROPERTY_NAMES,
        "qc_object_store_read_available",
        "qc_object_store_write_available",
    }
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in allowed_negative_properties:
            continue
        assert all(fragment not in node.name for fragment in forbidden_fragments)


def test_receipt_and_fixture_are_frozen_slotted_records():
    _, fixture, receipt = _load()
    assert dataclasses.is_dataclass(fixture)
    assert dataclasses.is_dataclass(receipt)
    with pytest.raises(dataclasses.FrozenInstanceError):
        fixture.transport_index_key = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        receipt.total_object_count = 0
    with pytest.raises(AttributeError):
        receipt.unreviewed_field = True


def test_every_closed_authority_accessor_is_one_literal_false_return():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    expected = {
        "SyntheticObjectStoreEntry": (),
        "SyntheticObjectStoreFixture": (
            "qc_object_store_read_available",
            "qc_object_store_write_available",
        ),
        "SyntheticTransportPartitionBinding": (),
        "SyntheticQcTransportLoad": FALSE_PROPERTY_NAMES,
    }
    expected_public_members = {
        SyntheticObjectStoreEntry: {"key", "payload"},
        SyntheticObjectStoreFixture: {
            "transport_index_key",
            "entries",
            "qc_object_store_read_available",
            "qc_object_store_write_available",
        },
        transport.SyntheticTransportPartitionBinding: {
            "ordinal",
            "role",
            "key",
            "byte_count",
            "row_count",
            "artifact_sha256",
        },
        SyntheticQcTransportLoad: {
            "transport_id",
            "transport_hash",
            "transport_artifact_sha256",
            "transport_index_key",
            "resolved_fixture_keys",
            "bundle",
            "total_object_count",
            "total_byte_count",
            "total_row_count",
            "synthetic_fixture_transport_validated",
            "real_qc_object_store_access_performed",
            "external_bindings",
            "capabilities",
            *FALSE_PROPERTY_NAMES,
        },
    }
    for accepted_class, public_members in expected_public_members.items():
        assert {
            name
            for name in vars(accepted_class)
            if not name.startswith("_")
        } == public_members
    for class_name, property_names in expected.items():
        methods = {
            node.name: node
            for node in classes[class_name].body
            if isinstance(node, ast.FunctionDef)
        }
        assert tuple(methods) == property_names
        for property_name in property_names:
            method = methods[property_name]
            assert len(method.body) == 1
            statement = method.body[0]
            assert isinstance(statement, ast.Return)
            assert isinstance(statement.value, ast.Constant)
            assert statement.value.value is False


def test_transport_index_artifact_and_semantic_identity_reproduce():
    _, _, _, fixture = _fixture()
    payload = fixture.entries[0].payload
    document = json.loads(payload)
    seed = dict(document)
    transport_id = seed.pop("transport_id")
    transport_hash = seed.pop("transport_hash")
    seed["transport_id"] = None
    seed["transport_hash"] = None
    expected = hashlib.sha256(
        transport.TRANSPORT_HASH_DOMAIN.encode("ascii")
        + b"\x00"
        + _canonical(seed)
    ).hexdigest()
    assert transport_hash == expected
    assert transport_id == f"arv2-qc-synthetic-transport-{expected[:16]}"
    candidate, _, receipt = _load()
    assert candidate.candidate_hash == document["run_candidate_binding"]["candidate_hash"]
    assert receipt.transport_artifact_sha256 == hashlib.sha256(payload).hexdigest()
