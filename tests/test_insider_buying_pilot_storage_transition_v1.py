"""Invented metadata only; caller enforces native process-tree network denial."""
from copy import deepcopy
import hashlib
import json

import pytest

from research import insider_buying_pilot_storage_transition_v1 as m


def inputs():
    historical = {"schema": m.STORAGE_SCHEMA, "root_kind": "fixed_user_application_support",
                  "device": 1, "inode": 2, "mode": 0o700, "owner": 501, "group": 20}
    current = {**historical, "device": 3}
    proof = {"passed": True, "fixture_only": False, "storage_identity": historical}
    qualification = {**deepcopy(proof), "receipt_sha256": m.expected_input_pins()["proof_complete"]["sha256"]}
    sources = {"research/invented.py": "1" * 64}
    execution = {"head": "2" * 40, "sources": sources,
                 "source_inventory_sha256": hashlib.sha256(m._raw(sources)).hexdigest()}
    return [current, proof, qualification, m.expected_input_pins(), execution]


def test_present_observation_keeps_historical_binding_and_all_authority_false():
    receipt = m.build_transition(*inputs())
    body = receipt.to_payload()
    assert body["contract_validated"] is body["current_byte_equivalence_only"] is True
    assert body["input_bytes_authenticated_by_factory"] is False
    assert body["historical_physical_continuity_established"] is body["historical_binding_passed"] is False
    assert body["historical_changed_fields"] == ["device"]
    assert body["authority"] == m.authority()
    assert all(v is False if isinstance(v, bool) else v == 0 for v in body["authority"].values())
    assert receipt.sha256 == hashlib.sha256(receipt.raw).hexdigest()
    assert json.loads(receipt.raw) == body
    assert m.build_transition(*inputs(), fixture_only=False).to_payload()["fixture_only"] is False


def test_inputs_and_returned_payload_cannot_mutate_the_receipt():
    values = inputs(); receipt = m.build_transition(*values); original = receipt.raw
    values[0]["device"] = 100
    values[1]["storage_identity"]["inode"] = 100
    values[3]["proof_complete"]["sha256"] = "0" * 64
    values[4]["sources"]["research/invented.py"] = "0" * 64
    returned = receipt.to_payload()
    returned["authority"]["point_in_time_data"] = True
    returned["input_pins"].clear()
    assert receipt.raw == original
    assert receipt.to_payload()["authority"]["point_in_time_data"] is False
    with pytest.raises(AttributeError):
        receipt._body = b"{}"
    object.__setattr__(receipt, "_body", b"{}")
    with pytest.raises(m.StorageTransitionError, match="genuine_transition_required"):
        receipt.to_payload()


def test_receipts_are_factory_only_and_fixed_pins_are_detached():
    with pytest.raises(m.StorageTransitionError, match="genuine_transition_required"):
        m.TransitionReceipt()
    clone = object.__new__(m.TransitionReceipt)
    with pytest.raises(m.StorageTransitionError, match="genuine_transition_required"):
        clone.to_payload()
    pins = m.expected_input_pins(); pins["provider_controls"]["bytes"] = 1
    assert m.expected_input_pins()["provider_controls"]["bytes"] == 18297


@pytest.mark.parametrize(("field", "value"), (("inode", 9), ("owner", 0), ("group", 21),
    ("mode", 0o755), ("schema", "invented"), ("root_kind", "invented_fixture"), ("device", True),
    ("inode", False), ("device", -1), ("owner", "501")))
def test_additional_identity_or_permission_changes_refuse(field, value):
    values = inputs(); values[0][field] = value
    with pytest.raises(m.StorageTransitionError): m.build_transition(*values)


def test_same_device_is_not_the_registered_transition():
    values = inputs(); values[0]["device"] = values[1]["storage_identity"]["device"]
    with pytest.raises(m.StorageTransitionError, match="device_only_difference_required"):
        m.build_transition(*values)


@pytest.mark.parametrize("index", (0, 1, 2))
@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_finite_storage_identity_shapes_are_exact(index, mutation):
    values = inputs(); value = values[0] if index == 0 else values[index]["storage_identity"]
    value.pop("inode") if mutation == "missing" else value.update({"authority": True})
    with pytest.raises(m.StorageTransitionError, match="storage_shape_refused"):
        m.build_transition(*values)


@pytest.mark.parametrize("index", (1, 2))
@pytest.mark.parametrize(("flag", "value"), (("passed", 1), ("passed", False),
    ("fixture_only", True), ("fixture_only", 0)))
def test_historical_actual_pass_flags_are_exact(index, flag, value):
    values = inputs(); values[index][flag] = value
    with pytest.raises(m.StorageTransitionError, match="historical_proof_refused"):
        m.build_transition(*values)


def test_conflicting_historical_proof_or_wrong_receipt_pin_refuses():
    values = inputs(); values[2]["storage_identity"]["inode"] = 7
    with pytest.raises(m.StorageTransitionError, match="historical_proof_conflict"):
        m.build_transition(*values)
    values = inputs(); values[2]["receipt_sha256"] = "0" * 64
    with pytest.raises(m.StorageTransitionError, match="historical_proof_link_refused"):
        m.build_transition(*values)


@pytest.mark.parametrize("mutation", ("missing", "extra", "hash", "size", "bool-size", "pin-extra"))
def test_every_fixed_leaf_pin_is_required_and_exact(mutation):
    values = inputs(); pins = values[3]
    if mutation == "missing": pins.pop("provider_controls")
    elif mutation == "extra": pins["invented"] = {"bytes": 1, "sha256": "0" * 64}
    elif mutation == "hash": pins["actions_projection"]["sha256"] = "0" * 64
    elif mutation == "size": pins["provider_storage"]["bytes"] += 1
    elif mutation == "bool-size": pins["provider_controls"]["bytes"] = True
    else: pins["proof_complete"]["authority"] = True
    with pytest.raises(m.StorageTransitionError, match="input_pins_refused"):
        m.build_transition(*values)


@pytest.mark.parametrize("mutation", ("extra", "head", "inventory", "missing-sources", "traversal", "absolute", "artifact", "not-python", "bad-hash"))
def test_execution_identity_requires_hash_bound_safe_relative_sources(mutation):
    values = inputs(); execution = values[4]
    if mutation == "extra": execution["verified"] = True
    elif mutation == "head": execution["head"] = "f" * 39
    elif mutation == "inventory": execution["source_inventory_sha256"] = "0" * 64
    elif mutation == "missing-sources": execution["sources"] = {}
    else:
        name = {"traversal": "research/../private.py", "absolute": "/private.py",
                "artifact": "artifacts/invented.py", "not-python": "research/invented.json",
                "bad-hash": "research/invented.py"}[mutation]
        execution["sources"] = {name: "BAD" if mutation == "bad-hash" else "1" * 64}
        execution["source_inventory_sha256"] = hashlib.sha256(m._raw(execution["sources"])).hexdigest()
    with pytest.raises(m.StorageTransitionError, match="execution_identity_refused"):
        m.build_transition(*values)


@pytest.mark.parametrize("value", (None, 0, 1, "false"))
def test_fixture_scope_flag_requires_boolean(value):
    with pytest.raises(m.StorageTransitionError, match="fixture_flag_refused"):
        m.build_transition(*inputs(), fixture_only=value)


def test_unrelated_historical_fields_are_not_copied_into_new_receipt():
    values = inputs()
    values[1]["unrelated"] = "PRIVATE HISTORICAL BODY"
    values[2]["unrelated"] = {"credential": "PRIVATE HISTORICAL BODY"}
    receipt = m.build_transition(*values)
    assert b"PRIVATE" not in receipt.raw and b"unrelated" not in receipt.raw


def test_serialized_transition_can_be_validated_without_becoming_a_genuine_receipt():
    values = inputs(); receipt = m.build_transition(*values)
    restored = json.loads(receipt.raw)
    validated = m.validate_payload(restored, execution_identity=values[4])
    assert validated == receipt.to_payload() and validated is not restored
    validated["authority"]["point_in_time_data"] = True
    assert restored["authority"]["point_in_time_data"] is False
    assert receipt.to_payload()["authority"]["point_in_time_data"] is False
    assert not isinstance(restored, m.TransitionReceipt)


@pytest.mark.parametrize(("name", "value"), (("contract_validated", False),
    ("contract_validated", 1), ("current_byte_equivalence_only", False),
    ("input_bytes_authenticated_by_factory", True),
    ("historical_physical_continuity_established", True), ("historical_binding_passed", True)))
def test_payload_cannot_change_contract_or_historical_assurance_flags(name, value):
    body = m.build_transition(*inputs()).to_payload(); body[name] = value
    with pytest.raises(m.StorageTransitionError, match="payload_refused"):
        m.validate_payload(body)


@pytest.mark.parametrize("name", tuple(m.authority()))
def test_payload_cannot_assert_any_positive_authority(name):
    body = m.build_transition(*inputs()).to_payload()
    body["authority"][name] = True if type(body["authority"][name]) is bool else 1
    with pytest.raises(m.StorageTransitionError, match="payload_refused"):
        m.validate_payload(body)


@pytest.mark.parametrize("mutation", ("extra", "missing", "schema", "changed-fields", "tuple-fields", "authority-extra", "counter-bool"))
def test_payload_keys_schema_and_observation_shape_are_exact(mutation):
    body = m.build_transition(*inputs()).to_payload()
    if mutation == "extra": body["verified"] = True
    elif mutation == "missing": body.pop("historical_binding_passed")
    elif mutation == "schema": body["schema"] = "invented"
    elif mutation == "changed-fields": body["historical_changed_fields"] = ["device", "inode"]
    elif mutation == "tuple-fields": body["historical_changed_fields"] = ("device",)
    elif mutation == "authority-extra": body["authority"]["approved"] = False
    else: body["authority"]["qc_jobs"] = False
    with pytest.raises(m.StorageTransitionError): m.validate_payload(body)


@pytest.mark.parametrize("side", ("current_storage_identity", "historical_storage_identity"))
@pytest.mark.parametrize(("field", "value"), (("inode", 9), ("owner", 0), ("mode", 0o755), ("device", True)))
def test_payload_storage_identity_mutations_must_still_satisfy_the_transition(side, field, value):
    body = m.build_transition(*inputs()).to_payload(); body[side][field] = value
    with pytest.raises(m.StorageTransitionError): m.validate_payload(body)


def test_payload_optional_execution_binding_rejects_a_different_valid_observer():
    values = inputs(); body = m.build_transition(*values).to_payload()
    changed = deepcopy(values[4]); changed["head"] = "3" * 40
    with pytest.raises(m.StorageTransitionError, match="execution_identity_refused"):
        m.validate_payload(body, execution_identity=changed)
    body["execution_identity"]["source_inventory_sha256"] = "0" * 64
    with pytest.raises(m.StorageTransitionError, match="execution_identity_refused"):
        m.validate_payload(body)
