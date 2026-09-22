import dataclasses
from decimal import Decimal, localcontext

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate as subject,
)


def _rows(
    universe_id,
    *,
    count=20,
    positive_count=12,
    reported_weight=None,
    missing_names=frozenset(),
    missing_caps=frozenset(),
    shared_security_id=None,
):
    weight = (
        Decimal(1) / Decimal(count)
        if reported_weight is None
        else reported_weight
    )
    result = []
    for index in range(count):
        security_id = f"sid-{universe_id}-{index:03d}"
        if index == 0 and shared_security_id is not None:
            security_id = shared_security_id
        result.append(
            subject.UniverseConstituent(
                reported_weight=weight,
                security_id=security_id,
                security_name=(
                    None
                    if index in missing_names
                    else f"{universe_id} Company {index:03d}"
                ),
                pit_market_cap=(
                    None
                    if index in missing_caps
                    else Decimal(count - index) * Decimal("1000000")
                ),
                firm_specific_score=(
                    Decimal(positive_count - index)
                    if index < positive_count
                    else Decimal(0)
                ),
            )
        )
    return tuple(result)


def _snapshots(**row_kwargs):
    return tuple(
        subject.UniverseSnapshot(
            universe_id=spec.universe_id,
            etf_ticker=spec.etf_ticker,
            etf_security_id=f"etf-sid-{spec.etf_ticker}",
            constituents=_rows(spec.universe_id, **row_kwargs),
        )
        for spec in subject.UNIVERSE_SPECS
    )


def _replace_snapshot(snapshots, universe_id, rows):
    return tuple(
        dataclasses.replace(snapshot, constituents=rows)
        if snapshot.universe_id == universe_id
        else snapshot
        for snapshot in snapshots
    )


def _slot(budget, count):
    with localcontext() as context:
        context.prec = 96
        return +(budget / Decimal(count))


def _gross(weights):
    return sum((item.weight for item in weights), Decimal(0))


def test_profiles_freeze_source_view_universes_and_distinct_top_counts():
    assert subject.UNIVERSE_IDS == (
        "SPY",
        "QQQ",
        "SOXX",
        "XLV",
        "REMX",
        "XLE",
    )
    assert subject.SOURCE_VIEW_ID == (
        "conservative_censored_current_vintage_non_pristine_pit"
    )
    assert subject.SCORE_ARM_ID == "firm_specific"
    assert subject.TOP10_PRIMARY_PROFILE.slot_count == 10
    assert subject.TOP5_SENSITIVITY_PROFILE.slot_count == 5
    assert subject.TOP10_PRIMARY_PROFILE.profile_id == (
        "arv2-six-universe-gate-top10-primary-v1-600ba939174f67b473451172"
    )
    assert subject.TOP5_SENSITIVITY_PROFILE.profile_id == (
        "arv2-six-universe-gate-top5-sensitivity-v1-16dbb321cf013cfdbf9ea2ec"
    )
    assert (
        subject.TOP10_PRIMARY_PROFILE.profile_sha256
        == "600ba939174f67b47345117279ab88818b479a0ba543d6ac4487f0dad99338f1"
    )
    assert (
        subject.TOP5_SENSITIVITY_PROFILE.profile_sha256
        == "16dbb321cf013cfdbf9ea2ec6af7888db080b293b72d58d027228377b68b8124"
    )
    assert subject.TOP10_PRIMARY_PROFILE != subject.TOP5_SENSITIVITY_PROFILE
    assert sum(subject.SLEEVE_BUDGETS, Decimal(0)) == Decimal("0.98")
    assert len(set(subject.SLEEVE_BUDGETS[:-1])) == 1
    assert subject.SLEEVE_BUDGETS[-1] - subject.SLEEVE_BUDGETS[0] == Decimal(
        "2e-24"
    )
    for profile in subject.PROFILES:
        record = profile.to_record()
        assert record["profile_id"] == profile.profile_id
        assert record["profile_sha256"] == profile.profile_sha256
        assert record["source_view_id"] == subject.SOURCE_VIEW_ID
        assert record["cross_sleeve_redistribution"] is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        subject.TOP10_PRIMARY_PROFILE.slot_count = 9


def test_top10_ranks_positive_scores_then_sid_and_count_matches_by_cap():
    snapshots = _snapshots()
    rows = list(snapshots[0].constituents)
    # The score order differs from cap order and the top-score tie is resolved
    # by stable security id, not caller row order.
    rows[0] = dataclasses.replace(rows[0], firm_specific_score=Decimal(9))
    rows[1] = dataclasses.replace(rows[1], firm_specific_score=Decimal(10))
    rows[2] = dataclasses.replace(rows[2], firm_specific_score=Decimal(10))
    snapshots = _replace_snapshot(snapshots, "SPY", tuple(reversed(rows)))

    result = subject.build_six_universe_construction(
        snapshots,
        subject.TOP10_PRIMARY_PROFILE,
    )
    spy = result.sleeves[0]
    assert spy.signal_security_ids[:3] == (
        "sid-SPY-001",
        "sid-SPY-002",
        "sid-SPY-000",
    )
    assert spy.matched_security_ids == tuple(
        f"sid-SPY-{index:03d}" for index in range(10)
    )
    assert len(spy.signal_security_ids) == len(spy.matched_security_ids) == 10
    assert spy.signal_etf_fallback_weight == 0
    assert spy.matched_etf_fallback_weight == 0


def test_top10_and_top5_profiles_have_fixed_distinct_outputs():
    snapshots = _snapshots(positive_count=12)
    top10 = subject.build_six_universe_construction(
        snapshots,
        subject.TOP10_PRIMARY_PROFILE,
    )
    top5 = subject.build_six_universe_construction(
        snapshots,
        subject.TOP5_SENSITIVITY_PROFILE,
    )
    assert top10.sleeves[0].signal_security_ids == tuple(
        f"sid-SPY-{index:03d}" for index in range(10)
    )
    assert top5.sleeves[0].signal_security_ids == tuple(
        f"sid-SPY-{index:03d}" for index in range(5)
    )
    assert top10.to_record()["construction_sha256"] != top5.to_record()[
        "construction_sha256"
    ]
    assert _gross(top10.signal_weights) == subject.TARGET_GROSS_EXPOSURE
    assert _gross(top5.signal_weights) == subject.TARGET_GROSS_EXPOSURE


def test_five_to_nine_positives_use_slots_and_own_etf_fallback():
    result = subject.build_six_universe_construction(
        _snapshots(positive_count=7),
        subject.TOP10_PRIMARY_PROFILE,
    )
    spy = result.sleeves[0]
    slot = _slot(spy.budget, 10)
    assert len(spy.signal_security_ids) == len(spy.matched_security_ids) == 7
    assert spy.signal_etf_fallback_weight == slot * 3
    assert spy.matched_etf_fallback_weight == slot * 3
    spy_etf = next(
        item for item in result.signal_weights if item.security_id == "etf-sid-SPY"
    )
    assert spy_etf.weight == slot * 3


def test_exactly_five_positives_is_admitted_at_the_frozen_floor():
    result = subject.build_six_universe_construction(
        _snapshots(positive_count=5),
        subject.TOP10_PRIMARY_PROFILE,
    )
    spy = result.sleeves[0]
    slot = _slot(spy.budget, 10)
    assert spy.positive_score_count == subject.MINIMUM_POSITIVE_SCORE_COUNT
    assert len(spy.signal_security_ids) == len(spy.matched_security_ids) == 5
    assert spy.signal_etf_fallback_weight == slot * 5
    assert spy.matched_etf_fallback_weight == slot * 5


def test_fewer_than_five_positives_falls_back_both_roles_to_own_etf():
    result = subject.build_six_universe_construction(
        _snapshots(positive_count=4),
        subject.TOP10_PRIMARY_PROFILE,
    )
    for index, sleeve in enumerate(result.sleeves):
        assert sleeve.coverage.valid is True
        assert sleeve.positive_score_count == 4
        assert sleeve.signal_security_ids == ()
        assert sleeve.matched_security_ids == ()
        assert sleeve.signal_stock_weights == ()
        assert sleeve.matched_stock_weights == ()
        assert sleeve.signal_etf_fallback_weight == subject.SLEEVE_BUDGETS[index]
        assert sleeve.matched_etf_fallback_weight == subject.SLEEVE_BUDGETS[index]
    expected = {
        item.security_id: item.weight for item in result.etf_basket_weights
    }
    assert {item.security_id: item.weight for item in result.signal_weights} == expected
    assert {item.security_id: item.weight for item in result.matched_weights} == expected


@pytest.mark.parametrize(
    ("rows", "reason"),
    (
        (
            _rows("SPY", reported_weight=Decimal("0.04")),
            "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE",
        ),
        (
            _rows("SPY", reported_weight=Decimal("0.06")),
            "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE",
        ),
        (
            _rows("SPY", missing_names=frozenset({0, 1, 2})),
            "SID_NAME_MAPPING_BELOW_MINIMUM",
        ),
        (
            _rows("SPY", missing_caps=frozenset({0})),
            "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM",
        ),
    ),
)
def test_invalid_coverage_falls_back_without_cross_sleeve_redistribution(
    rows,
    reason,
):
    result = subject.build_six_universe_construction(
        _replace_snapshot(_snapshots(), "SPY", rows),
        subject.TOP10_PRIMARY_PROFILE,
    )
    spy = result.sleeves[0]
    qqq = result.sleeves[1]
    assert spy.coverage.valid is False
    assert reason in spy.coverage.refusal_reasons
    assert spy.signal_etf_fallback_weight == spy.budget
    assert spy.matched_etf_fallback_weight == spy.budget
    assert qqq.coverage.valid is True
    assert qqq.signal_etf_fallback_weight == 0
    assert qqq.matched_etf_fallback_weight == 0


def test_coverage_exact_boundaries_are_inclusive():
    rows = list(
        _rows(
            "SPY",
            count=100,
            positive_count=20,
            reported_weight=Decimal("0.00095"),
            missing_names=frozenset(range(90, 100)),
            missing_caps=frozenset({99}),
        )
    )
    rows[:90] = [
        dataclasses.replace(row, reported_weight=Decimal("0.01045"))
        for row in rows[:90]
    ]
    result = subject.build_six_universe_construction(
        _replace_snapshot(_snapshots(), "SPY", tuple(rows)),
        subject.TOP10_PRIMARY_PROFILE,
    )
    coverage = result.sleeves[0].coverage
    assert coverage.total_reported_weight == Decimal("0.95")
    assert coverage.mapping_ratio == Decimal("0.9")
    assert coverage.cap_weight_coverage_ratio == Decimal("0.99")
    assert coverage.valid is True

    upper_rows = _rows(
        "SPY",
        count=20,
        reported_weight=Decimal("0.0525"),
    )
    upper = subject.build_six_universe_construction(
        _replace_snapshot(_snapshots(), "SPY", upper_rows),
        subject.TOP10_PRIMARY_PROFILE,
    )
    assert upper.sleeves[0].coverage.total_reported_weight == Decimal("1.05")
    assert upper.sleeves[0].coverage.valid is True


def test_repeating_coverage_ratio_uses_the_frozen_96_digit_recording_domain():
    ratio = subject._ratio(Decimal(30), Decimal(31))
    assert len(ratio.as_tuple().digits) == subject.DECIMAL_MAXIMUM_DIGITS
    assert ratio.as_tuple().exponent == subject.DECIMAL_MINIMUM_EXPONENT
    assert subject._decimal_text(ratio) == format(ratio, "f")

    with pytest.raises(subject.SixUniverseGateError, match="canonical Decimal"):
        subject._require_decimal(Decimal("1e-97"), "too-small ratio")


def test_cap_weight_coverage_counts_only_mapped_usable_constituents():
    rows = list(
        _rows(
            "SPY",
            count=10,
            positive_count=10,
            reported_weight=Decimal("0.01"),
            missing_names=frozenset({0}),
        )
    )
    rows[0] = dataclasses.replace(rows[0], reported_weight=Decimal("0.91"))
    result = subject.build_six_universe_construction(
        _replace_snapshot(_snapshots(), "SPY", tuple(rows)),
        subject.TOP10_PRIMARY_PROFILE,
    )
    coverage = result.sleeves[0].coverage
    assert coverage.total_reported_weight == Decimal("1")
    assert coverage.mapping_ratio == Decimal("0.9")
    assert coverage.cap_weight_coverage_ratio == Decimal("0.09")
    assert coverage.valid is False
    assert coverage.refusal_reasons == (
        "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM",
    )
    assert result.sleeves[0].signal_security_ids == ()
    assert result.sleeves[0].matched_security_ids == ()


def test_final_signal_and_matched_weights_bind_their_distinct_selected_ids():
    snapshots = _snapshots()
    rows = list(snapshots[0].constituents)
    rows[15] = dataclasses.replace(rows[15], firm_specific_score=Decimal("100"))
    result = subject.build_six_universe_construction(
        _replace_snapshot(snapshots, "SPY", tuple(rows)),
        subject.TOP10_PRIMARY_PROFILE,
    )
    spy = result.sleeves[0]
    assert "sid-SPY-015" in spy.signal_security_ids
    assert "sid-SPY-015" not in spy.matched_security_ids
    assert set(security_id for security_id, _ in spy.signal_stock_weights) == set(
        spy.signal_security_ids
    )
    assert set(security_id for security_id, _ in spy.matched_stock_weights) == set(
        spy.matched_security_ids
    )
    assert "sid-SPY-015" in {
        item.security_id for item in result.signal_weights
    }
    assert "sid-SPY-015" not in {
        item.security_id for item in result.matched_weights
    }


def test_market_cap_comparator_breaks_exact_cap_ties_by_security_id():
    snapshots = _snapshots()
    rows = list(snapshots[0].constituents)
    rows[1] = dataclasses.replace(rows[1], pit_market_cap=rows[0].pit_market_cap)
    result = subject.build_six_universe_construction(
        _replace_snapshot(snapshots, "SPY", tuple(reversed(rows))),
        subject.TOP10_PRIMARY_PROFILE,
    )
    assert result.sleeves[0].matched_security_ids[:2] == (
        "sid-SPY-000",
        "sid-SPY-001",
    )


def test_valid_boundary_excludes_high_score_unmapped_and_uncapped_rows():
    snapshots = _snapshots()
    rows = list(
        _rows(
            "SPY",
            count=200,
            positive_count=20,
            reported_weight=Decimal("0.005"),
            missing_names=frozenset({150}),
            missing_caps=frozenset({151}),
        )
    )
    rows[150] = dataclasses.replace(rows[150], firm_specific_score=Decimal("1000"))
    rows[151] = dataclasses.replace(rows[151], firm_specific_score=Decimal("999"))
    result = subject.build_six_universe_construction(
        _replace_snapshot(snapshots, "SPY", tuple(rows)),
        subject.TOP10_PRIMARY_PROFILE,
    )
    spy = result.sleeves[0]
    assert spy.coverage.valid is True
    assert spy.coverage.mapping_ratio == Decimal("0.995")
    assert spy.coverage.cap_weight_coverage_ratio == Decimal("0.99")
    assert "sid-SPY-150" not in spy.signal_security_ids
    assert "sid-SPY-151" not in spy.signal_security_ids


def test_construction_record_has_exact_inventory_and_golden_digest():
    record = subject.build_six_universe_construction(
        _snapshots(),
        subject.TOP10_PRIMARY_PROFILE,
    ).to_record()
    assert tuple(record) == (
        "schema",
        "profile_id",
        "profile_sha256",
        "sleeves",
        "signal_weights",
        "matched_weights",
        "etf_basket_weights",
        "construction_id",
        "construction_sha256",
    )
    assert tuple(record["sleeves"][0]) == (
        "universe_id",
        "etf_ticker",
        "etf_security_id",
        "budget",
        "coverage",
        "positive_score_count",
        "signal_security_ids",
        "matched_security_ids",
        "signal_stock_weights",
        "matched_stock_weights",
        "signal_etf_fallback_weight",
        "matched_etf_fallback_weight",
    )
    assert tuple(record["signal_weights"][0]) == (
        "security_id",
        "asset_kind",
        "weight",
    )
    assert record["construction_id"] == (
        "arv2-six-universe-construction-af3581ce3ddaf4a79de0bf6d"
    )
    assert record["construction_sha256"] == (
        "af3581ce3ddaf4a79de0bf6d55c21f6dcfbf4e376b6e25ffd211c25511eb9d1f"
    )


def test_duplicate_security_aggregation_caps_stock_and_returns_excess_to_own_etf():
    result = subject.build_six_universe_construction(
        _snapshots(
            positive_count=10,
            shared_security_id="sid-shared-leader",
        ),
        subject.TOP5_SENSITIVITY_PROFILE,
    )
    shared = next(
        item
        for item in result.signal_weights
        if item.security_id == "sid-shared-leader"
    )
    assert shared.asset_kind == "stock"
    assert shared.weight == subject.DIRECT_STOCK_WEIGHT_CAP
    assert all(
        item.weight <= subject.DIRECT_STOCK_WEIGHT_CAP
        for item in result.signal_weights
        if item.asset_kind == "stock"
    )
    # Frozen universe order spends the shared-name cap in SPY, QQQ, SOXX,
    # then returns the first material excess to XLV rather than another stock.
    assert result.sleeves[0].signal_etf_fallback_weight == 0
    assert result.sleeves[1].signal_etf_fallback_weight == 0
    assert result.sleeves[2].signal_etf_fallback_weight == 0
    assert result.sleeves[3].signal_etf_fallback_weight > 0
    for sleeve in result.sleeves:
        assert (
            sum((weight for _, weight in sleeve.signal_stock_weights), Decimal(0))
            + sleeve.signal_etf_fallback_weight
            == sleeve.budget
        )
        assert (
            sum((weight for _, weight in sleeve.matched_stock_weights), Decimal(0))
            + sleeve.matched_etf_fallback_weight
            == sleeve.budget
        )
    assert _gross(result.signal_weights) == subject.TARGET_GROSS_EXPOSURE
    assert _gross(result.matched_weights) == subject.TARGET_GROSS_EXPOSURE


def test_etf_basket_is_actual_frozen_six_etf_equal_budget_comparator():
    result = subject.build_six_universe_construction(
        _snapshots(),
        subject.TOP10_PRIMARY_PROFILE,
    )
    assert tuple(item.security_id for item in result.etf_basket_weights) == tuple(
        f"etf-sid-{ticker}" for ticker in subject.UNIVERSE_IDS
    )
    assert tuple(item.weight for item in result.etf_basket_weights) == (
        subject.SLEEVE_BUDGETS
    )
    assert _gross(result.etf_basket_weights) == subject.TARGET_GROSS_EXPOSURE


def test_snapshot_and_constituent_order_do_not_change_canonical_construction():
    snapshots = _snapshots()
    reversed_rows = tuple(
        dataclasses.replace(
            snapshot,
            constituents=tuple(reversed(snapshot.constituents)),
        )
        for snapshot in reversed(snapshots)
    )
    first = subject.build_six_universe_construction(
        snapshots,
        subject.TOP10_PRIMARY_PROFILE,
    ).to_record()
    second = subject.build_six_universe_construction(
        reversed_rows,
        subject.TOP10_PRIMARY_PROFILE,
    ).to_record()
    assert first == second
    assert first["construction_id"].endswith(first["construction_sha256"][:24])


@pytest.mark.parametrize(
    "bad_row",
    (
        subject.UniverseConstituent(
            0.05,
            "sid-SPY-000",
            "Company",
            Decimal(1),
            Decimal(1),
        ),
        subject.UniverseConstituent(
            Decimal("NaN"),
            "sid-SPY-000",
            "Company",
            Decimal(1),
            Decimal(1),
        ),
        subject.UniverseConstituent(
            Decimal("0.05"),
            "sid-SPY-000",
            "Company",
            Decimal(0),
            Decimal(1),
        ),
        subject.UniverseConstituent(
            Decimal("0.05"),
            "sid-SPY-000",
            "Company",
            Decimal(1),
            Decimal("Infinity"),
        ),
    ),
)
def test_non_decimal_nonfinite_or_nonpositive_inputs_fail_closed(bad_row):
    rows = list(_rows("SPY"))
    rows[0] = bad_row
    with pytest.raises(subject.SixUniverseGateError):
        subject.build_six_universe_construction(
            _replace_snapshot(_snapshots(), "SPY", tuple(rows)),
            subject.TOP10_PRIMARY_PROFILE,
        )


def test_duplicate_member_identity_and_unfrozen_profile_fail_closed():
    rows = list(_rows("SPY"))
    rows[1] = dataclasses.replace(rows[1], security_id=rows[0].security_id)
    with pytest.raises(
        subject.SixUniverseGateError,
        match="security id is duplicated",
    ):
        subject.build_six_universe_construction(
            _replace_snapshot(_snapshots(), "SPY", tuple(rows)),
            subject.TOP10_PRIMARY_PROFILE,
        )

    changed = dataclasses.replace(subject.TOP10_PRIMARY_PROFILE, slot_count=9)
    with pytest.raises(subject.SixUniverseGateError, match="profile is not frozen"):
        subject.build_six_universe_construction(_snapshots(), changed)


def test_six_universe_identity_topology_fails_closed():
    snapshots = _snapshots()
    cases = (
        (snapshots[:-1], "exactly six"),
        (
            snapshots[:-1]
            + (dataclasses.replace(snapshots[-1], universe_id="SPY"),),
            "snapshot is duplicated",
        ),
        (
            (dataclasses.replace(snapshots[0], etf_ticker="IVV"),)
            + snapshots[1:],
            "ETF ticker changed",
        ),
        (
            snapshots[:-1]
            + (
                dataclasses.replace(
                    snapshots[-1],
                    etf_security_id=snapshots[0].etf_security_id,
                ),
            ),
            "ETF security identity is duplicated",
        ),
    )
    for value, message in cases:
        with pytest.raises(subject.SixUniverseGateError, match=message):
            subject.build_six_universe_construction(
                value,
                subject.TOP10_PRIMARY_PROFILE,
            )

    colliding_rows = list(snapshots[0].constituents)
    colliding_rows[0] = dataclasses.replace(
        colliding_rows[0], security_id=snapshots[-1].etf_security_id
    )
    with pytest.raises(subject.SixUniverseGateError, match="identities collide"):
        subject.build_six_universe_construction(
            _replace_snapshot(snapshots, "SPY", tuple(colliding_rows)),
            subject.TOP10_PRIMARY_PROFILE,
        )
