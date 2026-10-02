"""Focused lifecycle-derived terminal-disposition builder tests."""
from __future__ import annotations

import ast
import json
import os
import types
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    sha256_bytes,
)
from research.analyst_revisions_v2_qc import formal_cloud_evaluator as cloud
from research.analyst_revisions_v2_qc import formal_evaluation as evaluation
from research.analyst_revisions_v2_qc import (
    formal_terminal_disposition_builder as terminal,
)
from research.analyst_revisions_v2_qc.formal_input_composer import (
    _decision_terminal_slot_id,
    _economic_terminal_slot_id,
)
from scripts import build_arv2_historical_preopen_bridge as historical


def test_builder_has_no_float_or_qc_delisting_payoff_surface():
    source = Path(terminal.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(
        isinstance(node, ast.Constant) and isinstance(node.value, float)
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
        for node in ast.walk(tree)
    )
    assert "delisting.price" not in source


def _lifecycle_row(
    *,
    session: date,
    session_ordinal: int,
    source_ordinal: int,
    security_id: str,
    delisting_date: str | None,
) -> dict[str, object]:
    identity = sha256_bytes(("identity:" + security_id).encode("ascii"))
    mapping = sha256_bytes(("mapping:" + security_id).encode("ascii"))
    source = sha256_bytes(
        (
            "source:"
            + session.isoformat()
            + ":"
            + security_id
            + ":"
            + str(source_ordinal)
        ).encode("ascii")
    )
    semantic: dict[str, object] = {
        "schema": historical.UNIVERSE_LIFECYCLE_BINDING_SCHEMA,
        "decision_session": session.isoformat(),
        "decision_session_ordinal": session_ordinal,
        "decision_open_utc": session.isoformat() + "T14:30:00.000000Z",
        "source_ordinal": source_ordinal,
        "discovery_disposition": "accepted",
        "discovery_refusal_reason": None,
        "qc_security_id": "QC-" + security_id,
        "cusip": "000000AA0",
        "display_ticker_non_authoritative": "TEST",
        "logical_security_id": security_id,
        "issuer_id": "issuer-" + security_id,
        "share_class_id": "share-" + security_id,
        "listing_id": "listing-" + security_id,
        "delisting_date": delisting_date,
        "available_at": session.isoformat() + "T13:00:00.000000Z",
        "identity_evidence_sha256": identity,
        "source_terminal_sha256": source,
        "mapping_row_sha256": mapping,
        "bridge_join_disposition": "accepted",
        "bridge_join_reason": None,
        "lifecycle_evidence_only": True,
        "payoff_semantics_assigned": False,
    }
    return {
        **semantic,
        "binding_sha256": sha256_bytes(canonical_json_bytes(semantic)),
    }


def _fake_bridge(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sessions: tuple[date, ...],
    terminal_states: dict[str, tuple[str | None, ...]],
    canonical_row_order: bool = False,
) -> object:
    assert sessions
    assert all(len(values) == len(sessions) for values in terminal_states.values())
    rows: list[dict[str, object]] = []
    for session_ordinal, session in enumerate(sessions, 1):
        for source_ordinal, security_id in enumerate(sorted(terminal_states)):
            rows.append(
                _lifecycle_row(
                    session=session,
                    session_ordinal=session_ordinal,
                    source_ordinal=source_ordinal,
                    security_id=security_id,
                    delisting_date=terminal_states[security_id][
                        session_ordinal - 1
                    ],
                )
            )
    if canonical_row_order:
        rows.sort(key=lambda row: str(row["binding_sha256"]))
    payload = b"".join(canonical_json_bytes(row) for row in rows)
    shard = historical.ReviewedHistoricalUniverseLifecycleBindingShard(
        ordinal=0,
        row_count=len(rows),
        compressed_sha256="1" * 64,
        compressed_byte_count=len(payload),
        uncompressed_sha256=sha256_bytes(payload),
        uncompressed_byte_count=len(payload),
        canonical_json_lines=payload,
    )
    bridge = types.SimpleNamespace(
        bridge_id="arv2-test-historical-lifecycle-bridge",
        bridge_sha256="2" * 64,
        universe_lifecycle_binding_inventory_sha256="3" * 64,
        universe_lifecycle_binding_shard_count=1,
        universe_lifecycle_binding_row_count=len(rows),
        first_session=sessions[0].isoformat(),
        last_session=sessions[-1].isoformat(),
    )
    monkeypatch.setattr(
        historical,
        "require_reviewed_historical_universe_to_preopen_bridge",
        lambda value: value,
    )
    monkeypatch.setattr(
        historical,
        "iter_reviewed_historical_universe_lifecycle_binding_shards",
        lambda value: iter((shard,)),
    )
    return bridge


def test_lifecycle_ingestion_is_order_independent_but_coordinate_exact(
    monkeypatch, tmp_path
):
    sessions = trading_sessions(date(2024, 1, 2), date(2024, 5, 31))
    bridge = _fake_bridge(
        monkeypatch,
        sessions=sessions,
        terminal_states={
            "security-active": tuple(None for _ in sessions),
            "security-second": tuple(None for _ in sessions),
        },
        canonical_row_order=True,
    )
    physical_order = []
    shard = next(
        historical.iter_reviewed_historical_universe_lifecycle_binding_shards(
            bridge
        )
    )
    for line in shard.canonical_json_lines.splitlines():
        row = json.loads(line)
        physical_order.append(
            (row["decision_session_ordinal"], row["source_ordinal"])
        )
    assert physical_order != sorted(physical_order)
    recorder = terminal.begin_formal_terminal_disposition_recording(
        historical_bridge=bridge,
        output_directory=tmp_path / "unordered-terminal-build",
    )
    terminal.record_formal_terminal_security(
        recorder, security_id="security-active"
    )
    terminal.record_formal_terminal_slot(
        recorder,
        slot_kind="decision_horizon",
        slot_id="unordered-active-slot",
        horizon_sessions=20,
        security_id="security-active",
        first_session=sessions[0],
        last_session=sessions[20],
    )
    build = terminal.finalize_formal_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 12)
    )
    assert build.lifecycle_row_count == len(sessions) * 2
    assert build.actual_slot_count == 1
    assert build.unaffected_slot_count == 1


def _recorded_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[terminal.FormalTerminalDispositionBuild, dict[str, object]]:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    sessions = trading_sessions(date(2024, 1, 2), date(2024, 6, 28))
    terminal_date = sessions[10].isoformat()
    changed_date = sessions[11].isoformat()
    states = {
        "security-active": tuple(None for _ in sessions),
        "security-ambiguous": tuple(
            None
            if index < 10
            else terminal_date
            if index < 30
            else changed_date
            for index in range(len(sessions))
        ),
        "security-terminal": tuple(
            None if index < 10 else terminal_date
            for index in range(len(sessions))
        ),
    }
    bridge = _fake_bridge(
        monkeypatch, sessions=sessions, terminal_states=states
    )
    recorder = terminal.begin_formal_terminal_disposition_recording(
        historical_bridge=bridge,
        output_directory=tmp_path / "terminal-build",
    )
    for security_id in (
        "security-active",
        "security-ambiguous",
        "security-missing",
        "security-terminal",
    ):
        terminal.record_formal_terminal_security(
            recorder, security_id=security_id
        )

    terminal_decision_id = "decision-terminal"
    terminal.record_formal_terminal_slot(
        recorder,
        slot_kind="decision_horizon",
        slot_id=_decision_terminal_slot_id(
            decision_id=terminal_decision_id, horizon=20
        ),
        horizon_sessions=20,
        security_id="security-terminal",
        first_session=sessions[0],
        last_session=sessions[20],
    )
    economic_slot_id = _economic_terminal_slot_id(
        view_id="current_vintage",
        fold_id="arv2-wf-test-2024",
        session_position=9,
        security_id="security-terminal",
    )
    terminal.record_formal_terminal_slot(
        recorder,
        slot_kind="economic_daily",
        slot_id=economic_slot_id,
        horizon_sessions=None,
        security_id="security-terminal",
        first_session=sessions[9],
        last_session=sessions[10],
    )
    for slot_id, security_id in (
        ("active-covered-slot", "security-active"),
        ("missing-security-slot", "security-missing"),
        ("ambiguous-security-slot", "security-ambiguous"),
    ):
        terminal.record_formal_terminal_slot(
            recorder,
            slot_kind="decision_horizon",
            slot_id=slot_id,
            horizon_sessions=20,
            security_id=security_id,
            first_session=sessions[0],
            last_session=sessions[20],
        )
    outcome_axis, positions = terminal._formal_outcome_axis()
    tail_first = sessions[-1]
    tail_last = outcome_axis[positions[tail_first] + 1]
    terminal.record_formal_terminal_slot(
        recorder,
        slot_kind="economic_daily",
        slot_id="active-post-lifecycle-tail-slot",
        horizon_sessions=None,
        security_id="security-active",
        first_session=tail_first,
        last_session=tail_last,
    )
    build = terminal.finalize_formal_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 12)
    )
    context = {
        "economic_slot_id": economic_slot_id,
        "economic_session": sessions[9],
        "economic_next_session": sessions[10],
    }
    return build, context


def test_builder_emits_exhaustive_decision_economic_and_tail_census(
    monkeypatch, tmp_path
):
    build, _context = _recorded_build(monkeypatch, tmp_path)

    assert terminal.require_formal_terminal_disposition_build(build) is build
    assert build.terminal_package.terminal_census is build.terminal_census
    assert build.security_count == build.lifecycle_coverage_count == 4
    assert build.actual_slot_count == 6
    assert build.unaffected_slot_count == 1
    assert build.terminal_requirement_count == 5
    assert build.known_terminal_refusal_count == 2
    assert build.missing_lifecycle_refusal_count == 2
    assert build.ambiguous_lifecycle_refusal_count == 1
    assert build.silently_omitted_count == 0
    assert len(build.terminal_package.rows) == 5
    assert all(
        row.disposition == "named_terminal_refusal"
        and row.stock_return is None
        for row in build.terminal_package.rows
    )
    reasons = {row.reason for row in build.terminal_package.rows}
    assert reasons == {
        "crsp_equivalent_terminal_payoff_unavailable",
        "missing_lifecycle_evidence_for_actual_slot",
        "ambiguous_or_inconsistent_lifecycle_evidence",
    }
    receipt = terminal.formal_terminal_disposition_build_record(build)
    assert receipt["security_count"] == 4
    assert receipt["actual_slot_count"] == 6
    assert receipt["terminal_census"] == build.terminal_census.to_record()
    assert receipt["qc_delisting_price_used"] is False
    assert receipt["merger_bankruptcy_successor_payoff_inferred"] is False
    assert receipt["terminal_payoff_source_available"] is False


def test_named_terminal_refusal_precedes_numeric_or_fill_forward_bar(
    monkeypatch, tmp_path
):
    build, context = _recorded_build(monkeypatch, tmp_path)
    terminal_row = next(
        row.to_record()
        for row in build.terminal_package.rows
        if row.slot_id == context["economic_slot_id"]
    )
    session = context["economic_session"].isoformat()
    next_session = context["economic_next_session"].isoformat()
    security_id = "security-terminal"
    start_id = cloud.build_daily_market_requirement_id(
        security_id=security_id, session=session
    )
    end_id = cloud.build_daily_market_requirement_id(
        security_id=security_id, session=next_session
    )
    daily = {
        start_id: {"disposition": "observation", "open": "10"},
        end_id: {
            "disposition": "observation",
            "open": "20",
            "fill_forward": True,
        },
    }
    used: set[tuple[str, str, int | None]] = set()
    outcome = cloud._economic_security_outcome(
        view="current_vintage",
        fold="arv2-wf-test-2024",
        position=9,
        session=session,
        next_session=next_session,
        security=security_id,
        benchmark_return=Decimal("0.25"),
        daily=daily,
        terminals={
            ("economic_daily", context["economic_slot_id"], None): terminal_row
        },
        used_terminals=used,
    )
    assert outcome.disposition is evaluation.EconomicOutcomeDisposition.NAMED_REFUSAL
    assert outcome.gross_total_return is None
    assert outcome.reason is evaluation.RefusalReason.TERMINAL_PAYOFF_UNRESOLVED
    assert used == {("economic_daily", context["economic_slot_id"], None)}


def test_recorder_rejects_duplicate_invalid_horizon_and_capacity(
    monkeypatch, tmp_path
):
    sessions = trading_sessions(date(2024, 1, 2), date(2024, 5, 31))
    bridge = _fake_bridge(
        monkeypatch,
        sessions=sessions,
        terminal_states={"security-active": tuple(None for _ in sessions)},
    )
    recorder = terminal.begin_formal_terminal_disposition_recording(
        historical_bridge=bridge,
        output_directory=tmp_path / "bounded-terminal-build",
    )
    terminal.record_formal_terminal_security(
        recorder, security_id="security-active"
    )
    terminal.record_formal_terminal_slot(
        recorder,
        slot_kind="decision_horizon",
        slot_id="bounded-slot",
        horizon_sessions=20,
        security_id="security-active",
        first_session=sessions[0],
        last_session=sessions[20],
    )
    assert terminal.record_formal_terminal_slot(
        recorder,
        slot_kind="decision_horizon",
        slot_id="bounded-slot",
        horizon_sessions=20,
        security_id="security-active",
        first_session=sessions[0],
        last_session=sessions[20],
    ) is False
    with pytest.raises(terminal.FormalTerminalDispositionBuildError, match="repeated"):
        terminal.record_formal_terminal_slot(
            recorder,
            slot_kind="decision_horizon",
            slot_id="bounded-slot",
            horizon_sessions=20,
            security_id="security-active",
            first_session=sessions[1],
            last_session=sessions[21],
        )
    with pytest.raises(
        terminal.FormalTerminalDispositionBuildError, match="outcome-axis"
    ):
        terminal.record_formal_terminal_slot(
            recorder,
            slot_kind="decision_horizon",
            slot_id="invalid-horizon-slot",
            horizon_sessions=20,
            security_id="security-active",
            first_session=sessions[0],
            last_session=sessions[19],
        )

    second = terminal.begin_formal_terminal_disposition_recording(
        historical_bridge=bridge,
        output_directory=tmp_path / "capacity-terminal-build",
    )
    terminal.record_formal_terminal_security(second, security_id="security-active")
    monkeypatch.setattr(terminal, "MAX_ACTUAL_SLOT_COUNT", 1)
    for index, slot_id in enumerate(("slot-one", "slot-two")):
        if index == 0:
            terminal.record_formal_terminal_slot(
                second,
                slot_kind="decision_horizon",
                slot_id=slot_id,
                horizon_sessions=20,
                security_id="security-active",
                first_session=sessions[0],
                last_session=sessions[20],
            )
        else:
            with pytest.raises(
                terminal.FormalTerminalDispositionCapacityRefusal,
                match="slot census",
            ):
                terminal.record_formal_terminal_slot(
                    second,
                    slot_kind="decision_horizon",
                    slot_id=slot_id,
                    horizon_sessions=20,
                    security_id="security-active",
                    first_session=sessions[1],
                    last_session=sessions[21],
                )


def test_artifact_tamper_race_and_symlink_are_refused(monkeypatch, tmp_path):
    build, _context = _recorded_build(monkeypatch, tmp_path)
    active_count = build.lifecycle_active_security_count
    object.__setattr__(
        build, "lifecycle_active_security_count", active_count + 1
    )
    with pytest.raises(terminal.FormalTerminalDispositionBuildError):
        terminal.require_formal_terminal_disposition_build(build)
    object.__setattr__(build, "lifecycle_active_security_count", active_count)
    assert terminal.require_formal_terminal_disposition_build(build) is build
    package = build.terminal_package_path
    original = package.read_bytes()
    package.write_bytes(b"x" + original[1:])
    with pytest.raises(terminal.FormalTerminalDispositionBuildError):
        terminal.require_formal_terminal_disposition_build(build)

    target = tmp_path / "symlink-target"
    target.mkdir(mode=0o700)
    linked = tmp_path / "symlink-output"
    linked.symlink_to(target, target_is_directory=True)
    sessions = trading_sessions(date(2024, 1, 2), date(2024, 5, 31))
    bridge = _fake_bridge(
        monkeypatch,
        sessions=sessions,
        terminal_states={"security-active": tuple(None for _ in sessions)},
    )
    with pytest.raises(terminal.FormalTerminalDispositionBuildError):
        terminal.begin_formal_terminal_disposition_recording(
            historical_bridge=bridge, output_directory=linked
        )

    race_build, _context = _recorded_build(monkeypatch, tmp_path / "race")
    real_read = os.read
    raced = False

    def racing_read(descriptor: int, count: int) -> bytes:
        nonlocal raced
        payload = real_read(descriptor, count)
        if payload and not raced:
            raced = True
            observed = race_build.terminal_package_path.stat()
            os.utime(
                race_build.terminal_package_path,
                ns=(observed.st_atime_ns, observed.st_mtime_ns + 1_000_000),
            )
        return payload

    monkeypatch.setattr(terminal.os, "read", racing_read)
    with pytest.raises(
        terminal.FormalTerminalDispositionBuildError, match="changed while read"
    ):
        terminal.require_formal_terminal_disposition_build(race_build)


def test_real_authenticated_full_axis_sidecar_is_consumed_boundedly(
    monkeypatch, tmp_path
):
    from tests.analyst_revisions_v2 import (
        test_historical_preopen_bridge as bridge_fixture,
    )

    discovery = bridge_fixture._discovery_receipt(monkeypatch, tmp_path)
    physical = bridge_fixture._physical_candidate(monkeypatch, tmp_path)
    bridge = historical.build_reviewed_historical_universe_to_preopen_bridge(
        discovery, physical, tmp_path / "historical-preopen-bridge"
    )
    accepted_row = None
    for shard in historical.iter_reviewed_historical_universe_lifecycle_binding_shards(
        bridge
    ):
        for line in shard.canonical_json_lines.splitlines():
            row = json.loads(line)
            if row["bridge_join_disposition"] == "accepted":
                accepted_row = row
                break
        if accepted_row is not None:
            break
    assert accepted_row is not None
    security_id = accepted_row["logical_security_id"]
    recorder = terminal.begin_formal_terminal_disposition_recording(
        historical_bridge=bridge,
        output_directory=tmp_path / "full-axis-terminal-build",
    )
    terminal.record_formal_terminal_security(recorder, security_id=security_id)
    outcome_axis, positions = terminal._formal_outcome_axis()
    terminal_session = date.fromisoformat(accepted_row["delisting_date"])
    first_session = outcome_axis[positions[terminal_session] - 10]
    last_session = outcome_axis[positions[first_session] + 20]
    terminal.record_formal_terminal_slot(
        recorder,
        slot_kind="decision_horizon",
        slot_id="full-axis-terminal-slot",
        horizon_sessions=20,
        security_id=security_id,
        first_session=first_session,
        last_session=last_session,
    )
    build = terminal.finalize_formal_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 12)
    )
    assert terminal.require_formal_terminal_disposition_build(build) is build
    assert build.session_axis_count == 3270
    assert build.lifecycle_row_count == 6 * 3270
    assert build.actual_slot_count == 1
    assert build.known_terminal_refusal_count == 1
    assert build.terminal_package.rows[0].reason == (
        "crsp_equivalent_terminal_payoff_unavailable"
    )
