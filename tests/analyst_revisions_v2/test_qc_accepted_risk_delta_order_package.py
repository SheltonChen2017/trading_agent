from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace

import pytest

from scripts import build_arv2_delta_order_input_package as build_script

from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as module,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as evaluator,
)


def _exact(message: str) -> str:
    return "^" + re.escape(message) + "$"


def _immutable_tree_snapshot(path):
    result = []
    descendants = sorted(
        path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()
    )
    for item in (path, *descendants):
        metadata = item.lstat()
        result.append(
            (
                item.relative_to(path).as_posix() if item != path else ".",
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_nlink,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
                (
                    hashlib.sha256(item.read_bytes()).hexdigest()
                    if item.is_file()
                    else None
                ),
            )
        )
    return tuple(result)


def _membership(*, security_id="security-a", first=0, last=2, sector="sector-a"):
    return evaluator.build_membership_record(
        security_id=security_id,
        first_session_index=first,
        last_session_index_exclusive=last,
        sector_id=sector,
    )


def _contribution(*, view, index, security_id, institution, suffix):
    row = {
        "source_view_id": view,
        "eligible_session_index": index,
        "security_id": security_id,
        "institution_id": institution,
        "contribution_id": "contribution-" + suffix,
    }
    return row


def _descriptor(role, *, compression="none"):
    return SimpleNamespace(role=role, compression=compression)


def _fixture_delta_lineage(
    *,
    session_count,
    prior_contribution_count=1,
    delta_contribution_count=1,
    extended_membership_count=1,
):
    return module._lineage_record(
        prior_package_id=module.EXPECTED_PRIOR_PACKAGE_ID,
        prior_package_sha256=module.EXPECTED_PRIOR_PACKAGE_SHA256,
        prior_source_disposition_sha256=(
            module.EXPECTED_PRIOR_SOURCE_DISPOSITION_SHA256
        ),
        parent_archive_id=module.EXPECTED_PARENT_ARCHIVE_ID,
        parent_archive_sha256=module.EXPECTED_PARENT_ARCHIVE_SHA256,
        parent_pair_sha256=module.EXPECTED_PARENT_PAIR_SHA256,
        delta_archive_id=module.EXPECTED_DELTA_ARCHIVE_ID,
        delta_archive_sha256=module.EXPECTED_DELTA_ARCHIVE_SHA256,
        delta_pair_sha256=module.EXPECTED_DELTA_PAIR_SHA256,
        composite_id=module.EXPECTED_COMPOSITE_ID,
        composite_sha256=module.EXPECTED_COMPOSITE_SHA256,
        composite_row_projection_sha256=(
            module.EXPECTED_COMPOSITE_ROW_PROJECTION_SHA256
        ),
        composite_row_count=module.EXPECTED_COMPOSITE_ROW_COUNT,
        delta_source_disposition_sha256=(
            module.EXPECTED_DELTA_SOURCE_DISPOSITION_SHA256
        ),
        security_master_admission_sha256=(
            module.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256
        ),
        firm_ontology_admission_sha256=(
            module.EXPECTED_FIRM_ADMISSION_SHA256
        ),
        global_rating_map_sha256=module.EXPECTED_GLOBAL_MAP_SHA256,
        session_count=session_count,
        prior_contribution_count=prior_contribution_count,
        delta_contribution_count=delta_contribution_count,
        combined_contribution_count=(
            prior_contribution_count + delta_contribution_count
        ),
        extended_membership_count=extended_membership_count,
    )


def _reloadable_delta_package(monkeypatch, tmp_path, *, mutate_manifest=None):
    sessions = module._successor_sessions()
    session_records = module._session_records(sessions)
    memberships = (
        {
            "security_id": "security-a",
            "first_session_index": 0,
            "last_session_index_exclusive": len(sessions),
            "sector_id": "sector-a",
        },
    )
    contributions = (
        {"contribution_id": "prior-contribution"},
        {"contribution_id": "delta-contribution"},
    )
    lineage = _fixture_delta_lineage(session_count=len(sessions))
    lineage_sha256 = module._sha_record(lineage)
    manifest = {
        "manifest_id": "manifest-delta-reload",
        "manifest_sha256": "c" * 64,
        "benchmark_security_id": module._prior.BENCHMARK_SECURITY_ID,
        "rating_history_start_session": module.RATING_HISTORY_START_SESSION,
        "session_axis_count": len(session_records),
        "membership_row_count": len(memberships),
        "contribution_row_count": len(contributions),
        "history_batch_security_count": (
            module._prior.HISTORY_BATCH_SECURITY_COUNT
        ),
        "scoring_sessions_per_callback": (
            module._prior.SCORING_SESSIONS_PER_CALLBACK
        ),
        "signal_seed_contributions_per_callback": (
            module._prior.SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK
        ),
        "source_view_ids": list(evaluator.SOURCE_VIEW_IDS),
        "source_lineage_sha256s": {
            "accepted_risk_input_pair_sha256": (
                module.EXPECTED_COMPOSITE_SHA256
            ),
            "security_master_admission_sha256": (
                module.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256
            ),
            "firm_ontology_admission_sha256": (
                module.EXPECTED_FIRM_ADMISSION_SHA256
            ),
            "global_rating_map_sha256": module.EXPECTED_GLOBAL_MAP_SHA256,
            "pre_normalized_contribution_source_sha256": lineage_sha256,
        },
    }
    if mutate_manifest is not None:
        mutate_manifest(manifest)
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: SimpleNamespace(marker="authenticated"),
    )
    package = module._prior._materialize(
        output_root=tmp_path,
        evaluator_manifest=manifest,
        session_records=session_records,
        membership_records=memberships,
        contribution_records=contributions,
        runtime_binding_records=(
            {
                "security_id": "security-a",
                "diagnostic_current_ticker": "AAA",
            },
        ),
        source_disposition_sha256=lineage_sha256,
        contribution_census={
            "prior_selected_contribution_count": 1,
            "delta_selected_contribution_count": 1,
            "combined_selected_contribution_count": 2,
        },
    )
    module._prior._AUTHORITIES.pop(id(package), None)
    monkeypatch.setattr(module, "EXPECTED_DELTA_PACKAGE_ID", package.package_id)
    monkeypatch.setattr(
        module, "EXPECTED_DELTA_PACKAGE_SHA256", package.package_sha256
    )
    monkeypatch.setattr(
        module, "EXPECTED_DELTA_LINEAGE_SHA256", lineage_sha256
    )
    return package, lineage, lineage_sha256


def _reload_delta(package, lineage_sha256):
    return module.load_accepted_risk_delta_order_package(
        package.package_path,
        expected_package_sha256=package.package_sha256,
        expected_lineage_sha256=lineage_sha256,
    )


def _rewrite_activation(package, mutate):
    path = package.package_path / "transport-manifest.json"
    record = json.loads(path.read_bytes())
    mutate(record)
    path.write_bytes(module._prior._canonical(record) + b"\n")


def _assert_artifact_auth_refusal(package, lineage_sha256, cause_fragment):
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("persisted delta package artifacts did not authenticate"),
    ) as raised:
        _reload_delta(package, lineage_sha256)
    assert isinstance(
        raised.value.__cause__,
        module.AcceptedRiskPreliminaryPackageError,
    )
    assert cause_fragment in str(raised.value.__cause__)


def test_successor_axis_and_both_windows_are_exact():
    sessions = module._successor_sessions()
    assert len(sessions) == 3_448
    assert sessions[0] == "2013-01-02"
    assert sessions[-2:] == ("2026-09-16", "2026-09-17")
    cutoff = sessions.index(module.DELTA_DECISION_END_SESSION)
    assert cutoff - sessions.index("2025-01-02") + 1 == 427
    assert cutoff - sessions.index("2026-01-02") + 1 == 177
    assert "2026-07-04" not in sessions
    assert "2026-09-13" not in sessions


def test_only_memberships_active_at_prior_cutoff_are_extended():
    prior_sessions = (
        {"session": "2025-12-30"},
        {"session": "2025-12-31"},
        {"session": "2026-01-02"},
    )
    rows = (
        _membership(security_id="ended", last=1),
        _membership(security_id="active", last=2),
    )
    extended, count = module._extend_memberships(
        prior_sessions, rows, 10
    )
    assert count == 1
    by_security = {row["security_id"]: row for row in extended}
    assert by_security["ended"]["last_session_index_exclusive"] == 1
    assert by_security["active"]["last_session_index_exclusive"] == 10
    assert by_security["active"]["row_sha256"] != rows[1]["row_sha256"]


def test_missing_prior_cutoff_has_distinct_refusal():
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("prior package session axis changed"),
    ):
        module._extend_memberships(
            ({"session": "2025-12-30"},),
            (_membership(last=1),),
            10,
        )


def test_no_active_membership_has_distinct_refusal():
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("no prior active membership survived the delta cutoff"),
    ):
        module._extend_memberships(
            (
                {"session": "2025-12-30"},
                {"session": "2025-12-31"},
            ),
            (_membership(last=1),),
            10,
        )


def test_known_ticker_map_requires_unique_exact_bindings():
    assert module._known_ticker_map(
        (
            {"diagnostic_current_ticker": "AAA", "security_id": "s-a"},
            {"diagnostic_current_ticker": "BBB", "security_id": "s-b"},
        )
    ) == {"AAA": "s-a", "BBB": "s-b"}
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("prior runtime binding ticker became ambiguous"),
    ):
        module._known_ticker_map(
            (
                {"diagnostic_current_ticker": "AAA", "security_id": "s-a"},
                {"diagnostic_current_ticker": "AAA", "security_id": "s-b"},
            )
        )


def test_contributions_merge_in_evaluator_canonical_order():
    current, conservative = evaluator.SOURCE_VIEW_IDS
    prior = (
        _contribution(
            view=current,
            index=1,
            security_id="s-a",
            institution="i-a",
            suffix="a",
        ),
        _contribution(
            view=conservative,
            index=1,
            security_id="s-a",
            institution="i-a",
            suffix="b",
        ),
    )
    delta = (
        _contribution(
            view=current,
            index=5,
            security_id="s-b",
            institution="i-b",
            suffix="c",
        ),
        _contribution(
            view=conservative,
            index=5,
            security_id="s-b",
            institution="i-b",
            suffix="d",
        ),
    )
    result = module._merge_contributions(prior, delta)
    assert [row["contribution_id"] for row in result] == [
        "contribution-a",
        "contribution-c",
        "contribution-b",
        "contribution-d",
    ]


def test_overlapping_contribution_identity_has_distinct_refusal():
    current = evaluator.SOURCE_VIEW_IDS[0]
    row = _contribution(
        view=current,
        index=1,
        security_id="s-a",
        institution="i-a",
        suffix="same",
    )
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("prior and delta contribution identities overlap"),
    ):
        module._merge_contributions((row,), (dict(row),))


def test_lineage_capability_defaults_remain_non_ordering():
    fields = {field.name for field in module.dataclasses.fields(
        module.AcceptedRiskDeltaOrderPackage
    )}
    assert {
        "current_snapshot_identity_only",
        "refreshed_security_master",
        "provider_access",
        "quantconnect_access",
        "outcome_access",
        "orders",
        "trading",
    }.issubset(fields)


def test_real_delta_lineage_preimage_schema_counts_and_pins_are_independent():
    expected = {
        "schema": "arv2-accepted-risk-delta-order-input-lineage-v1",
        "prior_package_id": (
            "arv2-preliminary-qc-package-e9851c2f3bc3f66d761dbff2"
        ),
        "prior_package_sha256": (
            "e9851c2f3bc3f66d761dbff2fcbd6d56ef94cf390e4f5ed30abf37ec89cab3d9"
        ),
        "prior_source_disposition_sha256": (
            "3828998a5c8011d75bc7c5ddb211741731fc6af99227054152b260a82ec7890c"
        ),
        "parent_archive_id": (
            "arv2-physical-accepted-risk-83ef125320d6a74ce9e4ba1c"
        ),
        "parent_archive_sha256": (
            "83ef125320d6a74ce9e4ba1c2003f396d076a23d310bcafadf76774b7316bd11"
        ),
        "parent_pair_sha256": (
            "aeb5cbae4adf4e19174b5c2404a250b0cd3dc0a6de67272c3ba07e8e3c2ee94a"
        ),
        "delta_archive_id": (
            "arv2-physical-accepted-risk-1678b925bc78e8b3f4fdf291"
        ),
        "delta_archive_sha256": (
            "1678b925bc78e8b3f4fdf2911e3e426327fb8a1307463d1ff2bd43f279a1cc77"
        ),
        "delta_pair_sha256": (
            "0452a4811db397068b0dbd4c0e22db92c1597bcfcef93559e71647ee87228ea8"
        ),
        "composite_id": (
            "arv2-parent-bound-massive-delta-0dc8a581fd2cff4113b1264f"
        ),
        "composite_sha256": (
            "0dc8a581fd2cff4113b1264f28a239ff92d66261f5069bf2ee6bebb18edcb8c9"
        ),
        "composite_row_projection_sha256": (
            "c053f537e809a4729766561114c07c2891a52daa41bcedd876dc323262e1e44d"
        ),
        "composite_row_count": 962_999,
        "delta_source_disposition_sha256": (
            "8b42a7b09bcf3be4a0c913edd05ac8cf32952e7351ea5f6265f9200c2e5a78e0"
        ),
        "security_master_admission_sha256": (
            "5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281"
        ),
        "firm_ontology_admission_sha256": (
            "cbdb0e8b4d529d32d01688dc80a2292af8b3329aa2023ccf6b55ad5ee2af2f0c"
        ),
        "global_rating_map_sha256": (
            "aaf5830c3c3fb403b0e84f5ad22d1f20fa3f91df41cf3bd64f33695875d2e3d9"
        ),
        "rating_history_start_session": "2013-01-02",
        "decision_cutoff_session": "2026-09-16",
        "final_execution_session": "2026-09-17",
        "window_start_sessions": ["2025-01-02", "2026-01-02"],
        "session_count": 3_448,
        "prior_contribution_count": 12_244,
        "delta_contribution_count": 743,
        "combined_contribution_count": 12_987,
        "extended_membership_count": 4_258,
        "security_policy": (
            "reuse_exact_reviewed_current_snapshot_FIGI_inventory_and_extend_"
            "only_memberships_active_at_2025_cutoff;_unknown_2026_tickers_refuse"
        ),
        "current_snapshot_identity_only": True,
        "refreshed_security_master": False,
        "point_in_time_security_master": False,
        "survivorship_free": False,
        "provider_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "orders": False,
        "trading": False,
    }
    actual = module._lineage_record(
        prior_package_id=module.EXPECTED_PRIOR_PACKAGE_ID,
        prior_package_sha256=module.EXPECTED_PRIOR_PACKAGE_SHA256,
        prior_source_disposition_sha256=(
            module.EXPECTED_PRIOR_SOURCE_DISPOSITION_SHA256
        ),
        parent_archive_id=module.EXPECTED_PARENT_ARCHIVE_ID,
        parent_archive_sha256=module.EXPECTED_PARENT_ARCHIVE_SHA256,
        parent_pair_sha256=module.EXPECTED_PARENT_PAIR_SHA256,
        delta_archive_id=module.EXPECTED_DELTA_ARCHIVE_ID,
        delta_archive_sha256=module.EXPECTED_DELTA_ARCHIVE_SHA256,
        delta_pair_sha256=module.EXPECTED_DELTA_PAIR_SHA256,
        composite_id=module.EXPECTED_COMPOSITE_ID,
        composite_sha256=module.EXPECTED_COMPOSITE_SHA256,
        composite_row_projection_sha256=(
            module.EXPECTED_COMPOSITE_ROW_PROJECTION_SHA256
        ),
        composite_row_count=module.EXPECTED_COMPOSITE_ROW_COUNT,
        delta_source_disposition_sha256=(
            module.EXPECTED_DELTA_SOURCE_DISPOSITION_SHA256
        ),
        security_master_admission_sha256=(
            module.EXPECTED_SECURITY_MASTER_ADMISSION_SHA256
        ),
        firm_ontology_admission_sha256=(
            module.EXPECTED_FIRM_ADMISSION_SHA256
        ),
        global_rating_map_sha256=module.EXPECTED_GLOBAL_MAP_SHA256,
        session_count=3_448,
        prior_contribution_count=12_244,
        delta_contribution_count=743,
        combined_contribution_count=12_987,
        extended_membership_count=4_258,
    )

    assert actual == expected
    assert module._sha_record(expected) == (
        "54723703380d5011420d8a364cf857a9978092b6b1d0daaa4d367dc1c65fb129"
    )
    assert module.EXPECTED_DELTA_LINEAGE_SHA256 == module._sha_record(expected)
    assert module.EXPECTED_DELTA_PACKAGE_ID == (
        "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
    )
    assert module.EXPECTED_DELTA_PACKAGE_SHA256 == (
        "7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f"
    )


def test_delta_contribution_cutoff_must_belong_to_supplied_axis():
    with pytest.raises(
        module._prior.AcceptedRiskPreliminaryPackageError,
        match=_exact(
            "preliminary contribution cutoff escaped its session axis"
        ),
    ):
        module._prior._derive_contributions(
            archive=object(),
            sessions=("2025-12-31",),
            ticker_to_security={},
            firm_admission=object(),
            global_contract=object(),
            spool_path=module.Path("unused.sqlite3"),
            maximum_eligible_session="2026-09-16",
        )


@pytest.mark.parametrize(
    ("objects", "message"),
    (
        (
            ((_descriptor("evaluator_manifest"), b"not-json\n"),),
            "prior evaluator manifest is unreadable",
        ),
        (
            ((_descriptor("evaluator_manifest"), b'{"b":2,"a":1}\n'),),
            "prior evaluator manifest is not exact canonical JSON",
        ),
        (
            ((_descriptor("unexpected"), b"value"),),
            "prior package role inventory changed",
        ),
        (
            ((_descriptor("evaluator_manifest"), b'{"a":1}\n'),),
            "prior package omits a required authenticated role",
        ),
    ),
)
def test_prior_role_loader_has_distinct_refusals(
    monkeypatch, objects, message,
):
    monkeypatch.setattr(
        module,
        "iter_accepted_risk_preliminary_upload_objects",
        lambda _package: iter(objects),
    )
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact(message),
    ):
        module._load_prior_roles(object())


@pytest.mark.parametrize(
    ("row", "message"),
    (
        (object(), "prior membership row changed type"),
        (
            {
                "security_id": "security-a",
                "first_session_index": 0,
                "last_session_index_exclusive": "2",
                "sector_id": "sector-a",
            },
            "prior membership interval changed type",
        ),
    ),
)
def test_membership_extension_has_distinct_shape_refusals(row, message):
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact(message),
    ):
        module._extend_memberships(
            (
                {"session": "2025-12-30"},
                {"session": "2025-12-31"},
            ),
            (row,),
            10,
        )


@pytest.mark.parametrize(
    ("row", "message"),
    (
        (object(), "prior runtime binding row changed type"),
        (
            {"diagnostic_current_ticker": "", "security_id": "s-a"},
            "prior runtime binding identity changed",
        ),
    ),
)
def test_known_ticker_map_has_distinct_shape_refusals(row, message):
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact(message),
    ):
        module._known_ticker_map((row,))


def test_successor_session_builder_has_distinct_refusals(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise ValueError("calendar unavailable")

    monkeypatch.setattr(module, "trading_sessions", unavailable)
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("delta order session axis is unavailable"),
    ):
        module._successor_sessions()

    monkeypatch.setattr(
        module,
        "trading_sessions",
        lambda *_args, **_kwargs: (module.date(2026, 9, 17),),
    )
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("delta order session axis changed"),
    ):
        module._successor_sessions()


def _patch_build_parents(monkeypatch, *, prior_manifest):
    composite = SimpleNamespace(
        composite_sha256=module.EXPECTED_COMPOSITE_SHA256,
        row_projection_sha256=(
            module.EXPECTED_COMPOSITE_ROW_PROJECTION_SHA256
        ),
        delta_archive=object(),
    )
    prior = SimpleNamespace(
        package_sha256=module.EXPECTED_PRIOR_PACKAGE_SHA256,
    )
    firms = SimpleNamespace(
        admission_sha256=module.EXPECTED_FIRM_ADMISSION_SHA256,
    )
    global_contract = SimpleNamespace(
        map_hash=module.EXPECTED_GLOBAL_MAP_SHA256,
    )
    monkeypatch.setattr(
        module, "require_parent_bound_massive_delta", lambda value: value
    )
    monkeypatch.setattr(
        module, "require_accepted_risk_preliminary_package", lambda value: value
    )
    monkeypatch.setattr(
        module,
        "require_section72_owner_waived_firm_admission",
        lambda value: value,
    )
    monkeypatch.setattr(
        module, "require_loaded_global_benchmark_contract", lambda value: value
    )
    monkeypatch.setattr(
        module,
        "_load_prior_roles",
        lambda _value: (
            prior_manifest,
            {
                "session_axis": (),
                "memberships": (),
                "contributions": (),
                "runtime_symbol_bindings": (),
            },
        ),
    )
    monkeypatch.setattr(module, "_successor_sessions", lambda: ("2026-09-17",))
    monkeypatch.setattr(module, "_session_records", lambda _sessions: ())
    monkeypatch.setattr(
        module, "_extend_memberships", lambda *_args: ((), 1)
    )
    monkeypatch.setattr(module, "_known_ticker_map", lambda _rows: {})
    monkeypatch.setattr(
        module._prior,
        "_derive_contributions",
        lambda **_kwargs: ((), "d" * 64, {}),
    )
    monkeypatch.setattr(module, "_merge_contributions", lambda *_args: ())
    return composite, prior, firms, global_contract


def test_build_refuses_changed_parent_identity_before_derivation(
    monkeypatch, tmp_path,
):
    composite, prior, firms, global_contract = _patch_build_parents(
        monkeypatch,
        prior_manifest={},
    )
    prior.package_sha256 = "0" * 64
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("delta order package parent identity changed"),
    ):
        module.build_accepted_risk_delta_order_package(
            composite=composite,
            prior_package=prior,
            firm_admission=firms,
            global_contract=global_contract,
            output_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("prior_manifest", "message"),
    (
        ({}, "prior evaluator source lineage changed"),
        (
            {"source_lineage_sha256s": {}},
            "prior security-master lineage changed",
        ),
    ),
)
def test_build_has_distinct_prior_lineage_refusals(
    monkeypatch, tmp_path, prior_manifest, message,
):
    composite, prior, firms, global_contract = _patch_build_parents(
        monkeypatch,
        prior_manifest=prior_manifest,
    )
    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact(message),
    ):
        module.build_accepted_risk_delta_order_package(
            composite=composite,
            prior_package=prior,
            firm_admission=firms,
            global_contract=global_contract,
            output_root=tmp_path,
        )


def test_persisted_delta_package_reloads_after_process_authority_is_gone(
    monkeypatch, tmp_path,
):
    original, lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )

    loaded = _reload_delta(original, lineage_sha256)

    assert loaded.package is not original
    assert loaded.package.package_id == original.package_id
    assert loaded.package.package_sha256 == original.package_sha256
    assert loaded.lineage == lineage
    assert loaded.lineage_sha256 == lineage_sha256
    assert loaded.prior_contribution_count == 1
    assert loaded.delta_contribution_count == 1
    assert loaded.extended_membership_count == 1
    assert loaded.orders is False
    assert loaded.trading is False
    uploads = tuple(
        module.iter_accepted_risk_preliminary_upload_objects(loaded.package)
    )
    assert uploads[-1][0].activation_manifest is True
    assert all(
        len(payload) == descriptor.byte_count
        and hashlib.sha256(payload).hexdigest()
        == descriptor.content_sha256
        for descriptor, payload in uploads
    )


def test_build_script_reuses_exact_persisted_delta_without_rebuilding_parents(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    monkeypatch.setattr(
        build_script, "EXPECTED_DELTA_PACKAGE_ID", package.package_id
    )
    monkeypatch.setattr(
        build_script,
        "EXPECTED_DELTA_PACKAGE_SHA256",
        package.package_sha256,
    )
    monkeypatch.setattr(
        build_script, "EXPECTED_DELTA_LINEAGE_SHA256", lineage_sha256
    )

    def unexpected_parent_access(*_args, **_kwargs):
        raise AssertionError("persisted package attempted parent rebuild")

    rebuild_entry_points = (
        "load_physical_accepted_risk_archive",
        "load_physical_firm_ontology_review_packet",
        "build_firm_ontology_proposal",
        "build_firm_ontology_owner_decision",
        "build_section72_owner_waived_firm_admission",
        "build_parent_bound_massive_delta",
        "load_accepted_risk_preliminary_package",
        "build_accepted_risk_delta_order_package",
        "_global_contract",
    )
    for name in rebuild_entry_points:
        monkeypatch.setattr(build_script, name, unexpected_parent_access)
    monkeypatch.setattr(
        build_script.tempfile, "mkdtemp", unexpected_parent_access
    )

    before = _immutable_tree_snapshot(tmp_path)
    loaded = build_script.build(tmp_path)
    after = _immutable_tree_snapshot(tmp_path)

    assert loaded.package.package_sha256 == package.package_sha256
    assert loaded.lineage_sha256 == lineage_sha256
    assert after == before


def test_persisted_delta_package_refuses_wrong_out_of_band_lineage_pin(
    monkeypatch, tmp_path,
):
    package, _lineage, _lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )

    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("persisted delta package out-of-band identity pin changed"),
    ):
        module.load_accepted_risk_delta_order_package(
            package.package_path,
            expected_package_sha256=package.package_sha256,
            expected_lineage_sha256="0" * 64,
        )


def test_persisted_delta_package_refuses_wrong_out_of_band_package_pin(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )

    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("persisted delta package out-of-band identity pin changed"),
    ):
        module.load_accepted_risk_delta_order_package(
            package.package_path,
            expected_package_sha256="0" * 64,
            expected_lineage_sha256=lineage_sha256,
        )


def test_persisted_delta_package_refuses_changed_evaluator_profile(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch,
        tmp_path,
        mutate_manifest=lambda manifest: manifest.__setitem__(
            "history_batch_security_count",
            module._prior.HISTORY_BATCH_SECURITY_COUNT + 1,
        ),
    )

    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("persisted delta evaluator profile changed"),
    ):
        _reload_delta(package, lineage_sha256)


def test_persisted_delta_package_refuses_changed_input_identity(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch,
        tmp_path,
        mutate_manifest=lambda manifest: manifest[
            "source_lineage_sha256s"
        ].__setitem__("accepted_risk_input_pair_sha256", "0" * 64),
    )

    with pytest.raises(
        module.AcceptedRiskDeltaOrderPackageError,
        match=_exact("persisted delta evaluator input lineage changed"),
    ):
        _reload_delta(package, lineage_sha256)


def test_persisted_delta_package_refuses_same_length_payload_tamper(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    descriptor = package.upload_objects[1]
    path = package.package_path / descriptor.relative_path
    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)

    _assert_artifact_auth_refusal(
        package, lineage_sha256, "member hash changed"
    )


def test_persisted_delta_package_refuses_missing_artifact(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    descriptor = package.upload_objects[1]
    (package.package_path / descriptor.relative_path).unlink()

    _assert_artifact_auth_refusal(
        package, lineage_sha256, "directory inventory changed"
    )


def test_persisted_delta_package_refuses_extra_artifact(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    extra = package.package_path / "undeclared.json"
    extra.write_bytes(b"{}\n")
    extra.chmod(0o600)

    _assert_artifact_auth_refusal(
        package, lineage_sha256, "directory inventory changed"
    )


def test_persisted_delta_package_refuses_unsafe_descriptor_path(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    _rewrite_activation(
        package,
        lambda record: record["objects"][1].__setitem__(
            "relative_path", "../escaped-jsonl.gz"
        ),
    )

    _assert_artifact_auth_refusal(
        package, lineage_sha256, "upload descriptor schema changed"
    )


def test_persisted_delta_package_refuses_symlinked_artifact(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    descriptor = package.upload_objects[1]
    path = package.package_path / descriptor.relative_path
    outside = tmp_path / "outside-payload.bin"
    outside.write_bytes(path.read_bytes())
    outside.chmod(0o600)
    path.unlink()
    path.symlink_to(outside)

    _assert_artifact_auth_refusal(
        package, lineage_sha256, "without following links"
    )


def test_persisted_delta_package_refuses_nonprivate_artifact_mode(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    descriptor = package.upload_objects[1]
    (package.package_path / descriptor.relative_path).chmod(0o644)

    _assert_artifact_auth_refusal(
        package, lineage_sha256, "not a bounded owner-private regular file"
    )


def test_persisted_delta_package_refuses_changed_record_count(
    monkeypatch, tmp_path,
):
    package, _lineage, lineage_sha256 = _reloadable_delta_package(
        monkeypatch, tmp_path
    )
    _rewrite_activation(
        package,
        lambda record: record["objects"][1].__setitem__(
            "record_count", record["objects"][1]["record_count"] + 1
        ),
    )

    _assert_artifact_auth_refusal(
        package, lineage_sha256, "compressed payload census changed"
    )
