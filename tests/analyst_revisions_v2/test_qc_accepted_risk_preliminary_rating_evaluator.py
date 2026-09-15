import ast
import copy
import hashlib
from datetime import date, timedelta
from decimal import Context, Decimal, ROUND_DOWN, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import production_scoring as frozen_scoring
from research.analyst_revisions_v2 import formulas as frozen_formulas
from research.analyst_revisions_v2_qc import formal_evaluation
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as subject,
)


def _sessions():
    result = []
    current = date(2013, 1, 2)
    end = date(2026, 4, 30)
    while current <= end:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return tuple(result)


def _session_records(sessions):
    return tuple(
        {
            "schema": subject.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )


def _lineage():
    return {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in (
            "accepted_risk_input_pair_sha256",
            "security_master_admission_sha256",
            "firm_ontology_admission_sha256",
            "global_rating_map_sha256",
            "pre_normalized_contribution_source_sha256",
        )
    }


def _fixture_records(
    *, history_batch=64, scoring_batch=5, seed_batch=3, security_count=20
):
    sessions = _sessions()
    session_rows = _session_records(sessions)
    memberships = tuple(
        subject.build_membership_record(
            security_id=f"perm-security-{index:02d}",
            first_session_index=0,
            last_session_index_exclusive=len(sessions),
            sector_id="sector-technology",
        )
        for index in range(security_count)
    )
    eligible = sessions.index("2019-12-30")
    contributions = []
    for view in subject.SOURCE_VIEW_IDS:
        for index in range(12):
            if index < 6:
                action = "downgrades"
                delta = Fraction(-(6 - index), 6)
            else:
                action = "upgrades"
                delta = Fraction(index - 5, 6)
            source_hash = hashlib.sha256(
                f"source-{index}".encode("ascii")
            ).hexdigest()
            contributions.append(
                subject.build_contribution_record(
                    source_view_id=view,
                    security_id=f"perm-security-{index:02d}",
                    eligible_session_index=eligible,
                    institution_id=f"firm-{index:02d}",
                    common_event_id=f"catalyst-{index:02d}",
                    rating_action=action,
                    firm_delta=delta,
                    global_delta=delta / 2,
                    source_row_sha256=source_hash,
                )
            )
    contribution_rows = tuple(contributions)
    manifest = subject.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=session_rows,
        membership_records=memberships,
        contribution_records=contribution_rows,
        source_lineage_sha256s=_lineage(),
        history_batch_security_count=history_batch,
        scoring_sessions_per_callback=scoring_batch,
        signal_seed_contributions_per_callback=seed_batch,
    )
    return manifest, session_rows, memberships, contribution_rows


def _loaded_input(**kwargs):
    records = _fixture_records(**kwargs)
    return subject.load_preliminary_rating_input(*records)


def _drift(security_id):
    if security_id == "benchmark-SPY-permanent-id":
        return Decimal(0)
    index = int(security_id.rsplit("-", 1)[1])
    if index < 6:
        return Decimal(index - 6) / Decimal("10000")
    if index < 12:
        return Decimal(index - 5) / Decimal("10000")
    return Decimal(0)


def _history_loader(runtime_input, requests, *, omit=None):
    positions = {value: index for index, value in enumerate(runtime_input.session_axis)}

    def load(request):
        assert request.schema == subject.HISTORY_REQUEST_SCHEMA
        assert request.normalization_mode == "total_return"
        assert request.observation == "session_open"
        assert len(request.security_ids) <= runtime_input.history_batch_security_count
        requests.append(request)
        begin = positions[request.start_session]
        end = positions[request.end_session]
        rows = []
        for security in request.security_ids:
            growth = Decimal(1) + _drift(security)
            price = Decimal(100)
            for offset, session in enumerate(
                runtime_input.session_axis[begin : end + 1]
            ):
                if offset:
                    with localcontext(frozen_scoring._context()):
                        price = +(price * growth)
                if omit != (security, session):
                    rows.append(
                        subject.TotalReturnOpenObservation(
                            subject.HISTORY_OBSERVATION_SCHEMA,
                            security,
                            session,
                            price,
                        )
                    )
        return tuple(rows)

    return load


@pytest.fixture(scope="module")
def completed_run(tmp_path_factory):
    value = _loaded_input(seed_batch=3, scoring_batch=5)
    scratch = tmp_path_factory.mktemp("preliminary-rating")
    runtime = subject.PreliminaryRatingEvaluationRuntime(
        value, scratch_directory=scratch
    )
    requests = []
    loader = _history_loader(value, requests)
    progress = []
    while runtime.phase is not subject.RuntimePhase.COMPLETED:
        progress.append(runtime.run_callback(loader))
    return value, runtime, requests, tuple(progress), scratch


def test_contract_anchors_the_existing_frozen_rating_and_ic_primitives():
    assert subject.HORIZONS == formal_evaluation.HORIZONS == (1, 5, 20, 60)
    assert frozen_scoring.HALF_LIFE_SESSIONS == 20
    assert frozen_scoring.MINIMUM_TOTAL_NAMES == 20
    assert frozen_scoring.MINIMUM_ACTIVE_NAMES == 5
    assert frozen_scoring.MAD_SCALE == Decimal("1.4826")
    assert frozen_scoring.SCORE_CLIP == Decimal(4)
    assert subject.MINIMUM_IC_ROWS == formal_evaluation.MINIMUM_IC_ROWS == 20


def test_compact_cloud_arithmetic_matches_frozen_host_primitives():
    for age in (0, 1, 19, 20, 21, 60, 500, 1_500):
        assert subject._decay(age) == frozen_scoring._decay(age)
    masses = (Decimal("0.5"), Decimal("1.25"), Decimal("0"), Decimal("2.75"))
    assert subject._effective_contributors(masses) == frozen_formulas.effective_contributors(masses)
    tiny = (Decimal("1e-19"),)
    assert subject._effective_contributors(tiny) == frozen_formulas.effective_contributors(tiny) == 0
    assert subject._stock_reliability(
        Decimal("2.5"), Decimal(1)
    ) == frozen_formulas.stock_reliability(
        independent_effective_n=Decimal("2.5"), quality=Decimal(1)
    )
    raw = {f"s-{index:02d}": Decimal(index - 10) for index in range(20)}
    members = tuple(sorted(raw))
    active = set(members)
    compact = subject._normalize_sector(raw, active, members)
    frozen, reason = frozen_scoring._normalize_sector(raw, active, members)
    assert reason is None
    assert compact == frozen
    scores = tuple(Decimal(value) for value in (1, 1, 2, 4, 7))
    outcomes = tuple(Decimal(value) for value in (5, 3, 4, 8, 9))
    assert subject._spearman(scores, outcomes) == formal_evaluation._spearman(
        scores, outcomes
    )


def test_authoritative_arithmetic_ignores_hostile_ambient_decimal_context():
    raw = {
        f"s-{index:02d}": Decimal(index - 9) / Decimal(7)
        for index in range(20)
    }
    members = tuple(sorted(raw))
    expected, reason = frozen_scoring._normalize_sector(raw, set(members), members)
    assert reason is None
    expected_reliable = frozen_formulas.stock_reliability(
        independent_effective_n=Decimal("2.7777777777777777777777777777"),
        quality=Decimal("0.3333333333333333333333333333"),
    )
    with localcontext(frozen_scoring._context()):
        expected_score = +(expected["s-00"] * expected_reliable)
        expected_share = +(Decimal(2) / Decimal(3))
    scores = tuple(Decimal(value) / Decimal(7) for value in (1, 1, 2, 4, 7))
    outcomes = tuple(Decimal(value) / Decimal(11) for value in (5, 3, 4, 8, 9))
    expected_ic = formal_evaluation._spearman(scores, outcomes)
    with localcontext(Context(prec=7, rounding=ROUND_DOWN)):
        assert subject._normalize_sector(raw, set(members), members) == expected
        assert subject._stock_reliability(
            Decimal("2.7777777777777777777777777777"),
            Decimal("0.3333333333333333333333333333"),
        ) == expected_reliable
        assert subject._reliable_score(
            expected["s-00"], expected_reliable
        ) == expected_score
        assert subject._spearman(scores, outcomes) == expected_ic
        assert subject._positive_share(
            (Decimal(-1), Decimal(2), Decimal(3))
        ) == expected_share


def test_loader_authenticates_exact_manifest_and_compact_shards():
    value = _loaded_input()
    assert value.session_axis[0] == "2013-01-02"
    assert len(value.memberships) == 20
    assert len(value.contributions) == 24
    assert dict(value.source_lineage_sha256s) == _lineage()


def test_global_rating_map_lineage_tamper_is_refused():
    manifest, sessions, memberships, contributions = _fixture_records()
    manifest = copy.deepcopy(manifest)
    manifest["source_lineage_sha256s"]["global_rating_map_sha256"] = "f" * 64
    with pytest.raises(
        subject.PreliminaryRatingEvaluationError,
        match="manifest identity is not content-derived",
    ):
        subject.load_preliminary_rating_input(
            manifest, sessions, memberships, contributions
        )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    (
        ("history_batch_security_count", True),
        ("scoring_sessions_per_callback", 6),
        ("signal_seed_contributions_per_callback", 20_001),
        ("maximum_backtest_runtime_hours", 11),
        ("q_data_policy_id", "invented-quality"),
        ("history_observation", "close_to_close"),
    ),
)
def test_manifest_policy_and_callback_bounds_have_distinct_refusals(
    field, bad_value
):
    manifest, sessions, memberships, contributions = _fixture_records()
    manifest = copy.deepcopy(manifest)
    manifest[field] = bad_value
    with pytest.raises(subject.PreliminaryRatingEvaluationError):
        subject.load_preliminary_rating_input(
            manifest, sessions, memberships, contributions
        )


def test_unknown_manifest_field_is_refused_even_with_recomputed_hash():
    manifest, sessions, memberships, contributions = _fixture_records()
    manifest = copy.deepcopy(manifest)
    manifest["surprise"] = False
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="fields changed"):
        subject.load_preliminary_rating_input(
            manifest, sessions, memberships, contributions
        )


def test_nested_manifest_scalars_require_exact_builtin_types():
    class StringSubclass(str):
        pass

    manifest, sessions, memberships, contributions = _fixture_records()
    changed = copy.deepcopy(manifest)
    changed["accepted_risk_disclosures"]["orders"] = 0
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="risk disclosures changed type"):
        subject.load_preliminary_rating_input(
            changed, sessions, memberships, contributions
        )
    changed = copy.deepcopy(manifest)
    changed["source_view_ids"][0] = StringSubclass(changed["source_view_ids"][0])
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="source views changed type"):
        subject.load_preliminary_rating_input(
            changed, sessions, memberships, contributions
        )


def test_public_policy_aliases_cannot_mutate_or_rebind_runtime_policy(monkeypatch):
    records = _fixture_records()
    value = subject.load_preliminary_rating_input(*records)
    with pytest.raises(TypeError):
        subject.PRIMARY_WINDOW["start_session"] = "2024-01-02"
    returned = subject._policy.primary_window_record()
    returned["start_session"] = "2024-01-02"
    assert subject._policy.primary_window_record()["start_session"] == "2020-01-02"
    monkeypatch.setattr(subject, "PRIMARY_WINDOW", {"start_session": "2024-01-02"})
    monkeypatch.setattr(subject, "WINDOWS", ())
    monkeypatch.setattr(
        subject,
        "ACCEPTED_RISK_DISCLOSURES",
        {"historical_point_in_time_security_master": True},
    )
    runtime = subject.PreliminaryRatingEvaluationRuntime(value)
    assert runtime._input.session_axis[runtime._evaluation_positions[0]] == "2020-01-02"
    runtime.abort()
    rebuilt = subject.build_preliminary_rating_manifest(
        benchmark_security_id=records[0]["benchmark_security_id"],
        session_axis_records=records[1],
        membership_records=records[2],
        contribution_records=records[3],
        source_lineage_sha256s=_lineage(),
    )
    assert rebuilt["primary_window"]["start_session"] == "2020-01-02"
    assert rebuilt["accepted_risk_disclosures"][
        "historical_point_in_time_security_master"
    ] is False


def test_session_index_bool_is_refused_before_stream_hash_comparison():
    manifest, sessions, memberships, contributions = _fixture_records()
    sessions = list(copy.deepcopy(sessions))
    sessions[0]["session_index"] = False
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="session index"):
        subject.load_preliminary_rating_input(
            manifest, tuple(sessions), memberships, contributions
        )


def test_nonuniform_q_data_is_not_silently_accepted():
    manifest, sessions, memberships, contributions = _fixture_records()
    memberships = list(copy.deepcopy(memberships))
    semantic = {
        key: value
        for key, value in memberships[0].items()
        if key != "row_sha256"
    }
    semantic["q_data"] = "0.9"
    memberships[0] = {**semantic, "row_sha256": subject._sha256(semantic)}
    memberships = tuple(memberships)
    manifest = subject.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=sessions,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s=_lineage(),
    )
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="uniform one"):
        subject.load_preliminary_rating_input(
            manifest, sessions, memberships, contributions
        )


def test_contribution_sign_must_match_the_directional_action():
    source_hash = "a" * 64
    with pytest.raises(
        subject.PreliminaryRatingEvaluationError,
        match="contradicts rating action",
    ):
        bad = subject.build_contribution_record(
            source_view_id=subject.SOURCE_VIEW_IDS[0],
            security_id="security-a",
            eligible_session_index=0,
            institution_id="firm-a",
            common_event_id="event-a",
            rating_action="upgrades",
            firm_delta=Fraction(-1, 2),
            global_delta=Fraction(1, 2),
            source_row_sha256=source_hash,
        )


def test_contribution_hash_mutation_is_refused_before_arithmetic():
    manifest, sessions, memberships, contributions = _fixture_records()
    contributions = list(copy.deepcopy(contributions))
    contributions[0]["firm_delta_numerator"] = -99
    with pytest.raises(
        subject.PreliminaryRatingEvaluationError,
        match="identity is not content-derived",
    ):
        subject.load_preliminary_rating_input(
            manifest, sessions, memberships, tuple(contributions)
        )


def test_daily_dedupe_key_is_enforced_after_rehashing():
    manifest, sessions, memberships, contributions = _fixture_records()
    duplicate = copy.deepcopy(contributions[0])
    duplicate["common_event_id"] = "different-catalyst"
    semantic = {
        key: value
        for key, value in duplicate.items()
        if key not in ("contribution_id", "row_sha256")
    }
    digest = subject._sha256(semantic)
    duplicate["contribution_id"] = (
        "arv2-preliminary-rating-contribution-" + digest[:24]
    )
    duplicate["row_sha256"] = digest
    contributions = tuple(
        sorted(
            (*contributions, duplicate),
            key=lambda row: (
                subject.SOURCE_VIEW_IDS.index(row["source_view_id"]),
                row["eligible_session_index"],
                row["security_id"],
                row["institution_id"],
                row["contribution_id"],
            ),
        )
    )
    manifest = subject.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=sessions,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s=_lineage(),
    )
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="duplicated"):
        subject.load_preliminary_rating_input(
            manifest, sessions, memberships, contributions
        )


def test_current_and_censored_views_admit_independently_deduped_events():
    manifest, sessions, memberships, contributions = _fixture_records()
    contributions = list(copy.deepcopy(contributions))
    censored = next(
        index
        for index, row in enumerate(contributions)
        if row["source_view_id"] == subject.SOURCE_VIEW_IDS[1]
    )
    contributions[censored]["source_row_sha256"] = "f" * 64
    semantic = {
        key: value
        for key, value in contributions[censored].items()
        if key not in ("contribution_id", "row_sha256")
    }
    digest = subject._sha256(semantic)
    contributions[censored]["contribution_id"] = (
        "arv2-preliminary-rating-contribution-" + digest[:24]
    )
    contributions[censored]["row_sha256"] = digest
    contributions = tuple(contributions)
    manifest = subject.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=sessions,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s=_lineage(),
    )
    loaded = subject.load_preliminary_rating_input(
        manifest, sessions, memberships, contributions
    )
    assert any(
        row.source_view_id == subject.SOURCE_VIEW_IDS[1]
        and row.source_row_sha256 == "f" * 64
        for row in loaded.contributions
    )


def test_empty_required_source_view_is_a_named_refusal():
    _manifest, sessions, memberships, contributions = _fixture_records()
    contributions = tuple(
        row for row in contributions
        if row["source_view_id"] == subject.SOURCE_VIEW_IDS[0]
    )
    manifest = subject.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=sessions,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s=_lineage(),
    )
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="no rating contribution"):
        subject.load_preliminary_rating_input(
            manifest, sessions, memberships, contributions
        )


def test_callback_progress_is_structurally_bounded(completed_run):
    value, runtime, requests, progress, _scratch = completed_run
    assert runtime.phase is subject.RuntimePhase.COMPLETED
    assert len(requests) == 1
    assert all(len(request.security_ids) <= 64 for request in requests)
    seed_progress = [item for item in progress if item.phase is subject.RuntimePhase.SIGNAL_SEED]
    assert seed_progress
    assert all(
        right.seeded_contribution_count - left.seeded_contribution_count <= 3
        for left, right in zip(seed_progress, seed_progress[1:])
    )
    scoring_progress = [item for item in progress if item.phase is subject.RuntimePhase.SCORING]
    assert scoring_progress
    assert all(
        right.completed_scoring_session_count
        - left.completed_scoring_session_count
        <= value.scoring_sessions_per_callback
        for left, right in zip(scoring_progress, scoring_progress[1:])
    )


def test_zero_prestart_contributions_still_budget_the_seed_transition(tmp_path):
    _manifest, sessions, memberships, contributions = _fixture_records()
    start = next(
        row["session_index"] for row in sessions if row["session"] == "2020-01-02"
    )
    moved = tuple(
        subject.build_contribution_record(
            source_view_id=row["source_view_id"],
            security_id=row["security_id"],
            eligible_session_index=start,
            institution_id=row["institution_id"],
            common_event_id=row["common_event_id"],
            rating_action=row["rating_action"],
            firm_delta=Fraction(
                row["firm_delta_numerator"], row["firm_delta_denominator"]
            ),
            global_delta=Fraction(
                row["global_delta_numerator"], row["global_delta_denominator"]
            ),
            source_row_sha256=row["source_row_sha256"],
        )
        for row in contributions
    )
    manifest = subject.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=sessions,
        membership_records=memberships,
        contribution_records=moved,
        source_lineage_sha256s=_lineage(),
    )
    value = subject.load_preliminary_rating_input(
        manifest, sessions, memberships, moved
    )
    runtime = subject.PreliminaryRatingEvaluationRuntime(
        value, scratch_directory=tmp_path
    )
    expected_scoring = (
        len(runtime._evaluation_positions) + value.scoring_sessions_per_callback - 1
    ) // value.scoring_sessions_per_callback
    assert runtime._maximum_callback_count == len(runtime._history_batches) + 1 + expected_scoring
    runtime.abort()


def test_history_matrix_slot_geometry_has_an_isolated_bound(monkeypatch, tmp_path):
    value = _loaded_input()
    monkeypatch.setattr(subject, "MAX_HISTORY_MATRIX_SLOT_COUNT", 1)

    with pytest.raises(
        subject.PreliminaryRatingEvaluationError,
        match="history observation geometry exceeds reviewed bound",
    ):
        subject.PreliminaryRatingEvaluationRuntime(
            value, scratch_directory=tmp_path
        )


def test_history_requests_pin_total_return_adjusted_open_and_spy(completed_run):
    value, _runtime, requests, _progress, _scratch = completed_run
    request = requests[0]
    assert request.normalization_mode == "total_return"
    assert request.observation == "session_open"
    assert value.benchmark_security_id in request.security_ids
    assert request.start_session == "2020-01-02"
    end = value.session_axis.index("2025-12-31") + 60
    assert request.end_session == value.session_axis[end]


def test_preliminary_results_preserve_both_windows_views_arms_and_horizons(
    completed_run,
):
    _value, runtime, _requests, _progress, _scratch = completed_run
    summary = runtime.aggregate_summary()
    assert summary["status"] == "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY"
    assert summary["history_normalization_mode"] == "TOTAL_RETURN"
    assert summary["history_value_field"] == "open"
    assert summary["outcome_definition"] == subject.HISTORY_OBSERVATION
    keys = {
        (
            item["window_id"],
            item["source_view_id"],
            item["score_arm"],
            item["horizon_sessions"],
        )
        for item in summary["cells"]
    }
    assert keys == {
        (window["window_id"], view, arm, horizon)
        for window in subject.WINDOWS
        for view in subject.SOURCE_VIEW_IDS
        for arm in subject.SCORE_ARMS
        for horizon in subject.HORIZONS
    }
    primary = next(
        item
        for item in summary["cells"]
        if item["window_id"] == subject.PRIMARY_WINDOW["window_id"]
        and item["source_view_id"] == subject.SOURCE_VIEW_IDS[0]
        and item["score_arm"] == "firm_specific"
        and item["horizon_sessions"] == 20
    )
    descriptive = next(
        item
        for item in summary["cells"]
        if item["window_id"] == subject.DESCRIPTIVE_WINDOW["window_id"]
        and item["source_view_id"] == subject.SOURCE_VIEW_IDS[0]
        and item["score_arm"] == "firm_specific"
        and item["horizon_sessions"] == 20
    )
    assert primary["valid_ic_date_count"] > descriptive["valid_ic_date_count"] > 0
    assert Decimal(primary["mean_daily_spearman_ic"]) > 0
    assert primary["status"] == "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
    assert primary["formal_accept_reject_disposition"] is None


def test_uniform_quality_waiver_does_not_masquerade_as_measured_q_data(
    completed_run,
):
    _value, runtime, _requests, _progress, _scratch = completed_run
    summary = runtime.aggregate_summary()
    assert summary["q_data_policy_id"] == subject.Q_DATA_POLICY_ID
    assert summary["accepted_risk_disclosures"]["owner_waived_uniform_q_data"] is True
    assert summary["accepted_risk_disclosures"][
        "byte_identical_formal_per_event_decay_replay"
    ] is False
    assert summary["accepted_risk_disclosures"]["control_residualization"] is False
    # A common positive quality multiplier is rank/IC invariant; it cannot
    # justify economic magnitudes or a formal fit claim.
    scores = (Decimal("-1"), Decimal("0"), Decimal("2"))
    outcomes = (Decimal("-0.2"), Decimal("0"), Decimal("0.3"))
    assert formal_evaluation._spearman(scores, outcomes) == formal_evaluation._spearman(
        tuple(value * Decimal("0.25") for value in scores), outcomes
    )


def test_summary_is_aggregate_only_and_loudly_enumerates_omissions(completed_run):
    _value, runtime, _requests, _progress, _scratch = completed_run
    summary = runtime.aggregate_summary()
    assert summary["raw_provider_rows_in_summary"] is False
    assert summary["raw_security_outcome_rows_in_summary"] is False
    assert summary["raw_price_rows_in_summary"] is False
    assert summary["formal_result"] is False
    assert summary["alpha_claim_authorized"] is False
    assert summary["accepted_risk_disclosures"][
        "complete_cross_section_required_for_each_date_ic"
    ] is True
    assert summary["accepted_risk_disclosures"][
        "sector_normalization_uses_active_signals_only"
    ] is True
    assert summary["accepted_risk_disclosures"][
        "missing_price_rows_excluded_without_imputation"
    ] is True
    assert set(summary["omitted_formal_components"]) == set(
        subject.OMITTED_FORMAL_COMPONENTS
    )
    for field in (
        "historical_point_in_time_security_master",
        "historical_point_in_time_sector_classification",
        "pristine_point_in_time_input",
        "frozen_26_family_formal_result",
        "etf_portfolio_construction",
        "actual_or_synthetic_leverage",
        "orders",
        "trading",
    ):
        assert summary["accepted_risk_disclosures"][field] is False


def test_custom_summary_is_bounded_and_contains_no_raw_rows(completed_run):
    _value, runtime, _requests, _progress, _scratch = completed_run
    statistics = runtime.custom_summary_statistics()
    assert len(statistics) == 33
    assert tuple(statistics) == subject.EVALUATOR_CUSTOM_SUMMARY_STATISTIC_NAMES
    assert max(map(len, statistics)) <= 64
    assert max(map(len, statistics.values())) <= 4096
    parsed = [__import__("json").loads(value) for value in statistics.values()]
    assert not any(
        "adjusted_open" in item
        for item in parsed
        if type(item) is dict
    )
    assert not any("perm-security" in value for value in statistics.values())


def test_completed_runtime_destroys_the_ephemeral_history_matrix(completed_run):
    _value, runtime, _requests, _progress, scratch = completed_run
    assert not tuple(scratch.iterdir())
    assert runtime._history_prices == []
    assert runtime._history_security_ids == ()
    assert runtime._history_sessions == ()


def test_ephemeral_history_matrix_preserves_the_current_summary_golden(completed_run):
    _value, runtime, _requests, _progress, _scratch = completed_run
    summary = subject._canonical_bytes(runtime.aggregate_summary())
    statistics = subject._canonical_bytes(runtime.custom_summary_statistics())

    assert hashlib.sha256(summary).hexdigest() == (
        "e5acc4e59efa7c81c2599181332e8a7929a48354ce9a8478c08ed159faa37fd6"
    )
    assert hashlib.sha256(statistics).hexdigest() == (
        "7f154773d289c0f05820197e8913412899cd0a73a1ddb186d60dbbb04d4d1c81"
    )


def test_ephemeral_history_matrix_refuses_an_already_occupied_slot(tmp_path):
    value = _loaded_input(history_batch=64)
    runtime = subject.PreliminaryRatingEvaluationRuntime(
        value, scratch_directory=tmp_path
    )
    request = runtime._history_request(0)
    observations = _history_loader(value, [])(request)
    runtime._accept_history(request, observations)

    with pytest.raises(
        subject.PreliminaryRatingEvaluationError,
        match="history cache slot is already occupied",
    ):
        runtime._accept_history(request, observations)
    runtime.abort()


def test_ephemeral_history_matrix_pins_price_text_bound_and_batch_atomicity(tmp_path):
    value = _loaded_input(history_batch=64)
    runtime = subject.PreliminaryRatingEvaluationRuntime(
        value, scratch_directory=tmp_path / "boundary"
    )
    request = runtime._history_request(0)
    boundary = subject.TotalReturnOpenObservation(
        subject.HISTORY_OBSERVATION_SCHEMA,
        request.security_ids[0],
        request.start_session,
        Decimal("1." + "1" * 62),
    )
    runtime._accept_history(request, (boundary,))
    session = runtime._history_session_positions[request.start_session]
    security = runtime._history_security_positions[request.security_ids[0]]
    assert len(runtime._history_prices[session][security]) == 64
    runtime.abort()

    runtime = subject.PreliminaryRatingEvaluationRuntime(
        value, scratch_directory=tmp_path / "refusal"
    )
    valid = subject.TotalReturnOpenObservation(
        subject.HISTORY_OBSERVATION_SCHEMA,
        request.security_ids[0],
        request.start_session,
        Decimal("100"),
    )
    overlong = subject.TotalReturnOpenObservation(
        subject.HISTORY_OBSERVATION_SCHEMA,
        request.security_ids[1],
        request.start_session,
        Decimal("1." + "1" * 63),
    )

    with pytest.raises(
        subject.PreliminaryRatingEvaluationError,
        match="adjusted open exceeds canonical-text bound",
    ):
        runtime._accept_history(request, (valid, overlong))
    session = runtime._history_session_positions[request.start_session]
    assert all(
        runtime._history_prices[session][
            runtime._history_security_positions[security_id]
        ]
        is None
        for security_id in request.security_ids[:2]
    )
    runtime.abort()


def test_history_loader_cannot_return_wrong_container_or_observation_type(tmp_path):
    value = _loaded_input()
    runtime = subject.PreliminaryRatingEvaluationRuntime(value, scratch_directory=tmp_path)
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="exact tuple"):
        runtime.run_callback(lambda _request: [])
    runtime.abort()
    runtime = subject.PreliminaryRatingEvaluationRuntime(value, scratch_directory=tmp_path)
    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="wrong record type"):
        runtime.run_callback(lambda _request: ({},))
    runtime.abort()


def test_history_loader_cannot_cross_request_identity(tmp_path):
    value = _loaded_input()
    runtime = subject.PreliminaryRatingEvaluationRuntime(value, scratch_directory=tmp_path)

    def hostile(request):
        return (
            subject.TotalReturnOpenObservation(
                subject.HISTORY_OBSERVATION_SCHEMA,
                "unrequested-security",
                request.start_session,
                Decimal(100),
            ),
        )

    with pytest.raises(subject.PreliminaryRatingEvaluationError, match="escaped"):
        runtime.run_callback(hostile)
    runtime.abort()


def test_missing_total_return_rows_are_counted_not_substituted(tmp_path):
    value = _loaded_input(scoring_batch=5, seed_batch=20, security_count=21)
    def run(name, omit=None):
        runtime = subject.PreliminaryRatingEvaluationRuntime(
            value, scratch_directory=tmp_path / name
        )
        loader = _history_loader(value, [], omit=omit)
        while runtime.phase is not subject.RuntimePhase.COMPLETED:
            runtime.run_callback(loader)
        return next(
            item
            for item in runtime.aggregate_summary()["cells"]
            if item["window_id"] == subject.PRIMARY_WINDOW["window_id"]
            and item["source_view_id"] == subject.SOURCE_VIEW_IDS[0]
            and item["score_arm"] == "firm_specific"
            and item["horizon_sessions"] == 1
        )

    baseline = run("baseline")
    cell = run("omitted", ("perm-security-00", "2020-01-03"))
    assert cell["missing_outcome_pair_count"] >= 1
    assert cell["accepted_outcome_pair_count"] < cell["eligible_score_row_count"]
    assert cell["invalid_ic_date_count"] == baseline["invalid_ic_date_count"]
    assert cell["valid_ic_date_count"] == baseline["valid_ic_date_count"]
    # Twenty survivors still meet MINIMUM_IC_ROWS. The absent row is counted
    # and excluded without imputation; it cannot invalidate the usable pairs.
    assert cell["eligible_score_row_count"] - cell["accepted_outcome_pair_count"] >= 1
    assert subject.MINIMUM_IC_ROWS == 20


def test_sparse_sector_normalizes_active_signals_and_keeps_structural_zeros():
    members = tuple(f"security-{index:02d}" for index in range(60))
    active = set(members[:5])
    raw = {
        security: Decimal(index + 1) if security in active else Decimal(0)
        for index, security in enumerate(members)
    }

    normalized = subject._normalize_sector(raw, active, members)

    assert normalized is not None
    assert {normalized[item] for item in members[5:]} == {Decimal(0)}
    assert len({normalized[item] for item in members[:5]}) > 1


def test_one_refused_sector_invalidates_otherwise_sufficient_date_ic(tmp_path):
    _manifest, sessions, memberships, contributions = _fixture_records()
    memberships = (*memberships, *(
        subject.build_membership_record(
            security_id=f"perm-security-{index:02d}",
            first_session_index=0,
            last_session_index_exclusive=len(sessions),
            sector_id="sector-refused-underfilled",
        )
        for index in range(20, 25)
    ))
    manifest = subject.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=sessions,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s=_lineage(),
        signal_seed_contributions_per_callback=20,
    )
    value = subject.load_preliminary_rating_input(
        manifest, sessions, memberships, contributions
    )
    runtime = subject.PreliminaryRatingEvaluationRuntime(
        value, scratch_directory=tmp_path
    )
    loader = _history_loader(value, [])
    runtime.run_callback(loader)
    while runtime.phase is subject.RuntimePhase.SIGNAL_SEED:
        runtime.run_callback(loader)
    runtime.run_callback(loader)
    cell = runtime._cells[(
        subject.SOURCE_VIEW_IDS[0],
        "firm_specific",
        1,
        subject.PRIMARY_WINDOW["window_id"],
    )]
    assert cell.sector_refused_rows == 25
    assert cell.accepted_outcome_pairs == subject.MINIMUM_IC_ROWS * 5
    assert cell.valid_ic_dates == 0
    assert cell.invalid_ic_dates == 5
    runtime.abort()


def test_source_is_small_qc_prelude_safe_and_has_no_order_surface():
    source_path = Path(subject.__file__)
    source = source_path.read_text(encoding="utf-8")
    assert source_path.stat().st_size < 60_000
    assert "from __future__" not in source
    tree = ast.parse(source)
    assert not {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "sqlite3"
    }
    forbidden = {
        "set_holdings",
        "SetHoldings",
        "market_order",
        "MarketOrder",
        "limit_order",
        "LimitOrder",
        "liquidate",
        "Liquidate",
    }
    assert not {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in forbidden
    }
    assert not {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in forbidden
    }
