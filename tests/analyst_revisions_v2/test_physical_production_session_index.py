from __future__ import annotations

import os
import re
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.production_input_pipeline import SignalArm
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_acquisition as acquisition,
)
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_bridge as bridge_module,
)
from research.analyst_revisions_v2_qc import (
    physical_production_session_index as index_module,
)
from research.analyst_revisions_v2_qc.physical_production_input_archive import (
    build_test_fixture_physical_production_input_archive,
    iter_physical_production_normalized_rows,
)
from tests.analyst_revisions_v2.test_production_input_pipeline import _authority
from tests.analyst_revisions_v2.test_qc_formal_run_protocol import _accepted_risk


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


@pytest.fixture()
def index_fixture(monkeypatch, tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    c2_root = tmp_path / "c2"
    c2_root.mkdir(mode=0o700)
    c2 = build_test_fixture_physical_production_input_archive(
        _authority(), output_root=c2_root
    )
    bridge = object.__new__(bridge_module.PhysicalProductionEvidenceBridge)
    object.__setattr__(bridge, "bridge_id", "arv2-physical-evidence-test")
    object.__setattr__(bridge, "bridge_sha256", "a" * 64)
    object.__setattr__(bridge, "production_input_archive", c2)
    monkeypatch.setattr(
        bridge_module,
        "require_physical_production_evidence_bridge",
        lambda value: value,
    )
    sessions = (
        SimpleNamespace(decision_session="2020-01-06"),
        SimpleNamespace(decision_session="2020-01-07"),
    )
    receipt = object.__new__(
        acquisition.PhysicalProductionEvidenceAcquisitionReceipt
    )
    values = {
        "bridge": bridge,
        "production_input_archive": c2,
        "preopen_acquisition_receipt": SimpleNamespace(control_sessions=sessions),
        "receipt_id": "arv2-physical-production-evidence-fixture",
        "receipt_sha256": "b" * 64,
        "production_input_archive_id": c2.archive_id,
        "production_input_archive_sha256": c2.archive_sha256,
        "fixture_only": True,
        "review_mode": acquisition.FIXTURE_REVIEW_MODE,
        "session_axis": tuple(item.decision_session for item in sessions),
        "owner_waived_firm_admission_id": None,
        "owner_waived_firm_admission_sha256": None,
        "firm_owner_decision_id": None,
        "firm_owner_decision_sha256": None,
        "firm_refusal_ledger_id": None,
        "firm_refusal_ledger_sha256": None,
        "owner_waiver_scope": None,
        "independently_reviewed": False,
        "owner_review_waived": False,
        "historical_availability_claimed": True,
        "post_first_formal_backtest_independent_review_required": False,
    }
    for name, value in values.items():
        object.__setattr__(receipt, name, value)
    monkeypatch.setattr(index_module, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        index_module._acquisition,
        "require_physical_production_evidence_receipt",
        lambda value: value,
    )
    output_root = tmp_path / "indexes"
    output_root.mkdir(mode=0o700)
    index = index_module._build_test_fixture_physical_production_session_index(
        receipt=receipt,
        output_root=output_root,
    )
    return index, c2


def test_index_replays_exact_c2_rows_by_session_without_retained_union(index_fixture):
    index, c2 = index_fixture

    blocks = tuple(index_module.iter_physical_production_session_blocks(index))

    assert [item.decision_session for item in blocks] == [
        "2020-01-06",
        "2020-01-07",
    ]
    expected = {
        arm: tuple(
            sorted(
                iter_physical_production_normalized_rows(c2, arm),
                key=lambda row: row.row_sha256,
            )
        )
        for arm in SignalArm
    }
    assert [
        item.normalized_evidence.normalized_row for item in blocks[0].current_rows
    ] == list(expected[SignalArm.CURRENT_VINTAGE])
    assert [
        item.normalized_evidence.normalized_row for item in blocks[0].censored_rows
    ] == list(expected[SignalArm.CONSERVATIVE_CENSORED])
    assert blocks[1].current_rows == ()
    assert blocks[1].censored_rows == ()
    assert index.current_row_count == len(expected[SignalArm.CURRENT_VINTAGE])
    assert index.censored_row_count == len(
        expected[SignalArm.CONSERVATIVE_CENSORED]
    )
    assert index.disk_backed is True
    assert index.full_pair_materialized is False
    assert index.full_batch_materialized is False
    assert index.full_union_materialized is False
    assert index.full_row_evidence_map_materialized is False


def test_session_index_is_authenticated_and_repeatably_streamable(index_fixture):
    index, _c2 = index_fixture

    assert index_module.require_physical_production_session_index(index) is index
    first = [
        item.block_sha256
        for item in index_module.iter_physical_production_session_blocks(index)
    ]
    second = [
        item.block_sha256
        for item in index_module.iter_physical_production_session_blocks(index)
    ]

    assert first == second
    assert index.index_file_byte_count > 0
    assert len(index.index_file_sha256) == 64
    assert len(index.session_projection_sha256) == 64
    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index is not formally eligible"),
    ):
        index_module.require_formal_physical_production_session_index(index)


def test_public_session_index_builder_and_formal_requirer_happy_path(
    monkeypatch, index_fixture, tmp_path
):
    fixture_index, _c2 = index_fixture
    receipt = fixture_index.production_evidence_receipt
    object.__setattr__(receipt, "fixture_only", False)
    object.__setattr__(receipt, "review_mode", acquisition.NORMAL_REVIEW_MODE)
    object.__setattr__(receipt, "independently_reviewed", True)
    object.__setattr__(receipt.bridge, "accepted_risk_archive", object())
    accepted_risk = _accepted_risk()
    monkeypatch.setattr(
        index_module._acquisition,
        "require_reviewed_physical_production_evidence_receipt",
        lambda value: value,
    )
    monkeypatch.setattr(
        index_module._c2,
        "build_physical_formal_accepted_risk_pair_binding",
        lambda _c1, _c2: accepted_risk,
    )
    output_root = tmp_path / "production-index"
    output_root.mkdir(mode=0o700)

    index = index_module.build_physical_production_session_index(
        receipt=receipt,
        output_root=output_root,
    )

    assert index_module.require_formal_physical_production_session_index(index) is index
    assert index.fixture_only is False
    assert index.accepted_risk_binding is accepted_risk
    assert index.accepted_risk_binding_sha256 == index_module.sha256_bytes(
        index_module.canonical_json_bytes(accepted_risk.to_record())
    )
    assert tuple(index_module.iter_physical_production_session_blocks(index))


def test_section72_owner_waived_index_is_formal_without_false_review_claim(
    monkeypatch, index_fixture, tmp_path
):
    fixture_index, _c2 = index_fixture
    receipt = fixture_index.production_evidence_receipt
    object.__setattr__(receipt, "fixture_only", False)
    object.__setattr__(
        receipt,
        "review_mode",
        acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE,
    )
    object.__setattr__(receipt, "independently_reviewed", False)
    object.__setattr__(receipt, "owner_review_waived", True)
    object.__setattr__(receipt, "historical_availability_claimed", False)
    object.__setattr__(
        receipt,
        "post_first_formal_backtest_independent_review_required",
        True,
    )
    object.__setattr__(
        receipt, "owner_waiver_scope", bridge_module.SECTION72_OWNER_WAIVER_SCOPE
    )
    object.__setattr__(
        receipt,
        "owner_waived_firm_admission_id",
        "arv2-section72-firm-admission-test",
    )
    object.__setattr__(receipt, "owner_waived_firm_admission_sha256", "1" * 64)
    object.__setattr__(
        receipt, "firm_owner_decision_id", "arv2-firm-owner-decision-test"
    )
    object.__setattr__(receipt, "firm_owner_decision_sha256", "2" * 64)
    object.__setattr__(
        receipt, "firm_refusal_ledger_id", "arv2-firm-refusal-ledger-test"
    )
    object.__setattr__(receipt, "firm_refusal_ledger_sha256", "3" * 64)
    object.__setattr__(receipt.bridge, "accepted_risk_archive", object())
    accepted_risk = _accepted_risk()
    monkeypatch.setattr(
        index_module._acquisition,
        "require_section72_owner_waived_production_evidence_receipt",
        lambda value: value,
    )
    monkeypatch.setattr(
        index_module._c2,
        "build_physical_formal_accepted_risk_pair_binding",
        lambda _c1, _c2: accepted_risk,
    )
    output_root = tmp_path / "waived-production-index"
    output_root.mkdir(mode=0o700)

    index = (
        index_module.build_section72_owner_waived_physical_production_session_index(
            receipt=receipt, output_root=output_root
        )
    )

    assert index_module.require_formal_physical_production_session_index(index) is index
    assert index.review_mode == acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
    assert index.independently_reviewed is False
    assert index.owner_review_waived is True
    assert index.historical_availability_claimed is False
    assert index.post_first_formal_backtest_independent_review_required is True
    assert index.owner_waived_firm_admission_id == (
        receipt.owner_waived_firm_admission_id
    )
    assert index.firm_owner_decision_sha256 == receipt.firm_owner_decision_sha256
    assert index.firm_refusal_ledger_sha256 == receipt.firm_refusal_ledger_sha256
    assert index.accepted_risk_binding is accepted_risk

    terminals = tuple(
        SimpleNamespace(
            decision_session=session,
            terminal_count=0,
            control_terminal_merkle_root="c" * 64,
            universe_terminal_merkle_root="u" * 64,
        )
        for session in receipt.session_axis
    )
    monkeypatch.setattr(
        index_module._bridge,
        "section72_owner_waived_preopen_session_axis",
        lambda _bridge: receipt.session_axis,
    )
    monkeypatch.setattr(
        index_module._bridge,
        "iter_section72_owner_waived_preopen_terminal_sessions",
        lambda _bridge: iter(terminals),
    )
    inputs = tuple(
        index_module.iter_physical_production_scoring_session_inputs(
            index, receipt.preopen_acquisition_receipt
        )
    )
    assert tuple(item.decision_session for item in inputs) == receipt.session_axis

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact(
            "owner-waived production index and prereview archive parents differ"
        ),
    ):
        next(
            index_module.iter_physical_production_scoring_session_inputs(
                index, object()
            )
        )


def test_session_index_refuses_overlapping_fixture_and_owner_waiver_modes(
    index_fixture, tmp_path
):
    index, _c2 = index_fixture
    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index admission modes overlap"),
    ):
        index_module._build_index(
            receipt=index.production_evidence_receipt,
            output_root=tmp_path,
            permit_fixture=True,
            permit_section72_owner_waiver=True,
        )


def test_session_index_builder_authority_is_process_local(
    monkeypatch, index_fixture
):
    index, _c2 = index_fixture
    builder_pid = os.getpid()
    monkeypatch.setattr(index_module.os, "getpid", lambda: builder_pid + 1)

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index lost builder authority"),
    ):
        index_module.require_physical_production_session_index(index)


def test_session_adapter_joins_preopen_terminals_without_a_global_event_map(
    monkeypatch, index_fixture
):
    index, _c2 = index_fixture
    preopen = index.production_evidence_receipt.preopen_acquisition_receipt
    archive = SimpleNamespace(preopen_acquisition_receipt=preopen)
    terminals = tuple(
        SimpleNamespace(
            decision_session=session.decision_session,
            terminal_count=3,
            control_terminal_merkle_root="c" * 64,
            universe_terminal_merkle_root="u" * 64,
        )
        for session in preopen.control_sessions
    )
    monkeypatch.setattr(
        index_module._streaming,
        "iter_physical_preopen_terminal_sessions",
        lambda _archive: iter(terminals),
    )

    inputs = tuple(
        index_module._iter_test_fixture_physical_production_scoring_session_inputs(
            index, archive
        )
    )

    assert [item.decision_session for item in inputs] == [
        "2020-01-06",
        "2020-01-07",
    ]
    assert len(inputs[0].current_event_rows) == index.current_row_count
    assert len(inputs[0].censored_event_rows) == index.censored_row_count
    assert inputs[1].current_event_rows == ()
    assert inputs[1].censored_event_rows == ()
    assert all(len(item.input_sha256) == 64 for item in inputs)


def test_formal_session_adapter_refuses_fixture_before_terminal_replay(
    monkeypatch, index_fixture
):
    index, _c2 = index_fixture
    archive = SimpleNamespace(
        preopen_acquisition_receipt=(
            index.production_evidence_receipt.preopen_acquisition_receipt
        )
    )
    called = False

    def iter_terminals(_archive):
        nonlocal called
        called = True
        return iter(())

    monkeypatch.setattr(
        index_module._streaming,
        "iter_physical_preopen_terminal_sessions",
        iter_terminals,
    )
    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index is not formally eligible"),
    ):
        next(
            index_module.iter_physical_production_scoring_session_inputs(
                index, archive
            )
        )
    assert called is False


def test_session_replay_detects_dependency_rebinding_between_blocks(
    monkeypatch, index_fixture
):
    index, _c2 = index_fixture
    original_label_builder = index_module.build_endpoint_label_evidence

    def require_label_builder() -> None:
        if index_module.build_endpoint_label_evidence is not original_label_builder:
            raise index_module.PhysicalProductionSessionIndexError(
                "physical production session-index dependency changed"
            )

    monkeypatch.setattr(
        index_module, "_require_dependencies", require_label_builder
    )
    blocks = index_module.iter_physical_production_session_blocks(index)
    next(blocks)
    monkeypatch.setattr(
        index_module,
        "build_endpoint_label_evidence",
        lambda **_kwargs: None,
    )

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index dependency changed"),
    ):
        next(blocks)


def test_session_replay_capacity_is_a_named_refusal(monkeypatch, index_fixture):
    index, _c2 = index_fixture
    monkeypatch.setattr(index_module, "MAX_SESSION_ROWS_PER_ARM", 0)

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexCapacityError,
        match=_exact("physical production session row census exceeded capacity"),
    ):
        next(index_module.iter_physical_production_session_blocks(index))


def test_session_replay_aggregate_row_capacity_precedes_materialization(
    monkeypatch, index_fixture
):
    index, _c2 = index_fixture
    monkeypatch.setattr(index_module, "MAX_SESSION_ROWS", 0)

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexCapacityError,
        match=_exact(
            "physical production session aggregate row census exceeded capacity"
        ),
    ):
        next(index_module.iter_physical_production_session_blocks(index))


def test_session_replay_aggregate_byte_capacity_precedes_materialization(
    monkeypatch, index_fixture
):
    index, _c2 = index_fixture
    monkeypatch.setattr(index_module, "MAX_SESSION_PAYLOAD_BYTES", 0)

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexCapacityError,
        match=_exact(
            "physical production session aggregate payload exceeded byte capacity"
        ),
    ):
        next(index_module.iter_physical_production_session_blocks(index))


def test_session_replay_authenticates_substituted_database_before_first_yield(
    monkeypatch, index_fixture, tmp_path
):
    index, _c2 = index_fixture
    substituted = tmp_path / "substituted-index.sqlite3"
    shutil.copy2(index.index_path, substituted)
    substituted.chmod(0o600)
    connection = sqlite3.connect(substituted)
    try:
        key = connection.execute(
            "SELECT decision_session, arm_rank, row_sha256 FROM scoring_rows "
            "ORDER BY decision_session DESC, arm_rank DESC, row_sha256 DESC LIMIT 1"
        ).fetchone()
        assert key is not None
        connection.execute(
            "DELETE FROM scoring_rows WHERE decision_session=? AND arm_rank=? "
            "AND row_sha256=?",
            key,
        )
        connection.commit()
    finally:
        connection.close()
    original_open = index_module._open_reader
    calls = 0

    def swap_after_authority_check(path):
        nonlocal calls
        calls += 1
        return original_open(path if calls == 1 else substituted)

    monkeypatch.setattr(index_module, "_open_reader", swap_after_authority_check)
    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact(
            "physical production session-index pre-replay projection changed"
        ),
    ):
        next(index_module.iter_physical_production_session_blocks(index))
    assert calls == 2


def test_index_file_mutation_is_rejected_before_replay(index_fixture):
    index, _c2 = index_fixture
    with index.index_path.open("ab") as stream:
        stream.write(b"changed")

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index file changed"),
    ):
        index_module.require_physical_production_session_index(index)


def test_index_output_cannot_overlap_immutable_c2(index_fixture):
    index, c2 = index_fixture

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production index output overlaps immutable input"),
    ):
        index_module._build_test_fixture_physical_production_session_index(
            receipt=index.production_evidence_receipt,
            output_root=c2.archive_path,
        )


def test_session_index_dependency_rebinding_is_a_named_refusal(monkeypatch):
    monkeypatch.setattr(
        index_module._bridge,
        "iter_physical_production_scoring_rows",
        lambda *_args: iter(()),
    )
    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index dependency changed"),
    ):
        index_module._require_dependencies()


def test_session_index_capacity_contract_rebinding_is_a_named_refusal(monkeypatch):
    monkeypatch.setattr(
        index_module,
        "MAX_SESSION_PAYLOAD_BYTES",
        index_module.MAX_SESSION_PAYLOAD_BYTES + 1,
    )

    with pytest.raises(
        index_module.PhysicalProductionSessionIndexError,
        match=_exact("physical production session-index dependency changed"),
    ):
        index_module._require_dependencies()
