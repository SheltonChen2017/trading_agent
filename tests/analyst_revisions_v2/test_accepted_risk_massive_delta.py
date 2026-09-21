"""Offline tests for the parent-bound 2026 Massive delta contract."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import MassiveSourceRole
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2_qc import accepted_risk_massive_delta as delta_module
from research.analyst_revisions_v2_qc.accepted_risk_massive_delta import (
    CENSORED_VIEW,
    CURRENT_VIEW,
    LITERAL_CUTOFF_CLOSE_AT,
    ParentBoundMassiveDeltaError,
    _build_parent_bound_massive_delta_for_test,
    build_parent_bound_massive_delta,
    iter_parent_bound_massive_delta_rows,
    render_parent_bound_massive_delta_manifest_bytes,
    require_parent_bound_massive_delta,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    _build_physical_accepted_risk_archive_for_test,
)
from scripts.capture_arv2_massive import (
    _capture_massive_history_spooled_for_test,
)
from tests.analyst_revisions_v2.test_massive_capture_adapter import (
    FakeResponse,
    FakeSession,
    KEY,
    ROLE_ORDER,
    _endpoint,
    _payload,
    _row,
)


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


def _dated_row(
    identifier: str,
    *,
    role: MassiveSourceRole,
    event_date: str,
) -> dict[str, object]:
    value = _row(identifier, role=role)
    value["date"] = event_date
    if role is MassiveSourceRole.CORPORATE_GUIDANCE:
        value["last_updated"] = f"{event_date} 09:30:00"
    else:
        value["last_updated"] = f"{event_date}T13:30:00Z"
    return value


def _archive(
    tmp_path: Path,
    *,
    label: str,
    first: str,
    last: str,
    event_date: str,
    clock: datetime,
    identifiers: dict[MassiveSourceRole, str],
):
    responses = [
        FakeResponse(
            _payload(
                [
                    _dated_row(
                        identifiers[role], role=role, event_date=event_date
                    )
                ]
            ),
            _endpoint(role),
        )
        for role in ROLE_ORDER
    ]
    capture = _capture_massive_history_spooled_for_test(
        requested_first_event_date=first,
        requested_last_event_date=last,
        artifact_root=tmp_path / f"captures-{label}",
        session=FakeSession(responses),
        clock=lambda: clock,
        api_key=KEY,
    )
    return _build_physical_accepted_risk_archive_for_test(
        source_artifact_path=capture.artifact_path,
        output_root=tmp_path / f"archives-{label}",
    )


def _archives(
    tmp_path: Path,
    *,
    parent_identifiers: dict[MassiveSourceRole, str] | None = None,
    delta_identifiers: dict[MassiveSourceRole, str] | None = None,
    parent_first: str = "2013-01-02",
    parent_last: str = "2025-12-31",
    delta_first: str = "2026-01-01",
    delta_last: str = "2026-09-16",
    parent_clock: datetime = datetime(
        2026, 9, 14, 1, 13, 37, 349022, tzinfo=timezone.utc
    ),
    delta_clock: datetime = datetime(
        2026, 9, 16, 20, 5, 0, 123456, tzinfo=timezone.utc
    ),
):
    parent_ids = parent_identifiers or {
        MassiveSourceRole.ANALYST_RATINGS: "parent-rating",
        MassiveSourceRole.EARNINGS: "parent-earnings",
        MassiveSourceRole.CORPORATE_GUIDANCE: "parent-guidance",
    }
    delta_ids = delta_identifiers or {
        MassiveSourceRole.ANALYST_RATINGS: "delta-rating",
        MassiveSourceRole.EARNINGS: "delta-earnings",
        MassiveSourceRole.CORPORATE_GUIDANCE: "delta-guidance",
    }
    parent = _archive(
        tmp_path,
        label="parent",
        first=parent_first,
        last=parent_last,
        event_date="2025-12-30",
        clock=parent_clock,
        identifiers=parent_ids,
    )
    delta = _archive(
        tmp_path,
        label="delta",
        first=delta_first,
        last=delta_last,
        event_date="2026-01-02",
        clock=delta_clock,
        identifiers=delta_ids,
    )
    return parent, delta


def _build(parent, delta):
    return _build_parent_bound_massive_delta_for_test(
        parent_archive=parent,
        delta_archive=delta,
        expected_parent_archive_id=parent.archive_id,
        expected_parent_archive_sha256=parent.archive_sha256,
        expected_delta_archive_id=delta.archive_id,
        expected_delta_archive_sha256=delta.archive_sha256,
    )


def test_builds_deterministic_parent_bound_multi_vintage_stream(tmp_path: Path):
    parent, delta = _archives(tmp_path)

    value = _build(parent, delta)

    assert require_parent_bound_massive_delta(value) is value
    assert value.source_row_count == value.admitted_row_count == 6
    assert value.excluded_row_count == 0
    assert value.multi_vintage is True
    assert value.transactional_snapshot is False
    assert value.pristine_point_in_time is False
    assert value.complete_version_history is False
    assert value.complete_deletion_tombstones is False
    assert value.production_transport is False
    assert value.literal_cutoff_close_at == LITERAL_CUTOFF_CLOSE_AT
    row_ids = [
        row.provider_event_id for row in iter_parent_bound_massive_delta_rows(value)
    ]
    assert row_ids == [
        "parent-rating",
        "parent-earnings",
        "parent-guidance",
        "delta-rating",
        "delta-earnings",
        "delta-guidance",
    ]
    first = render_parent_bound_massive_delta_manifest_bytes(value)
    second = render_parent_bound_massive_delta_manifest_bytes(value)
    assert first == second
    manifest = json.loads(first)
    assert manifest["accepted_risk_disclosures"]["current_view"] == CURRENT_VIEW
    assert manifest["accepted_risk_disclosures"]["censored_view"] == CENSORED_VIEW
    assert manifest["accepted_risk_disclosures"]["multi_vintage"] is True
    assert manifest["accepted_risk_disclosures"]["production_transport"] is False
    assert manifest["parent"]["capture_transport"] == "offline_test_double"
    assert manifest["delta"]["capture_transport"] == "offline_test_double"
    assert manifest["row_stream"]["current_view_included_count"] == 6
    assert manifest["row_stream"]["censored_view_included_count"] == 6
    assert (
        manifest["accepted_risk_disclosures"]["transactional_cross_vintage_claim"]
        is False
    )
    assert set(manifest["source_roles"]) == {
        "analyst_ratings",
        "earnings",
        "corporate_guidance",
    }
    assert manifest["accepted_risk_disclosures"]["security_admission"] == (
        "not_provided_by_massive_requires_separate_point_in_time_sharadar_authority"
    )
    assert not any(manifest["capabilities"].values())


def test_production_entrypoint_refuses_fixture_transports(tmp_path: Path):
    parent, delta = _archives(tmp_path)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact(
            "production parent-bound Massive delta requires production transports"
        ),
    ):
        build_parent_bound_massive_delta(
            parent_archive=parent,
            delta_archive=delta,
            expected_parent_archive_id=parent.archive_id,
            expected_parent_archive_sha256=parent.archive_sha256,
            expected_delta_archive_id=delta.archive_id,
            expected_delta_archive_sha256=delta.archive_sha256,
        )


class _AlwaysEqualStr(str):
    calls = 0

    def __eq__(self, _other):
        type(self).calls += 1
        return True

    def __ne__(self, _other):
        type(self).calls += 1
        return False


@pytest.mark.parametrize(
    ("pin", "replacement"),
    [
        ("expected_parent_archive_id", "wrong-parent"),
        ("expected_parent_archive_sha256", "0" * 64),
        ("expected_delta_archive_id", "wrong-delta"),
        ("expected_delta_archive_sha256", "1" * 64),
    ],
)
def test_hostile_archive_identity_pins_refuse_without_comparison(
    tmp_path: Path, pin: str, replacement: str
):
    parent, delta = _archives(tmp_path)
    arguments = {
        "parent_archive": parent,
        "delta_archive": delta,
        "expected_parent_archive_id": parent.archive_id,
        "expected_parent_archive_sha256": parent.archive_sha256,
        "expected_delta_archive_id": delta.archive_id,
        "expected_delta_archive_sha256": delta.archive_sha256,
    }
    _AlwaysEqualStr.calls = 0
    arguments[pin] = _AlwaysEqualStr(replacement)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("archive identity pins must be exact strings"),
    ):
        _build_parent_bound_massive_delta_for_test(**arguments)
    assert _AlwaysEqualStr.calls == 0


@pytest.mark.parametrize("pin", ["parent_id", "parent_sha", "delta_id", "delta_sha"])
def test_refuses_every_archive_identity_pin_mismatch(tmp_path: Path, pin: str):
    parent, delta = _archives(tmp_path)
    arguments = {
        "parent_archive": parent,
        "delta_archive": delta,
        "expected_parent_archive_id": parent.archive_id,
        "expected_parent_archive_sha256": parent.archive_sha256,
        "expected_delta_archive_id": delta.archive_id,
        "expected_delta_archive_sha256": delta.archive_sha256,
    }
    if pin == "parent_id":
        arguments["expected_parent_archive_id"] = "wrong-parent"
        message = "parent archive identity pin mismatch"
    elif pin == "parent_sha":
        arguments["expected_parent_archive_sha256"] = "0" * 64
        message = "parent archive identity pin mismatch"
    elif pin == "delta_id":
        arguments["expected_delta_archive_id"] = "wrong-delta"
        message = "delta archive identity pin mismatch"
    else:
        arguments["expected_delta_archive_sha256"] = "0" * 64
        message = "delta archive identity pin mismatch"
    with pytest.raises(ParentBoundMassiveDeltaError, match=_exact(message)):
        build_parent_bound_massive_delta(**arguments)


def test_refuses_nonadjacent_delta_range(tmp_path: Path):
    parent, delta = _archives(tmp_path, delta_first="2026-01-02")

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact(
            "delta archive is not the exact 2026-01-01 through 2026-09-16 successor"
        ),
    ):
        _build(parent, delta)


def test_refuses_capture_started_before_literal_close(tmp_path: Path):
    parent, delta = _archives(
        tmp_path,
        delta_clock=datetime(
            2026, 9, 16, 19, 59, 59, 999999, tzinfo=timezone.utc
        ),
    )

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("delta capture started before the literal cutoff session close"),
    ):
        _build(parent, delta)


def test_refuses_capture_vintages_in_the_wrong_order(tmp_path: Path):
    parent, delta = _archives(
        tmp_path,
        parent_clock=datetime(2026, 9, 17, 1, 0, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent and delta do not preserve two ordered capture vintages"),
    ):
        _build(parent, delta)


@pytest.mark.parametrize(
    ("role", "message"),
    [
        (
            MassiveSourceRole.ANALYST_RATINGS,
            "cross-boundary analyst_ratings provider event ID is forbidden",
        ),
        (
            MassiveSourceRole.EARNINGS,
            "cross-boundary earnings provider event ID is forbidden",
        ),
    ],
)
def test_refuses_cross_boundary_non_guidance_duplicate(
    tmp_path: Path, role: MassiveSourceRole, message: str
):
    common = "same-provider-event"
    parent_ids = {
        MassiveSourceRole.ANALYST_RATINGS: "parent-rating",
        MassiveSourceRole.EARNINGS: "parent-earnings",
        MassiveSourceRole.CORPORATE_GUIDANCE: "parent-guidance",
    }
    delta_ids = {
        MassiveSourceRole.ANALYST_RATINGS: "delta-rating",
        MassiveSourceRole.EARNINGS: "delta-earnings",
        MassiveSourceRole.CORPORATE_GUIDANCE: "delta-guidance",
    }
    parent_ids[role] = common
    delta_ids[role] = common
    parent, delta = _archives(
        tmp_path,
        parent_identifiers=parent_ids,
        delta_identifiers=delta_ids,
    )

    with pytest.raises(ParentBoundMassiveDeltaError, match=_exact(message)):
        _build(parent, delta)


def test_refuses_cross_boundary_role_change(tmp_path: Path):
    parent, delta = _archives(
        tmp_path,
        parent_identifiers={
            MassiveSourceRole.ANALYST_RATINGS: "same-provider-event",
            MassiveSourceRole.EARNINGS: "parent-earnings",
            MassiveSourceRole.CORPORATE_GUIDANCE: "parent-guidance",
        },
        delta_identifiers={
            MassiveSourceRole.ANALYST_RATINGS: "delta-rating",
            MassiveSourceRole.EARNINGS: "same-provider-event",
            MassiveSourceRole.CORPORATE_GUIDANCE: "delta-guidance",
        },
    )

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("cross-boundary provider event ID changes source role"),
    ):
        _build(parent, delta)


def test_guidance_duplicate_is_named_hashed_and_excluded_in_both_vintages(
    tmp_path: Path,
):
    duplicate = "private-guidance-event"
    parent, delta = _archives(
        tmp_path,
        parent_identifiers={
            MassiveSourceRole.ANALYST_RATINGS: "parent-rating",
            MassiveSourceRole.EARNINGS: "parent-earnings",
            MassiveSourceRole.CORPORATE_GUIDANCE: duplicate,
        },
        delta_identifiers={
            MassiveSourceRole.ANALYST_RATINGS: "delta-rating",
            MassiveSourceRole.EARNINGS: "delta-earnings",
            MassiveSourceRole.CORPORATE_GUIDANCE: duplicate,
        },
    )

    value = _build(parent, delta)

    assert value.source_row_count == 6
    assert value.admitted_row_count == 4
    assert value.excluded_row_count == 2
    assert value.current_view_included_count == 4
    assert value.censored_view_included_count == 4
    assert value.view_disagreement_count == 0
    assert value.role_admitted_row_counts == (
        (MassiveSourceRole.ANALYST_RATINGS, 2),
        (MassiveSourceRole.EARNINGS, 2),
        (MassiveSourceRole.CORPORATE_GUIDANCE, 0),
    )
    assert len(value.cross_boundary_guidance_refusals) == 1
    refusal = value.cross_boundary_guidance_refusals[0]
    assert refusal.parent_occurrence_count == 1
    assert refusal.delta_occurrence_count == 1
    assert refusal.excluded_occurrence_count == 2
    assert refusal.provider_event_id_sha256 == sha256_bytes(
        canonical_json_bytes({"provider_event_id": duplicate})
    )
    manifest = render_parent_bound_massive_delta_manifest_bytes(value)
    assert duplicate.encode() not in manifest
    assert refusal.refusal_id.encode() in manifest
    row_ids = [
        row.provider_event_id for row in iter_parent_bound_massive_delta_rows(value)
    ]
    assert row_ids == [
        "parent-rating",
        "parent-earnings",
        "delta-rating",
        "delta-earnings",
    ]


def test_mutated_composite_is_not_current_authority(tmp_path: Path):
    parent, delta = _archives(tmp_path)
    value = _build(parent, delta)
    object.__setattr__(value, "multi_vintage", False)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("composite authority changed"),
    ):
        require_parent_bound_massive_delta(value)


@pytest.mark.parametrize(
    "name",
    [
        "_validate_geometry",
        "_analyze_parent_and_delta",
        "_fingerprint",
        "canonical_json_bytes",
        "iter_physical_accepted_risk_rows",
    ],
)
def test_every_load_bearing_global_mutation_isolated_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
):
    parent, delta = _archives(tmp_path)
    monkeypatch.setattr(delta_module, name, lambda *args, **kwargs: None)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        _build(parent, delta)


def test_checker_and_pinned_geometry_cannot_be_rebound_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path, delta_first="2026-01-02")
    monkeypatch.setattr(delta_module, "_PINNED_REQUIRE_DEPENDENCIES", lambda: None)
    monkeypatch.setattr(delta_module, "_PINNED_VALIDATE_GEOMETRY", lambda *_: None)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        _build(parent, delta)


def test_internal_builder_and_its_pin_cannot_be_rebound_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    hostile_calls = 0

    def hostile(**_kwargs):
        nonlocal hostile_calls
        hostile_calls += 1
        return object()

    monkeypatch.setattr(delta_module, "_build_parent_bound_massive_delta", hostile)
    monkeypatch.setattr(delta_module, "_PINNED_INTERNAL_BUILD", hostile)
    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        _build(parent, delta)
    assert hostile_calls == 0


def test_render_refuses_rebound_composite_checker_before_reading_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    value = _build(parent, delta)
    object.__setattr__(value, "outcome_access", True)
    hostile_calls = 0

    def hostile(candidate):
        nonlocal hostile_calls
        hostile_calls += 1
        return candidate

    monkeypatch.setattr(delta_module, "_PINNED_REQUIRE_COMPOSITE", hostile)
    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        render_parent_bound_massive_delta_manifest_bytes(value)
    assert hostile_calls == 0


def test_authority_registry_and_mirrors_cannot_be_rebound_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    value = _build(parent, delta)
    forged_root = {}
    forged_lock = delta_module.threading.RLock()
    monkeypatch.setattr(delta_module, "_AUTHORITIES", forged_root)
    monkeypatch.setattr(delta_module, "_PINNED_AUTHORITIES", forged_root)
    monkeypatch.setattr(delta_module, "_AUTHORITY_LOCK", forged_lock)
    monkeypatch.setattr(delta_module, "_PINNED_AUTHORITY_LOCK", forged_lock)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        require_parent_bound_massive_delta(value)


def test_hostile_scalar_refuses_without_equality_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    _AlwaysEqualStr.calls = 0
    monkeypatch.setattr(delta_module, "SCHEMA", _AlwaysEqualStr("forged-schema"))

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        _build(parent, delta)
    assert _AlwaysEqualStr.calls == 0


def test_hostile_production_transport_pin_cannot_promote_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    _AlwaysEqualStr.calls = 0
    monkeypatch.setattr(
        delta_module,
        "_PINNED_PRODUCTION_TRANSPORT",
        _AlwaysEqualStr("offline_test_double"),
    )

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        build_parent_bound_massive_delta(
            parent_archive=parent,
            delta_archive=delta,
            expected_parent_archive_id=parent.archive_id,
            expected_parent_archive_sha256=parent.archive_sha256,
            expected_delta_archive_id=delta.archive_id,
            expected_delta_archive_sha256=delta.archive_sha256,
        )
    assert _AlwaysEqualStr.calls == 0


def test_analysis_reads_delta_parent_delta_and_parent_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    original = delta_module._PINNED_FOLD_ARCHIVE_ROWS
    calls = []
    legacy_calls = 0

    def counting(archive, visitor):
        calls.append(archive)
        return original(archive, visitor)

    def hostile_legacy(_archive):
        nonlocal legacy_calls
        legacy_calls += 1
        raise AssertionError("analysis must not use the forensic row iterator")

    monkeypatch.setattr(delta_module, "_PINNED_FOLD_ARCHIVE_ROWS", counting)
    monkeypatch.setattr(
        delta_module, "_PINNED_ITER_ARCHIVE_ROWS", hostile_legacy
    )
    delta_module._analyze_parent_and_delta(parent, delta)
    assert calls == [delta, parent, delta]
    assert legacy_calls == 0


def test_iterator_rechecks_before_advancing_after_each_yield(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    value = _build(parent, delta)
    rows = iter_parent_bound_massive_delta_rows(value)
    assert next(rows).provider_event_id == "parent-rating"
    hostile_calls = 0

    def hostile(_row):
        nonlocal hostile_calls
        hostile_calls += 1
        return b"{}"

    monkeypatch.setattr(delta_module, "_PINNED_ROW_PAYLOAD", hostile)
    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        next(rows)
    assert hostile_calls == 0


def test_record_type_rebinding_cannot_mint_noncanonical_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)

    class Replacement(delta_module.ParentBoundMassiveDelta):
        pass

    monkeypatch.setattr(delta_module, "ParentBoundMassiveDelta", Replacement)
    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent-bound Massive delta dependency changed"),
    ):
        _build(parent, delta)


def test_require_render_and_iteration_recheck_static_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    parent, delta = _archives(tmp_path)
    value = _build(parent, delta)
    monkeypatch.setattr(delta_module, "_validate_geometry", lambda *_: None)

    for action in (
        lambda: require_parent_bound_massive_delta(value),
        lambda: render_parent_bound_massive_delta_manifest_bytes(value),
        lambda: tuple(iter_parent_bound_massive_delta_rows(value)),
    ):
        with pytest.raises(
            ParentBoundMassiveDeltaError,
            match=_exact("parent-bound Massive delta dependency changed"),
        ):
            action()


@pytest.mark.parametrize(
    ("first", "last"),
    [
        ("2013-01-03", "2025-12-31"),
        ("2013-01-02", "2025-12-30"),
    ],
)
def test_refuses_every_parent_range_drift(
    tmp_path: Path, first: str, last: str
):
    parent, delta = _archives(
        tmp_path, parent_first=first, parent_last=last
    )

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact(
            "parent archive is not the exact 2013-01-02 through 2025-12-31 authority"
        ),
    ):
        _build(parent, delta)


def test_refuses_wrong_archive_type_before_any_iteration(tmp_path: Path):
    _parent, delta = _archives(tmp_path)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("parent archive has the wrong type"),
    ):
        build_parent_bound_massive_delta(
            parent_archive=object(),
            delta_archive=delta,
            expected_parent_archive_id="expected-parent",
            expected_parent_archive_sha256="0" * 64,
            expected_delta_archive_id=delta.archive_id,
            expected_delta_archive_sha256=delta.archive_sha256,
        )


def test_unissued_composite_is_refused(tmp_path: Path):
    unissued = object.__new__(delta_module.ParentBoundMassiveDelta)

    with pytest.raises(
        ParentBoundMassiveDeltaError,
        match=_exact("composite is not current builder authority"),
    ):
        require_parent_bound_massive_delta(unissued)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("composite_sha256", "0" * 64, "composite content root changed"),
        (
            "composite_id",
            "arv2-parent-bound-massive-delta-wrong",
            "composite ID/content root mismatch",
        ),
    ],
)
def test_content_root_and_id_are_independently_reauthenticated(
    tmp_path: Path, field: str, replacement: str, message: str
):
    parent, delta = _archives(tmp_path)
    value = _build(parent, delta)
    object.__setattr__(value, field, replacement)

    with pytest.raises(ParentBoundMassiveDeltaError, match=_exact(message)):
        require_parent_bound_massive_delta(value)
