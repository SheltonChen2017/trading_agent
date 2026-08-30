"""Dangerous-direction tests for exact PIT short-ratio acceleration."""
from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.contracts import (
    ReleasePrecision,
    recompute_days_to_cover,
)
from research.short_interest_etf.daily_short_volume import (
    DailyShortSaleVolumeRecord,
    DailyVolumeSemantic,
)
from research.short_interest_etf.dataset import build_vintage, load_synthetic_fixture
from research.short_interest_etf.pit_eligibility import (
    REFUSAL_MISSING_PRIOR,
    load_synthetic_pit_reference,
)
from research.short_interest_etf.stock_acceleration import (
    REFUSAL_INSUFFICIENT_PRIOR_DELTA_HISTORY,
    REFUSAL_PRIOR_DELTA_FEATURE_NOT_AVAILABLE,
    PitStockAccelerationFeature,
    StockAccelerationDisposition,
    StockAccelerationError,
    build_pit_stock_accelerations,
)
from research.short_interest_etf.stock_features import (
    ExactRational,
    StockFeatureError,
    build_pit_stock_raw_features,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "short_interest_etf"
SOURCE_FIXTURE = FIXTURE_ROOT / "official_style_v1.json"
REFERENCE_FIXTURE = FIXTURE_ROOT / "pit_reference_v1.json"


def _contains_float(value) -> bool:
    if type(value) is float:
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _three_cycle_raw_dispositions(
    third_short_shares: int = 1400,
    *,
    stale_middle: bool = False,
    same_open_middle_correction: bool = False,
):
    vintage = load_synthetic_fixture(SOURCE_FIXTURE)
    prior, current = vintage.snapshots
    middle = current
    if stale_middle:
        middle = replace(
            current,
            volume_basis=replace(
                current.volume_basis,
                window_end_date="2024-01-30",
                raw_record_sha256="f" * 64,
            ),
            raw_record_sha256="1" * 64,
        )
    third_release = replace(
        vintage.release_calendar[-1],
        settlement_date="2024-02-15",
        filing_deadline_date="2024-02-22",
        public_release_date="2024-02-29",
        public_release_at="2024-02-29T21:00:00Z",
        precision=ReleasePrecision.EXACT_TIMESTAMP,
        evidence_sha256="a" * 64,
        observed_at="2024-02-29T22:00:00Z",
    )
    third_volume = replace(
        current.volume_basis,
        average_daily_share_volume="140",
        window_start_date="2024-01-17",
        window_end_date="2024-02-15",
        available_at="2024-02-29T20:00:00Z",
        observed_at="2024-02-29T22:00:00Z",
        raw_record_sha256="b" * 64,
    )
    third_denominator = replace(
        current.denominator,
        value="12000",
        effective_date="2024-02-15",
        available_at="2024-02-29T20:00:00Z",
        observed_at="2024-02-29T22:00:00Z",
        raw_record_sha256="c" * 64,
    )
    third = replace(
        current,
        source_record_id="synthetic-si-2024-02-15-r1",
        settlement_date="2024-02-15",
        current_short_shares=third_short_shares,
        previous_settlement_date="2024-01-31",
        previous_short_shares=1200,
        release_calendar_key=third_release.key,
        volume_basis=third_volume,
        reported_days_to_cover="10",
        recomputed_days_to_cover=recompute_days_to_cover(
            third_short_shares,
            "140",
        ),
        denominator=third_denominator,
        revision_published_at="2024-02-29T21:00:00Z",
        observed_at="2024-02-29T22:00:00Z",
        raw_record_sha256="d" * 64,
    )
    snapshots = [prior, middle, third]
    if same_open_middle_correction:
        correction_denominator = replace(
            middle.denominator,
            value="10000",
            available_at="2024-02-29T20:00:00Z",
            observed_at="2024-02-29T22:00:00Z",
            raw_record_sha256="e" * 64,
        )
        middle_correction = replace(
            middle,
            source_record_id="synthetic-si-2024-01-31-r2",
            denominator=correction_denominator,
            revision_id="r2",
            revision_published_at="2024-02-29T21:00:00Z",
            observed_at="2024-02-29T22:00:00Z",
            supersedes_event_id=middle.event_id,
            raw_record_sha256="f" * 64,
        )
        snapshots.insert(2, middle_correction)
    manifest = replace(
        vintage.manifest,
        retrieved_at="2024-03-01T22:00:00Z",
        settlement_end="2024-02-15",
        requested_record_count=len(snapshots),
        input_row_count=len(snapshots),
        accepted_record_count=len(snapshots),
    )
    three_cycle_vintage = build_vintage(
        manifest,
        (*vintage.release_calendar, third_release),
        tuple(snapshots),
    )
    references = load_synthetic_pit_reference(REFERENCE_FIXTURE)
    return build_pit_stock_raw_features(three_cycle_vintage, references)


def _acceleration_dispositions():
    return build_pit_stock_accelerations(_three_cycle_raw_dispositions())


def _completed_acceleration():
    disposition = next(
        item for item in _acceleration_dispositions() if item.feature is not None
    )
    assert disposition.feature is not None
    assert disposition.prior is not None
    assert disposition.prior.feature is not None
    return disposition, disposition.feature


def test_three_cycles_retain_two_warmups_and_exact_negative_acceleration():
    raw = _three_cycle_raw_dispositions()
    results = build_pit_stock_accelerations(raw)

    assert len(results) == len(raw) == 3
    first, second, third = results
    assert first.feature is None
    assert first.prior is None
    assert first.refusal_reasons == (REFUSAL_MISSING_PRIOR,)
    assert first.refusal_reasons == first.current.refusal_reasons
    assert second.feature is None
    assert second.prior == first.current
    assert second.refusal_reasons == (
        REFUSAL_INSUFFICIENT_PRIOR_DELTA_HISTORY,
    )
    assert third.feature is not None
    assert third.refusal_reasons == ()

    feature = third.feature
    assert feature.prior_feature.current_short_ratio == ExactRational(6, 55)
    assert feature.prior_delta_short_ratio == ExactRational(1, 110)
    assert feature.current_feature.current_short_ratio == ExactRational(7, 60)
    assert feature.current_delta_short_ratio == ExactRational(1, 132)
    assert feature.acceleration_short_ratio == ExactRational(-1, 660)


def test_indexed_context_preserves_exact_acceleration_batch_payload_hashes():
    dispositions = _acceleration_dispositions()

    assert [item.refusal_reasons for item in dispositions] == [
        (REFUSAL_MISSING_PRIOR,),
        (REFUSAL_INSUFFICIENT_PRIOR_DELTA_HISTORY,),
        (),
    ]
    assert [item.sha256 for item in dispositions] == [
        "2ed654c211fb30cd02b838433796258a79f3f9f527399410b07a9172f1747608",
        "812011828346781049bc97d79e14f69e6f39273a93cedc8244ee221dfa8a8ee2",
        "04b4e3889653c51957daaea05e031e8d4ef1f68bc64a7591e8d49a7751a33d2a",
    ]


def test_acceleration_payload_hashes_every_exact_fact_without_floats():
    disposition, feature = _completed_acceleration()

    assert feature.sha256 == hash_payload(feature.to_payload())
    assert disposition.sha256 == hash_payload(disposition.to_payload())
    assert not _contains_float(feature.to_payload())
    assert not _contains_float(disposition.to_payload())
    assert set(feature.to_payload()) == {
        "acceleration_short_ratio",
        "current_delta_short_ratio",
        "current_raw_feature_sha256",
        "event_id",
        "preregistration_sha256",
        "previous_settlement_date",
        "prior_delta_short_ratio",
        "prior_event_id",
        "prior_previous_settlement_date",
        "prior_prior_event_id",
        "prior_raw_feature_sha256",
        "reference_bundle_sha256",
        "schema_version",
        "security_id",
        "settlement_date",
        "source_dataset_id",
        "source_vintage_sha256",
    }
    assert set(disposition.to_payload()) == {
        "current",
        "feature",
        "prior",
        "refusal_reasons",
    }


@pytest.mark.parametrize(
    "field_name",
    ["current_raw_feature_sha256", "prior_raw_feature_sha256"],
)
def test_both_raw_feature_hashes_are_load_bearing(field_name):
    _, feature = _completed_acceleration()
    with pytest.raises(StockAccelerationError, match=field_name):
        replace(feature, **{field_name: "a" * 64})


def test_acceleration_recomputes_subtraction_order_and_preserves_negative_sign():
    _, feature = _completed_acceleration()
    with pytest.raises(StockAccelerationError, match="acceleration_short_ratio"):
        replace(feature, acceleration_short_ratio=ExactRational(1, 660))
    with pytest.raises(StockAccelerationError, match="acceleration_short_ratio"):
        replace(feature, acceleration_short_ratio=ExactRational(0, 1))


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("source_dataset_id", "different-source-dataset"),
        ("source_vintage_sha256", "a" * 64),
        ("reference_bundle_sha256", "a" * 64),
        ("preregistration_sha256", "a" * 64),
        ("current_delta_short_ratio", ExactRational(1, 1)),
        ("prior_delta_short_ratio", ExactRational(1, 1)),
        ("event_id", "a" * 64),
        ("prior_event_id", "a" * 64),
        ("prior_prior_event_id", "a" * 64),
        ("security_id", "sec-other"),
        ("settlement_date", "2024-02-16"),
        ("previous_settlement_date", "2024-02-01"),
        ("prior_previous_settlement_date", "2023-12-28"),
    ],
)
def test_acceleration_projections_must_match_the_two_raw_witnesses(
    field_name, replacement
):
    _, feature = _completed_acceleration()
    with pytest.raises(StockAccelerationError, match=field_name):
        replace(feature, **{field_name: replacement})


def test_acceleration_schema_version_is_load_bearing():
    _, feature = _completed_acceleration()
    assert feature.schema_version == "1.0"
    with pytest.raises(StockAccelerationError, match="schema_version"):
        replace(feature, schema_version="0.9")

    class ForgedSchema(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(StockAccelerationError, match="schema_version"):
        replace(feature, schema_version=ForgedSchema("9.9"))


def test_missing_required_prior_event_makes_complete_batch_fail_closed():
    raw = _three_cycle_raw_dispositions()
    with pytest.raises(StockAccelerationError, match="event set is incomplete"):
        build_pit_stock_accelerations(raw[1:])


def test_omitted_terminal_event_makes_complete_batch_fail_closed():
    raw = _three_cycle_raw_dispositions()
    with pytest.raises(StockAccelerationError, match="event set is incomplete"):
        build_pit_stock_accelerations(raw[:-1])


def test_duplicate_event_makes_complete_batch_fail_closed():
    raw = _three_cycle_raw_dispositions()
    with pytest.raises(StockAccelerationError, match="duplicate.*event_id"):
        build_pit_stock_accelerations((*raw, raw[0]))


def test_mixed_vintage_lineage_cannot_enter_one_acceleration_batch():
    raw = _three_cycle_raw_dispositions()
    other_vintage = _three_cycle_raw_dispositions(third_short_shares=1500)

    with pytest.raises(StockAccelerationError, match="mix source_dataset_id"):
        build_pit_stock_accelerations((other_vintage[0], *raw[1:]))


def test_input_reordering_cannot_change_accelerations_or_hashes():
    raw = _three_cycle_raw_dispositions()
    original = build_pit_stock_accelerations(raw)
    reordered = build_pit_stock_accelerations(tuple(reversed(raw)))

    assert reordered == original
    assert [item.sha256 for item in reordered] == [
        item.sha256 for item in original
    ]


def test_warmup_refusal_cannot_be_dropped_or_recast_as_a_feature():
    _, warmup, completed = _acceleration_dispositions()
    with pytest.raises(StockAccelerationError, match="state-specific refusal"):
        replace(warmup, refusal_reasons=())
    with pytest.raises(StockAccelerationError, match="missing prior delta"):
        replace(warmup, feature=completed.feature, refusal_reasons=())


def test_non_history_prior_failure_is_not_mislabeled_as_normal_warmup():
    raw = _three_cycle_raw_dispositions(stale_middle=True)
    results = build_pit_stock_accelerations(raw)
    third = results[-1]

    assert third.current.feature is not None
    assert third.prior is not None
    assert third.prior.feature is None
    assert third.refusal_reasons == (
        REFUSAL_PRIOR_DELTA_FEATURE_NOT_AVAILABLE,
    )


def test_non_ready_raw_disposition_cannot_carry_authenticated_prior_readiness():
    raw = _three_cycle_raw_dispositions(stale_middle=True)
    non_ready = next(
        item
        for item in raw
        if item.readiness.settlement_date == "2024-01-31"
    )
    context = non_ready.source_context
    assert context is not None
    current_snapshot = next(
        item
        for item in context.source_vintage.snapshots
        if item.event_id == non_ready.readiness.event_id
    )
    prior_readiness = next(
        item
        for item in context.readiness_rows
        if item.security_id == current_snapshot.security.security_id
        and item.settlement_date == current_snapshot.previous_settlement_date
    )

    with pytest.raises(
        StockFeatureError,
        match="non-ready source data cannot carry prior_readiness",
    ):
        replace(non_ready, prior_readiness=prior_readiness)


def test_same_next_open_prior_correction_can_feed_current_acceleration():
    raw = _three_cycle_raw_dispositions(
        same_open_middle_correction=True,
    )
    results = build_pit_stock_accelerations(raw)
    third = next(
        item
        for item in results
        if item.current.readiness.settlement_date == "2024-02-15"
    )

    assert third.feature is not None
    assert third.prior is not None
    assert third.prior.feature is not None
    assert third.feature.current_feature.execution_at == (
        third.feature.prior_feature.execution_at
    )
    assert third.feature.current_feature.execution_at == "2024-03-01T14:30:00Z"


def test_older_same_settlement_revision_cannot_replace_authenticated_prior():
    raw = _three_cycle_raw_dispositions(
        same_open_middle_correction=True,
    )
    results = build_pit_stock_accelerations(raw)
    current = next(
        item
        for item in results
        if item.current.readiness.settlement_date == "2024-02-15"
    )
    assert current.feature is not None
    wrong_prior = next(
        item.feature
        for item in raw
        if item.feature is not None
        and item.readiness.settlement_date == "2024-01-31"
        and item.readiness.event_id != current.feature.prior_event_id
    )
    wrong_acceleration = ExactRational.from_fraction(
        current.feature.current_delta_short_ratio.to_fraction()
        - wrong_prior.delta_short_ratio.to_fraction()
    )

    with pytest.raises(
        StockAccelerationError,
        match="current prior_snapshot must equal prior current_snapshot",
    ):
        replace(
            current.feature,
            prior_feature=wrong_prior,
            prior_raw_feature_sha256=wrong_prior.sha256,
            prior_prior_event_id=wrong_prior.prior_event_id,
            prior_previous_settlement_date=wrong_prior.previous_settlement_date,
            prior_delta_short_ratio=wrong_prior.delta_short_ratio,
            acceleration_short_ratio=wrong_acceleration,
        )


def test_prior_feature_that_executes_strictly_later_is_rejected():
    _, feature = _completed_acceleration()
    later_prior = replace(
        feature.prior_feature,
        execution_session="2024-03-04",
        execution_at="2024-03-04T14:30:00Z",
    )

    with pytest.raises(StockAccelerationError, match="cannot execute after"):
        replace(
            feature,
            prior_feature=later_prior,
            prior_raw_feature_sha256=later_prior.sha256,
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("source_dataset_id", ""),
        ("current_raw_feature_sha256", "bad-hash"),
        ("settlement_date", "not-a-date"),
    ],
)
def test_malformed_acceleration_fields_use_one_error_contract(
    field_name, replacement
):
    _, feature = _completed_acceleration()
    with pytest.raises(StockAccelerationError, match="REFUSED"):
        replace(feature, **{field_name: replacement})


def test_exact_input_and_output_types_reject_subclasses_and_daily_volume():
    raw = _three_cycle_raw_dispositions()
    disposition, feature = _completed_acceleration()

    class RawDispositionSubclass(type(raw[0])):
        pass

    raw_impostor = RawDispositionSubclass(
        **{field.name: getattr(raw[0], field.name) for field in fields(raw[0])}
    )
    with pytest.raises(StockAccelerationError, match="exact tuple.*exact"):
        build_pit_stock_accelerations((raw_impostor, *raw[1:]))
    with pytest.raises(StockAccelerationError, match="exact tuple.*exact"):
        build_pit_stock_accelerations(list(raw))

    class AccelerationSubclass(PitStockAccelerationFeature):
        pass

    feature_impostor = AccelerationSubclass(
        **{field.name: getattr(feature, field.name) for field in fields(feature)}
    )
    with pytest.raises(StockAccelerationError, match="exact PitStockAcceleration"):
        replace(disposition, feature=feature_impostor)

    class RationalSubclass(ExactRational):
        def __eq__(self, other):
            return True

    for field_name in (
        "current_delta_short_ratio",
        "prior_delta_short_ratio",
        "acceleration_short_ratio",
    ):
        original = getattr(feature, field_name)
        rational_impostor = RationalSubclass(
            original.numerator,
            original.denominator,
        )
        with pytest.raises(
            StockAccelerationError,
            match=rf"{field_name}.*exact ExactRational",
        ):
            replace(feature, **{field_name: rational_impostor})

    class TextSubclass(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(StockAccelerationError, match="invalid.*source_dataset_id"):
        replace(feature, source_dataset_id=TextSubclass(feature.source_dataset_id))
    with pytest.raises(StockAccelerationError, match="invalid.*event_id"):
        replace(feature, event_id=TextSubclass(feature.event_id))

    daily = DailyShortSaleVolumeRecord(
        semantic=DailyVolumeSemantic.DAILY_SHORT_SALE_VOLUME,
        trade_date="2024-02-15",
        ticker="SYN",
        short_sale_volume=500,
        total_volume=1000,
        source_id="synthetic-daily-volume",
        source_version="1",
        raw_record_sha256="e" * 64,
    )
    with pytest.raises(StockAccelerationError, match="exact tuple.*exact"):
        build_pit_stock_accelerations((daily,))


def test_refusal_reasons_reject_tuple_subclass_equality_spoofing():
    first, warmup, _ = _acceleration_dispositions()

    class ForgedReasons(tuple):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    forged = ForgedReasons(("forged_reason",))
    with pytest.raises(StockAccelerationError, match="exact tuple type"):
        replace(first, refusal_reasons=forged)
    with pytest.raises(StockAccelerationError, match="exact tuple type"):
        replace(warmup, refusal_reasons=forged)
