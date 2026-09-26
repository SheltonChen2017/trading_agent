from __future__ import annotations

import dataclasses
from fractions import Fraction
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import MassiveSourceRole
from research.analyst_revisions_v2_qc import accepted_risk_latest_order_package as module


def _row(index, event, *, view=None, security="stock-a", firm="firm-a"):
    return module._evaluator.build_contribution_record(
        source_view_id=view or module._evaluator.SOURCE_VIEW_IDS[0],
        security_id=security, eligible_session_index=index,
        institution_id=firm, common_event_id=event, rating_action="upgrades",
        firm_delta=Fraction(1), global_delta=Fraction(1),
        source_row_sha256="a" * 64,
    )


def _fresh(**updates):
    value = {
        "capture_transport": "massive_https_bearer_default_session",
        "archive_id": "fresh-archive", "archive_sha256": "f" * 64,
        "source_manifest_sha256": "e" * 64, "pair_sha256": "d" * 64,
        "capture_started_at": "2026-09-25T20:01:00.000000Z",
        "capture_completed_at": "2026-09-25T20:02:00.000000Z",
        "requested_first_event_date": "2026-09-17",
        "requested_last_event_date": "2026-09-25", "source_row_count": 10,
        "role_row_counts": tuple((role, 1) for role in (
            MassiveSourceRole.ANALYST_RATINGS, MassiveSourceRole.EARNINGS,
            MassiveSourceRole.CORPORATE_GUIDANCE,
        )),
    }
    value.update(updates)
    return SimpleNamespace(**value)


def _old_archives():
    parent = _fresh(
        archive_id=module._old.EXPECTED_PARENT_ARCHIVE_ID,
        archive_sha256=module._old.EXPECTED_PARENT_ARCHIVE_SHA256,
    )
    delta = _fresh(
        archive_id=module._old.EXPECTED_DELTA_ARCHIVE_ID,
        archive_sha256=module._old.EXPECTED_DELTA_ARCHIVE_SHA256,
    )
    return parent, delta


def test_axis_preserves_old_session_indices_and_ends_at_latest_closed_date():
    old = module._old._successor_sessions()
    new = module._sessions()
    assert new[:len(old)] == old
    assert len(new) == len(old) + 6
    assert new[-1] == "2026-09-25"
    assert new[new.index("2026-09-16") + 1] == "2026-09-17"


def test_only_predecessor_active_memberships_extend_and_ended_rows_stay_identical():
    old_sessions = ({"session": "2026-09-16"}, {"session": "2026-09-17"})
    active = module._evaluator.build_membership_record(
        security_id="active", first_session_index=0,
        last_session_index_exclusive=2, sector_id="sector-a",
    )
    ended = module._evaluator.build_membership_record(
        security_id="ended", first_session_index=0,
        last_session_index_exclusive=1, sector_id="sector-a",
    )
    result, count = module._extend_memberships(
        old_sessions, (active, ended), ("2026-09-16", "2026-09-17", "2026-09-18"),
    )
    assert count == 1
    by_id = {row["security_id"]: row for row in result}
    assert by_id["ended"] == ended
    assert by_id["active"]["last_session_index_exclusive"] == 3


@pytest.mark.parametrize("sessions", [
    ("2026-09-17", "2026-09-18"), ("2026-09-16", "2026-09-17"),
])
def test_nonprefix_or_nonextended_axis_is_refused(sessions):
    with pytest.raises(module.LatestOrderInputPackageError, match="predecessor prefix"):
        module._extend_memberships(
            ({"session": "2026-09-16"}, {"session": "2026-09-17"}), (), sessions,
        )


def test_no_active_membership_is_refused():
    ended = module._evaluator.build_membership_record(
        security_id="ended", first_session_index=0,
        last_session_index_exclusive=1, sector_id="sector-a",
    )
    with pytest.raises(module.LatestOrderInputPackageError, match="no predecessor-active"):
        module._extend_memberships(
            ({"session": "2026-09-16"}, {"session": "2026-09-17"}),
            (ended,), ("2026-09-16", "2026-09-17", "2026-09-18"),
        )


def test_tail_recovery_preserves_prior_records_and_future_eligibility():
    prior = (_row(5, "old-event"),)
    tail = _row(6, "sep15-event")
    fresh = _row(8, "fresh-event")
    result, census, digest = module._merge_preserved_contributions(
        prior, (*prior, tail), (fresh,), 5, frozenset(),
    )
    by_id = {row["contribution_id"]: row for row in result}
    assert by_id[prior[0]["contribution_id"]] == prior[0]
    assert tail in result and fresh in result
    assert census["recovered_tail_contribution_count"] == 1
    assert census["fresh_contribution_count"] == 1
    assert len(digest) == 64


def test_changed_rederived_prior_row_is_refused_instead_of_replacing_history():
    prior = (_row(5, "old-event"),)
    with pytest.raises(module.LatestOrderInputPackageError, match="rederived predecessor"):
        module._merge_preserved_contributions(
            prior, (_row(5, "changed-event"),), (), 5, frozenset(),
        )


def test_fresh_reused_event_is_quarantined_without_erasing_original():
    prior = (_row(5, "reused-event"),)
    result, census, _ = module._merge_preserved_contributions(
        prior, prior, (_row(7, "reused-event"),), 5, frozenset({"reused-event"}),
    )
    assert result == prior
    assert census["cross_boundary_rating_event_refusal_count"] == 1
    assert census["fresh_contribution_count"] == 0


def test_cross_archive_daily_conflict_quarantines_both_new_rows():
    prior = (_row(5, "old-event"),)
    result, census, _ = module._merge_preserved_contributions(
        prior, (*prior, _row(7, "tail-event")), (_row(7, "fresh-event"),),
        5, frozenset(),
    )
    assert result == prior
    assert census["cross_archive_daily_ambiguity_count"] == 1


def test_duplicate_prior_identity_and_postcutoff_prior_row_are_refused():
    row = _row(5, "old-event")
    for prior, cutoff in (((row, row), 5), ((row,), 4)):
        with pytest.raises(module.LatestOrderInputPackageError, match="predecessor contribution"):
            module._merge_preserved_contributions(prior, (), (), cutoff, frozenset())


def test_forged_archive_has_no_production_authority():
    parent, delta = _old_archives()
    with pytest.raises(ValueError):
        module._authenticate_archives(parent, delta, _fresh())


@pytest.mark.parametrize("update", [
    {"requested_first_event_date": "2026-09-18"},
    {"requested_last_event_date": "2026-09-24"},
    {"capture_started_at": "2026-09-25T19:59:59.000000Z"},
    {"capture_completed_at": "2026-09-25T20:00:59.000000Z"},
    {"role_row_counts": ((MassiveSourceRole.ANALYST_RATINGS, 1),)},
    {"capture_transport": "offline_test_double"},
])
def test_exact_range_clock_roles_and_transport_are_required(monkeypatch, update):
    monkeypatch.setattr(module._archive, "require_physical_accepted_risk_archive", lambda value: value)
    parent, delta = _old_archives()
    with pytest.raises(module.LatestOrderInputPackageError):
        module._authenticate_archives(parent, delta, _fresh(**update))


def test_old_archive_pin_change_refuses(monkeypatch):
    monkeypatch.setattr(module._archive, "require_physical_accepted_risk_archive", lambda value: value)
    parent, delta = _old_archives()
    delta.archive_sha256 = "0" * 64
    with pytest.raises(module.LatestOrderInputPackageError, match="predecessor archive identity"):
        module._authenticate_archives(parent, delta, _fresh())


def test_cross_boundary_ids_use_rating_role_only_and_return_common_id(monkeypatch):
    parent, delta = _old_archives()
    fresh = _fresh()
    def source(identifier, role):
        return SimpleNamespace(provider_event_id=identifier, locator=SimpleNamespace(source_role=role))
    rows = {
        id(parent): (source("reuse", MassiveSourceRole.ANALYST_RATINGS),),
        id(delta): (source("guidance-only", MassiveSourceRole.CORPORATE_GUIDANCE),),
        id(fresh): (source("reuse", MassiveSourceRole.ANALYST_RATINGS),
                    source("guidance-only", MassiveSourceRole.ANALYST_RATINGS)),
    }
    monkeypatch.setattr(module._archive, "iter_physical_accepted_risk_rows", lambda value: iter(rows[id(value)]))
    assert module._cross_boundary_rating_events(parent, delta, fresh) == frozenset({
        module._compact._PINNED_COMMON_EVENT_ID("reuse"),
    })


def test_offline_build_materializes_real_canonical_package_and_activation(monkeypatch, tmp_path):
    sessions = module._sessions()
    old_sessions = module._old._successor_sessions()
    cutoff = sessions.index(module._old.DELTA_DECISION_END_SESSION)
    prior = tuple(_row(cutoff, "old-event", view=view)
                  for view in module._evaluator.SOURCE_VIEW_IDS)
    tail = tuple(_row(cutoff + 1, "tail-event", view=view)
                 for view in module._evaluator.SOURCE_VIEW_IDS)
    fresh_rows = tuple(_row(cutoff + 3, "fresh-event", view=view)
                       for view in module._evaluator.SOURCE_VIEW_IDS)
    memberships = (module._evaluator.build_membership_record(
        security_id="stock-a", first_session_index=0,
        last_session_index_exclusive=len(old_sessions), sector_id="sector-a",
    ),)
    roles = {
        "session_axis": module._old._session_records(old_sessions),
        "memberships": memberships, "contributions": prior,
        "runtime_symbol_bindings": ({"security_id": "stock-a", "diagnostic_current_ticker": "AAA"},),
    }
    old = SimpleNamespace(
        package=SimpleNamespace(package_id=module._old.EXPECTED_DELTA_PACKAGE_ID,
                                package_sha256=module._old.EXPECTED_DELTA_PACKAGE_SHA256),
        lineage_sha256=module._old.EXPECTED_DELTA_LINEAGE_SHA256,
        delta_contribution_count=len(prior),
    )
    monkeypatch.setattr(module._old, "load_accepted_risk_delta_order_package", lambda *_args, **_kwargs: old)
    original_load_roles = module._old._load_prior_roles
    monkeypatch.setattr(module._old, "_load_prior_roles", lambda _value: ({
        "source_lineage_sha256s": {"security_master_admission_sha256": module._old.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256},
    }, roles))
    parent, delta = _old_archives()
    fresh = _fresh()
    monkeypatch.setattr(module._archive, "require_physical_accepted_risk_archive", lambda value: value)
    monkeypatch.setattr(module, "_cross_boundary_rating_events", lambda *_args: frozenset())
    firms = SimpleNamespace(admission_sha256=module._old.EXPECTED_FIRM_ADMISSION_SHA256)
    contract = SimpleNamespace(map_hash=module._old.EXPECTED_GLOBAL_MAP_SHA256)
    monkeypatch.setattr(module, "require_section72_owner_waived_firm_admission", lambda value: value)
    monkeypatch.setattr(module, "require_loaded_global_benchmark_contract", lambda value: value)
    seen = []
    def derive(**kwargs):
        seen.append(kwargs)
        rows = (*prior, *tail) if kwargs["archive"] is delta else fresh_rows
        return tuple(rows), "b" * 64, {"rating_source_row_count": len(rows)}
    monkeypatch.setattr(module._compact, "_derive_contributions", derive)
    result = module.build_latest_order_input_package(
        old_delta_package_path=tmp_path / "old", parent_archive=parent,
        prior_delta_archive=delta, fresh_archive=fresh, firm_admission=firms,
        global_contract=contract, output_root=tmp_path / "new",
    )
    assert result.recovered_tail_contribution_count == 2
    assert result.fresh_contribution_count == 2
    assert all(item["maximum_eligible_session"] == "2026-09-25" for item in seen)
    assert result.lineage["historical_contributions_unchanged"] is True
    assert result.package.source_disposition_sha256 == result.lineage_sha256
    assert result.package.upload_objects[-1].activation_manifest is True
    detached = result.lineage
    detached["final_execution_session"] = "2099-01-01"
    assert module.require_latest_order_input_package(result) is result
    assert result.lineage["final_execution_session"] == "2026-09-25"
    forged = dataclasses.replace(result, lineage_bytes=result.lineage_bytes + b" ")
    with pytest.raises(module.LatestOrderInputPackageError, match="lineage or wrapper binding"):
        module.require_latest_order_input_package(forged)
    loaded = module._compact.load_accepted_risk_preliminary_package(
        result.package.package_path, expected_package_sha256=result.package.package_sha256,
    )
    assert loaded.package_sha256 == result.package.package_sha256
    objects = tuple(module._compact.iter_accepted_risk_preliminary_upload_objects(loaded))
    assert objects[-1][0].role == "activation_manifest"
    _, new_roles = original_load_roles(loaded)
    assert new_roles["contributions"] == module._old._merge_contributions(prior, (*tail, *fresh_rows))
    # Package publication is immutable/content-derived; replay returns the
    # same exact package rather than overwriting a different historical pin.
    assert result.package.package_id != module._old.EXPECTED_DELTA_PACKAGE_ID
