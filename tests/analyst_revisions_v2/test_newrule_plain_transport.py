"""Pure synthetic conversion; run with native network/artifact/Keychain denial."""
import copy
import dataclasses
import gc
import hashlib
import inspect
import json
import socket
from types import SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_plain_transport as m


def _deny(*_args, **_kwargs):
    raise AssertionError("operational boundary reached by synthetic test")


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    monkeypatch.setattr(m, "_REQUIRE_SOURCE", _deny)
    monkeypatch.setattr(m, "_ITER_SOURCE", _deny)
    monkeypatch.setattr(m.compact, "require_accepted_risk_preliminary_package", _deny)
    monkeypatch.setattr(m.compact, "iter_accepted_risk_preliminary_upload_objects", _deny)
    monkeypatch.setattr(m.compact, "_read_authenticated_package_payloads", _deny)
    monkeypatch.setattr(m.compact, "_iter_authenticated_package_payloads", _deny)
    monkeypatch.setattr(socket, "create_connection", _deny)
    monkeypatch.setattr(socket, "getaddrinfo", _deny)


def source_fixture(*, chunks=None, payload_edit=None, descriptor_edit=None, transport_edit=None):
    """An untrusted synthetic source, never an old package capability."""
    if chunks is None:
        chunks = {
            "session_axis": [[{"session": "2026-10-12"}]],
            "memberships": [[{"security_id": "synthetic-A"}]],
            "contributions": [[{"revision": "1.25"}]],
            "runtime_symbol_bindings": [[{"security_id": "synthetic-A", "figi": "synthetic"}]],
        }
    manifest = {"manifest_id": "synthetic-manifest", "manifest_sha256": "c" * 64}
    payloads = [("evaluator_manifest", 0, 1, "evaluator-manifest.json", m.canonical(manifest) + b"\n")]
    for role, groups in chunks.items():
        for ordinal, rows in enumerate(groups):
            payloads.append((role, ordinal, len(rows), f"{role}-{ordinal:04d}-jsonl.gz",
                             m.compact._gzip_records(rows)))
    pairs = []
    for index, (role, ordinal, count, name, payload) in enumerate(payloads):
        if payload_edit is not None:
            payload = payload_edit(index, payload)
        descriptor = m.compact.PreliminaryUploadObject(
            m.compact.UPLOAD_OBJECT_SCHEMA, role, ordinal, "arv2/preliminary-synthetic/" + name,
            name, len(payload), m.sha(payload), count, "identity" if role == "evaluator_manifest" else "gzip", False)
        if descriptor_edit is not None:
            descriptor = descriptor_edit(index, descriptor)
        pairs.append((descriptor, payload))
    binding_rows = [row for group in chunks.get("runtime_symbol_bindings", []) for row in group]
    record = m.compact._transport_seed(package_id=None, package_sha256=None,
        evaluator_manifest=manifest, objects=[item for item, _ in pairs],
        source_disposition_sha256="b" * 64, runtime_symbol_binding_count=len(binding_rows),
        runtime_symbol_bindings_sha256=m.compact._stream_hash(binding_rows), contribution_census={"accepted": 1})
    if transport_edit is not None:
        transport_edit(record)
    digest = m.sha(m.canonical(record))
    package_id = "arv2-preliminary-qc-package-" + digest[:24]
    record.update(package_id=package_id, package_sha256=digest)
    raw = m.canonical(record) + b"\n"
    activation = m.compact.PreliminaryUploadObject(m.compact.UPLOAD_OBJECT_SCHEMA, "activation_manifest", 0,
        "arv2/preliminary-synthetic/transport-manifest.json", "transport-manifest.json",
        len(raw), m.sha(raw), 1, "identity", True)
    pairs.append((activation, raw))
    package = NS(package_sha256=digest, package_id=package_id, source_disposition_sha256="b" * 64,
        upload_objects=tuple(item for item, _ in pairs), total_upload_byte_count=sum(len(raw) for _, raw in pairs))
    return NS(package=package, pairs=tuple(pairs), record=record, chunks=chunks)


def converted(source=None):
    source = source or source_fixture()
    return m._convert_payloads(source.package, source.pairs)


def authorized(monkeypatch, source=None, *, final_fail=False):
    """Only the synthetic auth seam is replaced, never operationally read."""
    source = source or source_fixture()
    events = []

    def require(package):
        assert package is source.package
        events.append("require")
        if final_fail and events.count("require") == 2:
            raise m.PlainTransportError("synthetic_final_refusal")
        return package

    def iterate(package):
        assert package is source.package
        events.append("iterate")
        yield from source.pairs
        events.append("exhausted")

    monkeypatch.setattr(m, "_REQUIRE_SOURCE", require)
    monkeypatch.setattr(m, "_ITER_SOURCE", iterate)
    return source, events


def build(source):
    return m.build_plain_transport(source.package, expected_package_sha256=source.package.package_sha256,
        expected_lineage_sha256=source.package.source_disposition_sha256)


def test_deterministic_plain_streams_and_distinct_transport():
    source = source_fixture()
    value = converted(source)
    assert value == converted(source)
    assert value.package_sha256 != source.package.package_sha256
    assert value.source_package_sha256 == source.package.package_sha256
    assert value.source_lineage_sha256 == "b" * 64
    assert len(value.upload_objects) == 6
    assert tuple(row.role for row in value.upload_objects) == (*m.ROLES, "activation_manifest")
    for old, new in zip(source.pairs[:-1], value.upload_objects[:-1]):
        descriptor, payload = old
        assert new.compression == "identity"
        assert new.byte_count == len(new.payload)
        assert new.content_sha256 == m.sha(new.payload)
        assert (new.role, new.ordinal, new.record_count) == (descriptor.role, descriptor.ordinal, descriptor.record_count)
        if new.role == "evaluator_manifest":
            assert new.payload == payload
        else:
            rows, count = m.compact._load_canonical_gzip_records(payload, descriptor)
            assert new.payload == b"".join(m.canonical(row) + b"\n" for row in rows)
            assert count == len(new.payload)
            assert new.relative_path.endswith(".jsonl")
    assert value.total_upload_byte_count == sum(row.byte_count for row in value.upload_objects)


def test_parent_proof_and_content_derived_inventory():
    source = source_fixture()
    value = converted(source)
    record = json.loads(value.record_bytes)
    parent = record["parent_proof"]
    assert set(parent) == {"schema", "source_package_sha256", "source_lineage_sha256",
        "source_activation_sha256", "source_activation_byte_count", "source_inventory_sha256", "streams"}
    assert parent["schema"] == m.PROOF_SCHEMA
    assert parent["source_activation_sha256"] == source.pairs[-1][0].content_sha256
    assert parent["source_activation_byte_count"] == source.pairs[-1][0].byte_count
    assert parent["source_inventory_sha256"] == m.sha(m.canonical([item.to_record() for item, _ in source.pairs]))
    assert value.parent_proof_sha256 == record["parent_proof_sha256"] == m.sha(m.canonical(parent))
    prefix = m.KEY_PREFIX + "/" + value.parent_proof_sha256[:24] + "/"
    for stream, item in zip(parent["streams"], value.upload_objects):
        assert stream == {key: item.to_record()[key] for key in stream}
        assert item.object_store_key == prefix + item.relative_path
    assert record["objects"] == [item.to_record() for item in value.upload_objects[:-1]]
    assert record["claims"] == source.record["claims"]
    assert record["runtime"] == source.record["runtime"]
    assert record["benchmark"] == source.record["benchmark"]
    assert record["runtime_symbol_bindings_sha256"] == source.record["runtime_symbol_bindings_sha256"]
    seed = dict(record, package_id=None, package_sha256=None)
    assert m.sha(m.canonical(seed)) == value.package_sha256
    assert value.package_id == "arv2-newrule-plain-package-" + value.package_sha256[:24]
    assert value.activation_manifest_key == prefix + "transport-manifest.json"
    assert value.activation_manifest_sha256 == m.sha(value.record_bytes)
    assert value.activation_manifest_byte_count == len(value.record_bytes)
    assert value.upload_objects[-1].payload == value.record_bytes
    assert value.upload_objects[-1].activation_manifest is True


def test_multiple_shards_preserve_all_order_counts_and_binding_digest():
    source = source_fixture()
    chunks = copy.deepcopy(source.chunks)
    chunks["contributions"] = [[{"i": 1}], [{"i": 2}, {"i": 3}]]
    chunks["runtime_symbol_bindings"] = [[{"id": "one"}], [{"id": "two"}]]
    source = source_fixture(chunks=chunks)
    value = converted(source)
    selected = [item for item in value.upload_objects if item.role == "contributions"]
    assert [(item.ordinal, item.record_count, item.payload) for item in selected] == [
        (0, 1, b'{"i":1}\n'), (1, 2, b'{"i":2}\n{"i":3}\n')]
    assert len(value.upload_objects) == 8


def test_builder_authenticates_before_and_after_exhaustion(monkeypatch):
    source, events = authorized(monkeypatch)
    value = build(source)
    assert events == ["require", "iterate", "exhausted", "require"]
    assert m.require_plain_transport(value) is value
    assert value.to_record()["package_sha256"] == value.package_sha256
    assert tuple(m.iter_plain_upload_objects(value)) == tuple((row, row.payload) for row in value.upload_objects)
    assert events == ["require", "iterate", "exhausted", "require"]  # no hidden private reload


def test_builder_rejects_final_source_drift_before_mint(monkeypatch):
    source, events = authorized(monkeypatch, final_fail=True)
    size = len(m._AUTHORITIES)
    with pytest.raises(m.PlainTransportError, match="synthetic_final_refusal"):
        build(source)
    assert events == ["require", "iterate", "exhausted", "require"]
    assert len(m._AUTHORITIES) <= size


@pytest.mark.parametrize("field", ["expected_package_sha256", "expected_lineage_sha256"])
def test_external_pin_mismatch_never_iterates(monkeypatch, field):
    source, events = authorized(monkeypatch)
    kwargs = dict(expected_package_sha256=source.package.package_sha256, expected_lineage_sha256="b" * 64)
    kwargs[field] = "e" * 64
    with pytest.raises(m.PlainTransportError, match="parent_pin"):
        m.build_plain_transport(source.package, **kwargs)
    assert events == ["require"]


@pytest.mark.parametrize("value", [None, True, 1, b"a" * 64, "A" * 64, "f" * 63, "g" * 64])
def test_invalid_external_pin_never_authenticates(value):
    with pytest.raises(m.PlainTransportError, match="hash"):
        m.build_plain_transport(object(), expected_package_sha256=value, expected_lineage_sha256="b" * 64)


def test_builder_does_not_trust_more_than_bounded_iterator(monkeypatch):
    source, _ = authorized(monkeypatch)
    count = []
    monkeypatch.setattr(m, "MAX_OBJECTS", 6)
    def infinite(_):
        for i in range(100):
            count.append(i)
            yield source.pairs[0]
    monkeypatch.setattr(m, "_ITER_SOURCE", infinite)
    with pytest.raises(m.PlainTransportError, match="inventory"):
        build(source)
    assert len(count) == 7


def test_iterator_failure_does_not_mint(monkeypatch):
    source, _ = authorized(monkeypatch)
    def failed(_):
        yield from source.pairs
        raise m.PlainTransportError("synthetic_exhaustion_refusal")
    monkeypatch.setattr(m, "_ITER_SOURCE", failed)
    with pytest.raises(m.PlainTransportError, match="synthetic_exhaustion_refusal"):
        build(source)


def test_pure_converter_never_mints_capability():
    value = converted()
    for operation in (m.require_plain_transport, lambda value: value.to_record(), lambda value: tuple(m.iter_plain_upload_objects(value))):
        with pytest.raises(m.PlainTransportError, match="authority"):
            operation(value)


def test_no_payload_bytes_in_default_repr(monkeypatch):
    source, _ = authorized(monkeypatch)
    value = build(source)
    assert "synthetic-A" not in repr(value)
    assert "synthetic-A" not in repr(value.upload_objects[2])
    assert "payload=" not in repr(value.upload_objects[2])
    assert "record_bytes=" not in repr(value)


def test_copy_and_replace_are_not_capabilities(monkeypatch):
    source, _ = authorized(monkeypatch)
    value = build(source)
    for other in (copy.copy(value), copy.deepcopy(value), dataclasses.replace(value)):
        with pytest.raises(m.PlainTransportError, match="authority"):
            m.require_plain_transport(other)


@pytest.mark.parametrize("field,value", [("package_id", "changed"), ("package_sha256", "a" * 64),
    ("source_package_sha256", "e" * 64), ("source_lineage_sha256", "e" * 64),
    ("parent_proof_sha256", "e" * 64), ("record_bytes", b"{}\n"),
    ("total_upload_byte_count", 1), ("upload_objects", ())])
def test_frozen_object_bypass_is_detected(monkeypatch, field, value):
    source, _ = authorized(monkeypatch)
    capability = build(source)
    object.__setattr__(capability, field, value)
    with pytest.raises(m.PlainTransportError, match="authority"):
        m.require_plain_transport(capability)


def test_mutated_descriptor_payload_is_detected_between_yields(monkeypatch):
    source, _ = authorized(monkeypatch)
    value = build(source)
    iterator = m.iter_plain_upload_objects(value)
    next(iterator)
    object.__setattr__(value.upload_objects[1], "payload", b"private-looking sentinel")
    with pytest.raises(m.PlainTransportError, match="authority"):
        next(iterator)


@pytest.mark.parametrize("field", ["record_bytes", "payload", "package_id"])
def test_equal_but_mutable_or_subclass_value_cannot_pass_authority(monkeypatch, field):
    source, _ = authorized(monkeypatch)
    value = build(source)
    if field == "payload":
        object.__setattr__(value.upload_objects[0], field, bytearray(value.upload_objects[0].payload))
    elif field == "record_bytes":
        object.__setattr__(value, field, bytearray(value.record_bytes))
    else:
        class Str(str):
            pass
        object.__setattr__(value, field, Str(value.package_id))
    with pytest.raises(m.PlainTransportError, match="authority"):
        m.require_plain_transport(value)


def test_wrong_process_authority_refuses(monkeypatch):
    source, _ = authorized(monkeypatch)
    value = build(source)
    real_pid = m.os.getpid()
    monkeypatch.setattr(m.os, "getpid", lambda: real_pid + 1)
    with pytest.raises(m.PlainTransportError, match="authority"):
        m.require_plain_transport(value)


def test_weak_authority_is_reclaimed(monkeypatch):
    source, _ = authorized(monkeypatch)
    value = build(source)
    identity = id(value)
    assert identity in m._AUTHORITIES
    del value
    gc.collect()
    assert identity not in m._AUTHORITIES


@pytest.mark.parametrize("value", [None, [], {}, (), b"data", (1,)])
def test_invalid_inventory_shape(value):
    source = source_fixture()
    with pytest.raises(m.PlainTransportError, match="inventory"):
        m._convert_payloads(source.package, value)


def test_source_inventory_and_payload_mismatch():
    source = source_fixture()
    changed = list(source.pairs)
    changed[2] = (changed[2][0], changed[2][1] + b"x")
    source.package.total_upload_byte_count += 1
    with pytest.raises(m.PlainTransportError, match="source_payload"):
        m._convert_payloads(source.package, tuple(changed))
    source = source_fixture()
    source.package.upload_objects = source.package.upload_objects[::-1]
    with pytest.raises(m.PlainTransportError, match="source_inventory"):
        converted(source)


def test_source_same_size_replacement_refuses_content_hash():
    source = source_fixture()
    changed = list(source.pairs)
    descriptor, payload = changed[2]
    changed[2] = descriptor, payload[:-1] + bytes([payload[-1] ^ 1])
    with pytest.raises(m.PlainTransportError, match="source_payload"):
        m._convert_payloads(source.package, tuple(changed))


@pytest.mark.parametrize("field,value", [("package_sha256", "a" * 64), ("package_id", "wrong"),
    ("source_disposition_sha256", "a" * 64), ("total_upload_byte_count", 1)])
def test_source_metadata_mismatch(field, value):
    source = source_fixture()
    setattr(source.package, field, value)
    with pytest.raises(m.PlainTransportError):
        converted(source)


@pytest.mark.parametrize("field,value", [("schema", "changed"), ("compression", "identity"),
    ("ordinal", True), ("ordinal", -1), ("record_count", True), ("record_count", 0),
    ("activation_manifest", 1), ("relative_path", "../x-jsonl.gz"), ("byte_count", True),
    ("content_sha256", "G" * 64)])
def test_source_descriptor_malformed(field, value):
    source = source_fixture(descriptor_edit=lambda i, row: dataclasses.replace(row, **{field: value}) if i == 2 else row)
    with pytest.raises((m.PlainTransportError, m.compact.AcceptedRiskPreliminaryPackageError)):
        converted(source)


@pytest.mark.parametrize("transform", [lambda raw: b"not compressed", lambda raw: raw + b"tail",
    lambda raw: raw[:-1], lambda raw: raw[:10] + b"broken" + raw[10:]])
def test_invalid_compressed_source_refuses(transform):
    source = source_fixture(payload_edit=lambda i, raw: transform(raw) if i == 2 else raw)
    with pytest.raises(m.PlainTransportError, match="source_rows"):
        converted(source)


def test_old_row_count_mismatch_refuses():
    source = source_fixture(descriptor_edit=lambda i, row: dataclasses.replace(row, record_count=2) if i == 2 else row)
    with pytest.raises(m.PlainTransportError, match="source_rows"):
        converted(source)


@pytest.mark.parametrize("edit", [lambda value: value.update(extra="not part of old contract"),
    lambda value: value["claims"].update(formal=True), lambda value: value["claims"].update(orders=True),
    lambda value: value["runtime"].update(history="different"),
    lambda value: value["benchmark"].update(ticker="OTHER")])
def test_source_contract_cannot_be_silently_changed(edit):
    with pytest.raises(m.PlainTransportError, match="source_contract"):
        converted(source_fixture(transport_edit=edit))


@pytest.mark.parametrize("field,value", [("runtime_symbol_binding_count", True), ("runtime_symbol_binding_count", 0),
    ("runtime_symbol_binding_count", 100_001), ("runtime_symbol_bindings_sha256", "x" * 64),
    ("contribution_census", {"accepted": True}), ("contribution_census", {"accepted": -1})])
def test_source_binding_and_census_types(field, value):
    with pytest.raises(m.PlainTransportError):
        converted(source_fixture(transport_edit=lambda record: record.update(**{field: value})))


@pytest.mark.parametrize("field,value", [("runtime_symbol_binding_count", 2), ("runtime_symbol_bindings_sha256", "a" * 64)])
def test_runtime_binding_stream_is_recomputed(field, value):
    with pytest.raises(m.PlainTransportError, match="source_binding_stream"):
        converted(source_fixture(transport_edit=lambda record: record.update(**{field: value})))


def test_missing_required_role_refuses():
    source = source_fixture()
    chunks = dict(source.chunks)
    del chunks["memberships"]
    chunks["contributions"] = [[{"i": 1}], [{"i": 2}]]
    with pytest.raises(m.PlainTransportError, match="role_order"):
        converted(source_fixture(chunks=chunks))


def test_reordered_role_refuses():
    source = source_fixture()
    chunks = {key: source.chunks[key] for key in reversed(source.chunks)}
    with pytest.raises(m.PlainTransportError, match="role_order"):
        converted(source_fixture(chunks=chunks))


def test_noncontiguous_ordinal_refuses():
    source = source_fixture(descriptor_edit=lambda i, row: dataclasses.replace(row, ordinal=1) if i == 2 else row)
    with pytest.raises(m.PlainTransportError, match="role_order"):
        converted(source)


def test_duplicate_source_path_refuses():
    source = source_fixture()
    original = source.pairs[1][0]
    source = source_fixture(descriptor_edit=lambda i, row: dataclasses.replace(row,
        object_store_key=original.object_store_key, relative_path=original.relative_path) if i == 2 else row)
    with pytest.raises(m.PlainTransportError, match="source_duplicate"):
        converted(source)


def test_plain_shard_bound_refuses_without_resharding(monkeypatch):
    source = source_fixture()
    monkeypatch.setattr(m, "MAX_ROW_SHARD_BYTES", 1)
    with pytest.raises(m.PlainTransportError, match="plain_rows"):
        converted(source)


def test_total_budget_includes_activation(monkeypatch):
    source = source_fixture()
    value = converted(source)
    assert value.total_upload_byte_count > source.package.total_upload_byte_count
    monkeypatch.setattr(m, "MAX_TOTAL_BYTES", value.total_upload_byte_count - 1)
    with pytest.raises(m.PlainTransportError, match="total_bound"):
        converted(source)


def test_exact_total_and_shard_bounds_accept(monkeypatch):
    source = source_fixture()
    value = converted(source)
    monkeypatch.setattr(m, "MAX_TOTAL_BYTES", value.total_upload_byte_count)
    monkeypatch.setattr(m, "MAX_ROW_SHARD_BYTES", max(row.byte_count for row in value.upload_objects[1:-1]))
    assert converted(source) == value


def test_new_activation_object_bound_refuses(monkeypatch):
    source = source_fixture()
    value = converted(source)
    assert value.activation_manifest_byte_count > len(source.pairs[-1][1])
    monkeypatch.setattr(m, "MAX_OBJECT_BYTES", value.activation_manifest_byte_count - 1)
    with pytest.raises(m.PlainTransportError, match="activation_bound"):
        converted(source)


def test_maximum_inventory_is_explicit_and_preserved(monkeypatch):
    source = source_fixture()
    monkeypatch.setattr(m, "MAX_OBJECTS", 5)
    with pytest.raises(m.PlainTransportError, match="inventory"):
        converted(source)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":1}\n', b'{ "a":1}\n', b'{"a":1}',
    b'{"a":NaN}\n', b'{"a":Infinity}\n', b'[]\n', b'{}\n{}\n', b'\xff'])
def test_strict_json_rejects_noncanonical_or_nondict(raw):
    with pytest.raises(m.PlainTransportError):
        m._json(raw)


@pytest.mark.parametrize("value", [(1,), {1: "x"}, b"data", object(), {1}, float("nan"), float("inf")])
def test_canonical_rejects_unsupported_values(value):
    with pytest.raises(m.PlainTransportError):
        m.canonical(value)


def test_canonical_preserves_finite_floats_and_ascii():
    value = {"unicode": "é", "finite": 0.25, "negative": -0.0, "boolean": True, "none": None}
    assert m.canonical(value) == m.compact._canonical(value)


def test_cyclic_or_too_deep_values_are_bounded():
    value = []
    value.append(value)
    with pytest.raises(m.PlainTransportError, match="json_bound"):
        m.canonical(value)


def test_module_has_no_operational_entrypoint_or_writer():
    source = inspect.getsource(m)
    for forbidden in ("requests.", "subprocess.", "open(", "write_bytes(", "write_text(", "backtests/", "security "):
        assert forbidden not in source
    assert "__main__" not in source
    assert m.MAX_OBJECT_BYTES == 32 * 1024 * 1024
    assert m.MAX_TOTAL_BYTES == 44 * 1024 * 1024
    assert m.MAX_ROW_SHARD_BYTES == 16 * 1024 * 1024
    assert m.MAX_OBJECTS == 96
