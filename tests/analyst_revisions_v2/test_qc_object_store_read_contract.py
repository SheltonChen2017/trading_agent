"""Value-only QC Object Store read-plan contract for ARV2-4F-B4."""
from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path
import pickle
import subprocess
import sys

import pytest

from research.analyst_revisions_v2.import_firewall import (
    DEFAULT_ALLOWED_STDLIB_ROOTS,
    DEFAULT_FORBIDDEN_IMPORT_PREFIXES,
)
from research.analyst_revisions_v2_qc import object_store_read_contract as read_contract
from research.analyst_revisions_v2_qc.object_store_read_contract import (
    CAPABILITIES,
    CONTAINS_KEY_OPERATION,
    EXPECTED_EVENT_COUNT,
    EXTERNAL_BINDINGS,
    QcObjectStoreReadContractError,
    READ_BYTES_OPERATION,
    SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID,
    SCHEMA_SHA256,
    SYNTHETIC_PROJECT_NAMESPACE,
    SyntheticObjectStoreReadDescriptor,
    SyntheticObjectStoreReadEvent,
    SyntheticQcObjectStoreReadPlan,
    SyntheticQcObjectStoreReadReceipt,
    SyntheticQcObjectStoreReadTranscript,
    build_synthetic_qc_object_store_read_plan,
    build_synthetic_qc_object_store_read_transcript,
    load_synthetic_qc_global_input_bundle_from_object_store_transcript,
    render_qc_object_store_read_contract_schema_bytes,
    require_synthetic_qc_object_store_read_plan,
    require_synthetic_qc_object_store_read_receipt,
    require_synthetic_qc_object_store_read_transcript,
)
from research.analyst_revisions_v2_qc.run_contract import (
    canonical_lf_python_source_bytes,
)
from research.analyst_revisions_v2_qc.synthetic_input_transport import (
    EXPECTED_OBJECT_COUNT,
    FALSE_PROPERTY_NAMES,
    SyntheticObjectStoreFixture,
    build_synthetic_qc_object_store_fixture,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import (
    _active_rows,
    _wire_inputs,
)
from tests.analyst_revisions_v2.test_qc_synthetic_input_transport import (
    _fixture as _b3_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "research/analyst_revisions_v2_qc"
MODULE = PACKAGE / "object_store_read_contract.py"
B3_MODULE = PACKAGE / "synthetic_input_transport.py"


def _plan(*, max_size: int | None = None, max_files: int = 1000):
    candidate, _, _, fixture = _b3_fixture()
    total = sum(len(item.payload) for item in fixture.entries)
    return candidate, fixture, build_synthetic_qc_object_store_read_plan(
        run_candidate=candidate,
        object_store=fixture,
        transport_index_key=fixture.transport_index_key,
        synthetic_max_size=total if max_size is None else max_size,
        synthetic_max_files=max_files,
    )


def _loaded():
    candidate, fixture, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    receipt = load_synthetic_qc_global_input_bundle_from_object_store_transcript(
        plan=plan,
        transcript=transcript,
    )
    return candidate, fixture, plan, transcript, receipt


def _replace_event(
    transcript: SyntheticQcObjectStoreReadTranscript,
    event_index: int,
    **changes: object,
) -> SyntheticQcObjectStoreReadTranscript:
    events = list(transcript.events)
    events[event_index] = dataclasses.replace(events[event_index], **changes)
    return dataclasses.replace(transcript, events=tuple(events))


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


def test_schema_and_reviewed_b3_source_identities_are_exact():
    payload = render_qc_object_store_read_contract_schema_bytes()
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert hashlib.sha256(payload).hexdigest() == SCHEMA_ARTIFACT_SHA256
    assert SCHEMA_ID == f"arv2-qc-object-store-read-contract-{SCHEMA_SHA256[:16]}"
    assert SCHEMA_ID == "arv2-qc-object-store-read-contract-5dcb6cffb8f9688b"
    assert SCHEMA_SHA256 == (
        "5dcb6cffb8f9688b1a63a0ea452fd7f4c3e706df7941691ede58c95e0f055dd2"
    )
    assert SCHEMA_ARTIFACT_SHA256 == (
        "95c3242405dddaaec40af01113a6823235fa74fcf405ab7b30ab5c6a45a8e987"
    )
    assert read_contract.B3_SOURCE_BYTE_COUNT == 65_144
    b3_source = canonical_lf_python_source_bytes(B3_MODULE.read_bytes())
    assert len(b3_source) == read_contract.B3_SOURCE_BYTE_COUNT
    assert hashlib.sha256(b3_source).hexdigest() == read_contract.B3_SOURCE_SHA256
    document = json.loads(payload)
    assert document["parent"] == {
        "schema_id": read_contract.B3_SCHEMA_ID,
        "schema_sha256": read_contract.B3_SCHEMA_SHA256,
        "schema_artifact_sha256": read_contract.B3_SCHEMA_ARTIFACT_SHA256,
        "source_sha256": read_contract.B3_SOURCE_SHA256,
        "source_byte_count": read_contract.B3_SOURCE_BYTE_COUNT,
        "parent_source_sha256": read_contract.B3_PARENT_SOURCE_SHA256,
        "parent_source_byte_count": read_contract.B3_PARENT_SOURCE_BYTE_COUNT,
    }


def test_schema_truth_and_authority_are_closed():
    document = json.loads(render_qc_object_store_read_contract_schema_bytes())
    assert document["namespace"] == {
        "synthetic_project_namespace": "synthetic-project-id-not-real",
        "separator": "/",
        "applied_exactly_once": True,
        "real_project_id": None,
    }
    assert document["inventory"] == {
        "object_count": 9,
        "event_count": 18,
        "event_order": ["contains_key", "read_bytes"],
    }
    assert document["truth"] == {
        "synthetic_value_plan": True,
        "synthetic_fixture_transcript": True,
        "real_object_store_access": False,
        "callbacks": False,
        "qc_imports": False,
    }
    assert all(value is None for value in document["external_bindings"].values())
    assert all(value is False for value in document["capabilities"].values())


def test_plan_is_derived_from_the_authenticated_b3_fixture_only():
    _, fixture, plan = _plan()
    assert plan.project_namespace == SYNTHETIC_PROJECT_NAMESPACE
    assert plan.total_object_count == EXPECTED_OBJECT_COUNT == 9
    assert plan.total_byte_count == sum(len(item.payload) for item in fixture.entries)
    assert tuple(item.logical_key for item in plan.objects) == tuple(
        item.key for item in fixture.entries
    )
    assert tuple(item.byte_count for item in plan.objects) == tuple(
        len(item.payload) for item in fixture.entries
    )
    assert tuple(item.artifact_sha256 for item in plan.objects) == tuple(
        hashlib.sha256(item.payload).hexdigest() for item in fixture.entries
    )
    assert tuple(item.ordinal for item in plan.objects) == tuple(range(1, 10))
    assert all(
        item.object_store_key == f"{SYNTHETIC_PROJECT_NAMESPACE}/{item.logical_key}"
        for item in plan.objects
    )
    assert all(
        not item.logical_key.startswith(f"{SYNTHETIC_PROJECT_NAMESPACE}/")
        for item in plan.objects
    )
    assert require_synthetic_qc_object_store_read_plan(plan) is plan


@pytest.mark.parametrize("mode", ("missing", "reordered", "duplicate"))
def test_plan_refuses_incomplete_or_ambiguous_b3_fixture(mode: str):
    candidate, _, _, fixture = _b3_fixture()
    entries = list(fixture.entries)
    if mode == "missing":
        entries.pop()
    elif mode == "reordered":
        entries[1], entries[2] = entries[2], entries[1]
    else:
        entries[-1] = entries[-2]
    changed = SyntheticObjectStoreFixture(
        transport_index_key=fixture.transport_index_key,
        entries=tuple(entries),
    )
    with pytest.raises(QcObjectStoreReadContractError, match="not authenticated"):
        build_synthetic_qc_object_store_read_plan(
            run_candidate=candidate,
            object_store=changed,
            transport_index_key=fixture.transport_index_key,
            synthetic_max_size=sum(len(item.payload) for item in fixture.entries),
            synthetic_max_files=1000,
        )


def test_plan_refuses_a_cross_candidate_fixture_and_retained_candidate_swap():
    candidate, fixture, plan = _plan()
    other_candidate, manifest, partitions = _wire_inputs(
        _active_rows(), partition_suffix="-other-candidate"
    )
    other_fixture = build_synthetic_qc_object_store_fixture(
        run_candidate=other_candidate,
        manifest_bytes=manifest,
        partition_payloads=partitions,
    )
    with pytest.raises(QcObjectStoreReadContractError, match="not authenticated"):
        build_synthetic_qc_object_store_read_plan(
            run_candidate=candidate,
            object_store=other_fixture,
            transport_index_key=other_fixture.transport_index_key,
            synthetic_max_size=sum(len(item.payload) for item in other_fixture.entries),
            synthetic_max_files=1000,
        )
    forged = dataclasses.replace(plan, _run_candidate=other_candidate)
    with pytest.raises(QcObjectStoreReadContractError, match="backing state"):
        require_synthetic_qc_object_store_read_plan(forged)
    assert require_synthetic_qc_object_store_read_plan(plan) is plan
    assert candidate is not other_candidate
    assert fixture.transport_index_key != other_fixture.transport_index_key


@pytest.mark.parametrize("value", (0, -1, True, False, 1.0, "9", None))
@pytest.mark.parametrize("field", ("synthetic_max_size", "synthetic_max_files"))
def test_synthetic_quota_inputs_must_be_exact_positive_integers(field: str, value):
    candidate, _, _, fixture = _b3_fixture()
    kwargs = {
        "run_candidate": candidate,
        "object_store": fixture,
        "transport_index_key": fixture.transport_index_key,
        "synthetic_max_size": sum(len(item.payload) for item in fixture.entries),
        "synthetic_max_files": 9,
    }
    kwargs[field] = value
    with pytest.raises(QcObjectStoreReadContractError, match="exact positive int"):
        build_synthetic_qc_object_store_read_plan(**kwargs)


def test_synthetic_quota_exact_boundaries_pass_and_one_below_refuses():
    _, fixture, plan = _plan(max_files=9)
    assert plan.synthetic_max_size == plan.total_byte_count
    assert plan.synthetic_max_files == plan.total_object_count
    candidate = plan._run_candidate
    with pytest.raises(QcObjectStoreReadContractError, match="max_size is below"):
        build_synthetic_qc_object_store_read_plan(
            run_candidate=candidate,
            object_store=fixture,
            transport_index_key=fixture.transport_index_key,
            synthetic_max_size=plan.total_byte_count - 1,
            synthetic_max_files=9,
        )
    with pytest.raises(QcObjectStoreReadContractError, match="max_files is below"):
        build_synthetic_qc_object_store_read_plan(
            run_candidate=candidate,
            object_store=fixture,
            transport_index_key=fixture.transport_index_key,
            synthetic_max_size=plan.total_byte_count,
            synthetic_max_files=8,
        )


def test_transcript_has_exactly_18_alternating_value_events():
    _, fixture, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    assert len(transcript.events) == EXPECTED_EVENT_COUNT == 18
    for index, (descriptor, entry) in enumerate(
        zip(plan.objects, fixture.entries, strict=True)
    ):
        contains, read = transcript.events[index * 2 : index * 2 + 2]
        assert contains == SyntheticObjectStoreReadEvent(
            ordinal=index * 2 + 1,
            operation=CONTAINS_KEY_OPERATION,
            object_store_key=descriptor.object_store_key,
            found=True,
            payload=None,
        )
        assert read == SyntheticObjectStoreReadEvent(
            ordinal=index * 2 + 2,
            operation=READ_BYTES_OPERATION,
            object_store_key=descriptor.object_store_key,
            found=None,
            payload=entry.payload,
        )
    assert require_synthetic_qc_object_store_read_transcript(
        transcript, plan=plan
    ) is transcript


@pytest.mark.parametrize("mode", ("missing", "reordered", "duplicate"))
def test_transcript_refuses_missing_reordered_or_duplicate_events(mode: str):
    _, _, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    events = list(transcript.events)
    if mode == "missing":
        events.pop()
    elif mode == "reordered":
        events[0], events[1] = events[1], events[0]
    else:
        events[-1] = events[-2]
    changed = dataclasses.replace(transcript, events=tuple(events))
    with pytest.raises(QcObjectStoreReadContractError, match="event census|alternate"):
        require_synthetic_qc_object_store_read_transcript(changed, plan=plan)


@pytest.mark.parametrize(
    ("event_ordinal", "changes"),
    (
        (0, {"ordinal": 2}),
        (0, {"operation": READ_BYTES_OPERATION}),
        (0, {"object_store_key": "synthetic-project-id-not-real/wrong"}),
        (0, {"found": False}),
        (0, {"found": 1}),
        (0, {"payload": b"unexpected"}),
        (1, {"ordinal": 1}),
        (1, {"operation": CONTAINS_KEY_OPERATION}),
        (1, {"object_store_key": "synthetic-project-id-not-real/wrong"}),
        (1, {"found": True}),
        (1, {"payload": None}),
        (1, {"payload": bytearray(b"not-bytes")}),
    ),
)
def test_each_event_shape_guard_is_load_bearing(event_ordinal: int, changes: dict):
    _, _, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    changed = _replace_event(transcript, event_ordinal, **changes)
    with pytest.raises(
        QcObjectStoreReadContractError,
        match="alternate|topology changed",
    ):
        require_synthetic_qc_object_store_read_transcript(changed, plan=plan)


def test_payload_length_hash_and_bytes_are_checked_before_final_b3_delegation():
    _, _, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    corruptions = (
        transcript.events[1].payload + b"x",
        b"x" * len(transcript.events[1].payload),
        transcript.events[1].payload[:-1],
    )
    for payload in corruptions:
        changed = _replace_event(transcript, 1, payload=payload)
        with pytest.raises(QcObjectStoreReadContractError, match="payload"):
            load_synthetic_qc_global_input_bundle_from_object_store_transcript(
                plan=plan, transcript=changed
            )

    # The authenticated bytes must be validated before the reconstructed
    # fixture crosses into the B3 decoder.
    function = next(
        node
        for node in ast.parse(MODULE.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
        and node.name
        == "load_synthetic_qc_global_input_bundle_from_object_store_transcript"
    )
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
    validation_line = min(
        node.lineno
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "_validate_transcript_events"
    )
    delegation_line = min(
        node.lineno
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id
        == "load_synthetic_qc_global_input_bundle_from_object_store_fixture"
    )
    assert validation_line < delegation_line


def test_successful_load_delegates_to_b3_and_reauthenticates_both_receipts():
    _, _, plan, transcript, receipt = _loaded()
    assert receipt.plan_id == plan.plan_id
    assert receipt.plan_hash == plan.plan_hash
    assert receipt.transcript_id == transcript.transcript_id
    assert receipt.transcript_hash == transcript.transcript_hash
    assert receipt.object_store_keys == tuple(
        item.object_store_key for item in plan.objects
    )
    assert receipt.transport_load.transport_id == plan.transport_id
    assert receipt.transport_load.transport_hash == plan.transport_hash
    assert receipt.transport_load.transport_artifact_sha256 == (
        plan.transport_artifact_sha256
    )
    assert require_synthetic_qc_object_store_read_receipt(receipt) is receipt


def test_cross_plan_and_cross_candidate_transcripts_are_refused():
    _, _, first = _plan()
    first_transcript = build_synthetic_qc_object_store_read_transcript(plan=first)
    _, _, second = _plan(max_size=first.total_byte_count + 1)
    second_transcript = build_synthetic_qc_object_store_read_transcript(plan=second)
    with pytest.raises(QcObjectStoreReadContractError, match="contract changed"):
        require_synthetic_qc_object_store_read_transcript(
            second_transcript, plan=first
        )

    other_candidate, manifest, partitions = _wire_inputs(
        _active_rows(), partition_suffix="-cross-transcript"
    )
    other_fixture = build_synthetic_qc_object_store_fixture(
        run_candidate=other_candidate,
        manifest_bytes=manifest,
        partition_payloads=partitions,
    )
    other_plan = build_synthetic_qc_object_store_read_plan(
        run_candidate=other_candidate,
        object_store=other_fixture,
        transport_index_key=other_fixture.transport_index_key,
        synthetic_max_size=sum(len(item.payload) for item in other_fixture.entries),
        synthetic_max_files=9,
    )
    other_transcript = build_synthetic_qc_object_store_read_transcript(plan=other_plan)
    with pytest.raises(QcObjectStoreReadContractError, match="contract changed"):
        require_synthetic_qc_object_store_read_transcript(
            other_transcript, plan=first
        )
    assert first_transcript.plan_hash != other_transcript.plan_hash


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("project_namespace", "real-project", "contract changed"),
        ("synthetic_quota_observation", False, "contract changed"),
        ("real_account_quota_authenticated", True, "contract changed"),
        ("real_qc_object_store_access_performed", True, "contract changed"),
        ("total_object_count", 8, "contract changed"),
        ("plan_hash", "0" * 64, "changed after construction"),
        (
            "external_bindings",
            (("bound", None),),
            "contract changed|topology changed",
        ),
        (
            "capabilities",
            (("qc_object_store_read", True),),
            "contract changed|topology changed",
        ),
    ),
)
def test_retained_plan_forgery_is_refused(field: str, value, message: str):
    _, _, plan = _plan()
    forged = dataclasses.replace(plan, **{field: value})
    with pytest.raises(QcObjectStoreReadContractError, match=message):
        require_synthetic_qc_object_store_read_plan(forged)


def test_retained_descriptor_reorder_duplicate_and_namespace_forgery_refuse():
    _, _, plan = _plan()
    mutations = (
        (plan.objects[1], plan.objects[0], *plan.objects[2:]),
        (*plan.objects[:-1], plan.objects[-2]),
        (
            dataclasses.replace(
                plan.objects[0],
                object_store_key=f"{SYNTHETIC_PROJECT_NAMESPACE}/wrong",
            ),
            *plan.objects[1:],
        ),
    )
    for objects in mutations:
        forged = dataclasses.replace(plan, objects=tuple(objects))
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_plan(forged)


def _hostile_probe():
    callbacks: list[str] = []

    class Hostile:
        def _trip(self, name: str):
            callbacks.append(name)
            raise AssertionError(f"hostile callback executed: {name}")

        def __eq__(self, _other):
            return self._trip("__eq__")

        def __ne__(self, _other):
            return self._trip("__ne__")

        def __lt__(self, _other):
            return self._trip("__lt__")

        def __le__(self, _other):
            return self._trip("__le__")

        def __gt__(self, _other):
            return self._trip("__gt__")

        def __ge__(self, _other):
            return self._trip("__ge__")

        def __iter__(self):
            return self._trip("__iter__")

        def __len__(self):
            return self._trip("__len__")

        def __bool__(self):
            return self._trip("__bool__")

        def __getattr__(self, _name):
            return self._trip("__getattr__")

        def __str__(self):
            return self._trip("__str__")

        def __repr__(self):
            return self._trip("__repr__")

    return Hostile(), callbacks


def test_plan_validator_refuses_hostile_fields_before_any_callback():
    _, _, plan = _plan()
    fields = (
        "plan_id",
        "plan_hash",
        "plan_artifact_sha256",
        "project_namespace",
        "synthetic_max_size",
        "synthetic_max_files",
        "transport_id",
        "transport_hash",
        "transport_artifact_sha256",
        "transport_index_key",
        "objects",
        "total_object_count",
        "total_byte_count",
        "total_row_count",
        "synthetic_quota_observation",
        "real_account_quota_authenticated",
        "real_qc_object_store_access_performed",
        "external_bindings",
        "capabilities",
        "_run_candidate",
        "_fixture",
        "_canonical_document",
    )
    for field in fields:
        hostile, callbacks = _hostile_probe()
        forged = dataclasses.replace(plan, **{field: hostile})
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_plan(forged)
        assert callbacks == [], field

    hostile, callbacks = _hostile_probe()
    forged = dataclasses.replace(plan, objects=(hostile, *plan.objects[1:]))
    with pytest.raises(QcObjectStoreReadContractError, match="topology"):
        require_synthetic_qc_object_store_read_plan(forged)
    assert callbacks == []


def test_transcript_validator_refuses_hostile_fields_and_events_without_callbacks():
    _, _, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    fields = (
        "transcript_id",
        "transcript_hash",
        "transcript_artifact_sha256",
        "plan_id",
        "plan_hash",
        "events",
        "synthetic_fixture_transcript",
        "real_qc_object_store_access_performed",
        "external_bindings",
        "capabilities",
        "_canonical_document",
    )
    for field in fields:
        hostile, callbacks = _hostile_probe()
        forged = dataclasses.replace(transcript, **{field: hostile})
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_transcript(forged, plan=plan)
        assert callbacks == [], field

    for event_index, field in (
        (0, "ordinal"),
        (0, "operation"),
        (0, "object_store_key"),
        (0, "found"),
        (0, "payload"),
        (1, "ordinal"),
        (1, "operation"),
        (1, "object_store_key"),
        (1, "found"),
        (1, "payload"),
    ):
        hostile, callbacks = _hostile_probe()
        forged = _replace_event(transcript, event_index, **{field: hostile})
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_transcript(forged, plan=plan)
        assert callbacks == [], (event_index, field)


def test_receipt_validator_refuses_hostile_fields_and_backing_values_without_callbacks():
    _, _, _, _, receipt = _loaded()
    fields = (
        "receipt_id",
        "receipt_hash",
        "plan_id",
        "plan_hash",
        "transcript_id",
        "transcript_hash",
        "object_store_keys",
        "transport_load",
        "total_object_count",
        "total_byte_count",
        "total_row_count",
        "synthetic_read_contract_validated",
        "real_account_quota_authenticated",
        "real_qc_object_store_access_performed",
        "external_bindings",
        "capabilities",
        "_plan",
        "_transcript",
    )
    for field in fields:
        hostile, callbacks = _hostile_probe()
        forged = dataclasses.replace(receipt, **{field: hostile})
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_receipt(forged)
        assert callbacks == [], field


def test_exact_string_and_integer_types_are_required_at_every_retained_boundary():
    _, _, plan, transcript, receipt = _loaded()

    class TextAlias(str):
        pass

    for field in (
        "plan_id",
        "plan_hash",
        "plan_artifact_sha256",
        "project_namespace",
        "transport_id",
        "transport_hash",
        "transport_artifact_sha256",
        "transport_index_key",
    ):
        forged = dataclasses.replace(plan, **{field: TextAlias(getattr(plan, field))})
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_plan(forged)
    for field in ("logical_key", "object_store_key", "artifact_sha256"):
        descriptor = dataclasses.replace(
            plan.objects[0], **{field: TextAlias(getattr(plan.objects[0], field))}
        )
        forged = dataclasses.replace(plan, objects=(descriptor, *plan.objects[1:]))
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_plan(forged)
    bool_descriptor = dataclasses.replace(plan.objects[0], ordinal=True)
    with pytest.raises(QcObjectStoreReadContractError):
        require_synthetic_qc_object_store_read_plan(
            dataclasses.replace(plan, objects=(bool_descriptor, *plan.objects[1:]))
        )

    for field in (
        "transcript_id",
        "transcript_hash",
        "transcript_artifact_sha256",
        "plan_id",
        "plan_hash",
    ):
        forged = dataclasses.replace(
            transcript, **{field: TextAlias(getattr(transcript, field))}
        )
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_transcript(forged, plan=plan)
    for event_index, field in ((0, "operation"), (0, "object_store_key")):
        event = transcript.events[event_index]
        forged = _replace_event(
            transcript,
            event_index,
            **{field: TextAlias(getattr(event, field))},
        )
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_transcript(forged, plan=plan)
    with pytest.raises(QcObjectStoreReadContractError):
        require_synthetic_qc_object_store_read_transcript(
            _replace_event(transcript, 0, ordinal=True), plan=plan
        )

    for field in (
        "receipt_id",
        "receipt_hash",
        "plan_id",
        "plan_hash",
        "transcript_id",
        "transcript_hash",
    ):
        forged = dataclasses.replace(
            receipt, **{field: TextAlias(getattr(receipt, field))}
        )
        with pytest.raises(QcObjectStoreReadContractError):
            require_synthetic_qc_object_store_read_receipt(forged)
    forged_keys = (
        TextAlias(receipt.object_store_keys[0]),
        *receipt.object_store_keys[1:],
    )
    with pytest.raises(QcObjectStoreReadContractError):
        require_synthetic_qc_object_store_read_receipt(
            dataclasses.replace(receipt, object_store_keys=forged_keys)
        )


def test_b4_self_static_constant_mutation_refuses_before_plan_construction(monkeypatch):
    candidate, _, _, fixture = _b3_fixture()
    monkeypatch.setattr(
        read_contract,
        "SYNTHETIC_PROJECT_NAMESPACE",
        "synthetic-project-id-mutated",
    )
    with pytest.raises(
        QcObjectStoreReadContractError,
        match="scalar contract|static|identity",
    ):
        build_synthetic_qc_object_store_read_plan(
            run_candidate=candidate,
            object_store=fixture,
            transport_index_key=fixture.transport_index_key,
            synthetic_max_size=sum(len(item.payload) for item in fixture.entries),
            synthetic_max_files=9,
        )


def test_global_error_class_replacement_uses_the_pinned_error_without_callback(
    monkeypatch,
):
    callbacks: list[str] = []

    class HostileError(Exception):
        def __new__(cls, *_args, **_kwargs):
            callbacks.append("__new__")
            raise AssertionError("mutated error class was invoked")

    monkeypatch.setattr(
        read_contract,
        "QcObjectStoreReadContractError",
        HostileError,
    )
    with pytest.raises(
        QcObjectStoreReadContractError,
        match="class identity|static topology|dependency identity",
    ):
        render_qc_object_store_read_contract_schema_bytes()
    assert callbacks == []


@pytest.mark.parametrize(
    ("name", "shadow"),
    (
        ("int", bool),
        ("bool", int),
        ("ValueError", RuntimeError),
    ),
)
def test_post_import_builtin_resolution_shadow_refuses_at_first_boundary(
    name: str,
    shadow: object,
):
    assert name not in vars(read_contract)
    setattr(read_contract, name, shadow)
    try:
        with pytest.raises(
            QcObjectStoreReadContractError,
            match="builtin resolution|static topology|dependency identity",
        ):
            render_qc_object_store_read_contract_schema_bytes()
    finally:
        delattr(read_contract, name)
    assert render_qc_object_store_read_contract_schema_bytes().endswith(b"\n")


def test_generated_dataclass_function_builtin_shadow_refuses_and_restores():
    generated_globals = SyntheticQcObjectStoreReadPlan.__repr__.__globals__
    had_id = "id" in generated_globals
    previous = generated_globals.get("id")
    generated_globals["id"] = bool
    try:
        with pytest.raises(
            QcObjectStoreReadContractError,
            match=(
                "B3 static preflight|builtin resolution|static topology|"
                "function topology"
            ),
        ):
            render_qc_object_store_read_contract_schema_bytes()
    finally:
        if had_id:
            generated_globals["id"] = previous
        else:
            del generated_globals["id"]
    assert render_qc_object_store_read_contract_schema_bytes().endswith(b"\n")


def test_in_place_authority_property_code_mutation_is_refused_and_restored():
    _, _, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    getter = SyntheticQcObjectStoreReadTranscript.qc_object_store_read_available.fget
    assert getter is not None
    original_code = getter.__code__

    def hostile_true(_self):
        return True

    try:
        getter.__code__ = hostile_true.__code__
        with pytest.raises(
            QcObjectStoreReadContractError,
            match="function topology|callable|identity",
        ):
            require_synthetic_qc_object_store_read_transcript(
                transcript,
                plan=plan,
            )
    finally:
        getter.__code__ = original_code
    assert require_synthetic_qc_object_store_read_transcript(
        transcript,
        plan=plan,
    ) is transcript


def test_records_are_frozen_slotted_and_copy_deepcopy_pickle_reauthenticate():
    _, _, plan, transcript, receipt = _loaded()
    for value, validator in (
        (plan, require_synthetic_qc_object_store_read_plan),
        (
            receipt,
            require_synthetic_qc_object_store_read_receipt,
        ),
    ):
        assert dataclasses.is_dataclass(value)
        assert not hasattr(value, "__dict__")
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.real_qc_object_store_access_performed = True
        with pytest.raises(AttributeError):
            value.unreviewed_field = True
        for reconstructed in (
            copy.copy(value),
            copy.deepcopy(value),
            pickle.loads(pickle.dumps(value)),
        ):
            assert validator(reconstructed) is reconstructed
    for reconstructed in (
        copy.copy(transcript),
        copy.deepcopy(transcript),
        pickle.loads(pickle.dumps(transcript)),
    ):
        assert require_synthetic_qc_object_store_read_transcript(
            reconstructed, plan=plan
        ) is reconstructed


def test_uninitialized_and_subclass_shells_do_not_cross_public_validators():
    _, _, plan, transcript, _ = _loaded()

    class PlanSubclass(SyntheticQcObjectStoreReadPlan):
        pass

    for shell, validator in (
        (
            object.__new__(SyntheticQcObjectStoreReadPlan),
            require_synthetic_qc_object_store_read_plan,
        ),
        (
            object.__new__(SyntheticQcObjectStoreReadReceipt),
            require_synthetic_qc_object_store_read_receipt,
        ),
    ):
        with pytest.raises(QcObjectStoreReadContractError):
            validator(shell)
    with pytest.raises(QcObjectStoreReadContractError, match="changed type"):
        require_synthetic_qc_object_store_read_plan(
            object.__new__(PlanSubclass)
        )
    with pytest.raises(QcObjectStoreReadContractError):
        require_synthetic_qc_object_store_read_transcript(
            object.__new__(SyntheticQcObjectStoreReadTranscript), plan=plan
        )
    assert require_synthetic_qc_object_store_read_transcript(
        transcript, plan=plan
    ) is transcript


def test_all_external_bindings_capabilities_and_accessors_remain_closed():
    _, _, plan, transcript, receipt = _loaded()
    assert EXTERNAL_BINDINGS
    assert CAPABILITIES
    for value in (plan, transcript, receipt):
        assert value.external_bindings == EXTERNAL_BINDINGS
        assert value.capabilities == CAPABILITIES
        assert all(binding is None for _, binding in value.external_bindings)
        assert all(enabled is False for _, enabled in value.capabilities)
        assert value.real_qc_object_store_access_performed is False
    for value in (plan, receipt):
        assert all(getattr(value, name) is False for name in FALSE_PROPERTY_NAMES)
    assert transcript.qc_object_store_read_available is False
    assert transcript.qc_object_store_write_available is False


def test_every_authority_accessor_is_one_literal_false_return():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    expected = {
        "SyntheticQcObjectStoreReadPlan": FALSE_PROPERTY_NAMES,
        "SyntheticQcObjectStoreReadTranscript": (
            "qc_object_store_read_available",
            "qc_object_store_write_available",
        ),
        "SyntheticQcObjectStoreReadReceipt": FALSE_PROPERTY_NAMES,
    }
    for class_name, names in expected.items():
        methods = {
            node.name: node
            for node in classes[class_name].body
            if isinstance(node, ast.FunctionDef)
        }
        assert tuple(methods) == names
        for name in names:
            method = methods[name]
            assert len(method.body) == 1
            statement = method.body[0]
            assert isinstance(statement, ast.Return)
            assert isinstance(statement.value, ast.Constant)
            assert statement.value.value is False


def test_public_boundaries_are_value_only_and_have_no_callback_surface():
    expected = {
        build_synthetic_qc_object_store_read_plan: (
            "run_candidate",
            "object_store",
            "transport_index_key",
            "synthetic_max_size",
            "synthetic_max_files",
        ),
        build_synthetic_qc_object_store_read_transcript: ("plan",),
        load_synthetic_qc_global_input_bundle_from_object_store_transcript: (
            "plan",
            "transcript",
        ),
        require_synthetic_qc_object_store_read_plan: ("value",),
        require_synthetic_qc_object_store_read_transcript: ("value", "plan"),
        require_synthetic_qc_object_store_read_receipt: ("value",),
    }
    for function, parameters in expected.items():
        assert tuple(inspect.signature(function).parameters) == parameters
        assert set(parameters).isdisjoint(
            {"callback", "client", "algorithm", "credentials", "account"}
        )


def _no_io_violations(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    forbidden_import_roots = {
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
    forbidden_calls = {
        "open",
        "__import__",
        "eval",
        "exec",
        "compile",
        "getenv",
        "contains_key",
        "get_file_path",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "put",
        "save",
        "delete",
        "create_project",
        "compile_project",
        "backtest",
        "launch",
        "submit_order",
    }
    violations: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in forbidden_calls
            and not (
                isinstance(node.value, ast.Name)
                and node.value.id == "re"
                and node.attr == "compile"
            )
        ):
            # Attribute reads matter even when the method is first aliased and
            # invoked later rather than called inline.
            violations.add(f"call:{node.attr}")
        if isinstance(node, ast.Call):
            requested: object | None = None
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
            ):
                requested = node.args[1]
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "__getattribute__"
                and node.args
            ):
                requested = node.args[0]
            if (
                isinstance(requested, ast.Constant)
                and type(requested.value) is str
                and requested.value in forbidden_calls
            ):
                violations.add(f"call:{requested.value}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0].lower()
                if root in forbidden_import_roots:
                    violations.add(f"import:{root}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0].lower()
            if root in forbidden_import_roots:
                violations.add(f"import:{root}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in forbidden_calls:
                violations.add(f"call:{node.func.id}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                node.func.attr in forbidden_calls
                and not (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "re"
                    and node.func.attr == "compile"
                )
            ):
                violations.add(f"call:{node.func.attr}")
    return tuple(sorted(violations))


def _local_module_path(module_name: str) -> tuple[Path, bool] | None:
    stem = ROOT.joinpath(*module_name.split("."))
    module = stem.with_suffix(".py")
    if module.is_file():
        return module, False
    initializer = stem / "__init__.py"
    if initializer.is_file():
        return initializer, True
    return None


def _resolved_imports(
    source: str, *, module_name: str, is_package: bool
) -> tuple[str, ...]:
    imports: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            parts = module_name.split(".")
            if not is_package:
                parts.pop()
            for _ in range(node.level - 1):
                parts.pop()
            if node.module:
                parts.extend(node.module.split("."))
            base = ".".join(parts)
        else:
            base = node.module or ""
        if base:
            imports.append(base)
        for alias in node.names:
            candidate = f"{base}.{alias.name}" if base else alias.name
            if alias.name != "*" and _local_module_path(candidate) is not None:
                imports.append(candidate)
    return tuple(dict.fromkeys(imports))


def _qc_transitive_import_closure() -> tuple[str, ...]:
    pending = [
        "research.analyst_revisions_v2_qc"
        if path.name == "__init__.py"
        else f"research.analyst_revisions_v2_qc.{path.stem}"
        for path in sorted(PACKAGE.glob("*.py"))
    ]
    visited: set[str] = set()
    allowed_external_roots = {
        *DEFAULT_ALLOWED_STDLIB_ROOTS,
        "functools",
        "inspect",
        "pandas",
        "pandas_market_calendars",
    }
    forbidden = DEFAULT_FORBIDDEN_IMPORT_PREFIXES - {
        "research.analyst_revisions_v2_qc"
    }
    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        located = _local_module_path(module_name)
        assert located is not None, module_name
        path, is_package = located
        visited.add(module_name)
        for imported in _resolved_imports(
            path.read_text(encoding="utf-8"),
            module_name=module_name,
            is_package=is_package,
        ):
            assert not any(
                imported == prefix or imported.startswith(prefix + ".")
                for prefix in forbidden
            ), f"forbidden import {module_name} -> {imported}"
            local = _local_module_path(imported)
            if local is not None:
                assert imported.startswith("research.analyst_revisions_v2_qc") or (
                    imported == "data.exchange_calendar"
                ), f"unapproved local import {module_name} -> {imported}"
                pending.append(imported)
                continue
            assert imported.partition(".")[0] in allowed_external_roots, (
                f"unapproved external import {module_name} -> {imported}"
            )
    return tuple(sorted(visited))


def test_whole_qc_package_transitive_import_and_no_io_closure_is_pinned():
    reached = _qc_transitive_import_closure()
    assert reached == (
        "data.exchange_calendar",
        "research.analyst_revisions_v2_qc",
        "research.analyst_revisions_v2_qc.event_study",
        "research.analyst_revisions_v2_qc.global_input_bundle",
        "research.analyst_revisions_v2_qc.global_input_schema",
        "research.analyst_revisions_v2_qc.object_store_read_contract",
        "research.analyst_revisions_v2_qc.run_contract",
        "research.analyst_revisions_v2_qc.synthetic_input_transport",
    )
    sources = tuple(sorted(PACKAGE.glob("*.py")))
    assert tuple(path.name for path in sources) == (
        "__init__.py",
        "event_study.py",
        "global_input_bundle.py",
        "global_input_schema.py",
        "object_store_read_contract.py",
        "run_contract.py",
        "synthetic_input_transport.py",
    )
    assert {
        path.name: _no_io_violations(path.read_text(encoding="utf-8"))
        for path in sources
    } == {path.name: () for path in sources}


def test_no_io_guard_detects_transitive_and_attribute_call_mutants():
    assert _no_io_violations(
        "import builtins\ndef hidden(store):\n"
        "    builtins.open('x')\n"
        "    return store.read_bytes('x')\n"
    ) == ("call:open", "call:read_bytes", "import:builtins")
    for source in (
        "def hidden(store):\n    read = store.read_bytes\n    return read('x')\n",
        "def hidden(store):\n    return getattr(store, 'read_bytes')('x')\n",
        (
            "def hidden(store):\n"
            "    return store.__getattribute__('read_bytes')('x')\n"
        ),
    ):
        assert _no_io_violations(source) == ("call:read_bytes",)


def test_b4_module_has_no_public_action_shaped_entrypoint():
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
        for name, value in vars(read_contract).items()
        if not name.startswith("_") and inspect.isfunction(value)
    }
    assert all(
        fragment not in name
        for name in public_callables
        for fragment in forbidden_fragments
    )
    assert _no_io_violations(MODULE.read_text(encoding="utf-8")) == ()


def test_b3_builtins_topology_change_is_refused_by_b4_preflight_subprocess():
    script = r"""
import builtins
from research.analyst_revisions_v2_qc import synthetic_input_transport
from research.analyst_revisions_v2_qc.object_store_read_contract import (
    QcObjectStoreReadContractError,
    render_qc_object_store_read_contract_schema_bytes,
)
builtins._arv2_b4_test_addition = object()
try:
    render_qc_object_store_read_contract_schema_bytes()
except QcObjectStoreReadContractError as exc:
    assert "B3 static preflight refused" in str(exc)
else:
    raise AssertionError("post-import builtins mutation was accepted")
finally:
    del builtins._arv2_b4_test_addition
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_plan_and_transcript_semantic_and_artifact_identities_reproduce():
    _, _, plan = _plan()
    transcript = build_synthetic_qc_object_store_read_transcript(plan=plan)
    for value, id_field, hash_field, domain, prefix in (
        (plan, "plan_id", "plan_hash", read_contract.HASH_DOMAIN, "arv2-qc-object-store-read-plan"),
        (
            transcript,
            "transcript_id",
            "transcript_hash",
            read_contract.TRANSCRIPT_HASH_DOMAIN,
            "arv2-qc-object-store-read-transcript",
        ),
    ):
        document = json.loads(value._canonical_document)
        semantic = document[hash_field]
        artifact_id = document[id_field]
        document[id_field] = None
        document[hash_field] = None
        reproduced = hashlib.sha256(
            domain.encode("ascii") + b"\x00" + _canonical(document)
        ).hexdigest()
        assert semantic == reproduced
        assert artifact_id == f"{prefix}-{reproduced[:16]}"
        assert hashlib.sha256(value._canonical_document).hexdigest() == getattr(
            value,
            "plan_artifact_sha256"
            if isinstance(value, SyntheticQcObjectStoreReadPlan)
            else "transcript_artifact_sha256",
        )
