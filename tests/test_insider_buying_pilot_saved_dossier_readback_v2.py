"""Invented five-leaf receipts; native caller supplies network/DATA denial."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX retained custody")
from research import insider_buying_pilot_saved_dossier_readback_v2 as m


def _fixture():
    path = Path(__file__).with_name("test_insider_buying_pilot_storage_dossier_runner_v1.py")
    spec = importlib.util.spec_from_file_location("saved_readback_v2_fixture", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    value, original = helper._readback_fixture()
    anchor = helper._seal_readback(value)
    reader = deepcopy(original)
    reader["head"] = "d" * 40
    reader["source_sha256"]["research/invented_saved_reader_v2.py"] = "e" * 64
    reader["source_inventory_sha256"] = m._sha(m._raw(reader["source_sha256"]))
    return value, original, reader, anchor, helper


def _validate(value, original, reader, anchor):
    return m.validate_invented(value, original_identity=original, reader_identity=reader,
                               complete_sha256=anchor)


def test_later_head_toy_readback_keeps_original_and_reader_lineage_separate():
    value, original, reader, anchor, _helper = _fixture()
    result = _validate(value, original, reader, anchor)
    assert result["fixture_only"] is True
    assert result["saved_receipt_contract_validated"] is True
    assert result["original_execution_head"] == original["head"]
    assert result["reader_execution_head"] == reader["head"] != original["head"]
    assert result["leaf_count"] == 5
    assert result["original_input_leaves_replayed"] == result["historical_evidence_gates_closed"] == 0
    assert result["historical_storage_identity_reauthenticated"] is False
    assert result["full_historical_environment_replayed"] is False
    assert result["authority"] == m.prior.transition.authority()
    assert "source_sha256" not in result and "controls" not in result


def test_toy_receipt_cannot_enter_the_actual_anchor_path():
    value, original, reader, _anchor, _helper = _fixture()
    with pytest.raises(m.SavedReadbackError):
        m.validate_saved(value, original_identity=original, reader_identity=reader)


def test_input_and_output_mutation_cannot_change_a_completed_result():
    value, original, reader, anchor, _helper = _fixture()
    result = _validate(value, original, reader, anchor)
    untouched = deepcopy(result)
    value["controls"]["complete.json"]["authority"]["backtesting_ready"] = True
    original["head"] = "f" * 40
    reader["source_sha256"].clear()
    result["counts"]["controls"] = 100
    assert untouched["counts"]["controls"] == 12
    assert untouched["authority"]["backtesting_ready"] is False


@pytest.mark.parametrize("path", ("./artifacts/private.py", "research/../private.py", "research/./reader.py",
    "/absolute.py", "artifacts/private.py", "research//reader.py", "research/trailing.py/"))
def test_source_identity_refuses_non_normalized_or_data_paths(path):
    _value, original, _reader, _anchor, _helper = _fixture()
    original["source_sha256"] = {path: "a" * 64}
    original["source_inventory_sha256"] = m._sha(m._raw(original["source_sha256"]))
    with pytest.raises(m.SavedReadbackError, match="saved_identity_refused"):
        m.source_identity(original)


@pytest.mark.parametrize("fault", ("missing", "changed", "bool-clean", "extra-key", "bad-head", "inventory"))
def test_reader_source_identity_must_cover_the_original_byte_map(fault):
    value, original, reader, anchor, _helper = _fixture()
    name = next(iter(original["source_sha256"]))
    if fault == "missing": reader["source_sha256"].pop(name)
    elif fault == "changed": reader["source_sha256"][name] = "0" * 64
    elif fault == "bool-clean": reader["clean"] = 1
    elif fault == "extra-key": reader["unexpected"] = True
    elif fault == "bad-head": reader["head"] = "d" * 39
    else: reader["source_inventory_sha256"] = "0" * 64
    if fault in {"missing", "changed"}:
        reader["source_inventory_sha256"] = m._sha(m._raw(reader["source_sha256"]))
    with pytest.raises(m.SavedReadbackError): _validate(value, original, reader, anchor)


@pytest.mark.parametrize("fault", ("complete-pin", "leaf-pin", "missing-leaf", "extra-leaf", "pin-bool", "pin-extra"))
def test_saved_pins_and_exact_inventory_are_not_self_authorizing(fault):
    value, original, reader, anchor, _helper = _fixture()
    if fault == "complete-pin": value["pins"]["complete.json"]["sha256"] = "0" * 64
    elif fault == "leaf-pin": value["pins"]["dossier.json"]["sha256"] = "0" * 64
    elif fault == "missing-leaf": value["controls"].pop("dossier.json")
    elif fault == "extra-leaf": value["controls"]["failure.json"] = {}
    elif fault == "pin-bool": value["pins"]["dossier.json"]["bytes"] = True
    else: value["pins"]["complete.json"]["unexpected"] = True
    with pytest.raises(m.SavedReadbackError): _validate(value, original, reader, anchor)


@pytest.mark.parametrize("where", ("complete", "started", "dossier-summary", "audit-summary", "registration"))
def test_boolean_integer_authority_alias_is_refused_after_all_hashes_are_resigned(where):
    value, original, reader, _anchor, helper = _fixture()
    controls = value["controls"]
    target = {"complete": controls["complete.json"], "started": controls["observation-started.json"],
              "dossier-summary": controls["complete.json"]["dossier_summary"],
              "audit-summary": controls["complete.json"]["audit_summary"],
              "registration": controls["reservation.json"]["registration"]}[where]
    target["authority"]["qc_jobs"] = False
    anchor = helper._seal_readback(value)
    with pytest.raises(m.SavedReadbackError, match="saved_authority_refused"):
        _validate(value, original, reader, anchor)


@pytest.mark.parametrize("fault", ("storage-bool", "complete-storage-bool", "original-head", "started-extra", "complete-extra", "float"))
def test_semantic_faults_cannot_hide_behind_resigned_pins(fault):
    value, original, reader, _anchor, helper = _fixture()
    if fault == "storage-bool": value["storage_identity"]["owner"] = True
    elif fault == "complete-storage-bool": value["controls"]["complete.json"]["storage_identity"]["owner"] = True
    elif fault == "original-head": value["controls"]["reservation.json"]["code_identity"]["head"] = "e" * 40
    elif fault == "started-extra": value["controls"]["observation-started.json"]["unexpected"] = True
    elif fault == "complete-extra": value["controls"]["complete.json"]["unexpected"] = True
    else: value["controls"]["complete.json"]["input_leaves"] = 20.0
    anchor = helper._seal_readback(value)
    with pytest.raises(m.SavedReadbackError): _validate(value, original, reader, anchor)


def test_external_complete_anchor_is_checked_before_the_legacy_semantic_validator(monkeypatch):
    value, original, reader, _anchor, _helper = _fixture()
    monkeypatch.setattr(m.prior, "validate_readback", lambda *_a, **_k: pytest.fail("unanchored semantics"))
    with pytest.raises(m.SavedReadbackError, match="saved_complete_anchor_refused"):
        _validate(value, original, reader, "0" * 64)


def test_legacy_semantics_are_still_mandatory_after_typed_checks(monkeypatch):
    value, original, reader, anchor, _helper = _fixture()
    def refuse(*_args):
        raise m.prior.StorageDossierError("invented semantic refusal")
    monkeypatch.setattr(m.prior, "validate_readback", refuse)
    with pytest.raises(m.SavedReadbackError, match="saved_readback_refused"):
        _validate(value, original, reader, anchor)


@pytest.mark.parametrize("fault", ("completed", "leaf-count", "replay", "gates", "history", "authority", "extra", "count", "head"))
def test_summary_ipc_refuses_untyped_promoted_or_unbound_results(fault):
    value, original, reader, anchor, _helper = _fixture()
    result = _validate(value, original, reader, anchor)
    if fault == "completed": result["completed"] = 1
    elif fault == "leaf-count": result["leaf_count"] = True
    elif fault == "replay": result["original_input_leaves_replayed"] = False
    elif fault == "gates": result["historical_evidence_gates_closed"] = False
    elif fault == "history": result["historical_storage_identity_reauthenticated"] = True
    elif fault == "authority": result["authority"]["qc_jobs"] = False
    elif fault == "extra": result["PRIVATE"] = "not permitted"
    elif fault == "count": result["counts"]["controls"] = True
    else: result["reader_execution_head"] = "f" * 40
    with pytest.raises(m.SavedReadbackError):
        m.validate_summary(result, original_identity=original, reader_identity=reader,
                           fixture_only=True, complete_sha256=anchor)


def test_actual_summary_cannot_be_minted_by_the_invented_path():
    value, original, reader, anchor, _helper = _fixture()
    result = _validate(value, original, reader, anchor)
    with pytest.raises(m.SavedReadbackError):
        m.validate_summary(result, original_identity=original, reader_identity=reader,
                           fixture_only=False, complete_sha256=anchor)


def _toy_actual_anchors(monkeypatch, original, anchor):
    monkeypatch.setattr(m, "ORIGINAL_HEAD", original["head"])
    monkeypatch.setattr(m, "ORIGINAL_INVENTORY", original["source_inventory_sha256"])
    monkeypatch.setattr(m, "ORIGINAL_SOURCE_COUNT", len(original["source_sha256"]))
    monkeypatch.setattr(m, "COMPLETE_SHA256", anchor)


def test_actual_entry_positive_control_uses_only_explicit_toy_anchors(monkeypatch):
    value, original, reader, anchor, _helper = _fixture()
    fixture_result = _validate(value, original, reader, anchor)
    _toy_actual_anchors(monkeypatch, original, anchor)
    monkeypatch.setattr(m, "TRANSITION_SHA256", value["pins"]["transition.json"]["sha256"])
    monkeypatch.setattr(m, "DOSSIER_SHA256", value["pins"]["dossier.json"]["sha256"])
    monkeypatch.setattr(m, "REFERENCE_AUDIT_SHA256", value["controls"]["complete.json"]["audit_summary"]["result_sha256"])
    monkeypatch.setattr(m, "ACTUAL_COUNTS", fixture_result["counts"])
    result = m.validate_saved(value, original_identity=original, reader_identity=reader)
    assert result["fixture_only"] is False and result["saved_receipt_contract_validated"] is True
    assert result["original_execution_head"] != result["reader_execution_head"]


def test_extract_identity_authenticates_complete_then_reservation_without_claiming_git(monkeypatch):
    value, original, _reader, anchor, _helper = _fixture()
    _toy_actual_anchors(monkeypatch, original, anchor)
    found = m.extract_original_identity(value)
    assert found == original
    found["source_sha256"].clear()
    assert original["source_sha256"]


@pytest.mark.parametrize("fault", ("complete", "reservation", "original-inventory", "original-head", "extra-original"))
def test_extract_identity_refuses_unanchored_or_differently_bound_saved_identity(monkeypatch, fault):
    value, original, _reader, anchor, _helper = _fixture()
    _toy_actual_anchors(monkeypatch, original, anchor)
    if fault == "complete": value["controls"]["complete.json"]["authority"]["backtesting_ready"] = True
    elif fault == "reservation": value["controls"]["reservation.json"]["registration"]["purpose"] = "changed"
    elif fault == "original-inventory": monkeypatch.setattr(m, "ORIGINAL_INVENTORY", "0" * 64)
    elif fault == "original-head": monkeypatch.setattr(m, "ORIGINAL_HEAD", "f" * 40)
    else: value["controls"]["reservation.json"]["code_identity"]["unknown"] = True
    with pytest.raises(m.SavedReadbackError): m.extract_original_identity(value)
