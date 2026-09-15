from __future__ import annotations

import dataclasses
import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.production_input_pipeline import SignalArm
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_bridge as physical,
)
from research.analyst_revisions_v2_qc import formal_streaming_input as streaming
from research.analyst_revisions_v2_qc.physical_production_input_archive import (
    build_test_fixture_physical_production_input_archive,
    iter_physical_normalized_evidence_rows,
    physical_production_batch,
)
from tests.analyst_revisions_v2.test_production_evidence_composer import (
    _build as _legacy_composer_build,
)
from tests.analyst_revisions_v2.test_production_evidence_composer import (
    _fixture as _composer_fixture,
)
from tests.analyst_revisions_v2.test_production_input_pipeline import (
    _authority,
)
from tests.analyst_revisions_v2.test_qc_physical_accepted_risk_archive import (
    _build as _build_physical_c1,
)
from tests.analyst_revisions_v2.test_qc_preopen_control_prereview_downloader import (
    _physical_capture as _build_physical_prereview_capture,
)
from tests.analyst_revisions_v2.test_qc_preopen_control_stage import (
    _reviewed_receipt as _build_reviewed_preopen_receipt,
)
from tests.analyst_revisions_v2.test_production_scoring import (
    _install_offline_physical_receipt_requires,
    _offline_physical_requirer,
)


@pytest.fixture(autouse=True)
def _install_offline_composer_receipt_aliases(
    monkeypatch,
    _install_offline_physical_receipt_requires,
):
    require_preopen = lambda value: _offline_physical_requirer("preopen", value)
    monkeypatch.setattr(
        physical._composer,
        "require_reviewed_preopen_control_acquisition_receipt",
        require_preopen,
    )
    monkeypatch.setattr(
        streaming,
        "require_reviewed_preopen_control_acquisition_receipt",
        require_preopen,
    )


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


def test_physical_evidence_iterator_matches_legacy_composer_without_pair_copy(
    monkeypatch,
    tmp_path: Path,
):
    fixture = _composer_fixture(monkeypatch, tmp_path / "parents")
    monkeypatch.setattr(physical, "_require_dependencies", lambda: None)
    legacy = _legacy_composer_build(fixture)
    directory = tmp_path / "spool"
    directory.mkdir(mode=0o700)
    connection, _path = physical._composer._open_spool(directory)
    state = physical._CompositionState()
    try:
        connection.execute(
            "CREATE TABLE physical_composition("
            "ordinal INTEGER PRIMARY KEY, payload BLOB NOT NULL)"
        )
        physical._composer._spool_sidecars(connection, fixture.bridge)
        physical._composer._spool_terminals(connection, fixture.archive)
        rows = physical._iter_composed_evidence_rows(
            source_rows=iter(fixture.pair.rows),
            connection=connection,
            state=state,
            truth_sources=physical._truth_sources(fixture.preopen),
            firm_ontology=fixture.ontology,
            firm_availability=fixture.availability,
        )

        observed = tuple(rows)
        projection = physical._composition_projection(
            connection, state.terminal_count
        )
    finally:
        connection.close()

    assert [item.to_record() for item in observed] == [
        item.to_record() for item in legacy.authority.row_evidence
    ]
    assert state.terminal_count == legacy.candidate_rating_row_count == 20
    assert projection == legacy.composition_terminal_projection_sha256


def test_physical_bridge_builder_composes_real_disk_c1_into_real_disk_c2(
    monkeypatch,
    tmp_path: Path,
):
    fixture = _composer_fixture(monkeypatch, tmp_path / "parents")
    _capture, c1 = _build_physical_c1(tmp_path / "physical-c1")
    truth_sources = physical._truth_sources(fixture.preopen)
    truth_sources["accepted_risk_capture"] = (c1.archive_id, c1.archive_sha256)
    fixture.bridge.pair_id = c1.pair_id
    fixture.bridge.pair_sha256 = c1.pair_sha256
    fixture.bridge.derived_capture_id = c1.capture_id
    fixture.bridge.derived_capture_sha256 = c1.capture_sha256
    fixture.bridge.accepted_risk_bridge_id = c1.archive_id
    fixture.bridge.accepted_risk_bridge_sha256 = c1.archive_sha256
    monkeypatch.setattr(physical, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        physical,
        "require_reviewed_preopen_control_acquisition_receipt",
        lambda value: _offline_physical_requirer("preopen", value),
    )
    monkeypatch.setattr(
        physical, "_truth_sources", lambda _receipt: dict(truth_sources)
    )
    c2_root = tmp_path / "physical-c2"
    c2_root.mkdir(mode=0o700)

    bridge = physical._build_test_fixture_physical_production_evidence_bridge(
        accepted_risk_archive=c1,
        historical_bridge=fixture.bridge,
        firm_ontology=fixture.ontology,
        firm_availability=fixture.availability,
        preopen_acquisition_receipt=fixture.preopen,
        terminal_archive=fixture.archive,
        output_root=c2_root,
    )

    assert physical.require_physical_production_evidence_bridge(bridge) is bridge
    assert bridge.accepted_risk_archive is c1
    assert bridge.production_input_archive.accepted_risk_archive is c1
    assert bridge.production_input_archive.fixture_only is True
    assert bridge.production_input_archive.archive_path.is_dir()
    assert bridge.composition_terminal_count == (
        bridge.production_input_archive.evidence_row_count
    )
    assert bridge.full_accepted_risk_pair_materialized is False
    assert bridge.full_production_evidence_materialized is False


def test_physical_evidence_iterator_preserves_named_refusal_terminal(
    monkeypatch,
    tmp_path: Path,
):
    fixture = _composer_fixture(
        monkeypatch, tmp_path / "parents", upstream_refusal=0
    )
    monkeypatch.setattr(physical, "_require_dependencies", lambda: None)
    legacy = _legacy_composer_build(fixture)
    directory = tmp_path / "spool"
    directory.mkdir(mode=0o700)
    connection, _path = physical._composer._open_spool(directory)
    state = physical._CompositionState()
    try:
        connection.execute(
            "CREATE TABLE physical_composition("
            "ordinal INTEGER PRIMARY KEY, payload BLOB NOT NULL)"
        )
        physical._composer._spool_sidecars(connection, fixture.bridge)
        physical._composer._spool_terminals(connection, fixture.archive)
        observed = tuple(
            physical._iter_composed_evidence_rows(
                source_rows=iter(fixture.pair.rows),
                connection=connection,
                state=state,
                truth_sources=physical._truth_sources(fixture.preopen),
                firm_ontology=fixture.ontology,
                firm_availability=fixture.availability,
            )
        )
        projection = physical._composition_projection(
            connection, state.terminal_count
        )
    finally:
        connection.close()

    assert observed[0].security is None
    assert observed[0].control is None
    assert projection == legacy.composition_terminal_projection_sha256


def test_named_refusal_without_terminal_payload_fails_closed(
    monkeypatch,
    tmp_path: Path,
):
    fixture = _composer_fixture(monkeypatch, tmp_path / "parents")
    monkeypatch.setattr(physical, "_require_dependencies", lambda: None)
    directory = tmp_path / "spool"
    directory.mkdir(mode=0o700)
    connection, _path = physical._composer._open_spool(directory)
    state = physical._CompositionState()
    try:
        connection.execute(
            "CREATE TABLE physical_composition("
            "ordinal INTEGER PRIMARY KEY, payload BLOB NOT NULL)"
        )
        physical._composer._spool_sidecars(connection, fixture.bridge)
        physical._composer._spool_terminals(connection, fixture.archive)
        monkeypatch.setattr(
            physical._composer,
            "_one_terminal",
            lambda *_args, **_kwargs: ("named_refusal", None),
        )
        rows = physical._iter_composed_evidence_rows(
            source_rows=iter(fixture.pair.rows),
            connection=connection,
            state=state,
            truth_sources=physical._truth_sources(fixture.preopen),
            firm_ontology=fixture.ontology,
            firm_availability=fixture.availability,
        )
        with pytest.raises(
            physical.PhysicalProductionEvidenceBridgeError,
            match=_exact(
                "physical named-refusal terminal payload is missing"
            ),
        ):
            next(rows)
    finally:
        connection.close()


def test_physical_composition_capacity_is_a_named_refusal(
    monkeypatch,
    tmp_path: Path,
):
    fixture = _composer_fixture(monkeypatch, tmp_path / "parents")
    monkeypatch.setattr(physical, "_require_dependencies", lambda: None)
    directory = tmp_path / "spool"
    directory.mkdir(mode=0o700)
    connection, _path = physical._composer._open_spool(directory)
    state = physical._CompositionState()
    monkeypatch.setattr(physical, "MAX_COMPOSITION_TERMINAL_ROWS", 0)
    try:
        connection.execute(
            "CREATE TABLE physical_composition("
            "ordinal INTEGER PRIMARY KEY, payload BLOB NOT NULL)"
        )
        physical._composer._spool_sidecars(connection, fixture.bridge)
        physical._composer._spool_terminals(connection, fixture.archive)
        rows = physical._iter_composed_evidence_rows(
            source_rows=iter(fixture.pair.rows),
            connection=connection,
            state=state,
            truth_sources=physical._truth_sources(fixture.preopen),
            firm_ontology=fixture.ontology,
            firm_availability=fixture.availability,
        )
        with pytest.raises(
            physical.PhysicalProductionEvidenceBridgeCapacityError,
            match=_exact(
                "physical composition-terminal census exceeded fixed capacity"
            ),
        ):
            next(rows)
    finally:
        connection.close()


def test_physical_composition_spool_installs_hard_sqlite_page_limit(tmp_path):
    path = tmp_path / "capacity.sqlite3"
    connection = sqlite3.connect(path)
    try:
        physical._install_sqlite_capacity(connection)
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        max_page_count = connection.execute("PRAGMA max_page_count").fetchone()[0]
    finally:
        connection.close()

    assert max_page_count == physical._composer.MAX_COMPOSER_SPOOL_BYTES // page_size


def test_sqlite_full_is_a_distinct_capacity_refusal():
    class FullConnection:
        def execute(self, *_args):
            raise sqlite3.OperationalError("database or disk is full")

    class Terminal:
        @staticmethod
        def to_record():
            return {"disposition": "named_refusal"}

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeCapacityError,
        match=_exact(
            "physical composition SQLite spool reached its hard capacity"
        ),
    ):
        physical._insert_composition_terminal(
            FullConnection(), physical._CompositionState(), Terminal()
        )


def test_section72_spool_reauthenticates_real_inert_physical_archive(
    monkeypatch, tmp_path: Path,
):
    (tmp_path / "prereview").mkdir(mode=0o700)
    _plan, context, archive = _build_physical_prereview_capture(
        monkeypatch, tmp_path / "prereview"
    )
    directory = tmp_path / "spool"
    directory.mkdir(mode=0o700)
    connection, _path = physical._composer._open_spool(directory)
    try:
        counts, peak = physical._spool_owner_waived_prereview_terminals(
            connection, archive
        )
        stored = connection.execute(
            "SELECT COUNT(*) FROM terminals"
        ).fetchone()[0]
    finally:
        connection.close()

    assert counts == (
        archive.terminal_count,
        archive.accepted_count,
        archive.refusal_count,
    )
    assert stored == archive.terminal_count
    assert peak > 0
    manifest = json.loads(context["material"]["output"])
    bridge = SimpleNamespace(
        firm_authority_mode=physical.SECTION72_FIRM_AUTHORITY_MODE,
        preopen_acquisition_receipt=archive,
        physical_terminal_count=archive.terminal_count,
        physical_accepted_count=archive.accepted_count,
        physical_refusal_count=archive.refusal_count,
    )
    monkeypatch.setattr(
        physical, "require_physical_production_evidence_bridge", lambda value: value
    )
    assert physical.section72_owner_waived_preopen_session_axis(bridge) == tuple(
        item["decision_session"] for item in manifest["control_sessions"]
    )
    blocks = tuple(
        physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge)
    )
    assert tuple(item.decision_session for item in blocks) == tuple(
        item["decision_session"] for item in manifest["control_sessions"]
    )
    assert sum(item.terminal_count for item in blocks) == archive.terminal_count
    assert sum(len(item.accepted) for item in blocks) == archive.accepted_count
    assert sum(len(item.refused) for item in blocks) == archive.refusal_count


def _section72_replay_context(monkeypatch, tmp_path: Path):
    receipt, material = _build_reviewed_preopen_receipt(tmp_path, monkeypatch)
    del receipt
    manifest = json.loads(material["output"])
    payload = material["payload"]
    projection, totals = physical._preopen_io._validated_batch_major_output_payloads(
        manifest, (payload,)
    )
    archive = object.__new__(physical._prereview.PreopenControlPreReviewArchive)
    for name, value in {
        "capture_id": "arv2-preopen-prereview-capture-test",
        "capture_sha256": "1" * 64,
        "output_shard_payload_projection_sha256": projection,
        "terminal_count": totals["terminal_count"],
        "accepted_count": totals["accepted_count"],
        "refusal_count": totals["refusal_count"],
    }.items():
        object.__setattr__(archive, name, value)
    bridge = SimpleNamespace(
        firm_authority_mode=physical.SECTION72_FIRM_AUTHORITY_MODE,
        preopen_acquisition_receipt=archive,
        physical_terminal_count=archive.terminal_count,
        physical_accepted_count=archive.accepted_count,
        physical_refusal_count=archive.refusal_count,
    )
    monkeypatch.setattr(physical, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        physical, "require_physical_production_evidence_bridge", lambda value: value
    )
    monkeypatch.setattr(
        physical._prereview,
        "require_preopen_control_prereview_archive",
        lambda value: value,
    )
    monkeypatch.setattr(
        physical,
        "_owner_waived_manifest",
        lambda value: (manifest, {}) if value is archive else (_ for _ in ()).throw(
            AssertionError("wrong archive")
        ),
    )
    monkeypatch.setattr(
        physical._prereview,
        "iter_preopen_control_prereview_output_shard_payloads",
        lambda value: iter((payload,)) if value is archive else iter(()),
    )
    return bridge, archive, manifest, payload, projection, totals


def test_section72_terminal_replay_accepts_exact_authenticated_bytes(
    monkeypatch, tmp_path: Path,
):
    bridge, archive, manifest, _payload, _projection, _totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )

    blocks = tuple(
        physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge)
    )

    assert tuple(item.decision_session for item in blocks) == tuple(
        item["decision_session"] for item in manifest["control_sessions"]
    )
    assert sum(item.terminal_count for item in blocks) == archive.terminal_count


def test_section72_terminal_replay_isolates_payload_projection_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, archive, *_rest = _section72_replay_context(monkeypatch, tmp_path)
    object.__setattr__(archive, "output_shard_payload_projection_sha256", "f" * 64)

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen terminal payload projection changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_aggregate_census_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, _archive, _manifest, _payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    hostile = dict(totals)
    hostile["terminal_count"] += 1
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, hostile),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen terminal aggregate census changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_bridge_census_binding_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, *_rest = _section72_replay_context(monkeypatch, tmp_path)
    bridge.physical_terminal_count += 1

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived bridge terminal census binding changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_control_axis_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, _archive, manifest, _payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    controls = physical._preopen_io.core._parse_control_sessions(
        manifest["control_sessions"]
    )
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )
    monkeypatch.setattr(
        physical._preopen_io.core,
        "_parse_control_sessions",
        lambda _records: controls + controls,
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen control session axis changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_universe_axis_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, _archive, _manifest, _payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )
    monkeypatch.setattr(
        physical._preopen_io.core,
        "_parse_universe_sessions",
        lambda _records: (),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen universe session axis changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


@pytest.mark.parametrize(
    ("hostile", "message"),
    (
        ((), "owner-waived preopen terminal descriptor inventory changed type"),
        ([object()], "owner-waived preopen terminal descriptor changed exact type"),
    ),
)
def test_section72_terminal_replay_isolates_descriptor_guards(
    monkeypatch, tmp_path: Path, hostile, message,
):
    bridge, _archive, manifest, _payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    manifest["output_shards"] = hostile
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(message),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


@pytest.mark.parametrize("authority", ("control", "universe"))
def test_section72_terminal_replay_isolates_session_census_guards(
    monkeypatch, tmp_path: Path, authority,
):
    bridge, _archive, manifest, _payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    parser_name = f"_parse_{authority}_sessions"
    records = getattr(physical._preopen_io.core, parser_name)(
        manifest[f"{authority}_sessions"]
    )
    hostile = (
        dataclasses.replace(
            records[0], accepted_count=2, terminal_count=2
        ),
    )
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )
    monkeypatch.setattr(
        physical._preopen_io.core, parser_name, lambda _records: hostile
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(f"owner-waived preopen {authority} session census changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


@pytest.mark.parametrize("authority", ("control", "universe"))
def test_section72_terminal_replay_isolates_session_root_guards(
    monkeypatch, tmp_path: Path, authority,
):
    bridge, _archive, manifest, _payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    parser_name = f"_parse_{authority}_sessions"
    records = getattr(physical._preopen_io.core, parser_name)(
        manifest[f"{authority}_sessions"]
    )
    hostile = (dataclasses.replace(records[0], terminal_merkle_root="f" * 64),)
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )
    monkeypatch.setattr(
        physical._preopen_io.core, parser_name, lambda _records: hostile
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(f"owner-waived preopen {authority} session root changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_row_reconstruction_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, *_rest = _section72_replay_context(monkeypatch, tmp_path)
    monkeypatch.setattr(
        physical._streaming,
        "_eligible_from_record",
        lambda _record: (_ for _ in ()).throw(ValueError("hostile")),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen terminal row could not be reconstructed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_capacity_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, *_rest = _section72_replay_context(monkeypatch, tmp_path)
    monkeypatch.setattr(physical, "MAX_COMPOSITION_TERMINAL_ROWS", 0)

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeCapacityError,
        match=_exact(
            "owner-waived preopen session terminal census exceeded capacity"
        ),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_shard_census_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, archive, _manifest, payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )
    monkeypatch.setattr(
        physical._prereview,
        "iter_preopen_control_prereview_output_shard_payloads",
        lambda value: iter((payload, payload)) if value is archive else iter(()),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen terminal shard census changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_exact_archive_type_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, *_rest = _section72_replay_context(monkeypatch, tmp_path)
    bridge.preopen_acquisition_receipt = object()

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen terminal archive changed exact type"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_shard_authentication_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, *_rest = _section72_replay_context(monkeypatch, tmp_path)
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (_ for _ in ()).throw(ValueError("hostile")),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "owner-waived preopen terminal session authority did not authenticate"
        ),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_declared_session_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, _archive, manifest, _payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    controls = physical._preopen_io.core._parse_control_sessions(
        manifest["control_sessions"]
    )
    universes = physical._preopen_io.core._parse_universe_sessions(
        manifest["universe_sessions"]
    )
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )
    monkeypatch.setattr(
        physical._preopen_io.core,
        "_parse_control_sessions",
        lambda _records: (
            dataclasses.replace(controls[0], decision_session="2021-01-05"),
        ),
    )
    monkeypatch.setattr(
        physical._preopen_io.core,
        "_parse_universe_sessions",
        lambda _records: (
            dataclasses.replace(universes[0], decision_session="2021-01-05"),
        ),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen terminal escaped declared sessions"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def test_section72_terminal_replay_isolates_global_order_guard(
    monkeypatch, tmp_path: Path,
):
    bridge, archive, manifest, payload, projection, totals = (
        _section72_replay_context(monkeypatch, tmp_path)
    )
    manifest["output_shards"] = [
        dict(manifest["output_shards"][0]),
        dict(manifest["output_shards"][0]),
    ]
    monkeypatch.setattr(
        physical._preopen_io,
        "_validated_batch_major_output_payloads",
        lambda *_args: (projection, totals),
    )
    monkeypatch.setattr(
        physical._prereview,
        "iter_preopen_control_prereview_output_shard_payloads",
        lambda value: iter((payload, payload)) if value is archive else iter(()),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived preopen terminal order changed"),
    ):
        tuple(physical.iter_section72_owner_waived_preopen_terminal_sessions(bridge))


def _section72_parent_context(monkeypatch):
    c1 = object.__new__(physical.PhysicalAcceptedRiskArchive)
    for name, value in {
        "archive_id": "arv2-c1-archive-test",
        "archive_sha256": "1" * 64,
        "pair_id": "arv2-pair-test",
        "pair_sha256": "2" * 64,
        "capture_id": "arv2-capture-test",
        "capture_sha256": "3" * 64,
    }.items():
        object.__setattr__(c1, name, value)
    historical = SimpleNamespace(
        bridge_id="arv2-historical-bridge-test",
        bridge_sha256="e" * 64,
        pair_id=c1.pair_id,
        pair_sha256=c1.pair_sha256,
        derived_capture_id=c1.capture_id,
        derived_capture_sha256=c1.capture_sha256,
        accepted_risk_bridge_id=c1.archive_id,
        accepted_risk_bridge_sha256=c1.archive_sha256,
        closed_input_manifest_sha256="4" * 64,
        input_shard_inventory_sha256="5" * 64,
        discovery_eligible_universe_artifact_id="arv2-universe-test",
        discovery_eligible_universe_artifact_sha256="6" * 64,
        security_master_artifact_id="arv2-security-test",
        security_master_artifact_sha256="7" * 64,
        physical_candidate_id="arv2-preopen-test",
        physical_candidate_sha256="8" * 64,
        firm_review_candidate_sha256="9" * 64,
        analyst_event_binding_row_count=3,
    )
    packet = SimpleNamespace(
        accepted_risk_archive_id=c1.archive_id,
        accepted_risk_archive_sha256=c1.archive_sha256,
    )
    admission = object.__new__(
        physical._composer.OwnerWaivedAcceptedRiskFirmAdmission
    )
    for name, value in {
        "review_packet": packet,
        "admission_id": "arv2-section72-admission-test",
        "admission_sha256": "a" * 64,
        "owner_decision_id": "arv2-section72-owner-decision-test",
        "owner_decision_sha256": "b" * 64,
        "refusal_ledger_id": "arv2-section72-refusal-ledger-test",
        "refusal_ledger_sha256": "c" * 64,
        "owner_waiver_scope": physical.SECTION72_OWNER_WAIVER_SCOPE,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
        "normal_registry_populated": False,
        "owner_signature_required_downstream": True,
    }.items():
        object.__setattr__(admission, name, value)
    archive = object.__new__(physical._prereview.PreopenControlPreReviewArchive)
    for name, value in {
        "capture_id": "arv2-preopen-prereview-capture-test",
        "capture_sha256": "d" * 64,
        "terminal_count": 5,
        "accepted_count": 3,
        "refusal_count": 2,
        "review_disposition": "NOT_PERFORMED_OWNER_WAIVED",
        "independent_review_complete": False,
        "owner_review_waiver_scope": physical.SECTION72_OWNER_WAIVER_SCOPE,
        "post_first_formal_backtest_independent_review_required": True,
    }.items():
        object.__setattr__(archive, name, value)
    sources = {
        "accepted_risk_capture": (
            historical.accepted_risk_bridge_id,
            historical.accepted_risk_bridge_sha256,
        ),
        "eligible_universe": (
            historical.discovery_eligible_universe_artifact_id,
            historical.discovery_eligible_universe_artifact_sha256,
        ),
        "security_master": (
            historical.security_master_artifact_id,
            historical.security_master_artifact_sha256,
        ),
        "firm_ontology": ("arv2-firm-seed-test", "9" * 64),
        "common_event": ("arv2-common-event-test", "b" * 64),
        "sector_classification": ("arv2-sector-test", "c" * 64),
        "preopen_control": (
            historical.physical_candidate_id,
            historical.physical_candidate_sha256,
        ),
        "data_quality": ("arv2-quality-test", "d" * 64),
    }
    manifest = {
        "input_manifest": {
            "content_sha256": historical.closed_input_manifest_sha256,
        },
        "input_source_inventory_sha256": (
            historical.input_shard_inventory_sha256
        ),
    }
    monkeypatch.setattr(physical, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        physical._physical_c1,
        "require_physical_accepted_risk_archive",
        lambda value: value,
    )
    monkeypatch.setattr(
        physical._historical,
        "require_reviewed_historical_universe_to_preopen_bridge",
        lambda value: value,
    )
    monkeypatch.setattr(
        physical._composer,
        "require_section72_owner_waived_firm_admission",
        lambda value: value,
    )
    monkeypatch.setattr(
        physical._prereview,
        "require_preopen_control_prereview_archive",
        lambda value: value,
    )
    monkeypatch.setattr(
        physical,
        "_owner_waived_manifest",
        lambda _archive: (manifest, sources),
    )
    return c1, historical, admission, archive


def test_section72_parent_reauthentication_uses_nested_manifest_binding(
    monkeypatch,
):
    c1, historical, admission, archive = _section72_parent_context(monkeypatch)

    sources, bindings = physical._reauthenticate_owner_waived_parents(
        accepted_risk_archive=c1,
        historical_bridge=historical,
        firm_admission=admission,
        preopen_prereview_archive=archive,
    )

    assert sources["firm_ontology"] == (
        admission.admission_id,
        admission.admission_sha256,
    )
    firm = next(
        item for item in bindings
        if item.kind is physical.EvidenceSourceKind.FIRM_ONTOLOGY
    )
    assert type(firm) is physical.Section72OwnerWaivedFirmSourceBinding
    assert firm.reviewed is False
    assert firm.point_in_time is False
    assert firm.independently_reviewed is False
    assert firm.historical_availability_claimed is False
    assert all(
        item.reviewed and item.point_in_time
        for item in bindings
        if item is not firm
    )


@pytest.mark.parametrize(
    ("field", "hostile"),
    (
        ("independently_reviewed", True),
        ("historical_availability_claimed", True),
        ("normal_registry_populated", True),
        ("owner_signature_required_downstream", False),
    ),
)
def test_section72_parent_reauthentication_isolates_admission_policy_guards(
    monkeypatch, field, hostile,
):
    c1, historical, admission, archive = _section72_parent_context(monkeypatch)
    object.__setattr__(admission, field, hostile)

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "owner-waived physical production policy disposition changed"
        ),
    ):
        physical._reauthenticate_owner_waived_parents(
            accepted_risk_archive=c1,
            historical_bridge=historical,
            firm_admission=admission,
            preopen_prereview_archive=archive,
        )


@pytest.mark.parametrize(
    ("field", "hostile"),
    (
        ("review_disposition", "INDEPENDENT_REVIEW_COMPLETE"),
        ("independent_review_complete", True),
        ("owner_review_waiver_scope", "wrong-scope"),
        ("post_first_formal_backtest_independent_review_required", False),
    ),
)
def test_section72_parent_reauthentication_isolates_prereview_policy_guards(
    monkeypatch, field, hostile,
):
    c1, historical, admission, archive = _section72_parent_context(monkeypatch)
    object.__setattr__(archive, field, hostile)

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "owner-waived physical production policy disposition changed"
        ),
    ):
        physical._reauthenticate_owner_waived_parents(
            accepted_risk_archive=c1,
            historical_bridge=historical,
            firm_admission=admission,
            preopen_prereview_archive=archive,
        )


def _registered_section72_bridge(monkeypatch):
    c1, historical, admission, archive = _section72_parent_context(monkeypatch)
    _sources, source_bindings = physical._reauthenticate_owner_waived_parents(
        accepted_risk_archive=c1,
        historical_bridge=historical,
        firm_admission=admission,
        preopen_prereview_archive=archive,
    )
    c2 = object.__new__(physical._physical_c2.PhysicalProductionInputArchive)
    for name, value in {
        "archive_id": "arv2-physical-c2-test",
        "archive_sha256": "2" * 64,
        "source_bindings": source_bindings,
        "source_projection_sha256": "3" * 64,
        "row_projection_sha256": "4" * 64,
        "evidence_row_count": 7,
    }.items():
        object.__setattr__(c2, name, value)
    real_require = physical.require_physical_production_evidence_bridge
    monkeypatch.setattr(
        physical, "require_physical_production_evidence_bridge", lambda value: value
    )
    bridge = physical._mint_bridge(
        c1=c1,
        c2=c2,
        historical_bridge=historical,
        firm_ontology=admission,
        firm_availability=admission,
        preopen=archive,
        terminal_archive=archive,
        firm_authority_mode=physical.SECTION72_FIRM_AUTHORITY_MODE,
        source_bindings=source_bindings,
        composition_count=c2.evidence_row_count,
        composition_projection="5" * 64,
        sidecar_count=historical.analyst_event_binding_row_count,
        physical_counts=(
            archive.terminal_count,
            archive.accepted_count,
            archive.refusal_count,
        ),
        peak=0,
    )
    monkeypatch.setattr(
        physical, "require_physical_production_evidence_bridge", real_require
    )
    monkeypatch.setattr(
        physical._physical_c2,
        "require_physical_production_input_archive",
        lambda value: value,
    )
    monkeypatch.setattr(
        physical,
        "_reauthenticate_owner_waived_parents",
        lambda **_kwargs: ({}, ()),
    )
    return bridge


@pytest.mark.parametrize(
    ("field", "hostile"),
    (
        ("firm_ontology_id", "arv2-hostile-firm"),
        ("firm_ontology_sha256", "6" * 64),
        ("firm_availability_id", "arv2-hostile-decision"),
        ("firm_availability_sha256", "6" * 64),
        ("preopen_acquisition_id", "arv2-hostile-preopen"),
        ("preopen_acquisition_sha256", "6" * 64),
        ("terminal_archive_id", "arv2-hostile-terminal"),
        ("terminal_archive_sha256", "6" * 64),
        ("sidecar_row_count", 4),
        ("physical_terminal_count", 6),
        ("physical_accepted_count", 4),
        ("physical_refusal_count", 3),
    ),
)
def test_section72_bridge_isolates_each_retained_parent_binding_guard(
    monkeypatch, field, hostile,
):
    bridge = _registered_section72_bridge(monkeypatch)
    object.__setattr__(bridge, field, hostile)
    reference, _record, _topology = physical._BRIDGES[id(bridge)]
    physical._BRIDGES[id(bridge)] = (
        reference,
        canonical_json_bytes(physical._bridge_record(bridge)),
        physical._bridge_topology(bridge),
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact("owner-waived bridge retained parent binding changed"),
    ):
        physical.require_physical_production_evidence_bridge(bridge)


@pytest.fixture()
def physical_epoch_fixture(monkeypatch, tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    authority = _authority()
    archive = build_test_fixture_physical_production_input_archive(
        authority,
        output_root=tmp_path,
    )
    bridge = object.__new__(physical.PhysicalProductionEvidenceBridge)
    object.__setattr__(
        bridge, "firm_authority_mode", physical.NORMAL_FIRM_AUTHORITY_MODE
    )
    for name in (
        "owner_waived_firm_admission_id",
        "owner_waived_firm_admission_sha256",
        "firm_owner_decision_id",
        "firm_owner_decision_sha256",
        "firm_refusal_ledger_id",
        "firm_refusal_ledger_sha256",
        "owner_waiver_scope",
    ):
        object.__setattr__(bridge, name, None)
    object.__setattr__(bridge, "historical_availability_claimed", True)
    object.__setattr__(bridge, "owner_waiver_signature_required", False)
    object.__setattr__(bridge, "bridge_id", "arv2-physical-evidence-test")
    object.__setattr__(bridge, "bridge_sha256", "a" * 64)
    object.__setattr__(bridge, "production_input_archive", archive)
    object.__setattr__(bridge, "accepted_risk_archive_id", "accepted-risk-test")
    object.__setattr__(bridge, "accepted_risk_archive_sha256", "b" * 64)
    object.__setattr__(bridge, "production_input_archive_id", archive.archive_id)
    object.__setattr__(
        bridge, "production_input_archive_sha256", archive.archive_sha256
    )
    object.__setattr__(
        bridge, "source_projection_sha256", archive.source_projection_sha256
    )
    object.__setattr__(bridge, "row_projection_sha256", archive.row_projection_sha256)
    object.__setattr__(
        bridge, "composition_terminal_count", archive.evidence_row_count
    )
    object.__setattr__(bridge, "composition_terminal_projection_sha256", "c" * 64)
    monkeypatch.setattr(
        physical,
        "require_physical_production_evidence_bridge",
        lambda value: value,
    )
    return bridge, archive


def test_review_candidate_refuses_fixture_archive(physical_epoch_fixture):
    bridge, _archive = physical_epoch_fixture

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence review candidate is not production eligible"
        ),
    ):
        physical.render_physical_production_evidence_review_candidate(bridge)


def test_review_candidate_is_row_free_and_non_authorizing(
    monkeypatch, physical_epoch_fixture
):
    bridge, archive = physical_epoch_fixture
    monkeypatch.setattr(
        physical._physical_c2,
        "require_reviewable_physical_production_archive",
        lambda value: value,
    )

    raw = json.loads(
        physical.render_physical_production_evidence_review_candidate(bridge)
    )

    assert raw["production_input_archive_sha256"] == archive.archive_sha256
    assert raw["independent_review_status"] == "pending"
    assert raw["production_evidence_receipt_available"] is False
    assert raw["full_accepted_risk_pair_materialized"] is False
    assert raw["full_production_evidence_materialized"] is False
    assert raw["contains_provider_rows"] is False
    assert raw["contains_outcome_or_price"] is False
    assert raw["qc_launch_available"] is False
    assert "row_evidence" not in raw
    assert "normalized_rows" not in raw


def test_epoch_streams_each_physical_arm_once_and_seals_exact_census(
    physical_epoch_fixture,
):
    bridge, archive = physical_epoch_fixture
    epoch = physical.begin_physical_production_evidence_epoch(bridge)

    observed = {}
    for arm in SignalArm:
        rows = tuple(physical.iter_physical_production_scoring_rows(epoch, arm))
        expected = tuple(iter_physical_normalized_evidence_rows(archive, arm))
        assert [item.normalized_evidence for item in rows] == list(expected)
        assert all(
            item.endpoint_label.c2_row_sha256
            == item.normalized_evidence.normalized_row.row_sha256
            for item in rows
        )
        observed[arm.value] = len(rows)

    receipt = physical.finish_physical_production_evidence_epoch(epoch)
    assert receipt.complete_two_arm_census is True
    assert receipt.full_pair_materialized is False
    assert dict(receipt.arm_row_counts) == observed
    assert dict(receipt.arm_row_counts) == {
        arm.value: physical_production_batch(archive, arm).normalized_row_count
        for arm in SignalArm
    }
    assert all(
        len(digest) == 64
        for _arm, digest in receipt.arm_row_projection_sha256s
    )
    assert receipt.receipt_sha256 == physical.sha256_bytes(
        canonical_json_bytes(receipt.to_record(include_identity=False))
    )


def test_epoch_rejects_replay_from_a_different_thread(physical_epoch_fixture):
    bridge, _archive = physical_epoch_fixture
    epoch = physical.begin_physical_production_evidence_epoch(bridge)
    observed = []

    def consume() -> None:
        try:
            next(
                physical.iter_physical_production_scoring_rows(
                    epoch, SignalArm.CURRENT_VINTAGE
                )
            )
        except BaseException as exc:
            observed.append(exc)

    worker = threading.Thread(target=consume)
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(observed) == 1
    assert type(observed[0]) is physical.PhysicalProductionEvidenceBridgeError
    assert str(observed[0]) == (
        "physical production-evidence epoch process or thread changed"
    )


def test_bridge_allows_only_one_live_epoch_and_never_reuses_completed_epoch_id(
    physical_epoch_fixture,
):
    bridge, _archive = physical_epoch_fixture
    first = physical.begin_physical_production_evidence_epoch(bridge)

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence bridge already has an active epoch"
        ),
    ):
        physical.begin_physical_production_evidence_epoch(bridge)

    for arm in SignalArm:
        tuple(physical.iter_physical_production_scoring_rows(first, arm))
    physical.finish_physical_production_evidence_epoch(first)
    second = physical.begin_physical_production_evidence_epoch(bridge)
    assert second.epoch_id != first.epoch_id


def test_epoch_wrong_arm_order_fails_closed_and_cannot_resume(
    physical_epoch_fixture,
):
    bridge, _archive = physical_epoch_fixture
    epoch = physical.begin_physical_production_evidence_epoch(bridge)

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence epoch arm order or lease changed"
        ),
    ):
        next(
            physical.iter_physical_production_scoring_rows(
                epoch, SignalArm.CONSERVATIVE_CENSORED
            )
        )
    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence epoch arm order or lease changed"
        ),
    ):
        next(
            physical.iter_physical_production_scoring_rows(
                epoch, SignalArm.CURRENT_VINTAGE
            )
        )


def test_epoch_partial_consumption_is_terminal_not_silently_replayable(
    physical_epoch_fixture,
):
    bridge, _archive = physical_epoch_fixture
    epoch = physical.begin_physical_production_evidence_epoch(bridge)
    iterator = physical.iter_physical_production_scoring_rows(
        epoch, SignalArm.CURRENT_VINTAGE
    )
    next(iterator)
    iterator.close()

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence epoch arm order or lease changed"
        ),
    ):
        next(
            physical.iter_physical_production_scoring_rows(
                epoch, SignalArm.CURRENT_VINTAGE
            )
        )
    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence epoch is incomplete, failed, or spent"
        ),
    ):
        physical.finish_physical_production_evidence_epoch(epoch)


def test_epoch_detects_dependency_rebinding_during_row_replay(
    monkeypatch, physical_epoch_fixture
):
    bridge, _archive = physical_epoch_fixture
    original_label_builder = physical.build_endpoint_label_evidence

    def require_label_builder() -> None:
        if physical.build_endpoint_label_evidence is not original_label_builder:
            raise physical.PhysicalProductionEvidenceBridgeError(
                "physical production-evidence dependency binding changed"
            )

    monkeypatch.setattr(physical, "_require_dependencies", require_label_builder)
    epoch = physical.begin_physical_production_evidence_epoch(bridge)
    iterator = physical.iter_physical_production_scoring_rows(
        epoch, SignalArm.CURRENT_VINTAGE
    )
    next(iterator)
    monkeypatch.setattr(
        physical,
        "build_endpoint_label_evidence",
        lambda **_kwargs: None,
    )

    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence dependency binding changed"
        ),
    ):
        next(iterator)


@pytest.mark.parametrize(
    ("target", "name"),
    (
        (physical._physical_c1, "iter_physical_accepted_risk_rows"),
        (physical._physical_c2, "iter_physical_normalized_evidence_rows"),
        (
            physical._historical,
            "iter_reviewed_historical_analyst_event_binding_shards",
        ),
        (physical._firm_module, "require_registered_production_firm_ontology"),
        (physical._composer, "iter_physical_preopen_terminal_sessions"),
        (
            physical._composer,
            "require_section72_owner_waived_firm_admission",
        ),
        (physical._composer, "_owner_waived_firm_component"),
        (
            physical._prereview,
            "require_preopen_control_prereview_archive",
        ),
        (
            physical._prereview,
            "read_preopen_control_prereview_manifest_bytes",
        ),
        (
            physical._prereview,
            "iter_preopen_control_prereview_output_shard_payloads",
        ),
        (
            physical._preopen_io,
            "_validated_batch_major_output_payloads",
        ),
        (physical._preopen_io, "_PhysicalShardCursor"),
        (physical._preopen_io, "_strict"),
        (physical._preopen_io.core, "_parse_control_sessions"),
        (physical._preopen_io.core, "_parse_universe_sessions"),
        (physical._preopen_io, "_merkle"),
        (physical._streaming, "_eligible_from_record"),
        (physical._streaming, "_refusal_from_record"),
        (physical._streaming, "PhysicalTerminalSessionBlock"),
        (physical, "require_identifier"),
        (physical, "build_endpoint_label_evidence"),
        (physical, "Section72OwnerWaivedFirmSourceBinding"),
        (physical, "SECTION72_OWNER_WAIVED_FIRM_ADMISSION_MODE"),
    ),
)
def test_bridge_dependency_rebinding_refuses_before_row_access(
    monkeypatch, target, name
):
    monkeypatch.setattr(target, name, lambda *_args, **_kwargs: None)
    with pytest.raises(
        physical.PhysicalProductionEvidenceBridgeError,
        match=_exact(
            "physical production-evidence dependency binding changed"
        ),
    ):
        physical._require_dependencies()
