"""Focused offline tests for the disk-backed ARV2 pre-open seed archive."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import MassiveSourceRole
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import physical_preopen_seed_archive as seed_module
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    _build_physical_accepted_risk_archive_for_test,
)
from research.analyst_revisions_v2_qc.physical_preopen_seed_archive import (
    PhysicalPreopenSeedArchiveCapacityError,
    PhysicalPreopenSeedArchiveError,
    _build_physical_preopen_seed_archive_for_test,
    build_fundamental_discovery_plan_for_physical_seed,
    iter_physical_composition_terminals,
    iter_physical_firm_rows,
    iter_physical_fundamental_seeds,
    iter_physical_session_counts,
    iter_physical_source_role_seeds,
    iter_physical_universe_candidates,
    load_physical_preopen_seed_archive,
    physical_preopen_seed_artifact_binding,
    read_physical_preopen_composition_report,
    require_physical_preopen_seed_archive,
)
from scripts.build_arv2_massive_input_pair import (
    _build_massive_accepted_risk_input_pair_for_test,
)
from scripts import build_arv2_preopen_input as legacy_module
from scripts.build_arv2_preopen_input import build_physical_preopen_input_candidate
from scripts.capture_arv2_massive import (
    ENDPOINT_PATHS,
    _capture_massive_history_spooled_for_test,
)
from scripts.capture_arv2_sharadar import (
    SharadarDataset,
    _capture_sharadar_history_for_test,
)
from tests.analyst_revisions_v2.test_massive_capture_adapter import (
    BASE_URL,
    FakeResponse as MassiveResponse,
    FakeSession as MassiveSession,
    _payload as massive_payload,
)
from tests.analyst_revisions_v2.test_physical_preopen_input_composer import (
    ACTIONS,
    FUNDAMENTALS,
    TICKERS,
)
from tests.analyst_revisions_v2.test_sharadar_capture_adapter import (
    FakeResponse as SharadarResponse,
    FakeSession as SharadarSession,
    _zip_bytes,
)


NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
MASSIVE_KEY = "offline-test-key-physical-seed-NEVER-REAL"
SHARADAR_KEY = "offline-test-key-sharadar-seed-NEVER-REAL"
RAW_ONLY_PROBE = "raw-provider-field-MUST-NOT-enter-derived-seed"


def _massive_row(identifier: str, role: MassiveSourceRole) -> dict[str, object]:
    value: dict[str, object] = {
        "benzinga_id": identifier,
        "date": "2021-01-04",
        "time": "08:30:00",
        "ticker": "AAA",
        "raw_only_probe": RAW_ONLY_PROBE,
    }
    if role is MassiveSourceRole.CORPORATE_GUIDANCE:
        value.update(
            {
                "last_updated": "2021-01-04 09:30:00",
                "guidance_type": "Revenue",
            }
        )
    else:
        value["last_updated"] = "2021-01-04T12:00:00Z"
    if role is MassiveSourceRole.ANALYST_RATINGS:
        value.update(
            {
                "benzinga_firm_id": "firm-1",
                "benzinga_analyst_id": "analyst-1",
                "firm": "Example Firm",
                "rating_action": "upgrades",
                "rating": "Buy",
                "previous_rating": "Hold",
            }
        )
    return value


def _sources(tmp_path: Path, *, fundamentals: bytes = FUNDAMENTALS):
    responses = []
    for role in MassiveSourceRole:
        endpoint = BASE_URL + ENDPOINT_PATHS[role]
        responses.append(
            MassiveResponse(
                massive_payload([_massive_row(f"{role.value}-1", role)]),
                endpoint,
            )
        )
    massive = _capture_massive_history_spooled_for_test(
        requested_first_event_date="2013-01-02",
        requested_last_event_date="2025-12-31",
        artifact_root=tmp_path / "massive",
        session=MassiveSession(responses),
        clock=lambda: NOW,
        api_key=MASSIVE_KEY,
    )
    c1 = _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=massive.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )
    sharadar = _capture_sharadar_history_for_test(
        artifact_root=tmp_path / "sharadar",
        session=SharadarSession(
            [
                SharadarResponse(
                    _zip_bytes(SharadarDataset.TICKERS, csv_bytes=TICKERS)
                ),
                SharadarResponse(
                    _zip_bytes(SharadarDataset.ACTIONS, csv_bytes=ACTIONS)
                ),
                SharadarResponse(
                    _zip_bytes(
                        SharadarDataset.FUNDAMENTALS, csv_bytes=fundamentals
                    )
                ),
            ]
        ),
        clock=lambda: NOW,
        api_key=SHARADAR_KEY,
    )
    return massive, c1, sharadar


def _built(tmp_path: Path, *, fundamentals: bytes = FUNDAMENTALS):
    massive, c1, sharadar = _sources(tmp_path, fundamentals=fundamentals)
    seed = _build_physical_preopen_seed_archive_for_test(
        c1, sharadar, tmp_path / "preopen-seeds"
    )
    legacy_bridge = _build_massive_accepted_risk_input_pair_for_test(
        massive.artifact_path
    )
    legacy = build_physical_preopen_input_candidate(legacy_bridge, sharadar)
    return massive, c1, sharadar, seed, legacy


def _physicalized_artifact(payload: bytes, c1, role: str) -> bytes:
    value = json.loads(payload)
    if "massive_bridge_id" in value:
        value["massive_bridge_id"] = c1.archive_id
        value["massive_bridge_sha256"] = c1.archive_sha256
    if role == "firm_review_candidate":
        value.pop("candidate_id")
        value.pop("candidate_semantic_sha256")
        semantic = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
        value["candidate_id"] = f"arv2-firm-vocabulary-{semantic[:24]}"
        value["candidate_semantic_sha256"] = semantic
    elif role in {
        "eligible_universe_artifact",
        "source_seed_candidate",
        "fundamental_seed_inventory",
    }:
        prefix = {
            "eligible_universe_artifact": "arv2-universe-review-",
            "source_seed_candidate": "arv2-source-seed-review-",
            "fundamental_seed_inventory": "arv2-fundamental-seeds-",
        }[role]
        value.pop("artifact_id")
        value.pop("semantic_sha256")
        semantic = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
        value["artifact_id"] = prefix + semantic[:24]
        value["semantic_sha256"] = semantic
    return canonical_json_bytes(value)


def test_disk_seed_matches_legacy_semantics_and_hashes_on_bounded_fixture(
    tmp_path,
):
    _massive, c1, _sharadar, seed, legacy = _built(tmp_path)

    assert require_physical_preopen_seed_archive(seed) is seed
    assert seed.massive_source_row_count == 3
    assert seed.composition_terminal_count == 3
    assert seed.candidate_security_count == 2
    assert seed.fundamental_seed_count == 1
    assert seed.raw_provider_rows_retained is False
    assert seed.full_history_materialized_in_memory is False
    assert seed.raw_free_derived_identity is True
    assert all(
        getattr(seed, name) is False
        for name in (
            "provider_access",
            "credential_access",
            "quantconnect_access",
            "outcome_access",
            "result_access",
            "deployment",
            "orders",
            "trading",
        )
    )
    assert all(
        RAW_ONLY_PROBE.encode("utf-8") not in path.read_bytes()
        for path in seed.archive_path.rglob("*")
        if path.is_file()
    )

    expected = {
        "firm_review_candidate": legacy.firm_review_candidate_bytes,
        "eligible_universe_artifact": legacy.eligible_universe_artifact_bytes,
        "source_seed_candidate": legacy.source_seed_candidate_bytes,
        "fundamental_seed_inventory": legacy.fundamental_seed_inventory_bytes,
    }
    physical_artifacts = {}
    for role, payload in expected.items():
        physical = _physicalized_artifact(payload, c1, role)
        physical_artifacts[role] = physical
        binding = physical_preopen_seed_artifact_binding(seed, role)
        assert binding.content_sha256 == hashlib.sha256(physical).hexdigest()
        assert binding.byte_count == len(physical)

    report = read_physical_preopen_composition_report(seed)
    expected_report = json.loads(legacy.composition_report_bytes)
    expected_report["massive_bridge_id"] = c1.archive_id
    expected_report["massive_bridge_sha256"] = c1.archive_sha256
    expected_report["firm_review_candidate_sha256"] = (
        physical_preopen_seed_artifact_binding(
            seed, "firm_review_candidate"
        ).content_sha256
    )
    expected_report["source_seed_candidate_sha256"] = (
        physical_preopen_seed_artifact_binding(
            seed, "source_seed_candidate"
        ).content_sha256
    )
    expected_report_bytes = canonical_json_bytes(expected_report)
    report_binding = physical_preopen_seed_artifact_binding(
        seed, "composition_report"
    )
    assert report == expected_report
    assert report_binding.content_sha256 == hashlib.sha256(
        expected_report_bytes
    ).hexdigest()
    assert report_binding.byte_count == len(expected_report_bytes)
    assert physical_preopen_seed_artifact_binding(
        seed, "quality_policy"
    ).content_sha256 == hashlib.sha256(legacy.quality_policy_bytes).hexdigest()
    candidate_record = legacy_module._candidate_record(
        bridge=SimpleNamespace(
            bridge_id=c1.archive_id,
            bridge_sha256=c1.archive_sha256,
            pair=SimpleNamespace(pair_id=c1.pair_id, pair_sha256=c1.pair_sha256),
            derived_capture_id=c1.capture_id,
            derived_capture_sha256=c1.capture_sha256,
        ),
        sharadar=_sharadar,
        first_session=legacy.first_session,
        last_session=legacy.last_session,
        calculation_session=legacy.calculation_session,
        blocking_refusals=legacy.blocking_refusals,
        firm_bytes=physical_artifacts["firm_review_candidate"],
        report_bytes=expected_report_bytes,
        universe_bytes=physical_artifacts["eligible_universe_artifact"],
        source_seed_bytes=physical_artifacts["source_seed_candidate"],
        fundamental_inventory_bytes=physical_artifacts[
            "fundamental_seed_inventory"
        ],
        quality_bytes=legacy.quality_policy_bytes,
        completeness=dict(seed.source_completeness),
    )
    expected_candidate = canonical_json_bytes(candidate_record)
    candidate_binding = physical_preopen_seed_artifact_binding(
        seed, "candidate_record"
    )
    assert seed.candidate_sha256 == hashlib.sha256(expected_candidate).hexdigest()
    assert seed.candidate_id == (
        "arv2-physical-preopen-input-" + seed.candidate_sha256[:24]
    )
    assert candidate_binding.content_sha256 == seed.candidate_sha256
    assert candidate_binding.byte_count == len(expected_candidate)

    legacy_universe = json.loads(legacy.eligible_universe_artifact_bytes)
    legacy_sources = json.loads(legacy.source_seed_candidate_bytes)
    legacy_fundamentals = json.loads(legacy.fundamental_seed_inventory_bytes)
    legacy_firms = json.loads(legacy.firm_review_candidate_bytes)
    assert list(iter_physical_universe_candidates(seed)) == legacy_universe[
        "candidate_security_rows"
    ]
    assert list(iter_physical_session_counts(seed)) == legacy_universe[
        "candidate_member_count_by_session"
    ]
    assert list(iter_physical_source_role_seeds(
        seed, MassiveSourceRole.ANALYST_RATINGS
    )) == legacy_sources["role_candidates"]["ratings"]
    assert list(iter_physical_source_role_seeds(
        seed, MassiveSourceRole.EARNINGS
    )) == legacy_sources["role_candidates"]["earnings"]
    assert list(iter_physical_source_role_seeds(
        seed, MassiveSourceRole.CORPORATE_GUIDANCE
    )) == legacy_sources["role_candidates"]["guidance"]
    assert list(iter_physical_composition_terminals(seed)) == legacy_sources[
        "composition_terminals"
    ]
    assert list(iter_physical_fundamental_seeds(seed)) == legacy_fundamentals[
        "seed_rows"
    ]
    assert list(iter_physical_firm_rows(seed)) == legacy_firms["firms"]


def test_source_order_and_canonical_terminal_roots_are_both_exact(tmp_path):
    _massive, _c1, _sharadar, seed, legacy = _built(tmp_path)
    report = json.loads(legacy.composition_report_bytes)
    canonical = json.loads(legacy.source_seed_candidate_bytes)[
        "composition_terminals"
    ]

    assert seed.source_order_terminal_projection_sha256 == report[
        "massive_composition_terminal_projection_sha256"
    ]
    assert seed.canonical_terminal_projection_sha256 == hashlib.sha256(
        canonical_json_bytes(canonical)
    ).hexdigest()


def test_non_art_rows_are_counted_but_never_enter_seed(tmp_path):
    mixed = FUNDAMENTALS + (
        b"AAA,MRY,2020-12-31,2021-02-10,2020-12-31,2021-02-10,"
        b"7777777,8888888,9999999\n"
    )
    _massive, _c1, _sharadar, seed, legacy = _built(
        tmp_path, fundamentals=mixed
    )

    assert list(iter_physical_fundamental_seeds(seed)) == json.loads(
        legacy.fundamental_seed_inventory_bytes
    )["seed_rows"]
    assert read_physical_preopen_composition_report(seed)[
        "fundamental_refusal_counts"
    ]["non-ART fundamental"] == 1


def test_loader_round_trip_and_shard_tamper_refusal(tmp_path):
    _massive, _c1, _sharadar, seed, _legacy = _built(tmp_path)
    loaded = load_physical_preopen_seed_archive(seed.archive_path)
    assert loaded == seed
    assert require_physical_preopen_seed_archive(loaded) is loaded

    descriptor = next(
        item for item in seed.shards if item.role == "universe_candidates"
    )
    path = seed.archive_path / descriptor.relative_path
    payload = bytearray(path.read_bytes())
    payload[len(payload) // 2] ^= 1
    path.write_bytes(payload)
    with pytest.raises(
        PhysicalPreopenSeedArchiveError, match="shard row|census or hash"
    ):
        require_physical_preopen_seed_archive(seed)


def test_loader_refuses_self_content_addressed_cross_binding_forgery(tmp_path):
    _massive, _c1, _sharadar, seed, _legacy = _built(tmp_path)
    manifest_path = seed.archive_path / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["archive_seed"]["census"]["composition_terminal_count"] += 1
    archive_sha = hashlib.sha256(
        canonical_json_bytes(manifest["archive_seed"])
    ).hexdigest()
    archive_id = f"arv2-physical-preopen-seed-{archive_sha[:24]}"
    manifest["archive_sha256"] = archive_sha
    manifest["archive_id"] = archive_id
    payload = canonical_json_bytes(manifest)
    manifest_path.write_bytes(payload)
    (seed.archive_path / "manifest.sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    forged_path = seed.archive_path.with_name(archive_id)
    seed.archive_path.rename(forged_path)

    with pytest.raises(
        PhysicalPreopenSeedArchiveError,
        match="fixed geometry or source census",
    ):
        load_physical_preopen_seed_archive(forged_path)


def test_sqlite_spool_has_a_real_hard_page_bound_and_capacity_guard(tmp_path):
    maximum_bytes = 128 * 1024
    path = tmp_path / "bounded-spool.sqlite3"
    connection = seed_module._open_spool(path, maximum_bytes=maximum_bytes)
    try:
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        maximum_pages = int(
            connection.execute("PRAGMA max_page_count").fetchone()[0]
        )
        effective_bound = maximum_pages * page_size
        assert effective_bound == connection.arv2_maximum_bytes
        assert effective_bound <= maximum_bytes
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "off"
        assert int(connection.execute("PRAGMA temp_store").fetchone()[0]) == 1
        assert int(connection.execute("PRAGMA mmap_size").fetchone()[0]) == 0
        cache_pages = int(connection.execute("PRAGMA cache_size").fetchone()[0])
        assert -8192 <= cache_pages < 0

        observed = seed_module._spool_bytes(connection)
        with pytest.raises(
            PhysicalPreopenSeedArchiveCapacityError,
            match="exceeds its fixed byte bound",
        ):
            seed_module._require_spool_capacity(
                connection, maximum_bytes=observed - 1
            )

        with pytest.raises(
            PhysicalPreopenSeedArchiveCapacityError,
            match="reached its hard capacity",
        ) as failure:
            for ordinal in range(1, 1_000):
                connection.execute(
                    "INSERT INTO terminals(source_ordinal, payload) VALUES (?, ?)",
                    (ordinal, bytes([ordinal % 251]) * 7_000),
                )
                connection.commit()
        assert isinstance(failure.value.__cause__, sqlite3.Error)
        assert (
            failure.value.__cause__.sqlite_errorcode & 0xFF
            == sqlite3.SQLITE_FULL
        )
    finally:
        connection.close()
    assert path.stat().st_size <= effective_bound <= maximum_bytes


@pytest.mark.parametrize("mismatch", ["total", "one_role"])
def test_finish_source_rows_requires_full_c1_count_and_role_exhaustion(
    tmp_path, mismatch
):
    _massive, c1, sharadar = _sources(tmp_path)
    connection = seed_module._open_spool(tmp_path / "exhaustion-spool.sqlite3")
    try:
        state = seed_module._BuildState(connection, c1=c1, sharadar=sharadar)
        state.source_row_count = c1.source_row_count
        state.role_seen.update(dict(c1.role_row_counts))
        if mismatch == "total":
            state.source_row_count -= 1
        else:
            role = next(iter(MassiveSourceRole))
            state.role_seen[role] -= 1
        with pytest.raises(
            PhysicalPreopenSeedArchiveError,
            match="did not exhaust its authenticated role census",
        ):
            state.finish_source_rows()
    finally:
        connection.close()


@pytest.mark.parametrize(
    "iterator_name",
    [
        "universe",
        "sessions",
        "source_role",
        "terminals",
        "fundamentals",
        "firms",
    ],
)
def test_every_public_iterator_reauthenticates_at_terminal_boundary(
    tmp_path, iterator_name
):
    _massive, _c1, _sharadar, seed, _legacy = _built(tmp_path)
    factories = {
        "universe": lambda: iter_physical_universe_candidates(seed),
        "sessions": lambda: iter_physical_session_counts(seed),
        "source_role": lambda: iter_physical_source_role_seeds(
            seed, MassiveSourceRole.ANALYST_RATINGS
        ),
        "terminals": lambda: iter_physical_composition_terminals(seed),
        "fundamentals": lambda: iter_physical_fundamental_seeds(seed),
        "firms": lambda: iter_physical_firm_rows(seed),
    }
    iterator = factories[iterator_name]()
    assert next(iterator)
    (seed.archive_path / "manifest.json").unlink()

    with pytest.raises(
        PhysicalPreopenSeedArchiveError,
        match="manifest is unavailable",
    ):
        tuple(iterator)


def test_output_must_be_separate_from_both_physical_sources(tmp_path):
    _massive, c1, sharadar = _sources(tmp_path)
    forbidden = c1.archive_path / "nested-output"
    with pytest.raises(
        PhysicalPreopenSeedArchiveError, match="sources and output"
    ):
        _build_physical_preopen_seed_archive_for_test(c1, sharadar, forbidden)
    assert not forbidden.exists()


def test_content_addressed_publication_never_overwrites_existing_archive(tmp_path):
    _massive, c1, sharadar = _sources(tmp_path)
    root = tmp_path / "preopen-seeds"
    first = _build_physical_preopen_seed_archive_for_test(c1, sharadar, root)
    manifest = (first.archive_path / "manifest.json").read_bytes()

    with pytest.raises(
        PhysicalPreopenSeedArchiveError, match="already exists|already claimed"
    ):
        _build_physical_preopen_seed_archive_for_test(c1, sharadar, root)
    assert (first.archive_path / "manifest.json").read_bytes() == manifest


def test_physical_seed_geometry_builds_the_reviewed_outcome_free_plan(tmp_path):
    _massive, _c1, _sharadar, seed, _legacy = _built(tmp_path)
    plan = build_fundamental_discovery_plan_for_physical_seed(seed)
    value = json.loads(plan)

    assert value["first_session"] == "2013-01-02"
    assert value["last_session"] == "2025-12-31"
    assert len(value["decision_sessions"]) == seed.decision_session_count
    assert value["execution_contract"]["outcome_or_result_access"] is False
    assert value["execution_contract"]["price_or_return_access"] is False


def test_seed_archive_has_no_provider_qc_outcome_or_order_entry_point():
    assert not hasattr(seed_module, "requests")
    assert not hasattr(seed_module, "capture_massive_history")
    assert not hasattr(seed_module, "capture_sharadar_history")
    assert not hasattr(seed_module, "run_backtest")
    assert not hasattr(seed_module, "read_outcomes")
    assert not hasattr(seed_module, "submit_order")


def test_seed_authority_mutation_is_refused(tmp_path):
    _massive, _c1, _sharadar, seed, _legacy = _built(tmp_path)
    original = seed.quantconnect_access
    object.__setattr__(seed, "quantconnect_access", True)
    try:
        with pytest.raises(
            PhysicalPreopenSeedArchiveError, match="not current loader authority"
        ):
            require_physical_preopen_seed_archive(seed)
    finally:
        object.__setattr__(seed, "quantconnect_access", original)
    assert require_physical_preopen_seed_archive(seed) is seed
