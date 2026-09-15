from __future__ import annotations

import dataclasses
import gc
import os
import re
import select
import signal
import sqlite3
import tempfile
import threading
import weakref
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.production_input_pipeline import SignalArm
from research.analyst_revisions_v2.production_scoring import (
    FinalDecisionInput,
    FoldPartition,
    ScoreState,
)
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.production_truth_gate import (
    FORMAL_SESSION_GEOMETRY,
)
from research.analyst_revisions_v2_qc import formal_streaming_input as legacy
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_acquisition as acquisition,
)
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_bridge as bridge_module,
)
from research.analyst_revisions_v2_qc import (
    physical_production_session_index as index_module,
)
from research.analyst_revisions_v2_qc import physical_streaming_scoring as scoring
from research.analyst_revisions_v2_qc import power_calibration_bridge as power
from research.analyst_revisions_v2_qc.physical_production_input_archive import (
    build_test_fixture_physical_production_input_archive,
)
from tests.analyst_revisions_v2.test_production_scoring import (
    _install_offline_physical_receipt_requires,
    _offline_physical_requirer,
    _global_contract,
)
from tests.analyst_revisions_v2.test_qc_formal_streaming_input import (
    _full_sparse_formal_fixture,
    _physical_archive,
)


def _exact(value: str) -> str:
    return f"^{re.escape(value)}$"


def _section72_capacity_fixture(monkeypatch):
    archive = object.__new__(
        scoring._prereview.PreopenControlPreReviewArchive
    )
    object.__setattr__(archive, "capture_id", "arv2-prereview-test")
    object.__setattr__(archive, "capture_sha256", "1" * 64)
    receipt = SimpleNamespace(
        receipt_id="arv2-physical-evidence-test",
        receipt_sha256="2" * 64,
        preopen_acquisition_receipt=archive,
    )
    index = object.__new__(index_module.PhysicalProductionSessionIndex)
    for name, value in {
        "index_id": "arv2-physical-index-test",
        "index_sha256": "3" * 64,
        "production_evidence_receipt": receipt,
        "review_mode": acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE,
        "owner_waiver_scope": bridge_module.SECTION72_OWNER_WAIVER_SCOPE,
        "independently_reviewed": False,
        "owner_review_waived": True,
        "historical_availability_claimed": False,
        "post_first_formal_backtest_independent_review_required": True,
    }.items():
        object.__setattr__(index, name, value)
    monkeypatch.setattr(scoring, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        scoring._index,
        "require_formal_physical_production_session_index",
        lambda value: value,
    )
    monkeypatch.setattr(
        scoring._prereview,
        "require_preopen_control_prereview_archive",
        lambda value: value,
    )
    capacity = scoring._build_section72_capacity(index=index, archive=archive)
    return capacity, index, archive, receipt


def test_section72_capacity_is_distinct_truthful_and_reauthenticates_parents(
    monkeypatch,
):
    capacity, index, archive, receipt = _section72_capacity_fixture(monkeypatch)

    assert type(capacity) is scoring.Section72PhysicalStreamingCapacityBinding
    assert type(capacity) is not legacy.FormalStreamingCapacityBinding
    assert capacity.physical_index is index
    assert capacity.preopen_acquisition_receipt is archive
    assert capacity.production_evidence_receipt is receipt
    assert capacity.independently_reviewed is False
    assert capacity.owner_review_waived is True
    assert capacity.historical_availability_claimed is False
    assert capacity.post_first_formal_backtest_independent_review_required is True
    assert capacity.outcome_or_qc_action_authorized is False
    assert (
        scoring.require_physical_streaming_scoring_capacity(capacity)
        is capacity
    )

    receipt.receipt_sha256 = "4" * 64
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("section-72 physical capacity changed after sealing"),
    ):
        scoring.require_section72_physical_streaming_capacity_binding(capacity)


def test_section72_capacity_refuses_cross_source_before_registration(monkeypatch):
    _capacity, index, archive, _receipt = _section72_capacity_fixture(monkeypatch)
    other = object.__new__(type(archive))
    object.__setattr__(other, "capture_id", "arv2-prereview-other")
    object.__setattr__(other, "capture_sha256", "5" * 64)

    before = set(scoring._SECTION72_CAPACITIES)
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("section-72 physical capacity parents changed"),
    ):
        scoring._build_section72_capacity(index=index, archive=other)
    assert set(scoring._SECTION72_CAPACITIES) == before


def test_section72_capacity_cannot_be_forged_or_survive_fork(monkeypatch):
    capacity, _index, _archive, _receipt = _section72_capacity_fixture(monkeypatch)
    forged = object.__new__(scoring.Section72PhysicalStreamingCapacityBinding)
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("section-72 physical capacity lacks builder authority"),
    ):
        scoring.require_section72_physical_streaming_capacity_binding(forged)

    if not hasattr(os, "fork") or not hasattr(os, "register_at_fork"):
        return
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - child result returned by pipe
        os.close(read_fd)
        try:
            scoring.require_section72_physical_streaming_capacity_binding(capacity)
        except scoring.PhysicalStreamingScoringError:
            payload = b"ok"
        else:
            payload = b"inherited"
        os.write(write_fd, payload)
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    assert os.read(read_fd, 16) == b"ok"
    os.close(read_fd)
    _waited, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0


def test_section72_capacity_retains_parents_until_capacity_is_released(monkeypatch):
    capacity, index, archive, receipt = _section72_capacity_fixture(monkeypatch)
    identity = id(capacity)
    index_ref = weakref.ref(index)
    archive_ref = weakref.ref(archive)
    del index, archive, receipt
    gc.collect()
    assert index_ref() is capacity.physical_index
    assert archive_ref() is capacity.preopen_acquisition_receipt
    del capacity
    gc.collect()
    assert index_ref() is None
    assert archive_ref() is None
    assert identity not in scoring._SECTION72_CAPACITIES


def test_physical_terminal_parent_refuses_unknown_exact_type():
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical scoring terminal parent changed exact type"),
    ):
        scoring._terminal_parent_identity(SimpleNamespace())


@pytest.fixture(autouse=True)
def _offline_authorities(monkeypatch, _install_offline_physical_receipt_requires):
    require_preopen = lambda value: _offline_physical_requirer("preopen", value)
    require_evidence = lambda value: _offline_physical_requirer("evidence", value)
    monkeypatch.setattr(
        legacy, "require_reviewed_preopen_control_acquisition_receipt", require_preopen
    )
    monkeypatch.setattr(
        legacy, "require_production_evidence_acquisition_receipt", require_evidence
    )


def _physical_index(monkeypatch, tmp_path: Path, archive):
    evidence = archive.capacity.production_evidence_receipt
    c2_root = tmp_path / "physical-c2"
    c2_root.mkdir(mode=0o700)
    c2 = build_test_fixture_physical_production_input_archive(
        evidence.authority, output_root=c2_root
    )
    bridge = object.__new__(bridge_module.PhysicalProductionEvidenceBridge)
    object.__setattr__(bridge, "bridge_id", "arv2-physical-scoring-test-bridge")
    object.__setattr__(bridge, "bridge_sha256", "a" * 64)
    object.__setattr__(bridge, "production_input_archive", c2)
    receipt = object.__new__(acquisition.PhysicalProductionEvidenceAcquisitionReceipt)
    for name, value in {
        "bridge": bridge,
        "production_input_archive": c2,
        "preopen_acquisition_receipt": archive.preopen_acquisition_receipt,
        "receipt_id": "arv2-physical-scoring-test-receipt",
        "receipt_sha256": "b" * 64,
        "production_input_archive_id": c2.archive_id,
        "production_input_archive_sha256": c2.archive_sha256,
        "evidence_authority_id": c2.evidence_authority_id,
        "evidence_authority_sha256": c2.evidence_authority_sha256,
        "review_mode": acquisition.FIXTURE_REVIEW_MODE,
        "session_axis": tuple(
            item.decision_session
            for item in archive.preopen_acquisition_receipt.control_sessions
        ),
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
        "fixture_only": True,
    }.items():
        object.__setattr__(receipt, name, value)
    object.__setattr__(bridge, "accepted_risk_archive", object())
    monkeypatch.setattr(index_module, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        index_module._acquisition,
        "require_physical_production_evidence_receipt",
        lambda value: value,
    )
    monkeypatch.setattr(
        bridge_module, "require_physical_production_evidence_bridge", lambda value: value
    )
    output = tmp_path / "physical-index"
    output.mkdir(mode=0o700)
    return index_module._build_test_fixture_physical_production_session_index(
        receipt=receipt, output_root=output
    )


def _physical_builder(monkeypatch, tmp_path: Path, archive):
    index = _physical_index(monkeypatch, tmp_path, archive)
    return scoring._begin_test_fixture_physical_streaming_scoring(
        index=index,
        archive=archive,
        global_contract=_global_contract(),
    )


def test_physical_begin_exhausts_real_index_and_avoids_legacy_graphs(
    monkeypatch, tmp_path
):
    archive, _path = _physical_archive(tmp_path)
    builder = _physical_builder(monkeypatch, tmp_path, archive)
    state = scoring._vault_require(builder)

    assert scoring.require_physical_streamed_production_scoring_builder(builder) is builder
    assert state.index.session_count == len(FORMAL_SESSION_GEOMETRY)
    assert not any(
        hasattr(state, name)
        for name in (
            "production_evidence_authority",
            "current_batch",
            "censored_batch",
            "union",
            "row_evidence",
        )
    )
    connection = sqlite3.connect(
        f"{state.spool_path.as_uri()}?mode=ro&immutable=1", uri=True
    )
    try:
        assert connection.execute("SELECT count(*) FROM sessions").fetchone()[0] == len(
            FORMAL_SESSION_GEOMETRY
        )
        assert connection.execute("SELECT count(*) FROM terminals").fetchone()[0] == (
            state.index.current_row_count + state.index.censored_row_count
        )
    finally:
        connection.close()


def test_production_entry_refuses_fixture_before_spool_creation(monkeypatch, tmp_path):
    archive, _path = _physical_archive(tmp_path)
    index = _physical_index(monkeypatch, tmp_path, archive)
    temporary_root = Path(tempfile.gettempdir())
    before = set(temporary_root.glob("arv2-physical-scoring-*"))

    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match="physical streaming scorer parents did not authenticate",
    ):
        scoring.begin_physical_streaming_scoring(
            index=index, archive=archive, global_contract=_global_contract()
        )

    assert set(temporary_root.glob("arv2-physical-scoring-*")) == before


def test_begin_refuses_physical_c2_authority_not_bound_to_formal_receipt(
    monkeypatch, tmp_path
):
    archive, _path = _physical_archive(tmp_path)
    index = _physical_index(monkeypatch, tmp_path, archive)
    object.__setattr__(
        index.production_evidence_receipt,
        "evidence_authority_id",
        "arv2-unrelated-physical-authority",
    )
    monkeypatch.setattr(scoring, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        scoring._index,
        "require_physical_production_session_index",
        lambda value: value,
    )

    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical scorer C2 and formal evidence authorities differ"),
    ):
        scoring._begin(
            index=index,
            archive=archive,
            global_contract=_global_contract(),
            permit_fixture=True,
        )


def test_physical_composition_context_refuses_equal_but_cross_source_binding(
    monkeypatch, tmp_path
):
    archive, accepted, *_rest = _full_sparse_formal_fixture(tmp_path)
    contract = _global_contract()
    evidence = archive.capacity.production_evidence_receipt
    physical_receipt = SimpleNamespace(
        preopen_acquisition_receipt=archive.preopen_acquisition_receipt,
        evidence_authority_id=evidence.authority.authority_id,
        evidence_authority_sha256=evidence.authority.authority_sha256,
    )
    index = SimpleNamespace(
        index_id="arv2-fixture-physical-index",
        index_sha256="1" * 64,
        production_evidence_receipt=physical_receipt,
        production_evidence_receipt_id="arv2-fixture-physical-receipt",
        production_evidence_receipt_sha256="2" * 64,
        production_input_archive_id="arv2-fixture-c2",
        production_input_archive_sha256="3" * 64,
        accepted_risk_binding=accepted,
        accepted_risk_binding_sha256=sha256_bytes(
            canonical_json_bytes(accepted.to_record())
        ),
        review_mode=acquisition.NORMAL_REVIEW_MODE,
        independently_reviewed=True,
        owner_review_waived=False,
        historical_availability_claimed=True,
        post_first_formal_backtest_independent_review_required=False,
        session_count=len(FORMAL_SESSION_GEOMETRY),
        current_row_count=accepted.current_admitted_decision_count,
        censored_row_count=accepted.censored_admitted_decision_count,
    )
    state = SimpleNamespace(
        fixture_only=False,
        index=index,
        archive=archive,
        capacity=archive.capacity,
        global_contract=contract,
        next_fold_index=0,
        active_fold=False,
        finalized=False,
    )
    monkeypatch.setattr(scoring, "_state", lambda _builder: state)

    context = scoring.physical_streaming_scoring_composition_context(
        object(), accepted_risk_binding=accepted
    )
    assert context.accepted_risk_binding is accepted
    assert context.lineage.index_id == index.index_id
    assert context.lineage.terminal_archive_id == archive.archive_id

    index.current_row_count += 1
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical formal scoring parent census changed"),
    ):
        scoring.physical_streaming_scoring_composition_context(
            object(), accepted_risk_binding=accepted
        )
    index.current_row_count -= 1

    equal_but_unrelated = dataclasses.replace(accepted)
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact(
            "physical formal accepted-risk parent differs from scoring index"
        ),
    ):
        scoring.physical_streaming_scoring_composition_context(
            object(), accepted_risk_binding=equal_but_unrelated
        )


def test_physical_builder_is_thread_bound_and_failure_removes_spool(
    monkeypatch, tmp_path
):
    archive, _path = _physical_archive(tmp_path)
    builder = _physical_builder(monkeypatch, tmp_path, archive)
    directory = scoring._vault_require(builder).spool_directory
    errors = []

    def cross_thread():
        try:
            scoring.require_physical_streamed_production_scoring_builder(builder)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=cross_thread)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], scoring.PhysicalStreamingScoringError)
    assert not directory.exists()


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="requires POSIX fork authority reset",
)
def test_physical_builder_authority_does_not_survive_fork(monkeypatch, tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = _physical_builder(monkeypatch, tmp_path, archive)
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - child result returned by pipe
        os.close(read_fd)
        try:
            try:
                scoring.require_physical_streamed_production_scoring_builder(builder)
            except scoring.PhysicalStreamingScoringError:
                payload = b"ok"
            else:
                payload = b"inherited"
        except BaseException as exc:
            payload = f"{type(exc).__name__}:{exc}".encode()[:1000]
        os.write(write_fd, payload)
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    ready, _write, _error = select.select([read_fd], [], [], 10)
    if not ready:
        os.kill(child, signal.SIGKILL)
        pytest.fail("forked physical authority check blocked")
    payload = os.read(read_fd, 1000)
    os.close(read_fd)
    waited, status = os.waitpid(child, 0)
    assert waited == child and os.waitstatus_to_exitcode(status) == 0
    assert payload == b"ok"
    assert scoring.require_physical_streamed_production_scoring_builder(builder) is builder


def test_physical_spool_tamper_is_rejected_and_revokes_builder(monkeypatch, tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = _physical_builder(monkeypatch, tmp_path, archive)
    state = scoring._vault_require(builder)
    with state.spool_path.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical scoring spool changed"),
    ):
        scoring.require_physical_streamed_production_scoring_builder(builder)
    assert not state.spool_directory.exists()


def test_spool_reader_binds_authenticated_inode_across_path_replacement(
    monkeypatch, tmp_path
):
    original_path = tmp_path / "authenticated.sqlite3"
    hostile_path = tmp_path / "replacement.sqlite3"
    saved_path = tmp_path / "authenticated.saved"
    for path, value in ((original_path, "authenticated"), (hostile_path, "hostile")):
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES (?)", (value,))
        connection.commit()
        connection.close()
        os.chmod(path, 0o600)
    state = SimpleNamespace(
        spool_path=original_path,
        spool_fingerprint=scoring._file_fingerprint(original_path),
    )
    original_connect = sqlite3.connect
    replaced = False

    def replace_path_then_connect(target, *args, **kwargs):
        nonlocal replaced
        original_path.replace(saved_path)
        hostile_path.replace(original_path)
        replaced = True
        return original_connect(target, *args, **kwargs)

    monkeypatch.setattr(scoring.sqlite3, "connect", replace_path_then_connect)
    connection = scoring._open_spool_reader(state)
    try:
        assert replaced is True
        assert connection.execute("SELECT value FROM marker").fetchone() == (
            "authenticated",
        )
    finally:
        connection.close()
        original_path.replace(hostile_path)
        saved_path.replace(original_path)


def test_underfilled_fold_refusal_exhausts_and_revokes_builder(monkeypatch, tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = _physical_builder(monkeypatch, tmp_path, archive)
    directory = scoring._vault_require(builder).spool_directory

    with pytest.raises(
        legacy.FormalStreamingRunRefusal,
        match=legacy.FormalStreamingRefusalReason.TRAINING_FIT_UNDERFILLED.value,
    ):
        tuple(scoring.iter_physical_streaming_scoring_fold(builder))

    assert id(builder) not in scoring._BUILDERS
    assert not directory.exists()


def _decision_projection(block):
    def rows(values):
        return tuple(
            (
                item.source_view_id,
                item.fold_id,
                item.decision_session,
                item.security_id,
                item.final_scoring_row_sha256,
            )
            for item in values
        )

    def refusals(values):
        return tuple(
            (
                item.source_view_id,
                item.fold_id,
                item.decision_session,
                item.security_id,
                item.disposition,
                item.source_refusal_sha256,
            )
            for item in values
        )

    return (
        block.decision_session,
        rows(block.current_accepted),
        refusals(block.current_refused),
        rows(block.censored_accepted),
        refusals(block.censored_refused),
        block.matched_terminal_count,
        block.matched_terminal_sha256,
    )


def _coverage_projection(value):
    return {
        "source_view_id": value.source_view_id,
        "fold_ids": value.fold_ids,
        "h20_test_intervals": value.h20_test_intervals,
        "ledgers": tuple(item.to_record() for item in value.ledgers),
        "endpoint_status_counts": value.endpoint_status_counts,
        "endpoint_pair_status_counts": value.endpoint_pair_status_counts,
        "direction_status_counts": value.direction_status_counts,
        "raw_canonical_label_counts": value.raw_canonical_label_counts,
        "raw_label_disposition_counts": value.raw_label_disposition_counts,
        "canonical_label_disposition_counts": value.canonical_label_disposition_counts,
        "raw_form_collision_counts": value.raw_form_collision_counts,
        "date_diagnostic_counts": value.date_diagnostic_counts,
        "diagnostic_ratios": tuple(item.to_record() for item in value.diagnostic_ratios),
        "ready": value.ready,
        "reasons": value.reasons,
    }


def _synthetic_power_runner(
    monkeypatch,
    tmp_path,
    *,
    consumer,
    calibration_sessions=None,
    lease_current=True,
    counts=None,
):
    fold = power._calibration_fold()
    axis = (
        ("2018-01-31", "2018-02-01")
        if calibration_sessions is None
        else calibration_sessions
    )
    limit_names = (
        "max_retained_input_graph_bytes",
        "max_industry_level_count_per_arm_fold",
    )
    evidence = SimpleNamespace(
        receipt_id="fixture-evidence",
        receipt_sha256="e" * 64,
    )
    archive = object.__new__(legacy.PhysicalPreopenTerminalArchive)
    object.__setattr__(archive, "archive_id", "fixture-terminal-archive")
    object.__setattr__(archive, "archive_sha256", "a" * 64)
    object.__setattr__(
        archive,
        "capacity",
        SimpleNamespace(
            limits=((limit_names[0], 10**9), (limit_names[1], 10)),
            production_evidence_receipt=evidence,
        ),
    )
    index = SimpleNamespace(
        accepted_risk_binding=None,
        accepted_risk_binding_sha256=None,
        index_id="fixture-index",
        index_sha256="1" * 64,
        production_evidence_receipt_id="fixture-physical-receipt",
        production_evidence_receipt_sha256="2" * 64,
        production_input_archive_id="fixture-c2",
        production_input_archive_sha256="3" * 64,
    )
    contract = SimpleNamespace(map_id="fixture-map", map_hash="4" * 64)
    observed = tuple(sorted({
        "maximum_physical_session_terminal_count": 0,
        "maximum_physical_session_uncompressed_bytes": 0,
        "maximum_active_contribution_count_per_arm_session": 0,
        "maximum_session_contribution_lineage_count": 0,
        "maximum_industry_level_count_per_arm_fold": 0,
        "maximum_disk_mgs_width": 0,
        "maximum_disk_mgs_live_decimal_count": 0,
        "maximum_disk_mgs_spool_row_count": 0,
        "maximum_disk_mgs_spool_byte_count": 0,
        "maximum_disk_mgs_spool_file_count": 0,
        "maximum_test_session_terminal_count_per_arm": 0,
        "retained_input_graph_bytes": 0,
    }.items()))
    state = SimpleNamespace(
        fixture_only=True,
        next_fold_index=0,
        active_fold=False,
        finalized=False,
        index=index,
        archive=archive,
        capacity=archive.capacity,
        global_contract=contract,
        base_retained_input_graph_bytes=0,
        spool_path=tmp_path / "synthetic-spool",
        spool_fingerprint=("synthetic",),
        observed=observed,
    )
    sessions = tuple(
        SimpleNamespace(
            decision_session=session,
            terminal_block=SimpleNamespace(terminal_count=1),
        )
        for session in ("2013-01-02", *axis)
    )
    precontrol = SimpleNamespace(
        state=ScoreState.ACTIVE,
        industry_id="industry-a",
        transformed_controls=(Decimal(0),) * len(scoring.CONTROL_COLUMNS),
        firm_reliable_score=Decimal("1"),
        global_reliable_score=Decimal("1"),
    )
    decision = object.__new__(FinalDecisionInput)
    object.__setattr__(decision, "security_id", "security-a")
    object.__setattr__(decision, "row_sha256", "5" * 64)

    class FakeConnection:
        def close(self):
            return None

    class FakeQr:
        def __init__(self, width, _limits):
            self.width = width
            self.decimal_count = width
            self.row_count = 0
            self.peak_spool_bytes = 0
            self.peak_spool_files = 1

        def update(self, *_args):
            self.row_count += 1

        def _cleanup(self):
            return None

    model = legacy.StreamedControlModel(
        model_id="pending",
        model_sha256="0" * 64,
        schema=legacy.STREAMING_MODEL_SCHEMA,
        signal_arm=SignalArm.CURRENT_VINTAGE,
        fold_id=fold.fold_id,
        columns=("intercept",),
        industry_levels=("industry-a",),
        reference_industry="industry-a",
        firm_coefficients=(Decimal(0),),
        global_coefficients=(Decimal(0),),
        active_training_rows=1,
    )
    model_seed = model.to_record()
    model_seed.pop("model_id")
    model_seed.pop("model_sha256")
    model_sha = sha256_bytes(canonical_json_bytes(model_seed))
    model = dataclasses.replace(
        model,
        model_id=f"arv2-streamed-production-control-current_vintage-{model_sha[:20]}",
        model_sha256=model_sha,
    )
    lease = object()
    if counts is None:
        counts = {"passes": 0, "revokes": 0, "finalizes": 0}
    monkeypatch.setattr(scoring, "_require_dependencies", lambda: None)
    monkeypatch.setattr(scoring, "_state", lambda _builder: state)
    monkeypatch.setattr(
        scoring, "_vault_acquire", lambda _builder, _purpose: (state, lease)
    )
    monkeypatch.setattr(
        scoring,
        "_vault_require_lease",
        lambda _builder, candidate, purpose: (
            state
            if lease_current
            and candidate is lease
            and purpose == "power_calibration"
            else None
        ),
    )
    monkeypatch.setattr(
        scoring,
        "_vault_revoke",
        lambda _builder: counts.__setitem__("revokes", counts["revokes"] + 1),
    )
    monkeypatch.setattr(
        scoring,
        "_vault_finalize_power_stream",
        lambda _builder, candidate, _value: (
            counts.__setitem__("finalizes", counts["finalizes"] + 1)
            if candidate is lease
            else None
        ),
    )
    monkeypatch.setattr(scoring, "_open_spool_reader", lambda _state: FakeConnection())
    monkeypatch.setattr(scoring, "_scoring_ordinals", lambda _connection: {})
    monkeypatch.setattr(scoring, "_retained_object_graph_bytes", lambda *_args: 0)

    def verified(_state, _connection, _observed):
        counts["passes"] += 1
        yield from sessions

    monkeypatch.setattr(scoring, "_verified_sessions", verified)
    monkeypatch.setattr(
        scoring,
        "_score_session_arm",
        lambda **_kwargs: ((precontrol,), (), (), ()),
    )
    monkeypatch.setattr(scoring, "_DiskBackedDecimalMgs", FakeQr)
    monkeypatch.setattr(scoring, "_build_streamed_model", lambda **_kwargs: model)
    monkeypatch.setattr(scoring, "_apply_streamed_model", lambda *_args: decision)
    monkeypatch.setattr(scoring, "_file_fingerprint", lambda _path: ("synthetic",))
    monkeypatch.setattr(
        scoring,
        "_require_test_fixture_physical_power_calibration_stream",
        lambda value: value,
    )
    result = scoring._run_test_fixture_physical_power_calibration_stream(
        object(),
        calibration_fold=fold,
        calibration_fold_sha256=power.CALIBRATION_FOLD_HASH,
        calibration_sessions=axis,
        calibration_axis_sha256="6" * 64,
        consumer=consumer,
    )
    return result, counts


def test_physical_power_runner_is_three_pass_and_releases_each_session_block(
    monkeypatch, tmp_path
) -> None:
    block_refs = []
    projections = []

    def consume(block):
        block_refs.append(weakref.ref(block))
        projections.append(block.to_record())

    result, counts = _synthetic_power_runner(
        monkeypatch, tmp_path, consumer=consume
    )
    gc.collect()
    assert counts == {"passes": 3, "revokes": 0, "finalizes": 1}
    assert len(projections) == result.calibration_session_count == 2
    assert result.accepted_decision_count == 2
    assert result.preoutcome_refusal_count == 0
    assert result.physical_replay_pass_count == 3
    assert all(reference() is None for reference in block_refs)


def test_physical_power_runner_callback_value_refuses_and_revokes(
    monkeypatch, tmp_path
) -> None:
    counts = {"passes": 0, "revokes": 0, "finalizes": 0}
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical calibration consumer returned a value"),
    ):
        _synthetic_power_runner(
            monkeypatch,
            tmp_path,
            consumer=lambda _block: object(),
            counts=counts,
        )
    assert counts["revokes"] == 1
    assert counts["finalizes"] == 0


def test_physical_power_runner_callback_cannot_mutate_delivered_block(
    monkeypatch, tmp_path
) -> None:
    counts = {"passes": 0, "revokes": 0, "finalizes": 0}

    def mutate(block):
        object.__setattr__(block, "block_sha256", "8" * 64)

    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical calibration callback mutated its block"),
    ):
        _synthetic_power_runner(
            monkeypatch,
            tmp_path,
            consumer=mutate,
            counts=counts,
        )
    assert counts["revokes"] == 1
    assert counts["finalizes"] == 0


def test_physical_power_runner_refuses_changed_axis_before_acquiring(
    monkeypatch, tmp_path
) -> None:
    counts = {"passes": 0, "revokes": 0, "finalizes": 0}
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical power-calibration axis or consumer changed"),
    ):
        _synthetic_power_runner(
            monkeypatch,
            tmp_path,
            consumer=lambda _block: None,
            calibration_sessions=("2018-02-01", "2018-01-31"),
            counts=counts,
        )
    assert counts == {"passes": 0, "revokes": 0, "finalizes": 0}


def test_physical_power_runner_refuses_state_change_after_callback(
    monkeypatch, tmp_path
) -> None:
    counts = {"passes": 0, "revokes": 0, "finalizes": 0}
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical calibration scorer changed after callback"),
    ):
        _synthetic_power_runner(
            monkeypatch,
            tmp_path,
            consumer=lambda _block: None,
            lease_current=False,
            counts=counts,
        )
    assert counts["revokes"] == 1
    assert counts["finalizes"] == 0


def _legacy_power_projection(builder):
    fold = power._calibration_fold()
    axis = power.calibration_axis()

    def consume(state, observed):
        levels = set()
        for block in legacy._iter_verified_sessions(state, observed):
            partition = fold.partition(block.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            rows, _refusals = legacy._score_session_arm(
                state,
                fold,
                partition,
                block,
                SignalArm.CURRENT_VINTAGE,
                observed,
            )
            levels.update(
                row.industry_id for row in rows
                if row.state is ScoreState.ACTIVE
            )
        ordered_levels = tuple(sorted(levels))
        qr = legacy._DiskBackedDecimalMgs(
            1 + len(scoring.CONTROL_COLUMNS) + len(ordered_levels) - 1,
            dict(state.archive.capacity.limits),
        )
        for block in legacy._iter_verified_sessions(state, observed):
            partition = fold.partition(block.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            rows, _refusals = legacy._score_session_arm(
                state,
                fold,
                partition,
                block,
                SignalArm.CURRENT_VINTAGE,
                observed,
            )
            for row in rows:
                if row.state is ScoreState.ACTIVE:
                    qr.update(
                        (
                            Decimal(1),
                            *row.transformed_controls,
                            *(
                                Decimal(row.industry_id == level)
                                for level in ordered_levels[1:]
                            ),
                        ),
                        row.firm_reliable_score,
                        row.global_reliable_score,
                    )
        model = legacy._build_streamed_model(
            arm=SignalArm.CURRENT_VINTAGE,
            fold=fold,
            levels=ordered_levels,
            qr=qr,
        )
        records = []
        for block in legacy._iter_verified_sessions(state, observed):
            if block.decision_session not in set(axis):
                continue
            rows, refusals = legacy._score_session_arm(
                state,
                fold,
                FoldPartition.VALIDATION,
                block,
                SignalArm.CURRENT_VINTAGE,
                observed,
            )
            accepted = []
            terminal_refusals = list(refusals)
            for row in rows:
                adjusted = legacy._apply_streamed_model(model, row)
                if type(adjusted) is FinalDecisionInput:
                    accepted.append(adjusted)
                else:
                    terminal_refusals.append(adjusted)
            records.append((
                block.decision_session,
                tuple(
                    (item.security_id, item.row_sha256)
                    for item in sorted(accepted, key=lambda item: item.security_id)
                ),
                tuple(
                    (item.security_id, item.refusal_sha256)
                    for item in sorted(
                        terminal_refusals, key=lambda item: item.security_id
                    )
                ),
            ))
        return model, tuple(records)

    return legacy._run_accepted_risk_power_calibration_stream(builder, consume)


def test_physical_power_stream_matches_legacy_and_reauthenticates_parents(
    monkeypatch, tmp_path
) -> None:
    archive, *_rest = _full_sparse_formal_fixture(tmp_path)
    physical_builder = _physical_builder(monkeypatch, tmp_path, archive)
    physical_state = scoring._vault_require(physical_builder)
    legacy_builder = legacy.begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    physical_records = []

    def consume(block):
        physical_records.append((
            block.decision_session,
            tuple(
                (item.security_id, item.row_sha256)
                for item in block.accepted
            ),
            tuple(
                (item.security_id, item.refusal_sha256)
                for item in block.refused
            ),
        ))

    physical_stream = (
        scoring._run_test_fixture_physical_power_calibration_stream(
            physical_builder,
            calibration_fold=power._calibration_fold(),
            calibration_fold_sha256=power.CALIBRATION_FOLD_HASH,
            calibration_sessions=power.calibration_axis(),
            calibration_axis_sha256=power.CALIBRATION_AXIS_SHA256,
            consumer=consume,
        )
    )
    legacy_model, legacy_records = _legacy_power_projection(legacy_builder)
    assert physical_stream.model.to_record() == legacy_model.to_record()
    assert tuple(physical_records) == legacy_records
    assert physical_stream.physical_replay_pass_count == 3
    assert physical_stream.calibration_session_count == len(power.calibration_axis())

    index_ref = weakref.ref(physical_state.index)
    archive_ref = weakref.ref(physical_state.archive)
    contract_ref = weakref.ref(physical_state.global_contract)
    del physical_builder, physical_state, archive
    gc.collect()
    assert index_ref() is physical_stream.physical_index
    assert archive_ref() is physical_stream.terminal_archive
    assert contract_ref() is physical_stream.global_contract
    assert (
        scoring._require_test_fixture_physical_power_calibration_stream(
            physical_stream
        )
        is physical_stream
    )
    original_axis_sha = physical_stream.calibration_axis_sha256
    object.__setattr__(physical_stream, "calibration_axis_sha256", "not-a-hash")
    try:
        with pytest.raises(
            scoring.PhysicalStreamingScoringError,
            match=_exact("physical power-calibration commitment changed"),
        ):
            scoring._require_test_fixture_physical_power_calibration_stream(
                physical_stream
            )
    finally:
        object.__setattr__(
            physical_stream, "calibration_axis_sha256", original_axis_sha
        )
    original_terminal_sha = physical_stream.calibration_terminal_sha256
    object.__setattr__(
        physical_stream, "calibration_terminal_sha256", "not-a-hash"
    )
    try:
        with pytest.raises(
            scoring.PhysicalStreamingScoringError,
            match=_exact("physical power-calibration commitment changed"),
        ):
            scoring._require_test_fixture_physical_power_calibration_stream(
                physical_stream
            )
    finally:
        object.__setattr__(
            physical_stream,
            "calibration_terminal_sha256",
            original_terminal_sha,
        )
    original_count = physical_stream.accepted_decision_count
    object.__setattr__(
        physical_stream, "accepted_decision_count", original_count + 1
    )
    try:
        with pytest.raises(
            scoring.PhysicalStreamingScoringError,
            match=_exact(
                "physical power-calibration stream changed after sealing"
            ),
        ):
            scoring._require_test_fixture_physical_power_calibration_stream(
                physical_stream
            )
    finally:
        object.__setattr__(
            physical_stream, "accepted_decision_count", original_count
        )
    if hasattr(os, "fork") and hasattr(os, "register_at_fork"):
        read_fd, write_fd = os.pipe()
        child = os.fork()
        if child == 0:  # pragma: no cover - child result returned by pipe
            os.close(read_fd)
            try:
                scoring._require_test_fixture_physical_power_calibration_stream(
                    physical_stream
                )
            except scoring.PhysicalStreamingScoringError:
                payload = b"ok"
            else:
                payload = b"inherited"
            os.write(write_fd, payload)
            os.close(write_fd)
            os._exit(0)
        os.close(write_fd)
        payload = os.read(read_fd, 16)
        os.close(read_fd)
        _waited, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert payload == b"ok"
    retained_index = index_ref()
    assert retained_index is not None
    original = retained_index.index_sha256
    object.__setattr__(retained_index, "index_sha256", "9" * 64)
    try:
        with pytest.raises(
            scoring.PhysicalStreamingScoringError,
            match=_exact(
                "physical power-calibration retained parent changed"
            ),
        ):
            scoring._require_test_fixture_physical_power_calibration_stream(
                physical_stream
            )
    finally:
        object.__setattr__(retained_index, "index_sha256", original)
    assert (
        scoring._require_test_fixture_physical_power_calibration_stream(
            physical_stream
        )
        is physical_stream
    )
    scoring._POWER_STREAMS[id(physical_stream)] = (
        weakref.ref(physical_stream),
        b"forged",
        (),
        True,
        os.getpid(),
    )
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact(
            "physical power-calibration stream lacks scorer authority"
        ),
    ):
        scoring._require_test_fixture_physical_power_calibration_stream(
            physical_stream
        )


def test_all_folds_match_legacy_and_seal_existing_artifact_semantics(
    monkeypatch, tmp_path
):
    archive, *_rest = _full_sparse_formal_fixture(tmp_path)
    physical = _physical_builder(monkeypatch, tmp_path, archive)
    legacy_builder = legacy.begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )

    physical_blocks = tuple(scoring.iter_physical_streaming_scoring_fold(physical))
    legacy_blocks = tuple(legacy.iter_streamed_production_scoring_fold(legacy_builder))
    physical_commitment = scoring._vault_require(physical).fold_commitments[0]
    legacy_commitment = legacy._state(legacy_builder).fold_commitments[0]

    assert physical_commitment.result_binding == legacy_commitment.result_binding
    assert physical_commitment.model_records == legacy_commitment.model_records
    assert physical_commitment.event_terminal_projection_sha256 == (
        legacy_commitment.event_terminal_projection_sha256
    )
    assert physical_commitment.partition_terminal_counts == (
        legacy_commitment.partition_terminal_counts
    )
    assert physical_commitment.partition_terminal_roots == (
        legacy_commitment.partition_terminal_roots
    )
    assert tuple(map(_decision_projection, physical_blocks)) == tuple(
        map(_decision_projection, legacy_blocks)
    )
    assert tuple(
        _coverage_projection(item)
        for item in physical_commitment.global_comparator_coverages
    ) == tuple(
        _coverage_projection(item)
        for item in legacy_commitment.global_comparator_coverages
    )

    for _fold_id in scoring.FORMAL_PRIMARY_FOLD_IDS[1:]:
        physical_blocks = tuple(
            scoring.iter_physical_streaming_scoring_fold(physical)
        )
        legacy_blocks = tuple(
            legacy.iter_streamed_production_scoring_fold(legacy_builder)
        )
        physical_commitment = scoring._vault_require(physical).fold_commitments[-1]
        legacy_commitment = legacy._state(legacy_builder).fold_commitments[-1]
        assert physical_commitment.result_binding == legacy_commitment.result_binding, (
            _fold_id,
            physical_commitment.result_binding,
            legacy_commitment.result_binding,
        )
        assert physical_commitment.model_records == legacy_commitment.model_records, (
            _fold_id,
            physical_commitment.model_records,
            legacy_commitment.model_records,
        )
        assert tuple(map(_decision_projection, physical_blocks)) == tuple(
            map(_decision_projection, legacy_blocks)
        ), _fold_id
        assert physical_commitment == legacy_commitment

    physical_state = scoring._vault_require(physical)
    legacy_state = legacy._state(legacy_builder)
    assert physical_state.fold_commitments == legacy_state.fold_commitments
    assert physical_state.matched_test_terminal_count == (
        legacy_state.matched_test_terminal_count
    )
    assert physical_state.matched_test_terminal_sha256 == (
        legacy_state.matched_test_terminal_sha256
    )

    physical_artifact = scoring._finish_test_fixture_physical_streaming_scoring(
        physical
    )
    legacy_artifact = legacy.finish_streamed_production_scoring(legacy_builder)
    assert physical_artifact.result_bindings == legacy_artifact.result_bindings
    assert physical_artifact.fold_commitments == legacy_artifact.fold_commitments
    assert physical_artifact.pooled_global_comparator_coverages == (
        legacy_artifact.pooled_global_comparator_coverages
    )
    assert physical_artifact.matched_test_terminal_count == (
        legacy_artifact.matched_test_terminal_count
    )
    assert physical_artifact.matched_test_terminal_sha256 == (
        legacy_artifact.matched_test_terminal_sha256
    )
    physical_record = physical_artifact.to_record()
    legacy_record = legacy_artifact.to_record()
    physical_record.pop("observed_capacity")
    legacy_record.pop("observed_capacity")
    assert physical_record == legacy_record
    assert (
        scoring._require_test_fixture_physical_streamed_production_scoring_artifact(
            physical_artifact
        )
        is physical_artifact
    )
    retained = scoring._vault_artifact_current(physical_artifact)
    assert retained is not None
    assert retained[3] is physical_state.index
    assert retained[4] is physical_state.archive
    index_ref = weakref.ref(physical_state.index)
    archive_ref = weakref.ref(physical_state.archive)
    del physical_state, physical, archive
    gc.collect()
    assert index_ref() is not None
    assert archive_ref() is not None
    retained_index = index_ref()
    assert retained_index is not None
    original_index_sha256 = retained_index.index_sha256
    object.__setattr__(retained_index, "index_sha256", "9" * 64)
    try:
        with pytest.raises(
            scoring.PhysicalStreamingScoringError,
            match=_exact("physical scoring artifact retained parent changed"),
        ):
            scoring._require_test_fixture_physical_streamed_production_scoring_artifact(
                physical_artifact
            )
    finally:
        object.__setattr__(
            retained_index, "index_sha256", original_index_sha256
        )
    assert (
        scoring._require_test_fixture_physical_streamed_production_scoring_artifact(
            physical_artifact
        )
        is physical_artifact
    )


def test_scoring_ordinals_retain_nondecision_nyse_sessions():
    connection = sqlite3.connect(":memory:", isolation_level=None)
    for statement in scoring._CREATE_DERIVED_SQL:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO contributions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            0,
            0,
            "2024-01-31",
            "security-00",
            "firm-00",
            "event-00",
            b"[]\n",
            b"{}\n",
        ),
    )
    try:
        ordinals = scoring._scoring_ordinals(connection)
    finally:
        connection.close()

    assert "2025-01-02" not in scoring.FORMAL_SESSION_GEOMETRY
    assert ordinals["2025-01-02"] + 1 == ordinals["2025-01-03"]


def test_capacity_constant_rebinding_is_an_isolated_refusal(monkeypatch):
    monkeypatch.setattr(
        scoring,
        "MAX_PHYSICAL_SCORING_RECORD_BYTES",
        scoring.MAX_PHYSICAL_SCORING_RECORD_BYTES + 1,
    )
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical streaming scoring dependency changed"),
    ):
        scoring._require_dependencies()


def test_nyse_ordinal_primitive_rebinding_is_an_isolated_refusal(monkeypatch):
    monkeypatch.setattr(scoring._legacy, "_stream_ordinals", lambda _values: {})
    with pytest.raises(
        scoring.PhysicalStreamingScoringError,
        match=_exact("physical streaming scoring dependency changed"),
    ):
        scoring._require_dependencies()


def test_visible_contributions_are_byte_bounded_before_decode(monkeypatch):
    connection = sqlite3.connect(":memory:", isolation_level=None)
    for statement in scoring._CREATE_DERIVED_SQL:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO contributions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            0,
            0,
            0,
            "2013-01-02",
            "security-00",
            "",
            "event-00",
            b"[]\n",
            b"payload-too-large-for-declared-bound",
        ),
    )
    decoded = False

    def forbidden_decode(_payload):
        nonlocal decoded
        decoded = True
        raise AssertionError("payload decoded before aggregate capacity check")

    monkeypatch.setattr(scoring, "_decode_firm", forbidden_decode)
    try:
        with pytest.raises(
            legacy.FormalStreamingRunRefusal,
            match=legacy.FormalStreamingRefusalReason.CONTRIBUTION_CAPACITY_EXCEEDED.value,
        ):
            scoring._visible(
                connection,
                arm=SignalArm.CURRENT_VINTAGE,
                kind=0,
                session="2013-01-02",
                security_ids=("security-00",),
                maximum_row_count=10,
                maximum_payload_bytes=1,
            )
        assert decoded is False
    finally:
        connection.close()


def test_coverage_refuses_missing_endpoint_evidence_before_sealing():
    connection = sqlite3.connect(":memory:", isolation_level=None)
    for statement in scoring._CREATE_DERIVED_SQL:
        connection.execute(statement)
    connection.execute(
        "INSERT INTO firm_lineage VALUES (?, ?, ?, ?)",
        (0, "security-00", "2020-01-06", "a" * 64),
    )
    state = scoring._CoverageState(
        fold_id="fold_2020",
        signal_arm=SignalArm.CURRENT_VINTAGE,
        expected_sessions=(),
        next_session_index=0,
        last_test_session_by_security={"security-00": "2020-01-06"},
    )
    try:
        with pytest.raises(
            scoring.PhysicalStreamingScoringError,
            match=_exact("physical coverage endpoint evidence disappeared"),
        ):
            scoring._coverage_finish(
                state,
                connection=connection,
                result_binding=object(),
            )
    finally:
        connection.close()


def test_incremental_coverage_graph_is_bounded_as_both_live_arms():
    coverages = {
        arm: scoring._CoverageState(
            fold_id="fold_2020",
            signal_arm=arm,
            expected_sessions=("2020-01-06",),
            next_session_index=0,
            last_test_session_by_security={},
        )
        for arm in scoring._ARM_ORDER
    }
    state = SimpleNamespace(
        base_retained_input_graph_bytes=1,
        capacity=SimpleNamespace(
            limits=(("max_retained_input_graph_bytes", 1),)
        ),
        archive=SimpleNamespace(
            capacity=SimpleNamespace(
                limits=(("max_retained_input_graph_bytes", 1),)
            )
        ),
    )
    observed = {"retained_input_graph_bytes": 0}

    with pytest.raises(
        legacy.FormalStreamingRunRefusal,
        match=legacy.FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED.value,
    ):
        scoring._enforce_coverage_capacity(state, coverages, observed, 0)

    assert observed["retained_input_graph_bytes"] > 1


def test_global_label_diagnostic_cap_stops_cursor_before_next_row(monkeypatch):
    resolution = scoring._GlobalLabelResolution(
        raw_label="Unknown Future Label",
        raw_label_sha256=scoring._label_digest("Unknown Future Label"),
        canonical_label_sha256=scoring._NO_CANONICAL_LABEL_SHA256,
        status="unknown",
        score_numerator=None,
        score_denominator=None,
    )
    payload = scoring._resolution_payload(resolution)

    class BoundedConnection:
        def execute(self, statement, _parameters=()):
            if statement.startswith("SELECT count(*)"):
                return SimpleNamespace(fetchone=lambda: (1,))
            if statement.startswith("SELECT DISTINCT"):
                def rows():
                    yield ("a" * 64, "upgrades", payload, payload)
                    raise AssertionError("coverage cursor advanced beyond fixed cap")

                return rows()
            return None

        def executemany(self, _statement, _parameters):
            return None

    state = scoring._CoverageState(
        fold_id="fold_2020",
        signal_arm=SignalArm.CURRENT_VINTAGE,
        expected_sessions=(),
        next_session_index=0,
        last_test_session_by_security={},
    )
    monkeypatch.setattr(scoring, "MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS", 0)

    with pytest.raises(
        scoring.PhysicalStreamingScoringCapacityError,
        match=_exact("physical global-label diagnostic census exceeded capacity"),
    ):
        scoring._coverage_finish(
            state,
            connection=BoundedConnection(),
            result_binding=object(),
        )


def test_artifact_public_registry_cannot_self_promote() -> None:
    forged = object.__new__(legacy.StreamedProductionScoringArtifact)
    scoring._ARTIFACTS[id(forged)] = (lambda: forged, b"{}", (), False, os.getpid())
    try:
        with pytest.raises(
            scoring.PhysicalStreamingScoringError,
            match="not builder-authenticated",
        ):
            scoring.require_physical_streamed_production_scoring_artifact(forged)
    finally:
        scoring._ARTIFACTS.pop(id(forged), None)


def test_physical_module_has_no_legacy_materialization_constructor() -> None:
    source = Path(scoring.__file__).read_text()
    assert "ProductionEvidenceAuthority" not in source.replace(
        "``ProductionEvidenceAuthority``", ""
    )
    assert "from research.analyst_revisions_v2.production_input_pipeline import (" not in source
    assert not hasattr(scoring, "ProductionInputBatch")
