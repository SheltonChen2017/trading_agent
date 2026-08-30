"""Dangerous-direction tests for exact PIT Short Interest stock features."""
from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.contracts import (
    DenominatorKind,
    recompute_days_to_cover,
)
from research.short_interest_etf.daily_short_volume import (
    DailyShortSaleVolumeRecord,
    DailyVolumeSemantic,
)
from research.short_interest_etf.dataset import build_vintage, load_synthetic_fixture
from research.short_interest_etf.pit_eligibility import (
    PitReferenceBundle,
    REFUSAL_MISSING_PRIOR,
    REFUSAL_UNAUDITED_FLOAT,
    load_synthetic_pit_reference,
)
from research.short_interest_etf.stock_features import (
    REFUSAL_PRIOR_DENOMINATOR_UNAUDITED_FLOAT,
    ExactRational,
    PitStockRawFeature,
    StockFeatureDisposition,
    StockFeatureError,
    build_pit_stock_raw_features,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "short_interest_etf"
SOURCE_FIXTURE = FIXTURE_ROOT / "official_style_v1.json"
REFERENCE_FIXTURE = FIXTURE_ROOT / "pit_reference_v1.json"


def _vintage():
    return load_synthetic_fixture(SOURCE_FIXTURE)


def _references():
    return load_synthetic_pit_reference(REFERENCE_FIXTURE)


def _dispositions():
    return build_pit_stock_raw_features(_vintage(), _references())


def _ready_feature() -> tuple[StockFeatureDisposition, PitStockRawFeature]:
    disposition = next(item for item in _dispositions() if item.feature is not None)
    assert disposition.feature is not None
    return disposition, disposition.feature


def _prior_correction(
    prior,
    *,
    published_at: str,
    denominator_available_at: str,
):
    denominator = replace(
        prior.denominator,
        value="9000",
        available_at=denominator_available_at,
        observed_at=denominator_available_at,
        raw_record_sha256="e" * 64,
    )
    observed_at = max(published_at, denominator_available_at)
    return replace(
        prior,
        source_record_id="synthetic-si-2024-01-12-r2",
        denominator=denominator,
        revision_id="r2",
        revision_published_at=published_at,
        observed_at=observed_at,
        supersedes_event_id=prior.event_id,
        raw_record_sha256="f" * 64,
    )


def _vintage_with_prior_correction(correction):
    vintage = _vintage()
    prior, current = vintage.snapshots
    manifest = replace(
        vintage.manifest,
        requested_record_count=3,
        input_row_count=3,
        accepted_record_count=3,
    )
    return build_vintage(
        manifest,
        vintage.release_calendar,
        (prior, correction, current),
    )


def _contains_float(value) -> bool:
    if type(value) is float:
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def test_every_source_event_keeps_a_feature_or_its_exact_readiness_refusal():
    vintage = _vintage()
    dispositions = _dispositions()

    assert len(dispositions) == len(vintage.snapshots) == 2
    assert {item.readiness.event_id for item in dispositions} == {
        item.event_id for item in vintage.snapshots
    }
    warmup, ready = dispositions
    assert warmup.feature is None
    assert warmup.refusal_reasons == (REFUSAL_MISSING_PRIOR,)
    assert warmup.refusal_reasons == warmup.readiness.refusal_reasons
    assert ready.refusal_reasons == ()
    assert ready.readiness.ready is True
    assert ready.feature is not None


def test_non_ready_disposition_cannot_carry_an_otherwise_valid_feature():
    dispositions = _dispositions()
    non_ready = next(item for item in dispositions if not item.readiness.ready)
    _, valid_feature = _ready_feature()

    with pytest.raises(
        StockFeatureError,
        match="non-ready source data cannot carry a stock feature",
    ):
        StockFeatureDisposition(
            readiness=non_ready.readiness,
            feature=valid_feature,
            refusal_reasons=non_ready.refusal_reasons,
        )


def test_golden_current_prior_and_delta_ratios_are_exact_and_use_each_denominator():
    disposition, feature = _ready_feature()
    vintage = _vintage()
    prior, current = vintage.snapshots

    # Current: 1200/11000 = 6/55. Prior: 1000/10000 = 1/10.
    # Reusing the current denominator for the prior would produce 1/11 and a
    # different delta, so this pins the dangerous denominator-backfill error.
    assert feature.current_short_ratio == ExactRational(6, 55)
    assert feature.prior_short_ratio == ExactRational(1, 10)
    assert feature.delta_short_ratio == ExactRational(1, 110)
    assert feature.current_denominator_value == "11000"
    assert feature.prior_denominator_value == "10000"
    assert feature.current_short_shares == 1200
    assert feature.prior_short_shares == 1000
    assert feature.event_id == current.event_id
    assert feature.prior_event_id == prior.event_id
    assert feature.readiness_sha256 == disposition.readiness.sha256
    assert feature.current_denominator_sha256 == hash_payload(
        current.denominator.to_payload()
    )
    assert feature.prior_denominator_sha256 == hash_payload(
        prior.denominator.to_payload()
    )


def test_falling_short_ratio_keeps_its_exact_negative_delta():
    vintage = _vintage()
    prior, current = vintage.snapshots
    lower_current = replace(
        current,
        current_short_shares=500,
        recomputed_days_to_cover=recompute_days_to_cover(
            500,
            current.volume_basis.average_daily_share_volume,
        ),
        raw_record_sha256="a" * 64,
    )
    changed = build_vintage(
        vintage.manifest,
        vintage.release_calendar,
        (prior, lower_current),
    )

    disposition = next(
        item
        for item in build_pit_stock_raw_features(changed, _references())
        if item.readiness.event_id == lower_current.event_id
    )
    assert disposition.feature is not None
    assert disposition.feature.current_short_ratio == ExactRational(1, 22)
    assert disposition.feature.prior_short_ratio == ExactRational(1, 10)
    assert disposition.feature.delta_short_ratio == ExactRational(-3, 55)


def test_prior_revision_with_future_inputs_cannot_leak_into_current_feature():
    prior, current = _vintage().snapshots
    correction = _prior_correction(
        prior,
        published_at="2024-02-12T21:00:00Z",
        denominator_available_at="2024-02-14T13:00:00Z",
    )
    changed = _vintage_with_prior_correction(correction)

    disposition = next(
        item
        for item in build_pit_stock_raw_features(changed, _references())
        if item.readiness.event_id == current.event_id
    )
    assert disposition.readiness.ready is True
    assert disposition.feature is not None
    assert disposition.feature.prior_event_id == prior.event_id
    assert disposition.feature.prior_denominator_value == "10000"


def test_prior_revision_fully_visible_by_execution_replaces_stale_revision():
    prior, current = _vintage().snapshots
    correction = _prior_correction(
        prior,
        published_at="2024-02-13T13:00:00Z",
        denominator_available_at="2024-02-13T13:00:00Z",
    )
    changed = _vintage_with_prior_correction(correction)

    disposition = next(
        item
        for item in build_pit_stock_raw_features(changed, _references())
        if item.readiness.event_id == current.event_id
    )
    assert disposition.readiness.ready is True
    assert disposition.feature is not None
    assert disposition.feature.prior_event_id == correction.event_id
    assert disposition.feature.prior_denominator_value == "9000"


def test_prior_join_uses_stable_security_id_across_a_ticker_change():
    vintage = _vintage()
    prior, current = vintage.snapshots
    retired_identity = replace(
        prior.security,
        valid_to="2024-01-12",
        raw_record_sha256="a" * 64,
    )
    renamed_prior = replace(
        prior,
        security=retired_identity,
        raw_record_sha256="b" * 64,
    )
    renamed_identity = replace(
        current.security,
        ticker="ALT",
        valid_from="2024-01-13",
        raw_record_sha256="c" * 64,
    )
    renamed_current = replace(
        current,
        security=renamed_identity,
        raw_record_sha256="d" * 64,
    )
    changed = build_vintage(
        vintage.manifest,
        vintage.release_calendar,
        (renamed_prior, renamed_current),
    )

    disposition = next(
        item
        for item in build_pit_stock_raw_features(changed, _references())
        if item.readiness.event_id == renamed_current.event_id
    )
    assert prior.security.ticker == "SYN"
    assert renamed_current.security.ticker == "ALT"
    assert disposition.feature is not None
    assert disposition.feature.security_id == renamed_prior.security.security_id
    assert disposition.feature.prior_event_id == renamed_prior.event_id


def test_prior_join_cannot_cross_security_ids_on_the_same_settlement():
    vintage = _vintage()
    prior, current = vintage.snapshots
    other_identity = replace(
        prior.security,
        security_id="sec-synth-002",
        vendor_security_id="vendor-synth-002",
        ticker="OTH",
        raw_record_sha256="a" * 64,
    )
    other_prior = replace(
        prior,
        source_record_id="synthetic-si-2024-01-12-other-r1",
        security=other_identity,
        volume_basis=replace(
            prior.volume_basis,
            security_id="sec-synth-002",
            raw_record_sha256="b" * 64,
        ),
        denominator=replace(
            prior.denominator,
            security_id="sec-synth-002",
            raw_record_sha256="c" * 64,
        ),
        raw_record_sha256="d" * 64,
    )
    manifest = replace(
        vintage.manifest,
        requested_record_count=3,
        input_row_count=3,
        accepted_record_count=3,
    )
    changed = build_vintage(
        manifest,
        vintage.release_calendar,
        (prior, other_prior, current),
    )

    disposition = next(
        item
        for item in build_pit_stock_raw_features(changed, _references())
        if item.readiness.event_id == current.event_id
    )
    assert disposition.feature is not None
    assert disposition.feature.security_id == prior.security.security_id
    assert disposition.feature.prior_event_id == prior.event_id


def test_feature_payload_and_disposition_hash_bind_every_exact_fact_without_floats():
    disposition, feature = _ready_feature()

    assert feature.sha256 == hash_payload(feature.to_payload())
    assert disposition.sha256 == hash_payload(disposition.to_payload())
    assert not _contains_float(feature.to_payload())
    assert not _contains_float(disposition.to_payload())
    assert set(feature.to_payload()) == {
        field.name for field in fields(feature)
    }
    assert feature.current_short_ratio.to_payload() == {
        "denominator": 55,
        "numerator": 6,
    }
    assert feature.to_payload()["prior_denominator_sha256"] == (
        feature.prior_denominator_sha256
    )


def test_exact_rational_contract_reduces_inputs_and_rejects_noncanonical_values():
    assert ExactRational.from_values(1200, 11000) == ExactRational(6, 55)
    assert ExactRational.from_values(0, 999) == ExactRational(0, 1)
    assert ExactRational.from_values(-5, 10) == ExactRational(-1, 2)

    with pytest.raises(StockFeatureError, match="must be reduced"):
        ExactRational(2, 4)
    with pytest.raises(StockFeatureError, match="positive"):
        ExactRational(1, 0)
    with pytest.raises(StockFeatureError, match="exact integer"):
        ExactRational(True, 1)
    with pytest.raises(StockFeatureError, match="positive exact integer"):
        ExactRational(1, True)


@pytest.mark.parametrize(
    ("field_name", "replacement", "error_pattern"),
    [
        ("current_short_ratio", ExactRational(1, 1), "current_short_ratio"),
        ("prior_short_ratio", ExactRational(1, 1), "prior_short_ratio"),
        ("delta_short_ratio", ExactRational(0, 1), "delta_short_ratio"),
    ],
)
def test_feature_contract_recomputes_all_three_ratios(
    field_name, replacement, error_pattern
):
    _, feature = _ready_feature()
    with pytest.raises(StockFeatureError, match=error_pattern):
        replace(feature, **{field_name: replacement})


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("classification_record_id", "a" * 64),
        ("reference_dataset_id", "synthetic-different-reference"),
        ("current_denominator_sha256", "a" * 64),
        ("event_id", "a" * 64),
        ("industry_code", "OTHER"),
        ("lifecycle_record_id", "a" * 64),
        ("readiness_sha256", "b" * 64),
        ("reference_bundle_sha256", "a" * 64),
        ("sector_code", "OTHER"),
        ("security_id", "sec-synth-other"),
        ("security_identity_sha256", "a" * 64),
        ("settlement_date", "2024-02-01"),
        ("taxonomy_id", "OTHER"),
    ],
)
def test_feature_lineage_must_match_the_exact_readiness_row(
    field_name, replacement
):
    disposition, feature = _ready_feature()
    mismatched = replace(feature, **{field_name: replacement})
    with pytest.raises(StockFeatureError, match=field_name):
        replace(disposition, feature=mismatched)


def test_feature_execution_lineage_must_match_as_one_valid_temporal_pair():
    disposition, feature = _ready_feature()
    mismatched = replace(
        feature,
        execution_session="2024-02-14",
        execution_at="2024-02-14T14:30:00Z",
    )
    with pytest.raises(StockFeatureError, match="execution_at"):
        replace(disposition, feature=mismatched)


def test_feature_source_vintage_lineage_rejects_same_dataset_prefix_tampering():
    disposition, feature = _ready_feature()
    replacement_tail = "a" * 48
    if feature.source_vintage_sha256.endswith(replacement_tail):
        replacement_tail = "b" * 48
    mismatched = replace(
        feature,
        source_vintage_sha256=(
            feature.source_vintage_sha256[:16] + replacement_tail
        ),
    )
    with pytest.raises(StockFeatureError, match="source_vintage_sha256"):
        replace(disposition, feature=mismatched)


def test_feature_source_dataset_lineage_rejects_a_valid_coupled_vintage_change():
    disposition, feature = _ready_feature()
    different_vintage = "a" * 64
    mismatched = replace(
        feature,
        source_dataset_id=(
            f"short-interest-vintage-{different_vintage[:16]}"
        ),
        source_vintage_sha256=different_vintage,
    )
    with pytest.raises(StockFeatureError, match="source_dataset_id"):
        replace(disposition, feature=mismatched)


def test_current_float_refusal_is_preserved_and_never_becomes_a_feature():
    vintage = _vintage()
    prior, current = vintage.snapshots
    float_current = replace(
        current,
        denominator=replace(
            current.denominator,
            kind=DenominatorKind.POINT_IN_TIME_FLOAT,
        ),
    )
    changed = build_vintage(
        vintage.manifest,
        vintage.release_calendar,
        (prior, float_current),
    )

    current_disposition = next(
        item
        for item in build_pit_stock_raw_features(changed, _references())
        if item.readiness.settlement_date == current.settlement_date
    )
    assert current_disposition.feature is None
    assert REFUSAL_UNAUDITED_FLOAT in current_disposition.refusal_reasons
    assert current_disposition.refusal_reasons == (
        current_disposition.readiness.refusal_reasons
    )


def test_prior_float_gets_a_separate_named_feature_refusal():
    vintage = _vintage()
    prior, current = vintage.snapshots
    float_prior = replace(
        prior,
        denominator=replace(
            prior.denominator,
            kind=DenominatorKind.POINT_IN_TIME_FLOAT,
        ),
    )
    changed = build_vintage(
        vintage.manifest,
        vintage.release_calendar,
        (float_prior, current),
    )

    current_disposition = next(
        item
        for item in build_pit_stock_raw_features(changed, _references())
        if item.readiness.settlement_date == current.settlement_date
    )
    assert current_disposition.readiness.ready is True
    assert current_disposition.feature is None
    assert current_disposition.refusal_reasons == (
        REFUSAL_PRIOR_DENOMINATOR_UNAUDITED_FLOAT,
    )


def test_input_reordering_cannot_change_dispositions_or_hashes():
    vintage = _vintage()
    references = _references()
    reordered_vintage = build_vintage(
        vintage.manifest,
        tuple(reversed(vintage.release_calendar)),
        tuple(reversed(vintage.snapshots)),
        tuple(reversed(vintage.refusals)),
    )
    reordered_references = PitReferenceBundle(
        manifest=references.manifest,
        lifecycles=tuple(reversed(references.lifecycles)),
        classifications=tuple(reversed(references.classifications)),
    )

    original = build_pit_stock_raw_features(vintage, references)
    reordered = build_pit_stock_raw_features(
        reordered_vintage, reordered_references
    )
    assert reordered == original
    assert [item.sha256 for item in reordered] == [
        item.sha256 for item in original
    ]


def test_exact_input_and_output_types_cannot_be_replaced_by_subclasses():
    vintage = _vintage()
    references = _references()
    disposition, feature = _ready_feature()

    class VintageSubclass(type(vintage)):
        def __post_init__(self):
            return None

    vintage_impostor = VintageSubclass(
        manifest=vintage.manifest,
        release_calendar=vintage.release_calendar,
        snapshots=vintage.snapshots,
        refusals=vintage.refusals,
    )
    with pytest.raises(StockFeatureError, match="exact ShortInterestVintage"):
        build_pit_stock_raw_features(vintage_impostor, references)

    class ReferenceSubclass(type(references)):
        def __post_init__(self):
            return None

    reference_impostor = ReferenceSubclass(
        manifest=references.manifest,
        lifecycles=references.lifecycles,
        classifications=references.classifications,
    )
    with pytest.raises(StockFeatureError, match="exact PitReferenceBundle"):
        build_pit_stock_raw_features(vintage, reference_impostor)

    class FeatureSubclass(type(feature)):
        pass

    feature_impostor = FeatureSubclass(
        **{field.name: getattr(feature, field.name) for field in fields(feature)}
    )
    with pytest.raises(StockFeatureError, match="exact PitStockRawFeature"):
        replace(disposition, feature=feature_impostor)

    class RationalSubclass(ExactRational):
        def __eq__(self, other):
            return True

    rational_impostor = RationalSubclass(
        feature.current_short_ratio.numerator,
        feature.current_short_ratio.denominator,
    )
    with pytest.raises(StockFeatureError, match="exact ExactRational"):
        replace(feature, current_short_ratio=rational_impostor)

    class ReadinessSubclass(type(disposition.readiness)):
        def __post_init__(self):
            return None

        @property
        def sha256(self):
            return disposition.readiness.sha256

    readiness_impostor = ReadinessSubclass(
        **{
            field.name: getattr(disposition.readiness, field.name)
            for field in fields(disposition.readiness)
        }
    )
    with pytest.raises(StockFeatureError, match="exact StockDataReadiness"):
        replace(disposition, readiness=readiness_impostor)

    daily = DailyShortSaleVolumeRecord(
        semantic=DailyVolumeSemantic.DAILY_SHORT_SALE_VOLUME,
        trade_date="2024-01-31",
        ticker="SYN",
        short_sale_volume=500,
        total_volume=1000,
        source_id="synthetic-daily-volume",
        source_version="1",
        raw_record_sha256="d" * 64,
    )
    with pytest.raises(StockFeatureError, match="exact ShortInterestVintage"):
        build_pit_stock_raw_features(daily, references)
