"""Dangerous-direction tests for exact PIT Short Interest stock features."""
from __future__ import annotations

from dataclasses import fields, replace
from decimal import Decimal
from fractions import Fraction
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
    REFUSAL_SUPERSEDED,
    REFUSAL_UNAUDITED_FLOAT,
    load_synthetic_pit_reference,
)
from research.short_interest_etf.stock_features import (
    REFUSAL_PRIOR_DENOMINATOR_UNAUDITED_FLOAT,
    REFUSAL_PRIOR_SNAPSHOT_NOT_AUTHENTICATED,
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


def test_feature_disposition_refusals_reject_tuple_subclass_equality_spoofing():
    non_ready = next(item for item in _dispositions() if not item.readiness.ready)

    class ForgedReasons(tuple):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(StockFeatureError, match="exact tuple"):
        replace(
            non_ready,
            refusal_reasons=ForgedReasons((REFUSAL_SUPERSEDED,)),
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
    assert feature.current_snapshot == current
    assert feature.prior_snapshot == prior
    assert disposition.prior_readiness is not None
    assert disposition.prior_readiness.event_id == prior.event_id
    assert feature.prior_readiness_sha256 == disposition.prior_readiness.sha256


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


def test_coherent_stale_prior_revision_cannot_replace_latest_visible_correction():
    prior, current = _vintage().snapshots
    correction = _prior_correction(
        prior,
        published_at="2024-02-13T13:00:00Z",
        denominator_available_at="2024-02-13T13:00:00Z",
    )
    changed = _vintage_with_prior_correction(correction)
    dispositions = build_pit_stock_raw_features(changed, _references())
    current_disposition = next(
        item
        for item in dispositions
        if item.readiness.event_id == current.event_id
    )
    stale_disposition = next(
        item for item in dispositions if item.readiness.event_id == prior.event_id
    )
    assert current_disposition.feature is not None
    stale_prior_ratio = ExactRational.from_values(
        prior.current_short_shares,
        int(Decimal(prior.denominator.value)),
    )
    stale_feature = replace(
        current_disposition.feature,
        prior_readiness_sha256=stale_disposition.readiness.sha256,
        prior_event_id=prior.event_id,
        prior_denominator=prior.denominator,
        prior_denominator_kind=prior.denominator.kind,
        prior_denominator_sha256=hash_payload(prior.denominator.to_payload()),
        prior_denominator_value=prior.denominator.value,
        prior_snapshot=prior,
        prior_short_shares=prior.current_short_shares,
        prior_short_ratio=stale_prior_ratio,
        delta_short_ratio=ExactRational.from_fraction(
            current_disposition.feature.current_short_ratio.to_fraction()
            - stale_prior_ratio.to_fraction()
        ),
    )

    with pytest.raises(StockFeatureError, match="latest execution-visible prior"):
        replace(
            current_disposition,
            feature=stale_feature,
            prior_readiness=stale_disposition.readiness,
        )


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
    assert disposition.source_context is not None
    context = disposition.source_context

    assert feature.sha256 == hash_payload(feature.to_payload())
    assert disposition.sha256 == hash_payload(disposition.to_payload())
    assert context.sha256 == hash_payload(context.to_payload())
    assert not _contains_float(feature.to_payload())
    assert not _contains_float(disposition.to_payload())
    assert not _contains_float(context.to_payload())
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
    assert set(disposition.to_payload()) == {
        "feature",
        "prior_readiness",
        "readiness",
        "refusal_reasons",
        "source_context_sha256",
    }
    assert disposition.to_payload()["source_context_sha256"] == context.sha256
    assert set(context.to_payload()) == {
        "readiness_rows",
        "reference_bundle_identity",
        "schema_version",
        "source_vintage_identity",
    }
    assert context.to_payload()["readiness_rows"] == [
        item.to_payload() for item in context.readiness_rows
    ]


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


def test_denominator_values_must_agree_with_their_recorded_lineage_digests():
    """A substituted denominator value must not survive behind a genuine digest.

    ``current_denominator_sha256`` is anchored to the readiness row, and the
    three ratios are recomputed from the carried denominator *values*.  Without
    a value-to-digest binding the two halves never meet: a caller could restate
    the denominator, recompute internally consistent ratios, and keep the
    genuine readiness-anchored digest, so the lineage chain would certify a
    ratio that was never derived from the authenticated PIT fact.
    """
    _, feature = _ready_feature()

    tampered_current = Fraction(feature.current_short_shares, 2_000_000)
    with pytest.raises(StockFeatureError, match="current_denominator_value"):
        replace(
            feature,
            current_denominator_value="2000000",
            current_short_ratio=ExactRational.from_fraction(tampered_current),
            delta_short_ratio=ExactRational.from_fraction(
                tampered_current - feature.prior_short_ratio.to_fraction()
            ),
        )

    tampered_prior = Fraction(feature.prior_short_shares, 2_000_000)
    with pytest.raises(StockFeatureError, match="prior_denominator_value"):
        replace(
            feature,
            prior_denominator_value="2000000",
            prior_short_ratio=ExactRational.from_fraction(tampered_prior),
            delta_short_ratio=ExactRational.from_fraction(
                feature.current_short_ratio.to_fraction() - tampered_prior
            ),
        )

    assert hash_payload(feature.current_denominator.to_payload()) == (
        feature.current_denominator_sha256
    )
    assert hash_payload(feature.prior_denominator.to_payload()) == (
        feature.prior_denominator_sha256
    )


def test_disposition_still_binds_the_current_denominator_digest_to_its_readiness():
    """The authenticated source context pins the exact readiness denominator."""
    disposition, feature = _ready_feature()
    substituted_readiness = replace(
        disposition.readiness,
        denominator_sha256=feature.prior_denominator_sha256,
    )
    with pytest.raises(StockFeatureError, match="readiness.denominator_sha256"):
        replace(
            disposition,
            readiness=substituted_readiness,
            feature=replace(
                feature,
                readiness_sha256=substituted_readiness.sha256,
            ),
        )


def test_denominator_digest_covers_the_whole_observation_not_only_its_value():
    """Provenance is part of the denominator fact, not just the share count."""
    _, feature = _ready_feature()
    restamped = replace(feature.current_denominator, raw_record_sha256="c" * 64)
    assert restamped.value == feature.current_denominator.value
    assert restamped.kind is feature.current_denominator.kind

    with pytest.raises(StockFeatureError, match="current_denominator_sha256"):
        replace(feature, current_denominator=restamped)


def test_current_short_shares_are_bound_to_the_authenticated_source_event():
    _, feature = _ready_feature()
    substituted_ratio = ExactRational.from_values(
        999_999,
        int(Decimal(feature.current_denominator_value)),
    )
    with pytest.raises(StockFeatureError, match="current_short_shares"):
        replace(
            feature,
            current_short_shares=999_999,
            current_short_ratio=substituted_ratio,
            delta_short_ratio=ExactRational.from_fraction(
                substituted_ratio.to_fraction()
                - feature.prior_short_ratio.to_fraction()
            ),
        )


def test_prior_source_facts_cannot_be_fabricated_behind_current_readiness():
    _, feature = _ready_feature()
    with pytest.raises(StockFeatureError, match="prior_event_id"):
        replace(feature, prior_event_id="f" * 64)

    substituted_prior = ExactRational.from_values(
        500,
        int(Decimal(feature.prior_denominator_value)),
    )
    with pytest.raises(StockFeatureError, match="prior_short_shares"):
        replace(
            feature,
            prior_short_shares=500,
            prior_short_ratio=substituted_prior,
            delta_short_ratio=ExactRational.from_fraction(
                feature.current_short_ratio.to_fraction()
                - substituted_prior.to_fraction()
            ),
        )


@pytest.mark.parametrize(
    ("side", "changes", "error_pattern"),
    [
        (
            "prior",
            {"kind": DenominatorKind.POINT_IN_TIME_FLOAT},
            "prior_denominator_kind",
        ),
        ("prior", {"security_id": "sec-other"}, "prior_denominator.security_id"),
        (
            "prior",
            {
                "effective_date": "2025-01-02",
                "available_at": "2025-01-03T14:00:00Z",
                "observed_at": "2025-01-03T14:00:00Z",
            },
            "prior_denominator",
        ),
    ],
)
def test_denominator_witness_semantics_are_bound_to_feature_lineage(
    side, changes, error_pattern
):
    _, feature = _ready_feature()
    observation = replace(getattr(feature, f"{side}_denominator"), **changes)
    with pytest.raises(StockFeatureError, match=error_pattern):
        replace(
            feature,
            **{
                f"{side}_denominator": observation,
                f"{side}_denominator_sha256": hash_payload(
                    observation.to_payload()
                ),
            },
        )


def test_future_prior_snapshot_inputs_cannot_be_recast_as_execution_visible():
    _, feature = _ready_feature()
    future_denominator = replace(
        feature.prior_snapshot.denominator,
        available_at="2025-01-03T14:00:00Z",
        observed_at="2025-01-03T14:00:00Z",
    )
    future_snapshot = replace(
        feature.prior_snapshot,
        denominator=future_denominator,
    )

    with pytest.raises(
        StockFeatureError,
        match="prior_snapshot.denominator.available_at",
    ):
        replace(
            feature,
            prior_snapshot=future_snapshot,
            prior_event_id=future_snapshot.event_id,
            prior_denominator=future_denominator,
            prior_denominator_sha256=hash_payload(
                future_denominator.to_payload()
            ),
        )


def test_raw_feature_schema_version_tracks_the_snapshot_witness_payload_shape():
    _, feature = _ready_feature()
    assert feature.schema_version == "2.0"
    with pytest.raises(StockFeatureError, match="raw feature schema_version"):
        replace(feature, schema_version="1.0")

    class ForgedSchema(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(StockFeatureError, match="raw feature schema_version"):
        replace(feature, schema_version=ForgedSchema("9.9"))


def test_source_context_schema_version_is_load_bearing():
    disposition, _ = _ready_feature()
    assert disposition.source_context is not None
    context = disposition.source_context

    assert context.schema_version == "1.0"
    with pytest.raises(StockFeatureError, match="source context schema_version"):
        replace(context, schema_version="0.9")

    class ForgedSchema(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(StockFeatureError, match="source context schema_version"):
        replace(context, schema_version=ForgedSchema("9.9"))


def test_source_context_recomputes_and_rejects_coherent_readiness_row_tampering():
    disposition, _ = _ready_feature()
    assert disposition.source_context is not None
    context = disposition.source_context
    changed_rows = list(context.readiness_rows)
    changed_rows[-1] = replace(changed_rows[-1], taxonomy_id="FAKE")

    with pytest.raises(
        StockFeatureError,
        match="readiness_rows do not exactly match",
    ):
        replace(context, readiness_rows=tuple(changed_rows))


@pytest.mark.parametrize(
    ("field_name", "replacement", "error_pattern"),
    [
        (
            "denominator_sha256",
            "a" * 64,
            "prior_readiness.denominator_sha256",
        ),
        ("event_id", "a" * 64, "prior_readiness"),
        ("security_id", "sec-other", "prior_readiness.security_id"),
        (
            "settlement_date",
            "2024-01-11",
            "prior_readiness.settlement_date",
        ),
        (
            "reference_dataset_id",
            "synthetic-different-reference",
            "prior_readiness.reference_dataset_id",
        ),
    ],
)
def test_prior_readiness_is_an_independent_external_lineage_anchor(
    field_name, replacement, error_pattern
):
    disposition, feature = _ready_feature()
    assert disposition.prior_readiness is not None
    substituted_readiness = replace(
        disposition.prior_readiness,
        **{field_name: replacement},
    )
    substituted_feature = replace(
        feature,
        prior_readiness_sha256=substituted_readiness.sha256,
    )

    with pytest.raises(StockFeatureError, match=error_pattern):
        replace(
            disposition,
            feature=substituted_feature,
            prior_readiness=substituted_readiness,
        )


def test_disposition_binds_the_complete_prior_readiness_digest():
    disposition, feature = _ready_feature()
    with pytest.raises(StockFeatureError, match="prior_readiness_sha256"):
        replace(
            disposition,
            feature=replace(feature, prior_readiness_sha256="a" * 64),
        )


@pytest.mark.parametrize(
    ("side", "field_name", "error_pattern"),
    [
        ("current", "volume_basis_sha256", "readiness.volume_basis_sha256"),
        ("prior", "volume_basis_sha256", "prior_readiness.volume_basis_sha256"),
        (
            "prior",
            "security_identity_sha256",
            "prior_readiness.security_identity_sha256",
        ),
    ],
)
def test_readiness_snapshot_digests_are_bound_on_both_sides(
    side, field_name, error_pattern
):
    disposition, feature = _ready_feature()
    readiness = (
        disposition.readiness
        if side == "current"
        else disposition.prior_readiness
    )
    assert readiness is not None
    substituted_readiness = replace(
        readiness,
        **{field_name: "a" * 64},
    )
    if side == "current":
        changes = {
            "readiness": substituted_readiness,
            "feature": replace(
                feature,
                readiness_sha256=substituted_readiness.sha256,
            ),
        }
    else:
        changes = {
            "prior_readiness": substituted_readiness,
            "feature": replace(
                feature,
                prior_readiness_sha256=substituted_readiness.sha256,
            ),
        }

    with pytest.raises(StockFeatureError, match=error_pattern):
        replace(disposition, **changes)


def test_readiness_execution_cohorts_are_recomputed_from_the_source_vintage():
    disposition, feature = _ready_feature()
    delayed_readiness = replace(
        disposition.readiness,
        execution_session="2024-02-14",
        execution_at="2024-02-14T14:30:00Z",
    )
    delayed_feature = replace(
        feature,
        readiness_sha256=delayed_readiness.sha256,
        execution_session=delayed_readiness.execution_session,
        execution_at=delayed_readiness.execution_at,
    )
    with pytest.raises(StockFeatureError, match="readiness.execution_session"):
        replace(
            disposition,
            readiness=delayed_readiness,
            feature=delayed_feature,
        )


def test_sector_and_industry_cannot_be_recast_behind_genuine_reference_hashes():
    disposition, feature = _ready_feature()
    substituted_readiness = replace(
        disposition.readiness,
        taxonomy_id="FAKE",
        sector_code="FAKE",
        industry_code="FAKE",
    )
    substituted_feature = replace(
        feature,
        readiness_sha256=substituted_readiness.sha256,
        taxonomy_id="FAKE",
        sector_code="FAKE",
        industry_code="FAKE",
    )

    with pytest.raises(StockFeatureError, match="readiness.taxonomy_id"):
        replace(
            disposition,
            readiness=substituted_readiness,
            feature=substituted_feature,
        )


def test_non_ready_refusal_is_recomputed_by_the_authenticated_source_context():
    non_ready = next(item for item in _dispositions() if not item.readiness.ready)
    substituted_readiness = replace(
        non_ready.readiness,
        refusal_reasons=(REFUSAL_SUPERSEDED,),
    )

    with pytest.raises(StockFeatureError, match="readiness.refusal_reasons"):
        replace(
            non_ready,
            readiness=substituted_readiness,
            refusal_reasons=substituted_readiness.refusal_reasons,
        )


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
    # The tampered field must be named and rejected somewhere in the
    # construction chain.  Binding each denominator digest to the exact
    # observation it was taken over moved the current-denominator case from the
    # disposition boundary to the feature contract itself; both boundaries are
    # still exercised, and every case still proves the field cannot drift.
    with pytest.raises(StockFeatureError, match=field_name):
        replace(disposition, feature=replace(feature, **{field_name: replacement}))


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
    with pytest.raises(
        StockFeatureError,
        match="prior-snapshot refusal conflicts",
    ):
        replace(
            current_disposition,
            refusal_reasons=(REFUSAL_PRIOR_SNAPSHOT_NOT_AUTHENTICATED,),
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
    assert disposition.source_context is not None
    with pytest.raises(StockFeatureError, match="context source_vintage.*exact"):
        replace(
            disposition.source_context,
            source_vintage=vintage_impostor,
        )

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

    class TextSubclass(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    with pytest.raises(StockFeatureError, match="invalid PIT stock raw feature"):
        replace(feature, source_dataset_id=TextSubclass(feature.source_dataset_id))
    with pytest.raises(StockFeatureError, match="invalid PIT stock raw feature"):
        replace(feature, event_id=TextSubclass(feature.event_id))

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

    assert disposition.prior_readiness is not None
    prior_readiness_impostor = ReadinessSubclass(
        **{
            field.name: getattr(disposition.prior_readiness, field.name)
            for field in fields(disposition.prior_readiness)
        }
    )
    with pytest.raises(StockFeatureError, match="prior_readiness.*exact"):
        replace(disposition, prior_readiness=prior_readiness_impostor)

    class SnapshotSubclass(type(feature.current_snapshot)):
        pass

    snapshot_impostor = SnapshotSubclass(
        **{
            field.name: getattr(feature.current_snapshot, field.name)
            for field in fields(feature.current_snapshot)
        }
    )
    with pytest.raises(StockFeatureError, match="current_snapshot.*exact"):
        replace(feature, current_snapshot=snapshot_impostor)

    assert disposition.source_context is not None

    class SourceContextSubclass(type(disposition.source_context)):
        pass

    context_impostor = SourceContextSubclass(
        **{
            field.name: getattr(disposition.source_context, field.name)
            for field in fields(disposition.source_context)
        }
    )
    with pytest.raises(StockFeatureError, match="source_context.*exact"):
        replace(disposition, source_context=context_impostor)

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
