"""Offline tests for the disk-backed physical-seed historical bridge."""
from __future__ import annotations

import dataclasses
import sqlite3
import weakref
from pathlib import Path

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import MassiveSourceRole
from research.analyst_revisions_v2_qc import physical_historical_preopen_bridge as physical_bridge_module
from research.analyst_revisions_v2_qc import physical_preopen_seed_archive as seed_module
from research.analyst_revisions_v2_qc.physical_historical_preopen_bridge import (
    MAX_PHYSICAL_HISTORICAL_SPOOL_BYTES,
    SQLITE_PAGE_BYTES,
    PhysicalHistoricalPreopenBridgeCapacityError,
    PhysicalHistoricalPreopenBridgeError,
    PhysicalHistoricalPreopenBridgePublicationAmbiguityError,
    _build_mappings,
    _create_schema,
    _execute,
    _open_spool,
    _publish_stage,
    build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed,
)
from scripts import build_arv2_historical_preopen_bridge as legacy_bridge_module
from scripts import build_arv2_preopen_input as legacy_seed_module
from scripts.build_arv2_historical_preopen_bridge import (
    build_reviewed_historical_universe_to_preopen_bridge,
    iter_reviewed_historical_analyst_event_binding_shards,
    iter_reviewed_historical_preopen_input_shards,
    iter_reviewed_historical_universe_lifecycle_binding_shards,
    require_reviewed_historical_universe_to_preopen_bridge,
)
from tests.analyst_revisions_v2 import test_historical_preopen_bridge as historical_fixture
from tests.analyst_revisions_v2 import test_physical_preopen_input_composer as source_fixture
from tests.analyst_revisions_v2 import test_physical_preopen_seed_archive as seed_fixture
from tests.analyst_revisions_v2 import test_qc_preopen_control_stage as preopen_fixture


_AMBIGUOUS_TICKERS = (
    b"fundamentals,DUP1,100003,N,Dup One,Domestic Common Stock,NASDAQ,"
    b"Technology,Software,2010-01-04,,BBG001DUP111,000000CC6\n"
    b"fundamentals,DUP2,100004,N,Dup Two,Domestic Common Stock,NYSE,"
    b"Technology,Software,2010-01-04,,BBG001DUP222,000000CC6\n"
)


def _sources(monkeypatch, tmp_path):
    discovery = historical_fixture._discovery_receipt(monkeypatch, tmp_path)
    monkeypatch.setattr(
        seed_fixture,
        "TICKERS",
        source_fixture.TICKERS + _AMBIGUOUS_TICKERS,
    )
    massive, c1, sharadar, seed, legacy = seed_fixture._built(tmp_path)
    return discovery, massive, c1, sharadar, seed, legacy


def _physicalized_legacy_candidate(seed, c1, legacy):
    physical = {
        role: seed_fixture._physicalized_artifact(
            getattr(legacy, field), c1, role
        )
        for role, field in {
            "firm_review_candidate": "firm_review_candidate_bytes",
            "eligible_universe_artifact": "eligible_universe_artifact_bytes",
            "source_seed_candidate": "source_seed_candidate_bytes",
            "fundamental_seed_inventory": "fundamental_seed_inventory_bytes",
        }.items()
    }
    report = seed_module.read_physical_preopen_composition_report(seed)
    report_bytes = seed_module.canonical_json_bytes(report)
    replacements = {
        "candidate_id": seed.candidate_id,
        "candidate_sha256": seed.candidate_sha256,
        "massive_bridge_id": c1.archive_id,
        "massive_bridge_sha256": c1.archive_sha256,
        "derived_capture_id": c1.capture_id,
        "derived_capture_sha256": c1.capture_sha256,
        "firm_review_candidate_bytes": physical["firm_review_candidate"],
        "composition_report_bytes": report_bytes,
        "eligible_universe_artifact_bytes": physical[
            "eligible_universe_artifact"
        ],
        "source_seed_candidate_bytes": physical["source_seed_candidate"],
        "fundamental_seed_inventory_bytes": physical[
            "fundamental_seed_inventory"
        ],
    }
    candidate = object.__new__(legacy_seed_module.PhysicalPreopenInputCandidate)
    for field in dataclasses.fields(candidate):
        object.__setattr__(
            candidate,
            field.name,
            replacements.get(field.name, getattr(legacy, field.name)),
        )
    identity = id(candidate)
    reference = weakref.ref(
        candidate,
        lambda ref, key=identity: legacy_seed_module._forget(key, ref),
    )
    with legacy_seed_module._AUTHORITIES_LOCK:
        legacy_seed_module._AUTHORITIES[identity] = (
            reference,
            legacy_seed_module._fingerprint(candidate),
        )
    return legacy_seed_module.require_physical_preopen_input_candidate(candidate)


def _public_fields(value):
    return {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if not field.name.startswith("_")
    }


def _file_inventory(root: Path):
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_physical_bridge_is_byte_exact_to_physicalized_legacy_oracle_and_join_matrix(
    monkeypatch, tmp_path
):
    discovery, _massive, c1, _sharadar, seed, legacy = _sources(
        monkeypatch, tmp_path
    )
    legacy_candidate = _physicalized_legacy_candidate(seed, c1, legacy)
    oracle_root = tmp_path / "legacy-oracle"
    physical_root = tmp_path / "physical-successor"
    oracle = build_reviewed_historical_universe_to_preopen_bridge(
        discovery, legacy_candidate, oracle_root
    )
    actual = (
        build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
            discovery, seed, physical_root
        )
    )

    assert require_reviewed_historical_universe_to_preopen_bridge(actual) is actual
    assert _public_fields(actual) == _public_fields(oracle)
    assert _file_inventory(physical_root) == _file_inventory(oracle_root)
    assert actual.accepted_security_count == 1
    assert actual.named_refusal_security_count == 4
    assert actual.universe_lifecycle_binding_row_count == 6 * 3270
    assert list(iter_reviewed_historical_preopen_input_shards(actual)) == list(
        iter_reviewed_historical_preopen_input_shards(oracle)
    )
    assert list(
        iter_reviewed_historical_analyst_event_binding_shards(actual)
    ) == list(iter_reviewed_historical_analyst_event_binding_shards(oracle))
    assert list(
        iter_reviewed_historical_universe_lifecycle_binding_shards(actual)
    ) == list(iter_reviewed_historical_universe_lifecycle_binding_shards(oracle))


def test_physical_inputs_and_output_are_separate_before_output_creation(
    monkeypatch, tmp_path
):
    discovery, _massive, _c1, _sharadar, seed, _legacy = _sources(
        monkeypatch, tmp_path
    )
    targets = (
        seed.archive_path,
        seed.archive_path / "must-not-create",
        discovery._archive_root,
        discovery._archive_root / "must-not-create",
    )
    for target in targets:
        with pytest.raises(
            PhysicalHistoricalPreopenBridgeError, match="new Path|separate"
        ):
            build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
                discovery, seed, target
            )
        if target.name == "must-not-create":
            assert not target.exists()


def test_every_physical_seed_and_discovery_iterator_is_exhausted_before_output(
    monkeypatch, tmp_path
):
    discovery, _massive, _c1, _sharadar, seed, _legacy = _sources(
        monkeypatch, tmp_path
    )
    simple_iterators = (
        "iter_physical_session_counts",
        "iter_physical_universe_candidates",
        "iter_physical_fundamental_seeds",
        "iter_physical_composition_terminals",
    )
    for index, name in enumerate(simple_iterators):
        original = getattr(seed_module, name)

        def trailing_failure(value, _original=original, _name=name):
            yield from _original(value)
            raise RuntimeError(f"{_name} drain sentinel")

        monkeypatch.setattr(seed_module, name, trailing_failure)
        output = tmp_path / f"must-not-publish-{index}"
        with pytest.raises(RuntimeError, match=f"{name} drain sentinel"):
            build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
                discovery, seed, output
            )
        assert not output.exists()
        monkeypatch.setattr(seed_module, name, original)

    original_roles = seed_module.iter_physical_source_role_seeds
    for offset, source_role in enumerate(MassiveSourceRole, start=4):
        def role_trailing_failure(
            value, role, *, _selected=source_role, _original=original_roles
        ):
            yield from _original(value, role)
            if role is _selected:
                raise RuntimeError(f"{role.value} drain sentinel")

        monkeypatch.setattr(
            seed_module, "iter_physical_source_role_seeds", role_trailing_failure
        )
        output = tmp_path / f"must-not-publish-{offset}"
        with pytest.raises(RuntimeError, match=f"{source_role.value} drain sentinel"):
            build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
                discovery, seed, output
            )
        assert not output.exists()
        monkeypatch.setattr(
            seed_module, "iter_physical_source_role_seeds", original_roles
        )

    original_terminals = legacy_bridge_module._terminal_rows

    def discovery_trailing_failure(value):
        yield from original_terminals(value)
        raise RuntimeError("discovery iterator drain sentinel")

    monkeypatch.setattr(
        legacy_bridge_module, "_terminal_rows", discovery_trailing_failure
    )
    discovery_output = tmp_path / "must-not-publish-7"
    with pytest.raises(RuntimeError, match="discovery iterator drain sentinel"):
        build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
            discovery, seed, discovery_output
        )
    assert not discovery_output.exists()


def test_late_failure_leaves_no_visible_output_and_same_path_retries(
    monkeypatch, tmp_path
):
    discovery, _massive, _c1, _sharadar, seed, _legacy = _sources(
        monkeypatch, tmp_path
    )
    original = physical_bridge_module._publish_stage
    observed = []

    def fail_after_complete_stage(stage, final):
        observed.append((stage, final))
        assert stage.is_dir()
        assert (stage / "closed-input-manifest.json").is_file()
        raise RuntimeError("late publication sentinel")

    monkeypatch.setattr(
        physical_bridge_module, "_publish_stage", fail_after_complete_stage
    )
    output = tmp_path / "retryable-final"
    with pytest.raises(RuntimeError, match="late publication sentinel"):
        build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
            discovery, seed, output
        )
    assert observed
    assert not output.exists()
    assert not list(tmp_path.glob(".arv2-historical-*"))

    monkeypatch.setattr(physical_bridge_module, "_publish_stage", original)
    value = build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
        discovery, seed, output
    )
    assert require_reviewed_historical_universe_to_preopen_bridge(value) is value


def test_post_publish_authority_failure_rolls_back_and_retries(
    monkeypatch, tmp_path
):
    discovery, _massive, _c1, _sharadar, seed, _legacy = _sources(
        monkeypatch, tmp_path
    )
    original = physical_bridge_module._mint
    output = tmp_path / "post-publish-retry"

    def fail_after_publication(**values):
        assert values["archive_root"] == output
        assert output.is_dir()
        raise RuntimeError("post-publication mint sentinel")

    monkeypatch.setattr(physical_bridge_module, "_mint", fail_after_publication)
    with pytest.raises(RuntimeError, match="post-publication mint sentinel"):
        build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
            discovery, seed, output
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".arv2-historical-*"))

    monkeypatch.setattr(physical_bridge_module, "_mint", original)
    value = build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
        discovery, seed, output
    )
    assert require_reviewed_historical_universe_to_preopen_bridge(value) is value


def test_sqlite_spool_installs_hard_cap_file_temp_and_indexed_output_order(
    tmp_path,
):
    connection = _open_spool(tmp_path / "bounded.sqlite3")
    try:
        _create_schema(connection)
        assert connection.execute("PRAGMA page_size").fetchone()[0] == SQLITE_PAGE_BYTES
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == 1
        assert connection.execute("PRAGMA mmap_size").fetchone()[0] == 0
        assert connection.execute("PRAGMA max_page_count").fetchone()[0] == (
            MAX_PHYSICAL_HISTORICAL_SPOOL_BYTES // SQLITE_PAGE_BYTES
        )
        plan = " ".join(
            row[3]
            for row in connection.execute(
                """EXPLAIN QUERY PLAN SELECT payload FROM input_row
                    WHERE batch=? AND role=? ORDER BY payload""",
                (0, "ratings"),
            )
        )
        assert "input_row_batch_role_payload" in plan
        assert "TEMP B-TREE" not in plan.upper()
        identity_plan = " ".join(
            row[3]
            for row in connection.execute(
                """EXPLAIN QUERY PLAN
                   SELECT sid, MIN(stream_ordinal), MIN(session), MAX(session),
                          MIN(available_at), MIN(cusip), MAX(cusip)
                     FROM terminal INDEXED BY terminal_sid_stream
                    WHERE disposition='accepted'
                    GROUP BY sid ORDER BY sid"""
            )
        )
        assert "terminal_sid_stream" in identity_plan
        assert "TEMP B-TREE" not in identity_plan.upper()
    finally:
        connection.close()


def test_identity_classification_fetches_only_fixed_1024_row_batches(
    monkeypatch, tmp_path
):
    connection = _open_spool(tmp_path / "identity-batches.sqlite3")
    observed_batch_sizes = []
    original_execute = physical_bridge_module._execute

    class ClassificationCursor:
        def __init__(self, cursor):
            self._cursor = cursor

        def fetchmany(self, size=None):
            assert size == physical_bridge_module.SQLITE_UPDATE_BATCH_ROWS
            rows = self._cursor.fetchmany(size)
            assert len(rows) <= physical_bridge_module.SQLITE_UPDATE_BATCH_ROWS
            observed_batch_sizes.append(len(rows))
            return rows

        def fetchall(self):
            raise AssertionError("identity classification materialized all IDs")

        def __iter__(self):
            raise AssertionError("identity classification bypassed fixed batches")

    def observe_classification_cursor(value, sql, parameters=()):
        cursor = original_execute(value, sql, parameters)
        normalized = " ".join(sql.split())
        if normalized == (
            "SELECT sid, cusip, candidate_security_id FROM identity ORDER BY sid"
        ):
            return ClassificationCursor(cursor)
        return cursor

    try:
        _create_schema(connection)
        connection.executemany(
            """INSERT INTO terminal(
                   stream_ordinal, disposition, sid, cusip, display_ticker,
                   session, opened, available_at, terminal_sha, payload
               ) VALUES (?, 'accepted', ?, ?, ?, '2021-01-04',
                   '2021-01-04T14:30:00.000000Z',
                   '2021-01-04T14:29:59.000000Z', ?, ?)""",
            (
                (
                    ordinal,
                    f"SID-{ordinal:04d}",
                    f"{ordinal:09d}",
                    f"T{ordinal:04d}",
                    f"{ordinal:064x}",
                    b"{}\n",
                )
                for ordinal in range(
                    physical_bridge_module.SQLITE_UPDATE_BATCH_ROWS + 1
                )
            ),
        )
        monkeypatch.setattr(
            physical_bridge_module, "_execute", observe_classification_cursor
        )

        assert physical_bridge_module._derive_identities(connection) == (
            physical_bridge_module.SQLITE_UPDATE_BATCH_ROWS + 1,
            physical_bridge_module.SQLITE_UPDATE_BATCH_ROWS + 1,
        )
        assert observed_batch_sizes == [
            physical_bridge_module.SQLITE_UPDATE_BATCH_ROWS,
            1,
            0,
        ]
    finally:
        connection.close()


def test_role_shard_reader_consumes_one_blob_per_cursor_step(
    monkeypatch, tmp_path
):
    connection = _open_spool(tmp_path / "role-cursor.sqlite3")
    original_execute = physical_bridge_module._execute
    original_decode = physical_bridge_module._decode
    observed = {
        "next_calls": 0,
        "bulk_calls": 0,
        "awaiting_decode": None,
    }

    class OneBlobCursor:
        def __init__(self, cursor):
            self._cursor = cursor

        def __iter__(self):
            return self

        def __next__(self):
            assert observed["awaiting_decode"] is None, (
                "role-shard reader retained an earlier BLOB before decoding it"
            )
            observed["next_calls"] += 1
            row = next(self._cursor)
            observed["awaiting_decode"] = row[0]
            return row

        def fetchmany(self, _size=None):
            observed["bulk_calls"] += 1
            raise AssertionError("role-shard reader fetched a BLOB batch")

        def fetchall(self):
            observed["bulk_calls"] += 1
            raise AssertionError("role-shard reader materialized all BLOBs")

    def observe_role_cursor(value, sql, parameters=()):
        cursor = original_execute(value, sql, parameters)
        normalized = " ".join(sql.split())
        if normalized == (
            "SELECT payload FROM input_row "
            "WHERE batch=? AND role=? ORDER BY payload"
        ):
            return OneBlobCursor(cursor)
        return cursor

    def observe_role_decode(payload, name):
        if name == "sid_mapping spooled input row":
            assert observed["awaiting_decode"] == payload
            observed["awaiting_decode"] = None
        return original_decode(payload, name)

    try:
        _create_schema(connection)
        payloads = [
            physical_bridge_module.canonical_json_bytes(
                preopen_fixture._sid_mapping_row(
                    security_id=f"sid-{ordinal}",
                    qc_security_id=f"qc-sid-{ordinal}",
                    issuer_id=f"issuer-{ordinal}",
                    share_class_id=f"share-class-{ordinal}",
                    listing_id=f"listing-{ordinal}",
                    historical_ticker=f"T{ordinal}",
                )
            )
            for ordinal in range(3)
        ]
        connection.executemany(
            "INSERT INTO input_row(role, batch, payload) VALUES (?, ?, ?)",
            (("sid_mapping", 0, payload) for payload in payloads),
        )
        root = tmp_path / "role-output"
        (root / legacy_bridge_module.ARCHIVE_SHARD_DIRECTORY).mkdir(
            parents=True, mode=0o700
        )
        monkeypatch.setattr(
            physical_bridge_module, "_execute", observe_role_cursor
        )
        monkeypatch.setattr(
            physical_bridge_module, "_decode", observe_role_decode
        )

        descriptors, bindings = physical_bridge_module._write_role_shards(
            connection=connection,
            root=root,
            role="sid_mapping",
            batch=0,
            first_session="2021-01-04",
            last_session="2021-01-04",
        )

        assert observed == {
            "next_calls": len(payloads) + 1,
            "bulk_calls": 0,
            "awaiting_decode": None,
        }
        assert [item["row_count"] for item in descriptors] == [len(payloads)]
        assert [item.row_count for item in bindings] == [len(payloads)]
    finally:
        connection.close()


def test_sqlite_full_uses_declared_capacity_refusal():
    class FullConnection:
        def execute(self, _sql, _parameters):
            error = sqlite3.OperationalError("database or disk is full")
            error.sqlite_errorcode = sqlite3.SQLITE_FULL
            raise error

    with pytest.raises(
        PhysicalHistoricalPreopenBridgeCapacityError,
        match="fixed byte bound",
    ):
        _execute(FullConnection(), "INSERT", ())


def test_atomic_publication_never_replaces_an_existing_destination(tmp_path):
    stage = tmp_path / ".complete-stage"
    stage.mkdir(mode=0o700)
    (stage / legacy_bridge_module.ARCHIVE_SHARD_DIRECTORY).mkdir(mode=0o700)
    (stage / legacy_bridge_module.ARCHIVE_EVIDENCE_DIRECTORY).mkdir(mode=0o700)
    destination = tmp_path / "final"
    destination.mkdir(mode=0o700)
    sentinel = destination / "owner-sentinel"
    sentinel.write_bytes(b"do-not-replace")
    sentinel.chmod(0o600)

    with pytest.raises(
        PhysicalHistoricalPreopenBridgeError, match="destination exists"
    ):
        _publish_stage(stage, destination)
    assert stage.is_dir()
    assert sentinel.read_bytes() == b"do-not-replace"


def test_post_rename_parent_sync_failure_rolls_back_and_retries(
    monkeypatch, tmp_path
):
    stage = tmp_path / ".complete-stage"
    stage.mkdir(mode=0o700)
    (stage / legacy_bridge_module.ARCHIVE_SHARD_DIRECTORY).mkdir(mode=0o700)
    (stage / legacy_bridge_module.ARCHIVE_EVIDENCE_DIRECTORY).mkdir(mode=0o700)
    destination = tmp_path / "final"
    original_fsync = physical_bridge_module.os.fsync
    calls = []

    def fail_publication_sync(descriptor):
        calls.append(descriptor)
        if len(calls) == 4:
            raise OSError("post-rename parent sync sentinel")
        return original_fsync(descriptor)

    monkeypatch.setattr(
        physical_bridge_module.os, "fsync", fail_publication_sync
    )
    with pytest.raises(
        PhysicalHistoricalPreopenBridgeError,
        match="sync failed and was rolled back",
    ):
        _publish_stage(stage, destination)
    assert len(calls) == 5
    assert stage.is_dir()
    assert not destination.exists()

    monkeypatch.setattr(physical_bridge_module.os, "fsync", original_fsync)
    _publish_stage(stage, destination)
    assert destination.is_dir()
    assert not stage.exists()


def test_uncertain_rollback_uses_named_ambiguity_and_preserves_stage(
    monkeypatch, tmp_path
):
    stage = tmp_path / ".complete-stage"
    stage.mkdir(mode=0o700)
    (stage / legacy_bridge_module.ARCHIVE_SHARD_DIRECTORY).mkdir(mode=0o700)
    (stage / legacy_bridge_module.ARCHIVE_EVIDENCE_DIRECTORY).mkdir(mode=0o700)
    destination = tmp_path / "final"
    original_fsync = physical_bridge_module.os.fsync
    calls = []

    def fail_both_parent_syncs(descriptor):
        calls.append(descriptor)
        if len(calls) >= 4:
            raise OSError("uncertain parent sync sentinel")
        return original_fsync(descriptor)

    monkeypatch.setattr(
        physical_bridge_module.os, "fsync", fail_both_parent_syncs
    )
    with pytest.raises(
        PhysicalHistoricalPreopenBridgePublicationAmbiguityError,
        match="ambiguous; residue preserved",
    ):
        _publish_stage(stage, destination)
    assert len(calls) == 5
    assert stage.is_dir()
    assert not destination.exists()


def test_security_batches_count_named_refusals_in_the_logical_order(tmp_path):
    connection = _open_spool(tmp_path / "batch.sqlite3")
    try:
        _create_schema(connection)
        for ordinal in range(13):
            sid = f"SID-{ordinal:02d}"
            logical = f"qc-join-refusal-{ordinal:024d}"
            connection.execute(
                """INSERT INTO identity(
                       sid, cusip, first_session, last_session,
                       first_available_at, display_ticker,
                       terminal_projection_sha, candidate_security_id,
                       candidate_payload, current_ticker_matches, reason,
                       logical, batch
                   ) VALUES (?, '', '2013-01-02', '2025-12-31',
                       '2013-01-02T14:29:59.999999Z', 'UNKNOWN', ?, NULL,
                       NULL, 0, 'missing_QC_CUSIP', ?, NULL)""",
                (sid, f"{ordinal:064x}", logical),
            )
        batch_count, accepted_count, mismatch_count = _build_mappings(
            connection, "security-master", "a" * 64
        )
        assert (batch_count, accepted_count, mismatch_count) == (2, 0, 0)
        assert connection.execute(
            "SELECT COUNT(*) FROM mapping WHERE batch=0"
        ).fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM mapping WHERE batch=1"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_exact_parent_types_are_required_before_output(tmp_path):
    with pytest.raises(
        PhysicalHistoricalPreopenBridgeError, match="exact discovery"
    ):
        build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
            object(), object(), tmp_path / "never-created"
        )
    assert not (tmp_path / "never-created").exists()
