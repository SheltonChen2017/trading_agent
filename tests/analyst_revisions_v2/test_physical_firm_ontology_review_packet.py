"""Focused offline tests for the inert physical firm-review packet."""
from __future__ import annotations

import ast
import dataclasses
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    MassiveSourceRole,
)
from research.analyst_revisions_v2_qc import (
    physical_firm_ontology_review_packet as packet_module,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    _build_physical_accepted_risk_archive_for_test,
    iter_physical_accepted_risk_rows,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    ADJUDICATION_TEMPLATE_FILENAME,
    FIRM_ROWS_FILENAME,
    TOP_FIRM_COUNT,
    PhysicalFirmOntologyReviewPacket,
    PhysicalFirmOntologyReviewPacketCapacityError,
    PhysicalFirmOntologyReviewPacketError,
    PhysicalFirmOntologyReviewPacketPublicationAmbiguityError,
    _build_physical_firm_ontology_review_packet_for_test,
    iter_physical_firm_ontology_review_rows,
    iter_physical_firm_owner_adjudication_template,
    require_physical_firm_ontology_review_packet,
)
from scripts.capture_arv2_massive import (
    ENDPOINT_PATHS,
    _capture_massive_history_spooled_for_test,
)
from tests.analyst_revisions_v2.test_massive_capture_adapter import (
    BASE_URL,
    FakeResponse,
    FakeSession,
    _payload,
)
from tests.analyst_revisions_v2.test_physical_preopen_seed_archive import (
    _built as _built_preopen_seed,
)


NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
KEY = "offline-test-key-firm-review-packet-NEVER-REAL"
RAW_ONLY_PROBE = "raw-provider-field-MUST-NOT-enter-firm-review"


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


def _rating(
    identifier: str,
    *,
    firm_id: str | None,
    firm_name: str | None,
    action: str,
    rating: str | None,
    previous_rating: str | None,
    event_date: str = "2021-01-04",
    event_time: str = "08:30:00",
    last_updated: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "benzinga_id": identifier,
        "date": event_date,
        "time": event_time,
        "last_updated": last_updated or f"{event_date}T12:00:00Z",
        "ticker": "AAA",
        "rating_action": action,
        "raw_only_probe": RAW_ONLY_PROBE,
    }
    if firm_id is not None:
        row["benzinga_firm_id"] = firm_id
    if firm_name is not None:
        row["firm"] = firm_name
    if rating is not None:
        row["rating"] = rating
    if previous_rating is not None:
        row["previous_rating"] = previous_rating
    return row


def _other_row(identifier: str, role: MassiveSourceRole) -> dict[str, object]:
    row: dict[str, object] = {
        "benzinga_id": identifier,
        "date": "2021-01-04",
        "time": "08:30:00",
        "ticker": "AAA",
        "raw_only_probe": RAW_ONLY_PROBE,
    }
    if role is MassiveSourceRole.CORPORATE_GUIDANCE:
        row.update(
            {
                "last_updated": "2021-01-04 09:30:00",
                "guidance_type": "Revenue",
            }
        )
    else:
        row["last_updated"] = "2021-01-04T12:00:00Z"
    return row


def _c1(tmp_path: Path, ratings: list[dict[str, object]]):
    responses = [
        FakeResponse(
            _payload(ratings),
            BASE_URL + ENDPOINT_PATHS[MassiveSourceRole.ANALYST_RATINGS],
        ),
        FakeResponse(
            _payload(
                [_other_row("earnings-1", MassiveSourceRole.EARNINGS)]
            ),
            BASE_URL + ENDPOINT_PATHS[MassiveSourceRole.EARNINGS],
        ),
        FakeResponse(
            _payload(
                [
                    _other_row(
                        "guidance-1", MassiveSourceRole.CORPORATE_GUIDANCE
                    )
                ]
            ),
            BASE_URL + ENDPOINT_PATHS[MassiveSourceRole.CORPORATE_GUIDANCE],
        ),
    ]
    capture = _capture_massive_history_spooled_for_test(
        requested_first_event_date="2013-01-02",
        requested_last_event_date="2025-12-31",
        artifact_root=tmp_path / "massive",
        session=FakeSession(responses),
        clock=lambda: NOW,
        api_key=KEY,
    )
    return _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / "accepted-risk",
    )


def _diagnostic_ratings() -> list[dict[str, object]]:
    return [
        _rating(
            "a-late",
            firm_id="firm-a",
            firm_name="Alpha Research",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
            event_time="09:00:00",
        ),
        _rating(
            "a-early",
            firm_id="firm-a",
            firm_name="Alpha & Co",
            action="upgrades",
            rating="Hold",
            previous_rating="Sell",
            event_time="08:00:00",
        ),
        _rating(
            "a-repeat",
            firm_id="firm-a",
            firm_name="Alpha Research",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
            event_date="2021-01-05",
        ),
        _rating(
            "a-conflict",
            firm_id="firm-a",
            firm_name="Alpha Research",
            action="downgrades",
            rating="Buy",
            previous_rating="Hold",
            event_date="2021-01-06",
        ),
        _rating(
            "b-down",
            firm_id="firm-b",
            firm_name="Beta Securities",
            action="downgrades",
            rating="Hold",
            previous_rating="Buy",
        ),
        _rating(
            "b-up",
            firm_id="firm-b",
            firm_name="Beta Securities",
            action="upgrades",
            rating="Hold",
            previous_rating="Sell",
            event_date="2021-01-05",
        ),
        _rating(
            "c-maintain",
            firm_id="firm-c",
            firm_name="Charlie Research",
            action="maintains",
            rating="Hold",
            previous_rating="Hold",
        ),
        _rating(
            "d-missing-prior",
            firm_id="firm-d",
            firm_name="Delta Research",
            action="upgrades",
            rating="Buy",
            previous_rating=None,
        ),
        _rating(
            "invalid-firm",
            firm_id=None,
            firm_name="No Identifier",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
        ),
    ]


def test_packet_has_exact_diagnostics_order_ranking_and_content_address(
    tmp_path: Path,
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "review-one",
    )
    firms = list(iter_physical_firm_ontology_review_rows(packet))
    template = list(iter_physical_firm_owner_adjudication_template(packet))

    assert require_physical_firm_ontology_review_packet(packet) is packet
    assert packet.source_row_count == 11
    assert packet.analyst_rating_source_row_count == 9
    assert packet.valid_firm_source_row_count == 8
    assert packet.invalid_firm_identity_row_count == 1
    assert packet.current_admitted_firm_row_count == 8
    assert packet.censored_admitted_firm_row_count == 8
    assert packet.exact_censored_source_clock_row_count == 8
    assert packet.firm_count == 4
    assert packet.observed_firm_name_count == 5
    assert packet.observed_label_count == 10
    assert packet.observed_transition_count == 6
    assert packet.ranked_firm_count == 2
    assert packet.adjudication_firm_count == 2
    assert [row["provider_firm_id"] for row in firms] == [
        "firm-a",
        "firm-b",
        "firm-c",
        "firm-d",
    ]

    alpha = firms[0]
    assert alpha["observed_firm_names"] == [
        {
            "firm_name": "Alpha & Co",
            "observed_count": 1,
            "first_event_date": "2021-01-04",
            "last_event_date": "2021-01-04",
        },
        {
            "firm_name": "Alpha Research",
            "observed_count": 3,
            "first_event_date": "2021-01-04",
            "last_event_date": "2021-01-06",
        },
    ]
    assert alpha["action_diagnostics"] == [
        {
            "action_label": "downgrades",
            "observed_count": 1,
            "censored_admitted_count": 1,
            "first_event_date": "2021-01-06",
            "last_event_date": "2021-01-06",
        },
        {
            "action_label": "upgrades",
            "observed_count": 3,
            "censored_admitted_count": 3,
            "first_event_date": "2021-01-04",
            "last_event_date": "2021-01-05",
        },
    ]
    assert alpha["transition_counts"] == [
        {
            "previous_rating": "Hold",
            "current_rating": "Buy",
            "action_label": "downgrades",
            "observed_count": 1,
            "censored_admitted_count": 1,
            "first_event_date": "2021-01-06",
            "last_event_date": "2021-01-06",
        },
        {
            "previous_rating": "Hold",
            "current_rating": "Buy",
            "action_label": "upgrades",
            "observed_count": 2,
            "censored_admitted_count": 2,
            "first_event_date": "2021-01-04",
            "last_event_date": "2021-01-05",
        },
        {
            "previous_rating": "Sell",
            "current_rating": "Hold",
            "action_label": "upgrades",
            "observed_count": 1,
            "censored_admitted_count": 1,
            "first_event_date": "2021-01-04",
            "last_event_date": "2021-01-04",
        },
    ]
    assert alpha["earliest_exact_censored_admitted_source"][
        "source_clock_at"
    ] == "2021-01-04T08:00:00.000000Z"
    assert alpha["earliest_exact_censored_admitted_source"]["locator"][
        "row_offset"
    ] == 1
    diagnostics = alpha["conflict_and_connectedness_diagnostics"]
    assert diagnostics["observed_firm_name_count"] == 2
    assert diagnostics["multiple_observed_firm_names"] is True
    assert diagnostics["graph_connected"] is True
    assert diagnostics["undirected_component_count"] == 1
    assert diagnostics["directional_preference_conflict_pair_count"] == 1
    assert diagnostics["directional_preference_cycle_detected"] is True
    assert alpha["predeclared_2021_2025_volume_ranking"] == {
        "ranking_ordinal": 1,
        "volume_count": 4,
        "selected_for_owner_adjudication": True,
    }
    assert [
        (
            row["ranking_ordinal"],
            row["provider_firm_id"],
            row["predeclared_2021_2025_volume_count"],
        )
        for row in template
    ] == [(1, "firm-a", 4), (2, "firm-b", 2)]
    assert all(
        row["owner_adjudication"]
        == {
            "review_status": None,
            "reviewer": None,
            "reviewed_at": None,
            "canonical_firm_name": None,
            "validity_intervals": [],
            "ordered_scale": [],
            "scope": None,
            "alias_mappings": [],
            "notes": None,
        }
        for row in template
    )
    assert not (packet.archive_path / "construction.sqlite3").exists()
    assert set(path.name for path in packet.archive_path.iterdir()) == {
        "manifest.json",
        "manifest.sha256",
        FIRM_ROWS_FILENAME,
        ADJUDICATION_TEMPLATE_FILENAME,
    }
    assert stat_mode(packet.archive_path) == 0o700
    assert all(
        stat_mode(path) == 0o600
        for path in packet.archive_path.iterdir()
    )
    assert all(
        RAW_ONLY_PROBE.encode("utf-8") not in path.read_bytes()
        for path in packet.archive_path.iterdir()
    )

    duplicate = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "review-two",
    )
    assert duplicate.packet_id == packet.packet_id
    assert duplicate.packet_sha256 == packet.packet_sha256
    assert {
        path.name: path.read_bytes() for path in duplicate.archive_path.iterdir()
    } == {path.name: path.read_bytes() for path in packet.archive_path.iterdir()}


def stat_mode(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


def test_exactly_top_74_positive_volume_firms_are_blank_templates(
    tmp_path: Path,
) -> None:
    assert TOP_FIRM_COUNT == 74
    ratings = [
        _rating(
            f"rating-{ordinal:03d}",
            firm_id=f"firm-{ordinal:03d}",
            firm_name=f"Firm {ordinal:03d}",
            action="upgrades",
            rating="Buy",
            previous_rating="Hold",
        )
        for ordinal in range(76)
    ]
    ratings.extend(
        (
            _rating(
                "excluded-censored",
                firm_id="firm-excluded-censored",
                firm_name="Excluded Censored",
                action="upgrades",
                rating="Buy",
                previous_rating="Hold",
                last_updated="2022-01-01T00:00:00Z",
            ),
            _rating(
                "excluded-date",
                firm_id="firm-excluded-date",
                firm_name="Excluded Date",
                action="upgrades",
                rating="Buy",
                previous_rating="Hold",
                event_date="2020-12-31",
            ),
            _rating(
                "excluded-action",
                firm_id="firm-excluded-action",
                firm_name="Excluded Action",
                action="maintains",
                rating="Buy",
                previous_rating="Hold",
            ),
        )
    )
    c1 = _c1(tmp_path, ratings)
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "review",
    )

    template = list(iter_physical_firm_owner_adjudication_template(packet))
    assert packet.ranked_firm_count == 76
    assert packet.adjudication_firm_count == 74
    assert [row["ranking_ordinal"] for row in template] == list(range(1, 75))
    assert [row["provider_firm_id"] for row in template] == [
        f"firm-{ordinal:03d}" for ordinal in range(74)
    ]
    assert all(row["production_authority"] is False for row in template)


def test_source_iterator_is_exhausted_and_a_short_iterator_is_refused(
    tmp_path: Path,
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    exhausted = False

    def observed_iterator(archive):
        nonlocal exhausted
        yield from iter_physical_accepted_risk_rows(archive)
        exhausted = True

    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "complete-review",
        row_iterator=observed_iterator,
    )
    assert exhausted is True
    assert packet.source_rows_exhausted is True

    def shortened_iterator(archive):
        yield next(iter_physical_accepted_risk_rows(archive))

    with pytest.raises(
        PhysicalFirmOntologyReviewPacketError,
        match=_exact(
            "firm-review iterator did not exhaust the accepted-risk census"
        ),
    ):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            output_root=tmp_path / "short-review",
            row_iterator=shortened_iterator,
        )


def test_sqlite_spool_has_a_hard_cap_and_failed_stage_is_removed(
    tmp_path: Path,
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    output = tmp_path / "review"

    with pytest.raises(
        PhysicalFirmOntologyReviewPacketCapacityError,
        match="hard byte cap",
    ):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            output_root=output,
            maximum_sqlite_spool_bytes=4096,
        )

    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_parent_fsync_failure_rolls_publication_back_and_same_path_retries(
    monkeypatch, tmp_path: Path
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    output = tmp_path / "review"
    original_fsync = packet_module.os.fsync
    parent_sync_calls = 0

    def fail_first_parent_sync(descriptor: int) -> None:
        nonlocal parent_sync_calls
        observed = os.fstat(descriptor)
        if output.exists():
            expected = os.stat(output, follow_symlinks=False)
            if (observed.st_dev, observed.st_ino) == (
                expected.st_dev,
                expected.st_ino,
            ):
                parent_sync_calls += 1
                if parent_sync_calls == 1:
                    raise OSError("parent publication fsync sentinel")
        original_fsync(descriptor)

    monkeypatch.setattr(packet_module.os, "fsync", fail_first_parent_sync)
    with pytest.raises(
        PhysicalFirmOntologyReviewPacketError,
        match=_exact(
            "firm-review publication sync failed and was rolled back"
        ),
    ):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            output_root=output,
        )
    assert parent_sync_calls == 2
    assert output.is_dir()
    assert list(output.iterdir()) == []

    monkeypatch.setattr(packet_module.os, "fsync", original_fsync)
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=output,
    )
    assert require_physical_firm_ontology_review_packet(packet) is packet


def test_ambiguous_rollback_preserves_private_residue(
    monkeypatch, tmp_path: Path
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    output = tmp_path / "review"
    original_fsync = packet_module.os.fsync
    parent_sync_calls = 0

    def fail_every_parent_sync(descriptor: int) -> None:
        nonlocal parent_sync_calls
        observed = os.fstat(descriptor)
        if output.exists():
            expected = os.stat(output, follow_symlinks=False)
            if (observed.st_dev, observed.st_ino) == (
                expected.st_dev,
                expected.st_ino,
            ):
                parent_sync_calls += 1
                raise OSError("ambiguous parent fsync sentinel")
        original_fsync(descriptor)

    monkeypatch.setattr(packet_module.os, "fsync", fail_every_parent_sync)
    with pytest.raises(
        PhysicalFirmOntologyReviewPacketPublicationAmbiguityError,
        match=_exact(
            "firm-review publication rollback is ambiguous; residue preserved"
        ),
    ):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            output_root=output,
        )
    assert parent_sync_calls == 2
    residue = list(output.iterdir())
    assert len(residue) == 1
    assert residue[0].name.startswith(".firm-review-stage-")
    assert stat_mode(residue[0]) == 0o700
    assert not (residue[0] / "construction.sqlite3").exists()
    assert {
        path.name for path in residue[0].iterdir()
    } == {
        "manifest.json",
        "manifest.sha256",
        FIRM_ROWS_FILENAME,
        ADJUDICATION_TEMPLATE_FILENAME,
    }


def test_post_publish_mint_failure_rolls_back_and_same_path_retries(
    monkeypatch, tmp_path: Path
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    output = tmp_path / "review"
    original_mint = packet_module._mint

    def fail_after_publish(**values):
        assert values["archive_path"].parent == output
        assert values["archive_path"].is_dir()
        raise RuntimeError("post-publication mint sentinel")

    monkeypatch.setattr(packet_module, "_mint", fail_after_publish)
    with pytest.raises(RuntimeError, match="post-publication mint sentinel"):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            output_root=output,
        )
    assert output.is_dir()
    assert list(output.iterdir()) == []

    monkeypatch.setattr(packet_module, "_mint", original_mint)
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=output,
    )
    assert require_physical_firm_ontology_review_packet(packet) is packet


def test_post_publish_rollback_collision_preserves_named_residue(
    monkeypatch, tmp_path: Path
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    output = tmp_path / "review"
    stage = output / ".firm-review-stage-fixed"
    monkeypatch.setattr(packet_module.secrets, "token_hex", lambda _size: "fixed")

    def fail_after_publish_and_occupy_stage(**values):
        assert values["archive_path"].is_dir()
        stage.mkdir(mode=0o700)
        raise RuntimeError("post-publication rollback collision sentinel")

    monkeypatch.setattr(packet_module, "_mint", fail_after_publish_and_occupy_stage)
    with pytest.raises(
        PhysicalFirmOntologyReviewPacketPublicationAmbiguityError,
        match=_exact(
            "firm-review late rollback is ambiguous; residue preserved"
        ),
    ):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            output_root=output,
        )
    visible = [path for path in output.iterdir() if path != stage]
    assert stage.is_dir()
    assert len(visible) == 1
    assert visible[0].is_dir()
    assert visible[0].name.startswith("arv2-firm-ontology-review-")


def test_atomic_no_replace_refuses_a_destination_created_at_rename(
    monkeypatch, tmp_path: Path
) -> None:
    tmp_path.chmod(0o700)
    stage = tmp_path / ".complete-stage"
    stage.mkdir(mode=0o700)
    final = tmp_path / "final"
    original_rename_noreplace = packet_module._rename_noreplace
    raced = False

    def create_competing_destination(
        parent_fd: int, source: str, destination: str
    ) -> None:
        nonlocal raced
        if not raced:
            raced = True
            os.mkdir(destination, 0o700, dir_fd=parent_fd)
            sentinel = final / "owner-sentinel"
            sentinel.write_bytes(b"must-not-replace")
            sentinel.chmod(0o600)
        original_rename_noreplace(parent_fd, source, destination)

    monkeypatch.setattr(
        packet_module, "_rename_noreplace", create_competing_destination
    )
    with pytest.raises(
        PhysicalFirmOntologyReviewPacketError,
        match=_exact("firm-review publication destination exists"),
    ):
        packet_module._publish_stage(stage, final)
    assert raced is True
    assert stage.is_dir()
    assert (final / "owner-sentinel").read_bytes() == b"must-not-replace"


def test_output_separation_and_exact_optional_seed_cross_check(
    tmp_path: Path,
) -> None:
    c1 = _c1(tmp_path / "first", _diagnostic_ratings())
    forbidden = c1.archive_path / "nested-output"
    with pytest.raises(
        PhysicalFirmOntologyReviewPacketError,
        match=_exact("firm-review sources and output must remain separate"),
    ):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            output_root=forbidden,
        )
    assert not forbidden.exists()

    _massive, exact_c1, _sharadar, seed, _legacy = _built_preopen_seed(
        tmp_path / "seed"
    )
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=exact_c1,
        preopen_seed_archive=seed,
        output_root=tmp_path / "seed-review",
    )
    assert packet.preopen_seed_cross_checked is True
    assert packet.preopen_seed_archive_id == seed.archive_id
    assert packet.preopen_seed_archive_sha256 == seed.archive_sha256

    with pytest.raises(
        PhysicalFirmOntologyReviewPacketError,
        match=_exact(
            "pre-open seed does not bind the exact accepted-risk archive"
        ),
    ):
        _build_physical_firm_ontology_review_packet_for_test(
            accepted_risk_archive=c1,
            preopen_seed_archive=seed,
            output_root=tmp_path / "mismatched-seed-review",
        )


def test_tampering_and_forged_authority_are_refused(tmp_path: Path) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "review",
    )
    forged = object.__new__(PhysicalFirmOntologyReviewPacket)
    for field in dataclasses.fields(packet):
        object.__setattr__(forged, field.name, getattr(packet, field.name))
    with pytest.raises(
        PhysicalFirmOntologyReviewPacketError,
        match=_exact("firm-review packet is not current builder authority"),
    ):
        require_physical_firm_ontology_review_packet(forged)

    firm_path = packet.archive_path / FIRM_ROWS_FILENAME
    firm_path.write_bytes(firm_path.read_bytes() + b"{}\n")
    with pytest.raises(
        PhysicalFirmOntologyReviewPacketError,
        match="entry identity changed|JSONL file changed",
    ):
        require_physical_firm_ontology_review_packet(packet)


def test_packet_exposes_no_provider_qc_outcome_or_action_capability(
    tmp_path: Path,
) -> None:
    c1 = _c1(tmp_path, _diagnostic_ratings())
    packet = _build_physical_firm_ontology_review_packet_for_test(
        accepted_risk_archive=c1,
        output_root=tmp_path / "review",
    )
    assert all(
        getattr(packet, name) is False
        for name in (
            "ordering_inferred",
            "scope_inferred",
            "ontology_reviewed",
            "availability_reviewed",
            "production_authority",
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
    source = Path(packet_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        imported == prefix or imported.startswith(prefix + ".")
        for imported in imports
        for prefix in (
            "requests",
            "urllib",
            "http",
            "socket",
            "quantconnect",
            "research.quantconnect",
        )
    )
    forbidden_calls = {
        "create_project",
        "compile_project",
        "backtest",
        "launch",
        "history",
        "add_equity",
        "set_summary_statistic",
        "submit_order",
    }
    assert not {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } & forbidden_calls
