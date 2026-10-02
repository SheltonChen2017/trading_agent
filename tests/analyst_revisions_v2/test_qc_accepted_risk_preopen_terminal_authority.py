from __future__ import annotations

import dataclasses
import gc
import hashlib
import tempfile
import weakref
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import (
    accepted_risk_preopen_terminal_authority as subject,
)
from research.analyst_revisions_v2_qc import formal_streaming_input as formal_streaming
from research.analyst_revisions_v2_qc.accepted_risk_qc_symbol_resolution import (
    build_runtime_ticker_binding,
    resolve_owner_accepted_qc_symbols,
)


SHA = "a" * 64
SESSION = "2021-01-04"
ROOT = Path(__file__).resolve().parents[2]


def _binding(security_id: str = "sid-one") -> dict[str, object]:
    return build_runtime_ticker_binding(
        security_id=security_id,
        issuer_id="issuer-" + security_id,
        share_class_id="class-" + security_id,
        listing_id="listing-" + security_id,
        current_snapshot_ticker="ONE" if security_id == "sid-one" else "TWO",
        exchange_mic="XNAS",
        candidate_first_session=SESSION,
        candidate_last_session="2025-12-31",
        source_snapshot_available_at="2026-09-14T01:02:03.000000Z",
        source_row_sha256=hashlib.sha256(("source-" + security_id).encode()).hexdigest(),
        identity_evidence_sha256=hashlib.sha256(
            ("identity-" + security_id).encode()
        ).hexdigest(),
        security_master_admission_sha256=SHA,
        admitted_mapping_inventory_sha256="b" * 64,
        admitted_mapping_count=1,
    )


def _resolution(*, accepted: bool = False):
    if accepted:
        class Sid:
            def __str__(self):
                return "QC SID ONE"

        class Symbol:
            id = Sid()

        return resolve_owner_accepted_qc_symbols(
            [_binding()], symbol_factory=lambda _ticker: Symbol()
        )
    return resolve_owner_accepted_qc_symbols(
        [_binding()], symbol_factory=lambda _ticker: None
    )


def _refusal_terminal(
    *, security_id: str = "sid-one", session: str = SESSION,
    qc_security_id: str | None = None,
) -> dict[str, object]:
    refusal = {
        "decision_session": session,
        "security_id": security_id,
        "issuer_id": "issuer-" + security_id,
        "share_class_id": "class-" + security_id,
        "listing_id": "listing-" + security_id,
        "historical_ticker": "ONE",
        "reason": "missing_preopen_controls",
        "source_id": "preopen-source",
        "source_sha256": SHA,
        "available_at": None,
    }
    refusal["refusal_sha256"] = hashlib.sha256(
        canonical_json_bytes(refusal)
    ).hexdigest()
    row = {
        "schema": "arv2-preopen-control-terminal-v1",
        "decision_session": session,
        "security_id": security_id,
        "qc_security_id": qc_security_id,
        "issuer_id": "issuer-" + security_id,
        "share_class_id": "class-" + security_id,
        "listing_id": "listing-" + security_id,
        "security_master_row_sha256": SHA,
        "disposition": "named_refusal",
        "detail_reason": "missing_preopen_controls",
        "eligible_security_session": None,
        "q_data_measurement": None,
        "census_refusal": refusal,
        "input_roots": {
            name: SHA
            for name in (
                "universe", "sid_mapping", "fundamentals", "earnings",
                "guidance", "ratings", "market_observations",
            )
        },
    }
    row["terminal_sha256"] = hashlib.sha256(canonical_json_bytes(row)).hexdigest()
    return row


def _recorder(*, accepted: bool = False):
    return subject.begin_owner_accepted_risk_preopen_terminal_recording(
        symbol_resolution=_resolution(accepted=accepted),
        decision_sessions=(SESSION, "2021-01-05"),
    )


def _summary(count: int = 1, *, resolution=None) -> dict[str, object]:
    resolution = resolution or _resolution()
    record = {
        "schema": subject.DIRECT_SUMMARY_SCHEMA,
        "summary_id": None,
        "summary_sha256": None,
        "source_input_manifest_sha256": "b" * 64,
        "symbol_resolution_sha256": resolution.resolution_sha256,
        "terminal_emission_count": count,
        "peer_aggregate_projection_sha256": "c" * 64,
        "market_session_projection_sha256": "d" * 64,
        "emission_order": (
            "security_batch_then_decision_chunk_then_decision_session_then_security_id"
        ),
        "object_store_terminal_writes": 0,
        "preliminary_evaluation_only": True,
        "formal_security_master_authority": False,
        "frozen_formal_evaluation_completed": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    record["summary_id"] = "arv2-direct-preopen-emission-" + digest[:24]
    record["summary_sha256"] = digest
    return record


def _assert_reason(expected, operation):
    with pytest.raises(subject.AcceptedRiskPreopenTerminalError) as captured:
        operation()
    assert captured.value.reason is expected


def test_batch_major_spool_seals_and_replays_empty_sessions_repeatedly():
    recorder = _recorder()
    recorder.consume_terminal(_refusal_terminal())
    authority = subject.finalize_owner_accepted_risk_preopen_terminal_recording(
        recorder=recorder,
        direct_emission_summary=_summary(resolution=recorder.symbol_resolution),
    )

    first = tuple(subject.iter_owner_accepted_risk_preopen_terminal_sessions(authority))
    second = tuple(subject.iter_owner_accepted_risk_preopen_terminal_sessions(authority))

    assert [item.decision_session for item in first] == [SESSION, "2021-01-05"]
    assert [item.terminal_count for item in first] == [1, 0]
    assert first == second
    assert authority.replay_passes_completed == 2
    assert authority.point_in_time is False
    assert authority.independently_reviewed is False
    assert authority.formal_lifecycle_authority is False
    assert authority.host_object_store_export_performed is False
    assert authority.raw_terminal_rows_spooled_process_locally is False
    assert authority.terminal_replay_projections_spooled_process_locally is True


def test_exact_first_run_geometry_exceeds_old_twelve_million_cap_with_headroom():
    capacity = subject._terminal_geometry_capacity(
        session_count=3_270, security_count=6_217
    )

    assert capacity == 20_329_590
    assert capacity > 12_000_000
    assert capacity < subject.MAX_TERMINAL_COUNT


@pytest.mark.parametrize(
    "relative",
    (
        "research/analyst_revisions_v2_qc/accepted_risk_preopen_terminal_authority.py",
        "research/analyst_revisions_v2_qc/accepted_risk_terminal_disposition.py",
    ),
)
def test_new_qc_runtime_source_compiles_after_an_injected_prelude(relative):
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "from __future__ import" not in source

    compile("QC_PRELUDE_SENTINEL = True\n" + source, relative, "exec")


def test_batch_ingestion_authenticates_resolution_once_and_uses_cached_indexes(
    monkeypatch,
):
    recorder = _recorder()
    original = subject.require_accepted_risk_qc_symbol_resolution
    calls = 0

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(subject, "require_accepted_risk_qc_symbol_resolution", counted)
    recorder.consume_terminal_batch(
        [_refusal_terminal(), _refusal_terminal(session="2021-01-05")]
    )

    assert calls == 1
    state = subject._RECORDERS[id(recorder)]
    assert state.session_counts == {SESSION: 1, "2021-01-05": 1}
    assert state.resolved_by_security == {}
    assert state.refused_security == {"sid-one"}


def test_commitment_derivation_releases_each_session_before_loading_the_next(
    monkeypatch,
):
    prior: list[weakref.ReferenceType[list[object]]] = []
    calls: list[str] = []

    class TrackedList(list):
        pass

    def one_session(_connection, session, **_kwargs):
        gc.collect()
        if prior:
            assert prior[-1]() is None
        rows = TrackedList()
        prior.append(weakref.ref(rows))
        calls.append(session)
        return rows

    monkeypatch.setattr(subject, "_session_compact_records", one_session)
    result = subject._derive(
        object(),
        (SESSION, "2021-01-05", "2021-01-06"),
        authentication_key=b"x" * 32,
        maximum_session_count=1,
    )

    assert calls == [SESSION, "2021-01-05", "2021-01-06"]
    assert result[:3] == (0, 0, 0)


def test_authority_changed_refusal_is_isolated():
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
        lambda: subject.begin_owner_accepted_risk_preopen_terminal_recording(
            symbol_resolution=_resolution(), decision_sessions=(SESSION, SESSION)
        ),
    )


def test_terminal_schema_invalid_refusal_is_isolated():
    recorder = _recorder()
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_SCHEMA_INVALID,
        lambda: recorder.consume_terminal({}),
    )


def test_terminal_hash_changed_refusal_is_isolated():
    recorder = _recorder()
    row = _refusal_terminal()
    row["terminal_sha256"] = "f" * 64
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_HASH_CHANGED,
        lambda: recorder.consume_terminal(row),
    )


def test_terminal_duplicate_refusal_is_isolated():
    recorder = _recorder()
    row = _refusal_terminal()
    recorder.consume_terminal(row)
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_DUPLICATE,
        lambda: recorder.consume_terminal(row),
    )


def test_session_outside_axis_refusal_is_isolated():
    recorder = _recorder()
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.SESSION_OUTSIDE_AXIS,
        lambda: recorder.consume_terminal(
            _refusal_terminal(session="2021-01-06")
        ),
    )


def test_security_outside_resolution_refusal_is_isolated():
    recorder = _recorder()
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.SECURITY_OUTSIDE_RESOLUTION,
        lambda: recorder.consume_terminal(_refusal_terminal(security_id="sid-two")),
    )


def test_qc_sid_mismatch_refusal_is_isolated():
    recorder = _recorder()
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.QC_SID_MISMATCH,
        lambda: recorder.consume_terminal(
            _refusal_terminal(qc_security_id="unexpected-qc-sid")
        ),
    )


def test_disposition_conflicts_resolution_refusal_is_isolated(monkeypatch):
    recorder = _recorder()
    row = _refusal_terminal()
    row["disposition"] = "accepted"
    semantic = dict(row)
    semantic.pop("terminal_sha256")
    row["terminal_sha256"] = hashlib.sha256(
        canonical_json_bytes(semantic)
    ).hexdigest()
    monkeypatch.setattr(
        subject._semantics,
        "validate_preopen_terminal_semantics",
        lambda row: dict(row),
    )
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.DISPOSITION_CONFLICTS_RESOLUTION,
        lambda: recorder.consume_terminal(row),
    )


def test_stream_binding_changed_refusal_is_isolated():
    recorder = _recorder()
    recorder.consume_terminal(_refusal_terminal())
    hostile = _summary(resolution=recorder.symbol_resolution)
    hostile["object_store_terminal_writes"] = 1
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
        lambda: subject.finalize_owner_accepted_risk_preopen_terminal_recording(
            recorder=recorder, direct_emission_summary=hostile
        ),
    )


def test_census_changed_refusal_is_isolated():
    recorder = _recorder()
    recorder.consume_terminal(_refusal_terminal())
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.CENSUS_CHANGED,
        lambda: subject.finalize_owner_accepted_risk_preopen_terminal_recording(
            recorder=recorder,
            direct_emission_summary=_summary(2, resolution=recorder.symbol_resolution),
        ),
    )


def test_storage_changed_refusal_is_isolated():
    recorder = _recorder()
    recorder.consume_terminal(_refusal_terminal())
    authority = subject.finalize_owner_accepted_risk_preopen_terminal_recording(
        recorder=recorder,
        direct_emission_summary=_summary(resolution=recorder.symbol_resolution),
    )
    state = subject._AUTHORITIES[id(authority)]
    with state.path.open("ab") as stream:
        stream.write(b"hostile")
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
        lambda: subject.require_owner_accepted_risk_preopen_terminal_authority(
            authority
        ),
    )


def test_capacity_exceeded_refusal_is_isolated(monkeypatch):
    recorder = _recorder()
    monkeypatch.setattr(subject, "MAX_TERMINAL_BYTES", 1)
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.CAPACITY_EXCEEDED,
        lambda: recorder.consume_terminal(_refusal_terminal()),
    )


def test_public_authority_mutation_is_refused():
    recorder = _recorder()
    recorder.consume_terminal(_refusal_terminal())
    authority = subject.finalize_owner_accepted_risk_preopen_terminal_recording(
        recorder=recorder,
        direct_emission_summary=_summary(resolution=recorder.symbol_resolution),
    )
    object.__setattr__(authority, "point_in_time", True)
    _assert_reason(
        subject.AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
        lambda: subject.require_owner_accepted_risk_preopen_terminal_authority(
            authority
        ),
    )


def test_formal_decimal_spool_uses_platform_scratch_root_not_macos_literal():
    limits = {
        "max_disk_mgs_width": 2,
        "max_disk_mgs_live_decimal_count": 100,
        "max_disk_mgs_spool_file_count": 10,
        "max_disk_mgs_spool_byte_count": 1024 * 1024,
    }
    spool = formal_streaming._DiskBackedDecimalMgs(1, limits)
    try:
        assert spool._directory.parent.resolve() == Path(tempfile.gettempdir()).resolve()
        assert str(spool._directory).startswith(tempfile.gettempdir())
        assert "/private/tmp/" not in str(spool._directory)
    finally:
        spool._design.close()
        spool._temporary.cleanup()
