"""Synthetic offline composer tests; no operational capture/archive paths."""
from __future__ import annotations

import dataclasses
import hashlib
import os
import sys
from fractions import Fraction
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as m


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    safe = {key: os.environ[key] for key in (
        "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    ) if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)
    assert "assistant.dispatch_fence" not in sys.modules


def contribution(index, event, *, firm="firm-a", view=None):
    return m._evaluator.build_contribution_record(
        source_view_id=view or m._evaluator.SOURCE_VIEW_IDS[0], security_id="stock-a",
        eligible_session_index=index, institution_id=firm, common_event_id=event,
        rating_action="upgrades", firm_delta=Fraction(1, 2), global_delta=Fraction(1),
        source_row_sha256="a" * 64)


def provider_row(**changes):
    return {"benzinga_id": "fixture-rating-1", "date": "2026-10-01", "time": "12:00:00",
        "last_updated": "2026-10-01T12:00:00Z", "ticker": "SYNTH",
        "benzinga_firm_id": "firm-a", "firm": "Synthetic Firm",
        "rating_action": "upgrades", "rating": "Buy", "previous_rating": "Hold", **changes}


def accepted_delta(tmp_path, monkeypatch, rows=None):
    d = m._ratings._transport
    source_rows = [provider_row()] if rows is None else rows
    source_rows = [*source_rows, source_rows[0]]
    raw = d.canonical_bytes({"status": "OK", "results": source_rows})
    extracted, _ = d._capture._response_rows_and_next_url(raw, page_limit=d.PAGE_LIMIT)
    page = d.build_page_record(page_number=1, raw_response=raw, provider_rows=extracted,
        response_received_at="2026-10-13T23:00:01.000000Z", request_cursor_sha256=None)
    manifest = d.build_manifest(pages=[page], capture_started_at="2026-10-13T23:00:00.000000Z",
        capture_completed_at="2026-10-13T23:00:02.000000Z")
    path = tmp_path / "synthetic-ratings"
    path.mkdir(mode=0o700)
    payload = d.canonical_bytes(manifest)
    digest = hashlib.sha256(payload).hexdigest()
    files = dict(zip(d.page_names(1), (raw, extracted), strict=True))
    files.update({"manifest.json": payload, "manifest.sha256": (digest + "\n").encode()})
    for name, data in files.items():
        (path / name).write_bytes(data)
        (path / name).chmod(0o600)
    monkeypatch.setattr(m._ratings, "EXPECTED_MANIFEST_SHA256", digest)
    monkeypatch.setattr(m._ratings, "EXPECTED_MANIFEST_BYTE_COUNT", len(payload))
    monkeypatch.setattr(m._ratings, "EXPECTED_SOURCE_ROW_COUNT", len(source_rows))
    monkeypatch.setattr(m._ratings, "EXPECTED_UNIQUE_ROW_COUNT", len(source_rows) - 1)
    return m._ratings._authenticate_retained_capture(path, digest, len(payload))


def firms():
    mappings = tuple(SimpleNamespace(provider_firm_id="firm-a", firm_name="Synthetic Firm",
        raw_label=label, normalized_score=score, valid_from="2013-01-01", valid_to=None,
        scale_size=3, scope="accepted-risk") for label, score in (("Buy", Fraction(1)), ("Hold", Fraction(1, 2))))
    return SimpleNamespace(mappings=mappings, refused_provider_firm_ids=(),
        admission_sha256=m._old.EXPECTED_FIRM_ADMISSION_SHA256)


def derive(rows, monkeypatch, **changes):
    monkeypatch.setattr(m._compact, "_global_delta", lambda **_kwargs: Fraction(1))
    values = dict(rows=rows, sessions=m._sessions(), ticker_to_security={"SYNTH": "stock-a"},
        firm_admission=firms(), global_contract=object(), minimum_position=0, maximum_rows=16000)
    values.update(changes)
    return m._derive_rating_rows(**values)


def archive(**changes):
    value = dict(archive_id="arv2-physical-accepted-risk-" + m.EXPECTED_TAIL_ARCHIVE_SHA256[:24],
        archive_sha256=m.EXPECTED_TAIL_ARCHIVE_SHA256,
        source_manifest_sha256=m.EXPECTED_TAIL_SOURCE_MANIFEST_SHA256,
        pair_sha256="d" * 64, capture_started_at="2026-09-26T06:00:00.000000Z",
        capture_completed_at="2026-09-26T06:01:00.000000Z",
        requested_first_event_date="2026-09-17", requested_last_event_date="2026-09-25",
        source_row_count=m.MAX_TAIL_SOURCE_ROWS)
    value.update(changes)
    return SimpleNamespace(**value)


def predecessor(**changes):
    value = dict(package=SimpleNamespace(package_sha256=m.EXPECTED_PREDECESSOR_PACKAGE_SHA256,
        package_id="arv2-preliminary-qc-package-" + m.EXPECTED_PREDECESSOR_PACKAGE_SHA256[:24]),
        lineage_sha256=m.EXPECTED_PREDECESSOR_LINEAGE_SHA256,
        lineage={"predecessor_package_sha256": m._old.EXPECTED_DELTA_PACKAGE_SHA256,
                 "predecessor_lineage_sha256": m._old.EXPECTED_DELTA_LINEAGE_SHA256})
    value.update(changes)
    return SimpleNamespace(**value)


def test_full_axis_preserves_all_original_indices_and_valuation_endpoint():
    prior = m._latest._sessions()
    new = m._sessions()
    assert len(prior) == 3454 and len(new) == 3466
    assert new[:len(prior)] == prior
    assert new[0] == "2013-01-02" and new[-1] == "2026-10-13"
    assert new[-2] == m.DECISION_CUTOFF_SESSION == "2026-10-12"


def test_profile_is_new_qualified_ratings_only_not_a_permit():
    profile = m.profile_record()
    assert m.PROFILE_SHA256 == m._sha(profile)
    assert profile["historical_prefix_count"] == 13015
    assert profile["tail_source_row_bound"] == 1398
    assert "stale" in profile["inventory_policy"]
    assert profile["contribution_eligibility_end_session"] == "2026-10-13"
    assert profile["valuation_end_session"] == "2026-10-13"
    assert "no_forced_Oct13_order" in profile["execution_policy"]
    assert all(profile[name] is False for name in ("orders", "trading", "point_in_time", "formal", "paper_or_live_ready"))


def test_only_active_inventory_extends_without_rewriting_history():
    prior = ({"session": "2026-09-24"}, {"session": "2026-09-25"})
    rows = tuple(m._evaluator.build_membership_record(security_id=name,
        first_session_index=0, last_session_index_exclusive=end, sector_id="sector-a")
        for name, end in (("active", 2), ("ended", 1)))
    result, count = m._extend_stale_inventory(prior, rows, ("2026-09-24", "2026-09-25", "2026-09-28"))
    assert count == 1
    assert result[1] == rows[1] and result[0]["last_session_index_exclusive"] == 3
    assert rows[0]["last_session_index_exclusive"] == 2


@pytest.mark.parametrize("prior,new", [
    ((), ("2026-09-25",)), (({"session": "2026-09-24"},), ("2026-09-24", "2026-09-25")),
    (({"session": "2026-09-25"},), ("2026-09-25",)),
    (({"session": "2026-09-25"},), ("2026-09-24", "2026-09-25", "2026-09-28")),
])
def test_nonprefix_inventory_axis_refuses(prior, new):
    with pytest.raises(m.OctoberOrderInputPackageError, match="axis_prefix"):
        m._extend_stale_inventory(prior, (), new)


def test_no_active_inventory_refuses():
    with pytest.raises(m.OctoberOrderInputPackageError, match="no_active"):
        m._extend_stale_inventory(({"session": "2026-09-25"},), (), ("2026-09-25", "2026-09-28"))


@pytest.mark.parametrize("field", ["package_sha256", "package_id", "lineage_sha256", "ancestor_package", "ancestor_lineage"])
def test_exact_predecessor_and_ancestry_pins(monkeypatch, field):
    monkeypatch.setattr(m._latest, "require_latest_order_input_package", lambda value: value)
    value = predecessor()
    assert m._require_predecessor(value) is value
    if field.startswith("package"):
        setattr(value.package, field, "wrong")
    elif field == "lineage_sha256":
        value.lineage_sha256 = "a" * 64
    else:
        value.lineage["predecessor_" + ("package_sha256" if field == "ancestor_package" else "lineage_sha256")] = "a" * 64
    with pytest.raises(m.OctoberOrderInputPackageError, match="ancestry_pin"):
        m._require_predecessor(value)


def test_forged_predecessor_and_refused_delta_are_not_authority(monkeypatch, tmp_path):
    with pytest.raises(ValueError):
        m._require_predecessor(predecessor())
    monkeypatch.setattr(m, "_require_predecessor", lambda value: value)
    def forbidden_archive_read(*_args):
        raise AssertionError("source authority must refuse before any historical archive access")
    monkeypatch.setattr(m, "_require_archives", forbidden_archive_read)
    for refused in (object(), {"terminal": "auth_refused"}, {"output_authenticated": True}):
        with pytest.raises(ValueError):
            m.build_october_order_input_package(predecessor=object(), parent_archive=object(),
                prior_delta_archive=object(), tail_archive=object(), ratings_delta=refused,
                firm_admission=object(), global_contract=object(), output_root=tmp_path / "never-created")
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize("field,bad", [
    ("archive_sha256", "0" * 64), ("source_manifest_sha256", "0" * 64),
    ("source_row_count", True), ("source_row_count", 1397), ("pair_sha256", "0" * 64),
])
def test_exact_original_tail_archive_bindings(monkeypatch, field, bad):
    monkeypatch.setattr(m._latest, "_authenticate_archives", lambda *values: values)
    values = (archive(archive_id="parent"), archive(archive_id="prior"), archive())
    old = predecessor(lineage=dict(zip(("parent_archive", "prior_delta_archive", "fresh_archive"),
        (m._latest._archive_binding(value) for value in values), strict=True)))
    assert m._require_archives(old, *values) == values
    setattr(values[-1], field, bad)
    with pytest.raises(m.OctoberOrderInputPackageError):
        m._require_archives(old, *values)


def test_genuine_delta_keeps_original_eligibility_and_economic_deltas(tmp_path, monkeypatch):
    fresh = accepted_delta(tmp_path, monkeypatch)
    rows = tuple(m._ratings.iter_authenticated_rating_rows(fresh))
    result, digest, census = derive(rows, monkeypatch)
    assert len(result) == 2 and len(digest) == 64
    assert {row["eligible_session_index"] for row in result} == {m._sessions().index(rows[0].current_view.eligible_session)}
    assert {row["firm_delta_numerator"] for row in result} == {1}
    assert {row["firm_delta_denominator"] for row in result} == {2}
    assert census["candidate"] == 1


def test_new_row_fold_matches_frozen_economic_oracle(tmp_path, monkeypatch):
    fresh = accepted_delta(tmp_path, monkeypatch, [provider_row(), provider_row(benzinga_id="fixture-rating-2", date="2026-10-02")])
    rows = tuple(m._ratings.iter_authenticated_rating_rows(fresh))
    observed = derive(rows, monkeypatch)
    monkeypatch.setattr(m._compact, "_PINNED_ITER_ACCEPTED_ROWS", lambda _archive: iter(rows))
    expected = m._compact._derive_contributions(archive=object(), sessions=m._sessions(),
        ticker_to_security={"SYNTH": "stock-a"}, firm_admission=firms(), global_contract=object(),
        spool_path=tmp_path / "synthetic-oracle.sqlite3", maximum_eligible_session="2026-10-13")
    assert observed == expected


def test_predecessor_prefix_is_not_rederived_or_clamped(tmp_path, monkeypatch):
    rows = tuple(m._ratings.iter_authenticated_rating_rows(accepted_delta(tmp_path, monkeypatch)))
    position = m._sessions().index(rows[0].current_view.eligible_session)
    result, _, census = derive(rows, monkeypatch, minimum_position=position + 1)
    assert result == () and census["no_included_preliminary_view"] == 1
    result, _, _ = derive(rows, monkeypatch, minimum_position=position)
    assert all(row["eligible_session_index"] == position for row in result)


def test_oct13_eligibility_is_retained_not_shifted_into_last_decision(tmp_path, monkeypatch):
    rows = tuple(m._ratings.iter_authenticated_rating_rows(accepted_delta(tmp_path, monkeypatch, [provider_row(date="2026-10-09")])) )
    result, _, _ = derive(rows, monkeypatch)
    assert rows[0].current_view.eligible_session == "2026-10-13"
    assert all(row["eligible_session_index"] == len(m._sessions()) - 1 for row in result)


@pytest.mark.parametrize("change,reason", [
    ({"rating_action": "initiates"}, "non_directional_or_invalid_rating_action"),
    ({"ticker": "UNKNOWN"}, "current_snapshot_ticker_not_admitted"),
    ({"firm": "Other Firm"}, "firm_mapping_unavailable_or_ambiguous"),
    ({"rating": "Hold", "previous_rating": "Buy"}, "firm_delta_contradicts_direction"),
    ({"rating": "Hold"}, "firm_delta_contradicts_direction"),
])
def test_refusal_economics_do_not_fabricate_contributions(tmp_path, monkeypatch, change, reason):
    rows = tuple(m._ratings.iter_authenticated_rating_rows(accepted_delta(tmp_path, monkeypatch, [provider_row(**change)])))
    result, _, census = derive(rows, monkeypatch)
    assert result == () and census[reason] == 1


@pytest.mark.parametrize("limit", [0, 1])
def test_row_capacity_refuses_before_processing(tmp_path, monkeypatch, limit):
    rows = tuple(m._ratings.iter_authenticated_rating_rows(accepted_delta(tmp_path, monkeypatch)))
    with pytest.raises(m.OctoberOrderInputPackageError, match="row_bound"):
        derive(rows * 2, monkeypatch, maximum_rows=limit)


def test_spool_capacity_is_not_silently_increased(tmp_path, monkeypatch):
    rows = tuple(m._ratings.iter_authenticated_rating_rows(accepted_delta(tmp_path, monkeypatch)))
    monkeypatch.setattr(m._compact, "MAX_SQLITE_SPOOL_BYTES", 1)
    with pytest.raises(m.OctoberOrderInputPackageError, match="spool_bound"):
        derive(rows, monkeypatch)


def test_same_archive_dedup_and_conflict_follow_frozen_rules(tmp_path, monkeypatch):
    rows = tuple(m._ratings.iter_authenticated_rating_rows(accepted_delta(tmp_path, monkeypatch)))
    selected, _, census = derive(rows * 2, monkeypatch)
    assert len(selected) == 2 and census["identical_daily_duplicate_candidate_count"] == 2
    other = dataclasses.replace(rows[0], provider_event_id="other-event")
    selected, _, census = derive((rows[0], other), monkeypatch)
    assert selected == () and census["ambiguous_daily_group_count"] == 2


def install_fold(monkeypatch, streams, *, fail_last=False):
    monkeypatch.setattr(m, "_PINNED_SOURCE_ROW_TYPE", SimpleNamespace)
    seen = []
    def fold(value, visitor):
        seen.append(value)
        for row in streams[value]:
            visitor(m._PINNED_SEMANTIC_ROW_TYPE(row, b"{}\n"))
        if fail_last and value == "prior":
            raise ValueError("synthetic terminal authentication failure")
    monkeypatch.setattr(m, "_PINNED_SEMANTIC_FOLD", fold)
    monkeypatch.setattr(m._archive, "_fold_authenticated_physical_accepted_risk_rows", fold)
    return seen


def id_row(event, role=m.MassiveSourceRole.ANALYST_RATINGS):
    return SimpleNamespace(provider_event_id=event, locator=SimpleNamespace(source_role=role))


def test_old_rejected_ids_still_quarantine_tail_and_fresh(tmp_path, monkeypatch):
    fresh = accepted_delta(tmp_path, monkeypatch, [provider_row(benzinga_id="new-reused")])
    seen = install_fold(monkeypatch, {
        "tail": (id_row("tail-reused"), id_row("tail-safe")),
        "parent": (id_row("tail-reused"), id_row("new-reused")),
        "prior": (id_row("tail-safe", m.MassiveSourceRole.EARNINGS),),
    })
    tail, new, tail_refusals, new_refusals = m._sources_and_collisions("parent", "prior", "tail", fresh)
    common = m._compact._PINNED_COMMON_EVENT_ID
    assert len(tail) == 2 and len(new) == 1
    assert tail_refusals == frozenset({common("tail-reused")})
    assert new_refusals == frozenset({common("new-reused")})
    assert seen == ["tail", "parent", "prior"]


def test_new_reuses_tail_id_is_quarantined(tmp_path, monkeypatch):
    fresh = accepted_delta(tmp_path, monkeypatch)
    install_fold(monkeypatch, {"tail": (id_row("fixture-rating-1"),), "parent": (), "prior": ()})
    result = m._sources_and_collisions("parent", "prior", "tail", fresh)
    assert result[-1] == frozenset({m._compact._PINNED_COMMON_EVENT_ID("fixture-rating-1")})


def test_terminal_fold_failure_never_returns_provisional_rows(tmp_path, monkeypatch):
    fresh = accepted_delta(tmp_path, monkeypatch)
    install_fold(monkeypatch, {"tail": (id_row("x"),), "parent": (), "prior": ()}, fail_last=True)
    with pytest.raises(ValueError, match="terminal authentication"):
        m._sources_and_collisions("parent", "prior", "tail", fresh)


def test_changed_fold_dependency_refuses_before_any_call(tmp_path, monkeypatch):
    fresh = accepted_delta(tmp_path, monkeypatch)
    monkeypatch.setattr(m._archive, "_fold_authenticated_physical_accepted_risk_rows", lambda *_args: None)
    with pytest.raises(m.OctoberOrderInputPackageError, match="fold_dependency"):
        m._sources_and_collisions(None, None, None, fresh)


def test_daily_cross_archive_conflicts_preserve_prefix_and_quarantine_both():
    old = (contribution(5, "old"),)
    result, census, _ = m._latest._merge_preserved_contributions(old,
        (contribution(6, "tail"),), (contribution(6, "fresh"),), 5, frozenset())
    assert result == old and census["cross_archive_daily_ambiguity_count"] == 1


@pytest.fixture
def built(tmp_path, monkeypatch, request):
    sessions = m._sessions()
    old_axis = m._latest._sessions()
    cutoff = sessions.index("2026-09-25")
    prior = tuple(contribution(cutoff, "old", view=view) for view in m._evaluator.SOURCE_VIEW_IDS)
    tail_rows = tuple(contribution(cutoff + 1, "tail", view=view) for view in m._evaluator.SOURCE_VIEW_IDS)
    fresh_rows = tuple(contribution(cutoff + 3, "fresh", view=view) for view in m._evaluator.SOURCE_VIEW_IDS)
    roles = {"session_axis": m._old._session_records(old_axis), "contributions": prior,
        "memberships": (m._evaluator.build_membership_record(security_id="stock-a", first_session_index=0,
            last_session_index_exclusive=len(old_axis), sector_id="sector-a"),),
        "runtime_symbol_bindings": ({"security_id": "stock-a", "diagnostic_current_ticker": "SYNTH"},)}
    old = predecessor(lineage={"combined_contribution_stream_sha256": m._compact._stream_hash(prior)})
    monkeypatch.setattr(m, "_require_predecessor", lambda value: value)
    monkeypatch.setattr(m, "EXPECTED_PREDECESSOR_CONTRIBUTION_COUNT", len(prior))
    monkeypatch.setattr(m, "_require_archives", lambda _old, *values: values)
    original_roles = m._old._load_prior_roles
    monkeypatch.setattr(m._old, "_load_prior_roles", lambda _package: ({"source_lineage_sha256s": {
        "security_master_admission_sha256": m._old.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256}}, roles))
    monkeypatch.setattr(m, "require_section72_owner_waived_firm_admission", lambda value: value)
    monkeypatch.setattr(m, "require_loaded_global_benchmark_contract", lambda value: value)
    fresh = accepted_delta(tmp_path, monkeypatch)
    collisions = frozenset({"tail"}) if getattr(request, "param", False) else frozenset()
    monkeypatch.setattr(m, "_sources_and_collisions", lambda *_args: (tail_rows, fresh_rows, collisions, frozenset()))
    monkeypatch.setattr(m, "_derive_rating_rows", lambda **values: (values["rows"], "b" * 64, {"rating_source_row_count": len(values["rows"])}))
    value = m.build_october_order_input_package(predecessor=old, parent_archive=archive(archive_id="parent"),
        prior_delta_archive=archive(archive_id="prior"), tail_archive=archive(), ratings_delta=fresh,
        firm_admission=firms(), global_contract=SimpleNamespace(map_hash=m._old.EXPECTED_GLOBAL_MAP_SHA256),
        output_root=tmp_path / "synthetic-package")
    monkeypatch.setattr(m._old, "_load_prior_roles", original_roles)
    return value, prior, tail_rows, fresh_rows


def test_real_canonical_materialization_preserves_prefix_runtime_and_new_wrapper(built):
    value, prior, tail, fresh = built
    assert type(value) is m.OctoberOrderInputPackage
    assert value.recovered_tail_contribution_count == value.fresh_contribution_count == 2
    manifest, roles = m._old._load_prior_roles(value.package)
    assert roles["contributions"] == m._old._merge_contributions(prior, (*tail, *fresh))
    assert m._compact._canonical(roles["contributions"][0]) == m._compact._canonical(prior[0])
    assert roles["runtime_symbol_bindings"] == ({"security_id": "stock-a", "diagnostic_current_ticker": "SYNTH"},)
    assert roles["session_axis"][-1]["session"] == "2026-10-13"
    assert manifest["source_lineage_sha256s"]["pre_normalized_contribution_source_sha256"] == value.lineage_sha256
    assert value.package.orders is False and value.package.point_in_time is False
    assert value.lineage["inventory_is_current_holdings"] is False
    assert value.lineage["fresh_QC_holdings_caps_identity_join_required"] is True
    assert value.lineage["historical_prefix_rederived"] is False
    delta = value.lineage["ratings_delta"]
    assert delta["source_row_count"] == 2 and delta["row_count"] == 1
    assert delta["duplicate_excess_count"] == delta["duplicate_group_count"] == 1
    assert len(delta["duplicate_disposition_sha256"]) == 64
    assert value.valuation_end_session == "2026-10-13"
    assert value.lineage["tail_collision_disposition_sha256"] == m._sha({
        "colliding_common_event_ids": [], "excluded_contribution_ids": []})
    detached = value.lineage
    detached["orders"] = True
    assert m.require_october_order_input_package(value) is value


@pytest.mark.parametrize("field,bad", [("lineage_bytes", b"{}"), ("lineage_sha256", "0" * 64),
    ("decision_cutoff_session", "2026-10-13"), ("final_execution_session", "2026-10-14"),
    ("recovered_tail_contribution_count", True), ("fresh_contribution_count", 2.0)])
def test_wrapper_mutations_refuse(built, field, bad):
    with pytest.raises(ValueError):
        m.require_october_order_input_package(dataclasses.replace(built[0], **{field: bad}))


@pytest.mark.parametrize("change", ["extra", "missing", "count_bool", "count_float", "flag_int", "historical_rederived", "valuation"])
def test_exact_lineage_schema_and_types_even_with_a_rebound_test_package(built, monkeypatch, change):
    # The production compact-package authority would refuse these mutations
    # first. This synthetic seam isolates the October schema guard itself.
    value = built[0]
    lineage = value.lineage
    if change == "extra":
        lineage["unexpected"] = "not-admitted"
    elif change == "missing":
        del lineage["runtime_binding_stream_sha256"]
    elif change == "count_bool":
        lineage["cross_archive_daily_ambiguity_count"] = False
    elif change == "count_float":
        lineage["tail_collision_refusal_count"] = 0.0
    elif change == "flag_int":
        lineage["orders"] = 0
    elif change == "historical_rederived":
        lineage["historical_prefix_rederived"] = True
    else:
        lineage["valuation_end_session"] = "2026-10-14"
    payload, digest = m._compact._canonical(lineage), m._sha(lineage)
    fake = SimpleNamespace(source_disposition_sha256=digest)
    monkeypatch.setattr(m._compact, "require_accepted_risk_preliminary_package", lambda item: item)
    changed = dataclasses.replace(value, package=fake, lineage_bytes=payload, lineage_sha256=digest)
    with pytest.raises(m.OctoberOrderInputPackageError):
        m.require_october_order_input_package(changed)


def test_mutated_compact_package_loses_authority(built):
    value = built[0]
    original = value.package.source_disposition_sha256
    try:
        object.__setattr__(value.package, "source_disposition_sha256", "0" * 64)
        with pytest.raises(ValueError):
            m.require_october_order_input_package(value)
    finally:
        object.__setattr__(value.package, "source_disposition_sha256", original)


@pytest.mark.parametrize("built", [True], indirect=True)
def test_nonempty_tail_collision_disposition_commits_each_excluded_identity(built):
    value, prior, tail, fresh = built
    assert value.recovered_tail_contribution_count == 0
    assert value.lineage["tail_collision_refusal_count"] == 1
    assert value.lineage["tail_collision_contribution_refusal_count"] == 2
    assert value.lineage["tail_collision_disposition_sha256"] == m._sha({
        "colliding_common_event_ids": ["tail"],
        "excluded_contribution_ids": sorted(row["contribution_id"] for row in tail)})
    _, roles = m._old._load_prior_roles(value.package)
    assert roles["contributions"] == m._old._merge_contributions(prior, fresh)


def test_external_pin_reload_and_immutable_sidecar(built, tmp_path):
    value = built[0]
    path = m.persist_october_order_input_lineage(value, tmp_path / "sidecars")
    assert path.read_bytes() == value.lineage_bytes
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    loaded = m.load_october_order_input_package(value.package.package_path,
        expected_package_sha256=value.package.package_sha256,
        lineage_path=path, expected_lineage_sha256=value.lineage_sha256)
    assert loaded.lineage_bytes == value.lineage_bytes
    with pytest.raises(FileExistsError):
        m.persist_october_order_input_lineage(value, tmp_path / "sidecars")
    with pytest.raises(ValueError):
        m.load_october_order_input_package(value.package.package_path,
            expected_package_sha256=value.package.package_sha256,
            lineage_path=path, expected_lineage_sha256="0" * 64)
    with pytest.raises(ValueError):
        m.load_october_order_input_package(value.package.package_path,
            expected_package_sha256="0" * 64, lineage_path=path, expected_lineage_sha256=value.lineage_sha256)
    path.write_bytes(value.lineage_bytes + b" ")
    with pytest.raises(ValueError):
        m.load_october_order_input_package(value.package.package_path,
            expected_package_sha256=value.package.package_sha256,
            lineage_path=path, expected_lineage_sha256=value.lineage_sha256)


def test_loader_name_refuses_before_any_read(tmp_path):
    with pytest.raises(m.OctoberOrderInputPackageError, match="lineage_name"):
        m.load_october_order_input_package(tmp_path / "not-read", expected_package_sha256="a" * 64,
            lineage_path=tmp_path / "wrong.json", expected_lineage_sha256="b" * 64)
