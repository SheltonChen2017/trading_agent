import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_evaluator as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_tilt as tilt,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as base,
)


def _sessions():
    return tuple(
        session.isoformat()
        for session in trading_sessions(
            date(2013, 1, 2), date(2026, 4, 30)
        )
    )


def _input(security_count=20, *, sector_count=1):
    sessions = _sessions()
    session_rows = tuple(
        {
            "schema": base.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )
    memberships = tuple(
        base.build_membership_record(
            security_id=f"perm-security-{index:02d}",
            first_session_index=0,
            last_session_index_exclusive=len(sessions),
            sector_id=(
                "sector-technology"
                if sector_count == 1
                else f"sector-{index % sector_count:02d}"
            ),
        )
        for index in range(security_count)
    )
    contributions = []
    contribution_sessions = tuple(
        sessions.index(
            next(
                session
                for session in sessions
                if session.startswith(f"{year}-")
            )
        )
        for year in range(2018, 2026)
    )
    for view in base.SOURCE_VIEW_IDS:
        for contribution_session in contribution_sessions:
            for index in range(security_count):
                midpoint = security_count // 2
                delta = Fraction(
                    index - midpoint
                    if index < midpoint
                    else index - midpoint + 1,
                    10,
                )
                contributions.append(
                    base.build_contribution_record(
                        source_view_id=view,
                        security_id=f"perm-security-{index:02d}",
                        eligible_session_index=contribution_session,
                        institution_id=f"firm-{index:02d}",
                        common_event_id=(
                            f"event-{contribution_session}-{index:02d}"
                        ),
                        rating_action=(
                            "downgrades"
                            if index < midpoint
                            else "upgrades"
                        ),
                        firm_delta=delta,
                        global_delta=delta / 2,
                        source_row_sha256=hashlib.sha256(
                            f"source-{view}-{contribution_session}-{index}".encode(
                                "ascii"
                            )
                        ).hexdigest(),
                    )
                )
    lineage = {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in base._SOURCE_LINEAGE_FIELDS
    }
    manifest = base.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=session_rows,
        membership_records=memberships,
        contribution_records=tuple(contributions),
        source_lineage_sha256s=lineage,
        history_batch_security_count=64,
        scoring_sessions_per_callback=5,
        signal_seed_contributions_per_callback=20_000,
    )
    return base.load_preliminary_rating_input(
        manifest,
        session_rows,
        memberships,
        tuple(contributions),
    )


def _caps(value, profile_id, security_ids=None):
    if security_ids is None:
        security_ids = tuple(
            sorted(item.security_id for item in value.memberships)
        )
    cap_by_security = {
        security_id: Decimal(index + 1)
        for index, security_id in enumerate(security_ids)
    }
    return {
        session: dict(cap_by_security)
        for session in subject.decision_sessions_for_input(value, profile_id)
    }


_DEFAULT_CAPS = object()


def _runtime(
    value,
    *,
    profile_id=subject.QQQ_2021_2025_PROFILE_ID,
    caps=_DEFAULT_CAPS,
):
    return subject.MarketCapStockPortfolioEvaluationRuntime(
        value,
        profile_id=profile_id,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
        eligibility_market_caps_by_decision_session=(
            _caps(value, profile_id) if caps is _DEFAULT_CAPS else caps
        ),
    )


def _history_loader(
    value,
    *,
    omissions=frozenset(),
    opening_jump=False,
    price_overrides=None,
):
    positions = {
        session: index for index, session in enumerate(value.session_axis)
    }
    price_overrides = {} if price_overrides is None else price_overrides

    def load(request):
        rows = []
        begin = positions[request.start_session]
        end = positions[request.end_session]
        for security_id in request.security_ids:
            for session in value.session_axis[begin : end + 1]:
                if (security_id, session) in omissions:
                    continue
                price = Decimal(100)
                if (
                    opening_jump
                    and security_id != value.benchmark_security_id
                    and session > "2021-01-04"
                ):
                    price = Decimal(200)
                price = price_overrides.get(
                    (security_id, session), price
                )
                rows.append(
                    base.TotalReturnOpenObservation(
                        base.HISTORY_OBSERVATION_SCHEMA,
                        security_id,
                        session,
                        price,
                    )
                )
        return tuple(rows)

    return load


def _complete(
    value,
    *,
    profile_id=subject.QQQ_2021_2025_PROFILE_ID,
    caps=_DEFAULT_CAPS,
    omissions=frozenset(),
    opening_jump=False,
    price_overrides=None,
):
    runtime = _runtime(value, profile_id=profile_id, caps=caps)
    loader = _history_loader(
        value,
        omissions=omissions,
        opening_jump=opening_jump,
        price_overrides=price_overrides,
    )
    while runtime.phase is not base.RuntimePhase.COMPLETED:
        runtime.run_callback(loader)
    return runtime


def _tilt_case(negative_count, positive_count, *, zero_count=0, missing_count=0):
    market_caps = {}
    scores = {}
    for index in range(negative_count):
        security_id = f"negative-{index:03d}"
        market_caps[security_id] = Decimal(index + 1)
        scores[security_id] = Decimal(index - negative_count)
    for index in range(positive_count):
        security_id = f"positive-{index:03d}"
        market_caps[security_id] = Decimal(positive_count - index)
        scores[security_id] = Decimal(index + 1)
    for index in range(zero_count):
        security_id = f"zero-{index:03d}"
        market_caps[security_id] = Decimal(index + 1)
        scores[security_id] = Decimal(0)
    for index in range(missing_count):
        market_caps[f"missing-{index:03d}"] = Decimal(index + 1)
    return market_caps, scores


def _sector_map(market_caps, sector_count=2):
    return {
        security_id: f"sector-{index % sector_count:02d}"
        for index, security_id in enumerate(sorted(market_caps))
    }


def test_successor_profiles_preserve_periods_and_superseded_identities():
    assert subject.V2_PROFILE_IDS == (
        subject.QQQ_2021_2025_V2_PROFILE_ID,
        subject.SPY_2021_2025_V2_PROFILE_ID,
        subject.QQQ_2019_2023_V2_PROFILE_ID,
        subject.SPY_2019_2023_V2_PROFILE_ID,
        subject.QQQ_2023_2025_V2_PROFILE_ID,
        subject.SPY_2023_2025_V2_PROFILE_ID,
    )
    assert subject.PROFILE_IDS == (
        subject.QQQ_2021_2025_V3_PROFILE_ID,
        subject.SPY_2021_2025_V3_PROFILE_ID,
    )
    assert subject.ALL_PROFILE_IDS == (
        subject.V1_PROFILE_IDS
        + subject.V2_PROFILE_IDS
        + subject.PROFILE_IDS
    )
    assert subject.QQQ_PROFILE_IDS == subject.PROFILE_IDS[::2]
    assert subject.SPY_PROFILE_IDS == subject.PROFILE_IDS[1::2]
    expected = {
        subject.QQQ_2021_2025_V2_PROFILE_ID: ("QQQ", 1_255, 261),
        subject.SPY_2021_2025_V2_PROFILE_ID: ("SPY", 1_255, 261),
        subject.QQQ_2019_2023_V2_PROFILE_ID: ("QQQ", 1_258, 261),
        subject.SPY_2019_2023_V2_PROFILE_ID: ("SPY", 1_258, 261),
        subject.QQQ_2023_2025_V2_PROFILE_ID: ("QQQ", 752, 157),
        subject.SPY_2023_2025_V2_PROFILE_ID: ("SPY", 752, 157),
    }
    historical_hashes = {
        subject.QQQ_2021_2025_V2_PROFILE_ID: (
            "71fe35e9a200e61c9c908fe839e244d97bcef89664a921ddaa3dfd09b8a09178"
        ),
        subject.SPY_2021_2025_V2_PROFILE_ID: (
            "0b6587206c68452b7468aff42432cb3b587a0f96cc078fbf57a6473f86feb59d"
        ),
        subject.QQQ_2019_2023_V2_PROFILE_ID: (
            "661d87e282f6c37cc258db7a3e814e5a261369209fc3fc4a96c1769edd71f83d"
        ),
        subject.SPY_2019_2023_V2_PROFILE_ID: (
            "72a4b469d7f8fa79ea4ea62836b6b43000069b5e0a7dca6941af00124ca68f4a"
        ),
        subject.QQQ_2023_2025_V2_PROFILE_ID: (
            "da7f4c75b9504c02f209362d2aebf69188d32cf608ac167fd543beb196067f93"
        ),
        subject.SPY_2023_2025_V2_PROFILE_ID: (
            "e56aa1c7777720ec36b8414ae2525858d0911b7c7954adca292d211c767fa0b3"
        ),
    }
    historical_names = (
        "ARV2_STOCK_PORTFOLIO_COST_0",
        "ARV2_STOCK_PORTFOLIO_COST_10",
        "ARV2_STOCK_PORTFOLIO_COST_20",
        "ARV2_STOCK_PORTFOLIO_COST_5",
        subject.MATCHED_AGGREGATES_STATISTIC_NAME,
        subject.META_STATISTIC_NAME,
        subject.SELECTED_AGGREGATES_STATISTIC_NAME,
    )
    for profile_id, (ticker, sessions, decisions) in expected.items():
        profile = subject.require_profile(profile_id)
        digest = profile.pop("profile_sha256")
        assert subject._sha(profile) == digest
        assert digest == historical_hashes[profile_id]
        assert profile["expected_session_count"] == sessions
        assert profile["expected_decision_session_count"] == decisions
        assert profile["r055_score_rule"] == "exact_unchanged_R055_cross_section"
        assert profile["target_gross_exposure"] == "0.98"
        assert profile["execution_timing"] == "next_authenticated_session_open"
        assert profile["cost_bps_per_side"] == [0, 5, 10, 20]
        assert profile["history_collection_window_policy"] == (
            subject.OUT_OF_WINDOW_COLLECTION_POLICY
        )
        assert profile["leverage"] is False
        assert subject.constituent_etf_tickers_for_profile(profile_id) == (
            ticker,
        )
        assert subject.expected_custom_summary_statistic_names(
            profile_id
        ) == historical_names
    assert all(
        "history_collection_window_policy" not in subject.require_profile(profile_id)
        for profile_id in subject.V1_PROFILE_IDS
    )
    assert all(
        subject.expected_custom_summary_statistic_names(profile_id)
        == historical_names
        for profile_id in subject.V1_PROFILE_IDS
    )
    for profile_id in subject.PROFILE_IDS:
        profile = subject.require_profile(profile_id)
        assert profile["selection"].startswith(
            "full_point_in_time_eligible_benchmark"
        )
        assert profile["matched_comparator"].startswith(
            "same_full_point_in_time_eligible_benchmark"
        )
        assert profile["maximum_holdings"] is None
        assert profile["sector_neutrality_rule"].startswith(
            "exact_selected_weight_equals_benchmark_weight"
        )
        assert profile["sector_mapping_rule"].startswith(
            "exhaustive_exact_security_to_sector_mapping"
        )
        assert profile["sector_neutral_execution_rule"] == (
            "execute_each_tradable_name_at_its_exact_frozen_target_preserve_"
            "each_locked_weight_never_redistribute_missing_or_locked_budget_"
            "and_count_sector_target_underfill_for_missing_or_below_frozen_"
            "locks_or_sector_gross_under_and_locked_sector_over_target_for_"
            "above_frozen_locks_or_sector_gross_over"
        )
        assert profile["portfolio_weight_quantum"] == format(
            subject.PORTFOLIO_WEIGHT_QUANTUM, "f"
        )
        assert len(subject.expected_custom_summary_statistic_names(profile_id)) == 8
        assert subject.TILT_AGGREGATES_STATISTIC_NAME in (
            subject.expected_custom_summary_statistic_names(profile_id)
        )


def test_profiles_are_detached_and_unknown_profile_refuses():
    profile = subject.require_profile(subject.QQQ_2021_2025_PROFILE_ID)
    profile["cost_bps_per_side"].append(99)
    assert subject.require_profile(subject.QQQ_2021_2025_PROFILE_ID)[
        "cost_bps_per_side"
    ] == [0, 5, 10, 20]
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="exact fixed profile",
    ):
        subject.require_profile("unknown")


def test_average_rank_tilts_use_exact_midranks_for_ties():
    result = tilt.average_rank_tilts(
        {
            "d": Decimal(2),
            "b": Decimal(-1),
            "a": Decimal(-2),
            "c": Decimal(-1),
        }
    )

    assert result == {
        "a": Decimal(-1),
        "b": Decimal(0),
        "c": Decimal(0),
        "d": Decimal(1),
    }


@pytest.mark.parametrize(
    ("negative_count", "positive_count", "expected_status"),
    (
        (19, 20, tilt.TILT_UNDERFILLED),
        (20, 19, tilt.TILT_UNDERFILLED),
        (21, 19, tilt.TILT_UNDERFILLED),
        (19, 21, tilt.TILT_UNDERFILLED),
        (20, 20, tilt.TILT_ENABLED),
    ),
)
def test_tilt_breadth_and_score_sign_boundaries(
    negative_count, positive_count, expected_status
):
    caps, scores = _tilt_case(negative_count, positive_count)

    result = tilt.build_benchmark_tilt(caps, scores, _sector_map(caps))

    assert result.status == expected_status
    assert result.ranked_nonzero_score_count == negative_count + positive_count
    assert result.negative_score_count == negative_count
    assert result.positive_score_count == positive_count
    if expected_status == tilt.TILT_UNDERFILLED:
        assert result.selected_weights == result.benchmark_weights
        assert result.tilted_name_count == 0
        assert result.one_way_active_share == 0
    else:
        assert result.tilted_name_count >= 40


def test_missing_and_zero_scores_remain_exact_benchmark_weights():
    caps, scores = _tilt_case(21, 21, zero_count=2, missing_count=2)

    result = tilt.build_benchmark_tilt(caps, scores, _sector_map(caps))

    assert result.status == tilt.TILT_ENABLED
    for security_id in (
        "zero-000",
        "zero-001",
        "missing-000",
        "missing-001",
    ):
        assert (
            result.selected_weights[security_id]
            == result.benchmark_weights[security_id]
        )
        assert security_id not in result.rank_tilts


def test_breadth_confirmed_scores_fall_back_when_sectors_cannot_cross_fund():
    caps, scores = _tilt_case(20, 20)
    sectors = {
        security_id: (
            "sector-negative"
            if security_id.startswith("negative-")
            else "sector-positive"
        )
        for security_id in caps
    }

    result = tilt.build_benchmark_tilt(caps, scores, sectors)

    assert result.ranked_nonzero_score_count == 40
    assert result.positive_score_count == 20
    assert result.negative_score_count == 20
    assert result.status == tilt.TILT_UNDERFILLED
    assert result.selected_weights == result.benchmark_weights


def test_enabled_tilt_obeys_every_frozen_bound_and_exact_conservation():
    caps, scores = _tilt_case(20, 20)

    sectors = _sector_map(caps)
    result = tilt.build_benchmark_tilt(caps, scores, sectors)
    with localcontext(base._context()):
        active = {
            security_id: +(
                result.selected_weights[security_id]
                - result.benchmark_weights[security_id]
            )
            for security_id in result.selected_weights
        }
        overweights = tuple(value for value in active.values() if value > 0)
        underweights = tuple(-value for value in active.values() if value < 0)
        benchmark_hhi = +base._stable_sum(
            (weight / subject.TARGET_GROSS_EXPOSURE) ** 2
            for weight in result.benchmark_weights.values()
        )
        selected_hhi = +base._stable_sum(
            (weight / subject.TARGET_GROSS_EXPOSURE) ** 2
            for weight in result.selected_weights.values()
        )
        active_imbalance = +base._stable_sum(active.values())
        overweight_total = +base._stable_sum(overweights)
        underweight_total = +base._stable_sum(underweights)
        observed_one_way = +(
            base._stable_sum(abs(value) for value in active.values())
            / Decimal(2)
        )
        relative_bounds_hold = all(
            Decimal("0.8") * result.benchmark_weights[security_id]
            <= result.selected_weights[security_id]
            <= Decimal("1.2") * result.benchmark_weights[security_id]
            for security_id in result.selected_weights
        )
        hhi_bound = +(Decimal("1.44") * benchmark_hhi)
        observed_hhi_ratio = +(selected_hhi / benchmark_hhi)

    assert result.status == tilt.TILT_ENABLED
    assert base._stable_sum(result.benchmark_weights.values()) == Decimal("0.98")
    assert base._stable_sum(result.selected_weights.values()) == Decimal("0.98")
    assert abs(active_imbalance) <= Decimal("1e-48")
    assert abs(overweight_total - underweight_total) <= Decimal("1e-48")
    assert result.one_way_active_share == observed_one_way
    assert result.one_way_active_share <= Decimal("0.049")
    assert result.maximum_overweight == max(overweights)
    assert result.maximum_overweight <= Decimal("0.0049")
    assert result.tilted_name_count >= 40
    assert relative_bounds_hold
    assert selected_hhi <= hhi_bound
    assert result.hhi_ratio_to_benchmark == observed_hhi_ratio
    assert result.sector_count == 2
    assert result.maximum_absolute_sector_active_weight == 0
    for sector_id in sorted(set(sectors.values())):
        members = tuple(
            security_id
            for security_id in result.selected_weights
            if sectors[security_id] == sector_id
        )
        assert base._stable_sum(
            result.selected_weights[security_id]
            for security_id in members
        ) == base._stable_sum(
            result.benchmark_weights[security_id]
            for security_id in members
        )


def test_tilt_is_deterministic_across_cap_score_and_tie_insertion_order():
    caps, scores = _tilt_case(22, 22, zero_count=1, missing_count=1)
    scores["negative-000"] = scores["negative-001"]
    scores["positive-020"] = scores["positive-021"]

    sectors = _sector_map(caps, 4)
    first = tilt.build_benchmark_tilt(caps, scores, sectors)
    second = tilt.build_benchmark_tilt(
        dict(reversed(tuple(caps.items()))),
        dict(reversed(tuple(scores.items()))),
        dict(reversed(tuple(sectors.items()))),
    )
    residual = tilt.bounded_pro_rata(
        Decimal("0.1"),
        {"c": Decimal("0.2"), "a": Decimal("0.2"), "b": Decimal("0.2")},
    )

    assert first == second
    assert tuple(first.selected_weights) == tuple(sorted(first.selected_weights))
    assert tuple(residual) == ("a", "b", "c")
    assert base._stable_sum(residual.values()) == Decimal("0.1")
    assert all(Decimal(0) <= residual[key] <= Decimal("0.2") for key in residual)


@pytest.mark.parametrize(
    "bad_score",
    (1, 1.0, Decimal("NaN"), Decimal("Infinity")),
)
def test_tilt_refuses_non_exact_or_nonfinite_scores(bad_score):
    caps, scores = _tilt_case(20, 20)
    scores["negative-000"] = bad_score

    with pytest.raises(
        tilt.BoundedBenchmarkTiltError,
        match="score must be exact finite Decimal",
    ):
        tilt.build_benchmark_tilt(caps, scores, _sector_map(caps))


def test_tilt_refuses_nonexhaustive_or_invalid_sector_mapping():
    caps, scores = _tilt_case(20, 20)
    valid = _sector_map(caps)
    missing = dict(valid)
    missing.pop(min(missing))
    extra = {**valid, "outside-universe": "sector-00"}
    invalid = dict(valid)
    invalid[min(invalid)] = ""

    for mapping, message in (
        (None, "must be an exact dict"),
        (missing, "is not exhaustive"),
        (extra, "is not exhaustive"),
        (invalid, "mapping changed"),
    ):
        with pytest.raises(tilt.BoundedBenchmarkTiltError, match=message):
            tilt.build_benchmark_tilt(caps, scores, mapping)


def test_membership_sector_mapping_is_exhaustive_and_one_to_one():
    value = _input()
    caps = {
        item.security_id: Decimal(index + 1)
        for index, item in enumerate(value.memberships)
    }

    mapping = tilt.sector_map_from_memberships(caps, value.memberships)

    assert mapping == {
        security_id: "sector-technology" for security_id in sorted(caps)
    }
    with pytest.raises(
        tilt.BoundedBenchmarkTiltError,
        match="membership mapping is not exhaustive",
    ):
        tilt.sector_map_from_memberships(caps, value.memberships[:-1])
    with pytest.raises(
        tilt.BoundedBenchmarkTiltError,
        match="membership mapping is not one-to-one",
    ):
        tilt.sector_map_from_memberships(
            caps, (*value.memberships[:-1], value.memberships[0])
        )


def test_tilt_census_binds_enabled_underfilled_and_zero_enabled_minima():
    enabled_caps, enabled_scores = _tilt_case(20, 20)
    underfilled_caps, underfilled_scores = _tilt_case(19, 20)
    enabled = tilt.build_benchmark_tilt(
        enabled_caps, enabled_scores, _sector_map(enabled_caps)
    )
    underfilled = tilt.build_benchmark_tilt(
        underfilled_caps,
        underfilled_scores,
        _sector_map(underfilled_caps),
    )
    census = tilt.TiltCensus()
    census.observe(enabled)
    census.observe(underfilled)

    aggregate = census.aggregates()

    assert aggregate["decision_session_count"] == 2
    assert aggregate["tilt_enabled_decision_count"] == 1
    assert aggregate["tilt_underfilled_decision_count"] == 1
    assert aggregate["minimum_tilted_name_count_when_enabled"] >= 40
    assert Decimal(aggregate["maximum_one_way_active_share"]) <= Decimal(
        "0.049"
    )
    assert aggregate["minimum_point_in_time_sector_count"] == 2
    assert aggregate["sector_mapping_exhaustive"] is True
    assert aggregate["sector_neutrality_exact"] is True
    assert aggregate["sector_neutrality_scope"] == "frozen_target"
    assert aggregate["maximum_absolute_sector_active_weight"] == "0"
    only_underfilled = tilt.TiltCensus()
    only_underfilled.observe(underfilled)
    underfilled_aggregate = only_underfilled.aggregates()
    assert underfilled_aggregate["minimum_tilted_name_count_when_enabled"] == 0
    assert underfilled_aggregate["maximum_one_way_active_share"] == "0"
    assert (
        underfilled_aggregate[
            "minimum_weight_ratio_to_benchmark_when_enabled"
        ]
        == "0"
    )


def test_executable_tilt_target_never_redistributes_missing_or_locked_budget():
    caps, scores = _tilt_case(20, 20)
    sectors = _sector_map(caps)
    construction = tilt.build_benchmark_tilt(
        caps, scores, sectors
    )
    desired = tuple(construction.selected_weights)
    locked_id = desired[0]
    missing_id = desired[1]
    locked = {
        locked_id: construction.selected_weights[locked_id]
    }
    tradable = tuple(
        security_id
        for security_id in desired
        if security_id not in (locked_id, missing_id)
    )

    execution = tilt.executable_selected_target(
        construction.selected_weights,
        sectors,
        desired,
        tradable,
        locked,
    )
    targets = execution.weights

    assert targets[locked_id] == construction.selected_weights[locked_id]
    assert missing_id not in targets
    with localcontext(base._context()):
        expected_executed_gross = +(
            Decimal("0.98") - construction.selected_weights[missing_id]
        )
    assert base._stable_sum(targets.values()) == expected_executed_gross
    assert execution.locked_sector_over_target_count == 0
    assert execution.sector_target_underfill_count == 1
    assert all(
        targets[security_id] == construction.selected_weights[security_id]
        for security_id in tradable
    )
    over_target_lock = {locked_id: Decimal("0.99")}
    over_target = tilt.executable_selected_target(
        construction.selected_weights,
        sectors,
        desired,
        tuple(item for item in desired if item != locked_id),
        over_target_lock,
    )
    assert over_target.weights[locked_id] == Decimal("0.99")
    assert over_target.locked_sector_over_target_count == 1
    blocked_sector = sectors[locked_id]
    underfilled = tilt.executable_selected_target(
        construction.selected_weights,
        sectors,
        desired,
        tuple(
            security_id for security_id in desired
            if sectors[security_id] != blocked_sector
        ),
        {},
    )
    assert underfilled.locked_sector_over_target_count == 0
    assert underfilled.sector_target_underfill_count == 1


def test_execution_counters_survive_exact_sector_gross_cancellation():
    caps, scores = _tilt_case(20, 20)
    sectors = _sector_map(caps)
    construction = tilt.build_benchmark_tilt(caps, scores, sectors)
    desired = tuple(construction.selected_weights)
    locked_id = desired[0]
    locked_sector = sectors[locked_id]
    missing_id = next(
        security_id
        for security_id in desired
        if security_id != locked_id
        and sectors[security_id] == locked_sector
    )
    with localcontext(base._context()):
        cancellation_weight = +(
            construction.selected_weights[locked_id]
            + construction.selected_weights[missing_id]
        )
    locked = {locked_id: cancellation_weight}
    tradable = tuple(
        security_id
        for security_id in desired
        if security_id not in (locked_id, missing_id)
    )

    execution = tilt.executable_selected_target(
        construction.selected_weights,
        sectors,
        desired,
        tradable,
        locked,
    )

    assert base._stable_sum(execution.weights.values()) == Decimal("0.98")
    assert execution.weights[locked_id] == locked[locked_id]
    assert missing_id not in execution.weights
    assert execution.locked_sector_over_target_count == 1
    assert execution.sector_target_underfill_count == 1


def test_40_name_missing_price_reproduction_keeps_frozen_execution_bounds():
    caps, scores = _tilt_case(20, 20)
    sectors = _sector_map(caps)
    construction = tilt.build_benchmark_tilt(caps, scores, sectors)
    desired = tuple(construction.selected_weights)
    tradable = (
        "negative-001",
        "positive-008",
        "positive-013",
        "positive-017",
    )
    selected_execution = tilt.executable_selected_target(
        construction.selected_weights,
        sectors,
        desired,
        tradable,
        {},
    )
    matched_execution = tilt.executable_selected_target(
        construction.benchmark_weights,
        sectors,
        desired,
        tradable,
        {},
    )
    reproduced_id = "negative-001"
    reproduced_sector = sectors[reproduced_id]
    sector_members = tuple(
        security_id
        for security_id in desired
        if sectors[security_id] == reproduced_sector
    )
    tradable_sector_members = tuple(
        security_id
        for security_id in tradable
        if sectors[security_id] == reproduced_sector
    )
    with localcontext(base._context()):
        old_selected = +(
            base._stable_sum(
                construction.selected_weights[security_id]
                for security_id in sector_members
            )
            * construction.selected_weights[reproduced_id]
            / base._stable_sum(
                construction.selected_weights[security_id]
                for security_id in tradable_sector_members
            )
        )
        old_matched = +(
            base._stable_sum(
                construction.benchmark_weights[security_id]
                for security_id in sector_members
            )
            * construction.benchmark_weights[reproduced_id]
            / base._stable_sum(
                construction.benchmark_weights[security_id]
                for security_id in tradable_sector_members
            )
        )
        old_relative_ratio = +(old_selected / old_matched)
        executed_active_share = +(
            base._stable_sum(
                abs(
                    selected_execution.weights[security_id]
                    - matched_execution.weights[security_id]
                )
                for security_id in tradable
            )
            / Decimal(2)
        )
        executed_ratios = tuple(
            +(
                selected_execution.weights[security_id]
                / matched_execution.weights[security_id]
            )
            for security_id in tradable
        )

    assert old_relative_ratio < Decimal("0.8")
    assert all(
        selected_execution.weights[security_id]
        == construction.selected_weights[security_id]
        and matched_execution.weights[security_id]
        == construction.benchmark_weights[security_id]
        for security_id in tradable
    )
    assert Decimal("0.8") <= min(executed_ratios)
    assert max(executed_ratios) <= Decimal("1.2")
    assert executed_active_share <= Decimal("0.049")
    assert selected_execution.locked_sector_over_target_count == 0
    assert selected_execution.sector_target_underfill_count == 2
    assert matched_execution.locked_sector_over_target_count == 0
    assert matched_execution.sector_target_underfill_count == 2


def test_v3_matched_comparator_stays_exact_cap_weighted_and_score_independent():
    runtime = _runtime(_input())
    runtime._price = lambda _security_id, _position: Decimal(100)
    caps, scores = _tilt_case(20, 20)
    sectors = _sector_map(caps)
    first = tilt.build_benchmark_tilt(caps, scores, sectors)
    reversed_scores = {
        security_id: -score for security_id, score in scores.items()
    }
    second = tilt.build_benchmark_tilt(caps, reversed_scores, sectors)
    desired = tuple(first.selected_weights)
    first_decision = subject._Decision(
        selected=desired,
        eligible=desired,
        market_caps=caps,
        selected_weights=first.selected_weights,
        benchmark_weights=first.benchmark_weights,
        sector_by_security_id=sectors,
    )
    second_decision = subject._Decision(
        selected=desired,
        eligible=desired,
        market_caps=caps,
        selected_weights=second.selected_weights,
        benchmark_weights=second.benchmark_weights,
        sector_by_security_id=sectors,
    )

    first_matched = runtime._targets(
        subject._Account("matched"), first_decision, desired, 0, {}
    )
    second_matched = runtime._targets(
        subject._Account("matched"), second_decision, desired, 0, {}
    )
    first_selected = runtime._targets(
        subject._Account("selected"), first_decision, desired, 0, {}
    )

    assert first_matched == first.benchmark_weights
    assert second_matched == first_matched
    assert first_selected == first.selected_weights
    assert first_selected != first_matched


def test_v3_runtime_counts_sector_execution_exceptions():
    runtime = _runtime(_input())
    caps, scores = _tilt_case(20, 20)
    sectors = _sector_map(caps)
    construction = tilt.build_benchmark_tilt(caps, scores, sectors)
    desired = tuple(construction.selected_weights)
    decision = subject._Decision(
        selected=desired,
        eligible=desired,
        market_caps=caps,
        selected_weights=construction.selected_weights,
        benchmark_weights=construction.benchmark_weights,
        sector_by_security_id=sectors,
    )
    locked_id = desired[0]
    runtime._price = lambda _security_id, _position: Decimal(100)
    locked_account = subject._Account("selected")

    runtime._targets(
        locked_account,
        decision,
        desired,
        0,
        {locked_id: Decimal("0.99")},
    )

    assert locked_account.locked_sector_over_target_count == 1
    assert locked_account.sector_target_underfill_count == 0
    locked_aggregate = tilt.account_aggregates(
        locked_account, 1, sector_neutral=True
    )
    assert locked_aggregate["locked_sector_over_target_count"] == 1
    blocked_sector = sectors[locked_id]
    runtime._price = lambda security_id, _position: (
        None if sectors[security_id] == blocked_sector else Decimal(100)
    )
    missing_account = subject._Account("selected")

    runtime._targets(
        missing_account, decision, desired, 0, {}
    )

    assert missing_account.locked_sector_over_target_count == 0
    assert missing_account.sector_target_underfill_count == 1


def test_benchmark_binding_is_order_invariant_and_decimal_canonical():
    sessions = (
        "2021-01-05",
        "2021-01-06",
        "2021-01-07",
        "2021-01-08",
    )
    observations = tuple(
        zip(
            sessions,
            (
                Decimal("100"),
                Decimal("110"),
                Decimal("121"),
                Decimal("133.1"),
            ),
            strict=True,
        )
    )
    canonical_equivalents = tuple(
        zip(
            sessions,
            (
                Decimal("1E2"),
                Decimal("110.0"),
                Decimal("121.00"),
                Decimal("133.100"),
            ),
            strict=True,
        )
    )

    first = tilt.build_benchmark_series_binding(
        observations,
        sessions,
        logical_benchmark_id="SPY",
    )
    reversed_input = tilt.build_benchmark_series_binding(
        tuple(reversed(observations)),
        sessions,
        logical_benchmark_id="SPY",
    )
    equivalent = tilt.build_benchmark_series_binding(
        canonical_equivalents,
        sessions,
        logical_benchmark_id="SPY",
    )

    assert first == reversed_input == equivalent
    assert first.observation_count == 4
    assert first.return_interval_count == 3
    assert first.first_used_session == sessions[0]
    assert first.last_used_session == sessions[-1]
    assert set(first.summary_fields()) == tilt.BENCHMARK_SERIES_META_FIELDS


def test_benchmark_raw_and_scale_invariant_path_digests_bind_distinct_domains():
    sessions = (
        "2021-01-05",
        "2021-01-06",
        "2021-01-07",
        "2021-01-08",
    )
    values = (
        Decimal("100"),
        Decimal("110"),
        Decimal("121"),
        Decimal("133.1"),
    )

    def binding(bound_sessions, bound_values):
        return tilt.build_benchmark_series_binding(
            tuple(zip(bound_sessions, bound_values, strict=True)),
            bound_sessions,
            logical_benchmark_id="SPY",
        )

    original = binding(sessions, values)
    rescaled = binding(
        sessions, tuple(value * Decimal(3) for value in values)
    )
    interior_changed = binding(
        sessions,
        (values[0], Decimal("112"), values[2], values[3]),
    )
    changed_sessions = (
        sessions[0],
        sessions[1],
        "2021-01-07a",
        sessions[3],
    )
    session_changed = binding(changed_sessions, values)

    assert original.raw_observation_sha256 != rescaled.raw_observation_sha256
    assert original.return_path_sha256 == rescaled.return_path_sha256
    assert (
        original.raw_observation_sha256
        != interior_changed.raw_observation_sha256
    )
    assert original.return_path_sha256 != interior_changed.return_path_sha256
    assert original.raw_observation_sha256 != session_changed.raw_observation_sha256
    assert original.return_path_sha256 != session_changed.return_path_sha256


def test_benchmark_binding_refuses_missing_duplicate_or_changed_used_sessions():
    sessions = ("2021-01-05", "2021-01-06", "2021-01-07")
    observations = tuple(
        (session, Decimal(index + 100))
        for index, session in enumerate(sessions)
    )

    with pytest.raises(
        tilt.BoundedBenchmarkTiltError,
        match="incomplete or changed",
    ):
        tilt.build_benchmark_series_binding(
            observations[:-1], sessions, logical_benchmark_id="SPY"
        )
    with pytest.raises(
        tilt.BoundedBenchmarkTiltError,
        match="duplicated",
    ):
        tilt.build_benchmark_series_binding(
            (observations[0], observations[0], observations[2]),
            sessions,
            logical_benchmark_id="SPY",
        )
    with pytest.raises(
        tilt.BoundedBenchmarkTiltError,
        match="incomplete or changed",
    ):
        tilt.build_benchmark_series_binding(
            (
                observations[0],
                ("2021-01-06a", observations[1][1]),
                observations[2],
            ),
            sessions,
            logical_benchmark_id="SPY",
        )


def test_v3_summary_binds_only_used_benchmark_window_and_keeps_prices_private():
    value = _input()
    profile_id = subject.QQQ_2021_2025_V3_PROFILE_ID
    baseline_runtime = _complete(value, profile_id=profile_id)
    baseline = baseline_runtime.aggregate_summary()
    profile = subject.require_profile(profile_id)
    end_position = value.session_axis.index(profile["evaluation_end_session"])
    h60_session = value.session_axis[end_position + max(base.HORIZONS)]
    changed_runtime = _complete(
        value,
        profile_id=profile_id,
        price_overrides={
            (
                value.benchmark_security_id,
                profile["evaluation_start_session"],
            ): Decimal("200"),
            (value.benchmark_security_id, h60_session): Decimal("300"),
        },
    )
    changed = changed_runtime.aggregate_summary()
    binding_fields = tilt.BENCHMARK_SERIES_META_FIELDS

    assert baseline["benchmark_logical_id"] == "SPY"
    assert baseline["benchmark_history_normalization_mode"] == "total_return"
    assert baseline["benchmark_history_observation"] == "session_open"
    assert baseline["benchmark_first_used_session"] == "2021-01-05"
    assert baseline["benchmark_last_used_session"] == "2025-12-31"
    assert baseline["benchmark_observation_count"] == 1_254
    assert baseline["benchmark_return_interval_count"] == 1_253
    assert {
        field: baseline[field] for field in binding_fields
    } == {
        field: changed[field] for field in binding_fields
    }
    assert baseline["summary_sha256"] == changed["summary_sha256"]
    assert baseline["raw_price_rows_in_summary"] is False
    assert baseline["tilt_aggregates"]["decision_session_count"] == 261
    for name in ("selected_aggregates", "matched_aggregates"):
        assert baseline[name]["locked_sector_over_target_count"] == 0
        assert baseline[name]["sector_target_underfill_count"] == 0
    assert (
        baseline["tilt_aggregates"]["tilt_enabled_decision_count"]
        + baseline["tilt_aggregates"]["tilt_underfilled_decision_count"]
        == 261
    )
    statistics = baseline_runtime.custom_summary_statistics()
    assert len(statistics) == 8
    assert tuple(statistics) == subject.expected_custom_summary_statistic_names(
        profile_id
    )
    wire_meta = json.loads(statistics[subject.META_STATISTIC_NAME])
    assert binding_fields.issubset(wire_meta)
    assert "benchmark_first_adjusted_open" not in wire_meta
    assert "benchmark_last_adjusted_open" not in wire_meta


def test_decision_schedule_and_history_request_bind_each_fixed_window():
    value = _input()
    for profile_id in subject.PROFILE_IDS:
        profile = subject.require_profile(profile_id)
        decisions = subject.decision_sessions_for_input(value, profile_id)
        assert len(decisions) == profile["expected_decision_session_count"]
        runtime = _runtime(value, profile_id=profile_id)
        assert len(runtime._evaluation_positions) == profile["expected_session_count"]
        request = runtime._history_request(0)
        assert request.start_session == profile["evaluation_start_session"]
        expected_end = value.session_axis[
            value.session_axis.index(profile["evaluation_end_session"])
            + max(base.HORIZONS)
        ]
        assert request.end_session == expected_end


@pytest.mark.parametrize(
    ("replacement", "message"),
    (
        (None, "must be an exact dict"),
        (Decimal(0), "positive finite Decimal"),
        (Decimal("NaN"), "positive finite Decimal"),
        (Decimal("Infinity"), "positive finite Decimal"),
        (Decimal("1e1000"), "positive finite Decimal"),
        (1.0, "positive finite Decimal"),
    ),
)
def test_market_cap_map_refuses_wrong_container_or_value(replacement, message):
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    caps = _caps(value, profile_id)
    if replacement is None:
        caps = None
    else:
        first_session = min(caps)
        caps[first_session]["perm-security-00"] = replacement
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match=message,
    ):
        _runtime(value, profile_id=profile_id, caps=caps)


def test_market_cap_map_requires_every_decision_and_input_security_ids():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    caps = _caps(value, profile_id)
    caps.pop(min(caps))
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="sessions are not exhaustive",
    ):
        _runtime(value, profile_id=profile_id, caps=caps)
    caps = _caps(value, profile_id)
    caps[min(caps)]["not-an-input-security"] = Decimal(1)
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="escaped input securities",
    ):
        _runtime(value, profile_id=profile_id, caps=caps)


def test_exact_r055_intersection_precedes_ranking_and_caller_mutation():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    eligible = tuple(f"perm-security-{index:02d}" for index in range(9))
    caps = _caps(value, profile_id, eligible)
    runtime = _runtime(value, profile_id=profile_id, caps=caps)
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    caps[first].clear()
    position = value.session_axis.index(first)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        f"perm-security-{index:02d}": Decimal(index)
        for index in range(20)
    }
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    decision = runtime._decisions[first]
    assert decision.eligible == eligible
    assert decision.selected == ("perm-security-08",)


def test_runtime_reuses_r055_state_scoring_without_overriding_it():
    assert issubclass(
        subject.MarketCapStockPortfolioEvaluationRuntime,
        base.PreliminaryRatingEvaluationRuntime,
    )
    assert (
        subject.MarketCapStockPortfolioEvaluationRuntime._score_cross_section
        is base.PreliminaryRatingEvaluationRuntime._score_cross_section
    )
    assert (
        subject.MarketCapStockPortfolioEvaluationRuntime._apply_contribution
        is base.PreliminaryRatingEvaluationRuntime._apply_contribution
    )
    assert subject.PRIMARY_SOURCE_VIEW_ID == base.SOURCE_VIEW_IDS[1]
    assert subject.PRIMARY_SCORE_ARM == "firm_specific"


def test_v3_runtime_uses_membership_sectors_and_refuses_mapping_gaps():
    value = _input(40, sector_count=2)
    profile_id = subject.QQQ_2021_2025_V3_PROFILE_ID
    runtime = _runtime(value, profile_id=profile_id)
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    position = value.session_axis.index(first)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        f"perm-security-{index:02d}": Decimal(
            index - 20 if index < 20 else index - 19
        )
        for index in range(40)
    }

    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )

    decision = runtime._decisions[first]
    assert decision.sector_by_security_id == {
        item.security_id: item.sector_id for item in value.memberships
    }
    for sector_id in ("sector-00", "sector-01"):
        members = tuple(
            security_id
            for security_id in decision.selected
            if decision.sector_by_security_id[security_id] == sector_id
        )
        assert base._stable_sum(
            decision.selected_weights[security_id]
            for security_id in members
        ) == base._stable_sum(
            decision.benchmark_weights[security_id]
            for security_id in members
        )
    aggregate = runtime._tilt_census.aggregates()
    assert aggregate["tilt_enabled_decision_count"] == 1
    assert aggregate["minimum_point_in_time_sector_count"] == 2
    assert aggregate["maximum_absolute_sector_active_weight"] == "0"

    refused = _runtime(value, profile_id=profile_id)
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="membership mapping is not exhaustive",
    ):
        refused._after_score_cross_section(
            position,
            value.memberships[:-1],
            {axis: scores},
            {axis: 0},
        )


def test_small_universe_selected_and_matched_books_each_reach_exact_98_percent():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    eligible = tuple(f"perm-security-{index:02d}" for index in range(9))
    runtime = _runtime(
        value,
        profile_id=profile_id,
        caps=_caps(value, profile_id, eligible),
    )
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    position = value.session_axis.index(first)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        security_id: Decimal(index)
        for index, security_id in enumerate(eligible)
    }
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    decision = runtime._decisions[first]
    runtime._price = lambda _security_id, _position: Decimal(100)
    selected_account = subject._Account("selected")
    matched_account = subject._Account("matched")
    selected = runtime._targets(
        selected_account,
        decision,
        decision.selected,
        position + 1,
        {},
    )
    matched = runtime._targets(
        matched_account,
        decision,
        decision.eligible,
        position + 1,
        {},
    )
    assert selected == {"perm-security-08": Decimal("0.98")}
    assert base._stable_sum(matched.values()) == Decimal("0.98")
    assert matched["perm-security-08"] / matched["perm-security-00"] == 9


def test_missing_entry_is_counted_and_remaining_caps_renormalize_to_target():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    eligible = tuple(f"perm-security-{index:02d}" for index in range(20))
    runtime = _runtime(value, profile_id=profile_id)
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    position = value.session_axis.index(first)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        security_id: Decimal(index)
        for index, security_id in enumerate(eligible)
    }
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    decision = runtime._decisions[first]
    runtime._price = lambda security_id, _position: (
        None if security_id == "perm-security-19" else Decimal(100)
    )
    account = subject._Account("selected")
    targets = runtime._targets(
        account,
        decision,
        decision.selected,
        position + 1,
        {},
    )
    assert targets == {"perm-security-18": Decimal("0.98")}
    assert account.entry_price_refusal_count == 1


def test_selected_and_matched_targets_are_market_cap_proportional():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    runtime = _runtime(value, profile_id=profile_id)
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    position = value.session_axis.index(first)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        f"perm-security-{index:02d}": Decimal(index)
        for index in range(20)
    }
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    decision = runtime._decisions[first]
    runtime._price = lambda _security_id, _position: Decimal(100)
    selected = runtime._targets(
        subject._Account("selected"),
        decision,
        decision.selected,
        position + 1,
        {},
    )
    matched = runtime._targets(
        subject._Account("matched"),
        decision,
        decision.eligible,
        position + 1,
        {},
    )
    assert base._stable_sum(selected.values()) == Decimal("0.98")
    assert selected["perm-security-19"] / selected["perm-security-18"] == (
        Decimal(20) / Decimal(19)
    )
    assert matched["perm-security-19"] / matched["perm-security-00"] == 20


def test_stale_selected_holdings_preserve_the_fifty_name_cap():
    runtime = _runtime(_input())
    runtime._price = lambda _security_id, _position: Decimal(100)
    desired = tuple(f"candidate-{index:02d}" for index in range(50))
    decision = subject._Decision(
        selected=desired,
        eligible=desired,
        market_caps={security_id: Decimal(1) for security_id in desired},
    )
    targets = runtime._targets(
        subject._Account("selected"),
        decision,
        desired,
        0,
        {"stale-security": Decimal("0.01")},
    )
    assert len(targets) == subject.MAXIMUM_HOLDINGS
    assert "candidate-49" not in targets
    assert base._stable_sum(targets.values()) == Decimal("0.98")


def test_complete_result_has_four_costs_full_exposure_and_concentration_metrics():
    runtime = _complete(_input())
    summary = runtime.aggregate_summary()
    assert summary["summary_sha256"] == (
        "9ff45344ba9998999ffb9812574c908d3d764cd481313015507bc1171342d9cb"
    )
    assert summary["r055_signal_rule_changed"] is False
    assert summary["decision_session_count"] == 261
    assert summary["portfolio_return_session_count"] == 1_254
    assert summary["mean_eligible_score_count"] == "20"
    assert summary["mean_selected_name_count"] == "2"
    for name in ("selected_aggregates", "matched_aggregates"):
        aggregate = summary[name]
        assert aggregate["rebalance_execution_count"] == 261
        assert aggregate["full_target_execution_count"] == 261
        assert aggregate["underfilled_target_execution_count"] == 0
        assert Decimal(aggregate["mean_executed_gross_exposure"]) == Decimal(
            "0.98"
        )
        assert Decimal(aggregate["minimum_executed_gross_exposure"]) == Decimal(
            "0.98"
        )
        assert Decimal(aggregate["maximum_executed_gross_exposure"]) == Decimal(
            "0.98"
        )
        assert Decimal(aggregate["mean_invested_weight_hhi"]) > 0
        assert Decimal(aggregate["mean_effective_holding_count"]) >= 1
    assert [
        cell["cost_bps_per_side"] for cell in summary["portfolio_cells"]
    ] == [0, 5, 10, 20]
    returns = [
        Decimal(cell["cumulative_return"])
        for cell in summary["portfolio_cells"]
    ]
    assert returns == [
        Decimal(0),
        Decimal("-0.00049"),
        Decimal("-0.00098"),
        Decimal("-0.00196"),
    ]
    statistics = runtime.custom_summary_statistics()
    expected_names = (
        "ARV2_STOCK_PORTFOLIO_COST_0",
        "ARV2_STOCK_PORTFOLIO_COST_10",
        "ARV2_STOCK_PORTFOLIO_COST_20",
        "ARV2_STOCK_PORTFOLIO_COST_5",
        subject.MATCHED_AGGREGATES_STATISTIC_NAME,
        subject.META_STATISTIC_NAME,
        subject.SELECTED_AGGREGATES_STATISTIC_NAME,
    )
    assert tuple(statistics) == expected_names
    assert subject.expected_custom_summary_statistic_names(
        subject.QQQ_2021_2025_PROFILE_ID
    ) == expected_names
    assert all(len(value) <= 3_072 for value in statistics.values())

    wire_summary = json.loads(statistics[subject.META_STATISTIC_NAME])
    profile_id = wire_summary.pop("profile_id")
    profile_sha256 = wire_summary.pop("profile_sha256")
    wire_summary["profile"] = subject.require_profile(profile_id)
    assert wire_summary["profile"]["profile_sha256"] == profile_sha256
    wire_summary["selected_aggregates"] = json.loads(
        statistics[subject.SELECTED_AGGREGATES_STATISTIC_NAME]
    )
    wire_summary["matched_aggregates"] = json.loads(
        statistics[subject.MATCHED_AGGREGATES_STATISTIC_NAME]
    )
    wire_summary["portfolio_cells"] = [
        json.loads(statistics["ARV2_STOCK_PORTFOLIO_COST_" + str(cost)])
        for cost in subject.COST_BPS_SCENARIOS
    ]
    assert wire_summary == summary
    assert all(cell["leverage"] is False for cell in summary["portfolio_cells"])


def test_v2_fixture_result_and_seven_statistic_shape_are_unchanged():
    runtime = _complete(
        _input(), profile_id=subject.QQQ_2021_2025_V2_PROFILE_ID
    )

    summary = runtime.aggregate_summary()
    statistics = runtime.custom_summary_statistics()

    assert summary["summary_sha256"] == (
        "c733a50c482d35b65df319291e48920fd5ce68dff72096a87d802a5b307905cf"
    )
    assert tuple(statistics) == subject.expected_custom_summary_statistic_names(
        subject.QQQ_2021_2025_V2_PROFILE_ID
    )
    assert len(statistics) == 7
    assert "tilt_aggregates" not in summary
    assert not tilt.BENCHMARK_SERIES_META_FIELDS.intersection(summary)


def test_first_decision_executes_at_next_open_not_same_open():
    runtime = _complete(_input(), opening_jump=True)
    zero_cost = runtime.aggregate_summary()["portfolio_cells"][0]
    assert zero_cost["cost_bps_per_side"] == 0
    assert zero_cost["cumulative_return"] == "0"
    assert zero_cost["matched_eligible_stock_cumulative_return"] == "0"


def test_missing_eligibility_exit_uses_symmetric_zero_recovery():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    decisions = subject.decision_sessions_for_input(value, profile_id)
    caps = _caps(value, profile_id)
    for session in decisions[1:]:
        caps[session].pop("perm-security-19")
    exit_position = value.session_axis.index(decisions[1]) + 1
    exit_session = value.session_axis[exit_position]
    runtime = _complete(
        value,
        caps=caps,
        omissions=frozenset({("perm-security-19", exit_session)}),
    )
    summary = runtime.aggregate_summary()
    assert summary["selected_aggregates"][
        "eligibility_exit_zero_recovery_count"
    ] == 1
    assert summary["matched_aggregates"][
        "eligibility_exit_zero_recovery_count"
    ] == 1
    assert summary["portfolio_cells"][0]["status"] == (
        "PRELIMINARY_DESCRIPTIVE_ZERO_RECOVERY_SENSITIVITY"
    )


def test_custom_summary_refuses_oversized_split_account_fragment(monkeypatch):
    runtime = _complete(_input())
    summary = runtime.aggregate_summary()
    summary["selected_aggregates"]["average_holding_count"] = "1" * 4_097
    monkeypatch.setattr(runtime, "aggregate_summary", lambda: summary)

    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="market-cap stock custom summary exceeded compact bound",
    ):
        runtime.custom_summary_statistics()


def test_missing_price_inside_eligibility_defers_only_stale_holding():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    decisions = subject.decision_sessions_for_input(value, profile_id)
    stale_position = value.session_axis.index(decisions[1]) + 1
    stale_session = value.session_axis[stale_position]
    runtime = _complete(
        value,
        omissions=frozenset({("perm-security-19", stale_session)}),
    )
    summary = runtime.aggregate_summary()
    for name in ("selected_aggregates", "matched_aggregates"):
        assert summary[name]["stale_mark_session_count"] == 1
        assert summary[name]["partial_rebalance_decision_count"] == 1
        assert summary[name]["eligibility_exit_zero_recovery_count"] == 0


def test_module_is_pure_and_does_not_import_old_giant_evaluator():
    source = open(subject.__file__, encoding="utf-8").read()
    assert "accepted_risk_stock_portfolio_evaluator" not in source
    for forbidden in (
        "requests",
        "urllib",
        "subprocess",
        "socket",
        "os.environ",
    ):
        assert forbidden not in source


def test_locked_gross_above_target_assigns_no_budget_and_never_goes_short():
    """ARV2R93: locked drifted weight above the target must not create negative targets."""

    runtime = _runtime(_input())
    runtime._price = lambda _security_id, _position: Decimal(100)
    desired = ("candidate-00", "candidate-01")
    decision = subject._Decision(
        selected=desired,
        eligible=desired,
        market_caps={security_id: Decimal(1) for security_id in desired},
    )
    locked = {"stale-a": Decimal("0.60"), "stale-b": Decimal("0.50")}

    targets = runtime._targets(
        subject._Account("selected"), decision, desired, 0, locked
    )

    assert targets == locked
    assert all(weight > 0 for weight in targets.values())
