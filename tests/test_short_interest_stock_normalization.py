"""Dangerous-direction tests for exact SI-3C S0/S1 normalization."""
from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from functools import lru_cache
from fractions import Fraction
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.contracts import (
    ReleasePrecision,
    recompute_days_to_cover,
)
from research.short_interest_etf.dataset import build_vintage, load_synthetic_fixture
from research.short_interest_etf.pit_eligibility import (
    PitReferenceBundle,
    REFUSAL_MISSING_PRIOR,
    load_synthetic_pit_reference,
    reference_fixture_body_sha256,
)
from research.short_interest_etf.stock_features import (
    ExactRational,
    build_pit_stock_raw_features,
)
from research.short_interest_etf.stock_normalization import (
    NORMALIZATION_POLICY_ID,
    REFUSAL_INSUFFICIENT_SECTOR_PEERS,
    REFUSAL_MIXED_TAXONOMY_LINEAGE,
    REFUSAL_NON_COMMON_STOCK_SECURITY,
    REFUSAL_NON_US_SECURITY,
    REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF,
    REFUSAL_SUPERSEDED_AT_RELEASE_CUTOFF,
    REFUSAL_ZERO_SECTOR_MAD,
    STOCK_NORMALIZATION_POLICY,
    STRUCTURAL_SCORE_AUTHORITY,
    RevisionSelectionState,
    StockNormalizationError,
    StockScoreDisposition,
    StockScoreModel,
    build_pit_stock_normalized_scores,
    require_stock_normalization_policy,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "short_interest_etf"
SOURCE_FIXTURE = FIXTURE_ROOT / "official_style_v1.json"
REFERENCE_FIXTURE = FIXTURE_ROOT / "pit_reference_v1.json"
CURRENT_SETTLEMENT = "2024-01-31"


def _sha(label: str) -> str:
    return hash_payload({"synthetic_si3c_fixture": label})


@dataclass(frozen=True)
class _Spec:
    index: int
    sector: str
    current_shares: int
    prior_shares: int
    country: str = "US"
    security_type: str = "COMMON_STOCK"
    taxonomy_id: str = "SYNTHETIC_SECTOR_V1"
    taxonomy_source_id: str = "synthetic-sector-master"
    taxonomy_source_version: str = "2024.v1"
    ticker: str | None = None
    share_class: str = "A"


@dataclass(frozen=True)
class _ScaleMetrics:
    disposition_count: int
    unique_cohort_count: int
    cohort_payload_occurrences: int
    outcome_count: int
    raw_inventory_embeddings: int
    candidate_member_embeddings: int
    eligible_member_embeddings: int
    sector_member_embeddings: int
    total_repeated_witnesses: int
    canonical_payload_bytes: int
    payload_sha256: str


def _base_specs() -> tuple[_Spec, ...]:
    return tuple(
        _Spec(
            index=index,
            sector="TECHNOLOGY" if index % 2 == 0 else "HEALTHCARE",
            current_shares=100 + index,
            prior_shares=130 - index,
        )
        for index in range(40)
    )


def _single_sector_specs(count: int) -> tuple[_Spec, ...]:
    return tuple(
        _Spec(
            index=index,
            sector="TECHNOLOGY",
            current_shares=100 + index,
            prior_shares=130 - index,
        )
        for index in range(count)
    )


@lru_cache(maxsize=None)
def _raw_batch(
    specs: tuple[_Spec, ...],
    correction: tuple[int, str] | None = None,
):
    base_vintage = load_synthetic_fixture(SOURCE_FIXTURE)
    prior_template, current_template = base_vintage.snapshots
    snapshots = []
    current_by_index = {}
    for spec in specs:
        security_id = f"sec-si3c-{spec.index:03d}"
        ticker = spec.ticker or f"S{spec.index:03d}"
        security = replace(
            prior_template.security,
            security_id=security_id,
            vendor_security_id=f"vendor-si3c-{spec.index:03d}",
            ticker=ticker,
            share_class=spec.share_class,
            country=spec.country,
            security_type=spec.security_type,
            raw_record_sha256=_sha(f"identity-{spec.index}"),
        )

        def make_snapshot(template, *, current: bool):
            shares = spec.current_shares if current else spec.prior_shares
            denominator = replace(
                template.denominator,
                security_id=security_id,
                value="10000",
                raw_record_sha256=_sha(
                    f"denominator-{spec.index}-{'current' if current else 'prior'}"
                ),
            )
            volume = replace(
                template.volume_basis,
                security_id=security_id,
                average_daily_share_volume="100",
                raw_record_sha256=_sha(
                    f"volume-{spec.index}-{'current' if current else 'prior'}"
                ),
            )
            dtc = recompute_days_to_cover(
                shares, volume.average_daily_share_volume
            )
            return replace(
                template,
                source_record_id=(
                    f"synthetic-si3c-{spec.index:03d}-"
                    f"{'current' if current else 'prior'}-r1"
                ),
                security=security,
                current_short_shares=shares,
                previous_short_shares=(
                    spec.prior_shares if current else max(spec.prior_shares - 1, 0)
                ),
                volume_basis=volume,
                reported_days_to_cover=dtc,
                recomputed_days_to_cover=dtc,
                denominator=denominator,
                raw_record_sha256=_sha(
                    f"snapshot-{spec.index}-{'current' if current else 'prior'}"
                ),
            )

        prior = make_snapshot(prior_template, current=False)
        current = make_snapshot(current_template, current=True)
        snapshots.extend((prior, current))
        current_by_index[spec.index] = current

    if correction is not None:
        index, published_at = correction
        original = current_by_index[index]
        corrected_shares = original.current_short_shares + 7
        corrected_dtc = recompute_days_to_cover(
            corrected_shares,
            original.volume_basis.average_daily_share_volume,
        )
        snapshots.append(
            replace(
                original,
                source_record_id=f"synthetic-si3c-{index:03d}-current-r2",
                current_short_shares=corrected_shares,
                reported_days_to_cover=corrected_dtc,
                recomputed_days_to_cover=corrected_dtc,
                revision_id="r2",
                revision_published_at=published_at,
                observed_at=published_at,
                supersedes_event_id=original.event_id,
                raw_record_sha256=_sha(f"snapshot-{index}-current-r2-{published_at}"),
            )
        )

    manifest = replace(
        base_vintage.manifest,
        source_dataset_id="synthetic-si3c-normalization-v1",
        snapshot_name="synthetic-si3c-multi-sector-normalization",
        requested_record_count=len(snapshots),
        input_row_count=len(snapshots),
        accepted_record_count=len(snapshots),
        raw_artifact_sha256=hash_payload(
            [item.to_payload() for item in snapshots]
        ),
    )
    vintage = build_vintage(
        manifest,
        base_vintage.release_calendar,
        tuple(snapshots),
    )

    base_references = load_synthetic_pit_reference(REFERENCE_FIXTURE)
    lifecycle_template = base_references.lifecycles[0]
    classification_template = base_references.classifications[0]
    lifecycles = []
    classifications = []
    for spec in specs:
        security_id = f"sec-si3c-{spec.index:03d}"
        lifecycles.append(
            replace(
                lifecycle_template,
                security_id=security_id,
                raw_record_sha256=_sha(f"lifecycle-{spec.index}"),
            )
        )
        classifications.append(
            replace(
                classification_template,
                security_id=security_id,
                taxonomy_id=spec.taxonomy_id,
                sector_code=spec.sector,
                industry_code=f"{spec.sector}_SYNTHETIC",
                source_id=spec.taxonomy_source_id,
                source_version=spec.taxonomy_source_version,
                raw_record_sha256=_sha(f"classification-{spec.index}"),
            )
        )
    reference_manifest = replace(
        base_references.manifest,
        reference_dataset_id="synthetic-si3c-pit-reference-v1",
        lifecycle_record_count=len(lifecycles),
        classification_record_count=len(classifications),
        source_body_sha256=reference_fixture_body_sha256(
            [item.to_payload() for item in lifecycles],
            [item.to_payload() for item in classifications],
        ),
    )
    references = PitReferenceBundle(
        manifest=reference_manifest,
        lifecycles=tuple(lifecycles),
        classifications=tuple(classifications),
    )
    return build_pit_stock_raw_features(vintage, references)


def _scores(
    specs: tuple[_Spec, ...] | None = None,
    correction: tuple[int, str] | None = None,
) -> tuple[StockScoreDisposition, ...]:
    return build_pit_stock_normalized_scores(
        _raw_batch(specs or _base_specs(), correction)
    )


@lru_cache(maxsize=None)
def _raw_batch_with_two_release_keys_for_one_settlement():
    raw = _raw_batch(_base_specs())
    source_context = raw[0].source_context
    vintage = source_context.source_vintage
    first_release = next(
        item
        for item in vintage.release_calendar
        if item.settlement_date == CURRENT_SETTLEMENT
    )
    second_release = replace(
        first_release,
        calendar_id="finra-synthetic-calendar-v2",
        public_release_date="2024-02-14",
        public_release_at="2024-02-14T21:00:00Z",
        precision=ReleasePrecision.EXACT_TIMESTAMP,
        evidence_sha256=_sha("second-release-lineage"),
        observed_at="2024-02-14T22:00:00Z",
    )
    corrections = []
    for original in vintage.snapshots:
        if original.settlement_date != CURRENT_SETTLEMENT:
            continue
        corrected_shares = original.current_short_shares + 7
        corrected_dtc = recompute_days_to_cover(
            corrected_shares,
            original.volume_basis.average_daily_share_volume,
        )
        corrections.append(
            replace(
                original,
                source_record_id=f"{original.source_record_id}-second-release",
                release_calendar_key=second_release.key,
                current_short_shares=corrected_shares,
                reported_days_to_cover=corrected_dtc,
                recomputed_days_to_cover=corrected_dtc,
                revision_id="r2",
                revision_published_at="2024-02-14T21:00:00Z",
                observed_at="2024-02-14T22:00:00Z",
                supersedes_event_id=original.event_id,
                raw_record_sha256=_sha(
                    f"second-release-{original.security.security_id}"
                ),
            )
        )
    snapshots = vintage.snapshots + tuple(corrections)
    manifest = replace(
        vintage.manifest,
        requested_record_count=len(snapshots),
        input_row_count=len(snapshots),
        accepted_record_count=len(snapshots),
        raw_artifact_sha256=hash_payload(
            [item.to_payload() for item in snapshots]
        ),
    )
    mixed = build_vintage(
        manifest,
        vintage.release_calendar + (second_release,),
        snapshots,
    )
    return build_pit_stock_raw_features(mixed, source_context.reference_bundle)


def _current(scores):
    return tuple(
        item
        for item in scores
        if item.current.readiness.settlement_date == CURRENT_SETTLEMENT
    )


def _by_security(scores, security_id: str):
    return tuple(
        item
        for item in scores
        if item.current.readiness.security_id == security_id
        and item.current.readiness.settlement_date == CURRENT_SETTLEMENT
    )


def _model(disposition: StockScoreDisposition, model: StockScoreModel):
    return next(item for item in disposition.outcomes if item.model is model)


def _contains_float(value) -> bool:
    if type(value) is float:
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _scale_metrics(
    scores: tuple[StockScoreDisposition, ...],
) -> _ScaleMetrics:
    payloads = [item.to_payload() for item in scores]
    raw_inventory_embeddings = sum(
        len(payload["cohort"]["raw_disposition_inventory"])
        for payload in payloads
    )
    candidate_member_embeddings = sum(
        len(payload["cohort"]["candidate_members"])
        for payload in payloads
    )
    eligible_member_embeddings = sum(
        len(payload["cohort"]["eligible_members"])
        for payload in payloads
    )
    sector_member_embeddings = sum(
        len(outcome["sector_members"])
        for payload in payloads
        for outcome in payload["outcomes"]
    )
    total_repeated_witnesses = (
        raw_inventory_embeddings
        + candidate_member_embeddings
        + eligible_member_embeddings
        + sector_member_embeddings
    )
    return _ScaleMetrics(
        disposition_count=len(payloads),
        unique_cohort_count=len({item.cohort.sha256 for item in scores}),
        cohort_payload_occurrences=sum("cohort" in payload for payload in payloads),
        outcome_count=sum(len(payload["outcomes"]) for payload in payloads),
        raw_inventory_embeddings=raw_inventory_embeddings,
        candidate_member_embeddings=candidate_member_embeddings,
        eligible_member_embeddings=eligible_member_embeddings,
        sector_member_embeddings=sector_member_embeddings,
        total_repeated_witnesses=total_repeated_witnesses,
        canonical_payload_bytes=len(canonical_json(payloads).encode("utf-8")),
        payload_sha256=hash_payload(payloads),
    )


def test_policy_v1_is_exact_hash_bound_without_changing_preregistration():
    before = STOCK_NORMALIZATION_POLICY.preregistration_sha256
    assert STOCK_NORMALIZATION_POLICY.policy_id == NORMALIZATION_POLICY_ID
    assert STOCK_NORMALIZATION_POLICY.models == (
        StockScoreModel.S0_LEVEL,
        StockScoreModel.S1_DELTA,
    )
    assert STOCK_NORMALIZATION_POLICY.epsilon == ExactRational(0, 1)
    assert STOCK_NORMALIZATION_POLICY.winsor_lower_probability == ExactRational(1, 100)
    assert STOCK_NORMALIZATION_POLICY.winsor_upper_probability == ExactRational(99, 100)
    assert STOCK_NORMALIZATION_POLICY.minimum_sector_peers == 20
    assert STOCK_NORMALIZATION_POLICY.mad_scale == ExactRational(7413, 5000)
    assert STOCK_NORMALIZATION_POLICY.to_payload()["post_score_clip"] is None
    assert STOCK_NORMALIZATION_POLICY.to_payload()["sector_fallback"] is None
    assert require_stock_normalization_policy(STOCK_NORMALIZATION_POLICY) is (
        STOCK_NORMALIZATION_POLICY
    )
    assert STOCK_NORMALIZATION_POLICY.preregistration_sha256 == before
    assert STOCK_NORMALIZATION_POLICY.sha256 == (
        "16074b0d27180f386057a6405b36cb1685f7565fb2cf2f81ad2263706147a66c"
    )
    assert STOCK_NORMALIZATION_POLICY.sha256 == hash_payload(
        STOCK_NORMALIZATION_POLICY.to_payload()
    )


def test_global_type7_bounds_and_sector_mad_match_exact_golden_oracle():
    scores = _scores()
    current = _current(scores)
    assert len(current) == 40
    cohort = current[0].cohort
    assert len(cohort.candidate_members) == len(cohort.eligible_members) == 40
    assert cohort.bounds_for(StockScoreModel.S0_LEVEL).lower == ExactRational(
        10039, 1000000
    )
    assert cohort.bounds_for(StockScoreModel.S0_LEVEL).upper == ExactRational(
        13861, 1000000
    )
    assert cohort.bounds_for(StockScoreModel.S1_DELTA).lower == ExactRational(
        -1461, 500000
    )
    assert cohort.bounds_for(StockScoreModel.S1_DELTA).upper == ExactRational(
        2361, 500000
    )

    technology = _by_security(scores, "sec-si3c-000")[0]
    healthcare = _by_security(scores, "sec-si3c-001")[0]
    technology_high = _by_security(scores, "sec-si3c-038")[0]
    healthcare_high = _by_security(scores, "sec-si3c-039")[0]
    tech_s0 = _model(technology, StockScoreModel.S0_LEVEL)
    health_s0 = _model(healthcare, StockScoreModel.S0_LEVEL)
    tech_s1 = _model(technology, StockScoreModel.S1_DELTA)
    health_s1 = _model(healthcare, StockScoreModel.S1_DELTA)
    assert (tech_s0.sector_median, tech_s0.sector_mad, tech_s0.scaled_mad) == (
        ExactRational(119, 10000),
        ExactRational(1, 1000),
        ExactRational(7413, 5000000),
    )
    assert (health_s0.sector_median, health_s0.sector_mad, health_s0.scaled_mad) == (
        ExactRational(3, 250),
        ExactRational(1, 1000),
        ExactRational(7413, 5000000),
    )
    assert (tech_s1.sector_median, tech_s1.sector_mad, tech_s1.scaled_mad) == (
        ExactRational(1, 1250),
        ExactRational(1, 500),
        ExactRational(7413, 2500000),
    )
    assert (health_s1.sector_median, health_s1.sector_mad, health_s1.scaled_mad) == (
        ExactRational(1, 1000),
        ExactRational(1, 500),
        ExactRational(7413, 2500000),
    )
    assert tech_s0.score == tech_s1.score == ExactRational(-9305, 7413)
    assert health_s0.score == health_s1.score == ExactRational(-9500, 7413)
    assert (
        _model(technology_high, StockScoreModel.S0_LEVEL).score
        == _model(technology_high, StockScoreModel.S1_DELTA).score
        == ExactRational(9500, 7413)
    )
    assert (
        _model(healthcare_high, StockScoreModel.S0_LEVEL).score
        == _model(healthcare_high, StockScoreModel.S1_DELTA).score
        == ExactRational(9305, 7413)
    )
    assert all(not _contains_float(item.to_payload()) for item in scores)


def test_s0_and_s1_share_prior_complete_members_but_not_bounds_or_statistics():
    scores = _scores()
    warmups = tuple(
        item for item in scores if item.current.readiness.settlement_date != CURRENT_SETTLEMENT
    )
    assert len(warmups) == 40
    assert all(
        outcome.refusal_reasons == (REFUSAL_MISSING_PRIOR,)
        for item in warmups
        for outcome in item.outcomes
    )
    for disposition in _current(scores):
        s0, s1 = disposition.outcomes
        assert s0.sector_members_sha256 == s1.sector_members_sha256
        assert s0.peer_count == s1.peer_count == 20
        assert (s0.winsor_lower, s0.winsor_upper) != (
            s1.winsor_lower,
            s1.winsor_upper,
        )
        assert s0.raw_feature_sha256 == s1.raw_feature_sha256
        assert s0.normalization_cohort_sha256 == s1.normalization_cohort_sha256


def test_underfilled_sector_is_excluded_before_global_winsor_bounds():
    extras = tuple(
        _Spec(
            index=index,
            sector="ENERGY",
            current_shares=20000 + index,
            prior_shares=100 + index,
        )
        for index in range(40, 59)
    )
    scores = _scores(_base_specs() + extras)
    cohort = _current(scores)[0].cohort
    assert len(cohort.candidate_members) == 59
    assert len(cohort.eligible_members) == 40
    assert cohort.bounds_for(StockScoreModel.S0_LEVEL).lower == ExactRational(
        10039, 1000000
    )
    assert cohort.bounds_for(StockScoreModel.S0_LEVEL).upper == ExactRational(
        13861, 1000000
    )
    energy = tuple(
        item
        for item in _current(scores)
        if item.current.readiness.sector_code == "ENERGY"
    )
    assert len(energy) == 19
    assert all(
        outcome.refusal_reasons == (REFUSAL_INSUFFICIENT_SECTOR_PEERS,)
        and outcome.peer_count == 19
        and outcome.score is None
        for item in energy
        for outcome in item.outcomes
    )


def test_twenty_unique_security_ids_score_and_nineteen_refuse():
    twenty = tuple(item for item in _base_specs() if item.index % 2 == 0)
    scored = _current(_scores(twenty))
    assert len(scored) == 20
    assert all(outcome.score is not None for item in scored for outcome in item.outcomes)

    refused = _current(_scores(twenty[:-1]))
    assert len(refused) == 19
    assert all(
        outcome.refusal_reasons == (REFUSAL_INSUFFICIENT_SECTOR_PEERS,)
        for item in refused
        for outcome in item.outcomes
    )


def test_zero_mad_refuses_only_the_affected_model_sector_without_epsilon():
    specs = tuple(
        replace(item, current_shares=item.prior_shares + 10)
        if item.sector == "TECHNOLOGY"
        else item
        for item in _base_specs()
    )
    technology = tuple(
        item
        for item in _current(_scores(specs))
        if item.current.readiness.sector_code == "TECHNOLOGY"
    )
    assert len(technology) == 20
    assert all(
        _model(item, StockScoreModel.S1_DELTA).refusal_reasons
        == (REFUSAL_ZERO_SECTOR_MAD,)
        and _model(item, StockScoreModel.S1_DELTA).sector_mad == ExactRational(0, 1)
        and _model(item, StockScoreModel.S1_DELTA).score is None
        and _model(item, StockScoreModel.S0_LEVEL).score is not None
        for item in technology
    )


def test_zero_mad_s0_refuses_only_s0_while_varied_s1_still_scores():
    specs = tuple(
        replace(item, current_shares=100)
        if item.sector == "TECHNOLOGY"
        else item
        for item in _base_specs()
    )
    technology = tuple(
        item
        for item in _current(_scores(specs))
        if item.current.readiness.sector_code == "TECHNOLOGY"
    )
    assert len(technology) == 20
    assert all(
        _model(item, StockScoreModel.S0_LEVEL).refusal_reasons
        == (REFUSAL_ZERO_SECTOR_MAD,)
        and _model(item, StockScoreModel.S0_LEVEL).score is None
        and _model(item, StockScoreModel.S1_DELTA).score is not None
        for item in technology
    )


def test_ratios_above_one_remain_uncapped_and_scores_are_not_post_clipped():
    specs = tuple(
        replace(item, current_shares=20000)
        if item.index == 38
        else item
        for item in _base_specs()
    )
    extreme = _by_security(_scores(specs), "sec-si3c-038")[0]
    s0 = _model(extreme, StockScoreModel.S0_LEVEL)
    assert s0.raw_value == ExactRational(2, 1)
    member = next(
        item
        for item in extreme.cohort.candidate_members
        if item.security_id == "sec-si3c-038"
    )
    assert member.s0_value == ExactRational(2, 1)
    assert extreme.cohort.bounds_for(StockScoreModel.S0_LEVEL).upper == (
        ExactRational(1225421, 1000000)
    )
    assert s0.winsorized_value.to_fraction() < s0.raw_value.to_fraction()
    assert s0.score == ExactRational(2022535, 2471)


def test_winsorization_occurs_before_sector_median_and_mad():
    technology_values = (0,) * 9 + (9900,) * 10 + (10000,)
    tech_position = 0
    specs = []
    for item in _base_specs():
        if item.sector == "TECHNOLOGY":
            shares = technology_values[tech_position]
            tech_position += 1
            specs.append(
                replace(item, current_shares=shares, prior_shares=shares)
            )
        else:
            specs.append(replace(item, prior_shares=item.current_shares))
    technology = _by_security(_scores(tuple(specs)), "sec-si3c-000")[0]
    s0 = _model(technology, StockScoreModel.S0_LEVEL)
    assert technology.cohort.bounds_for(StockScoreModel.S0_LEVEL).upper == (
        ExactRational(9961, 10000)
    )
    assert s0.sector_median == ExactRational(99, 100)
    assert s0.sector_mad == ExactRational(61, 20000)
    assert s0.sector_mad != ExactRational(1, 200)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("taxonomy_id", "SYNTHETIC_SECTOR_V2"),
        ("taxonomy_source_id", "synthetic-sector-master-v2"),
        ("taxonomy_source_version", "2024.v2"),
    ),
)
def test_mixed_taxonomy_lineage_refuses_the_whole_selected_cycle(field, value):
    specs = tuple(
        replace(item, **{field: value})
        if item.index == 0
        else item
        for item in _base_specs()
    )
    current = _current(_scores(specs))
    assert len(current[0].cohort.taxonomy_lineages) == 2
    assert not current[0].cohort.eligible_members
    assert all(
        outcome.refusal_reasons == (REFUSAL_MIXED_TAXONOMY_LINEAGE,)
        for item in current
        for outcome in item.outcomes
    )


def test_non_us_row_is_named_and_cannot_help_its_sector_reach_twenty():
    specs = tuple(
        replace(item, country="CA") if item.index == 0 else item
        for item in _base_specs()
    )
    scores = _scores(specs)
    non_us = _by_security(scores, "sec-si3c-000")[0]
    assert all(
        outcome.refusal_reasons == (REFUSAL_NON_US_SECURITY,)
        for outcome in non_us.outcomes
    )
    technology = tuple(
        item
        for item in _current(scores)
        if item.current.readiness.sector_code == "TECHNOLOGY"
        and item.current.readiness.security_id != "sec-si3c-000"
    )
    assert len(technology) == 19
    assert all(
        outcome.refusal_reasons == (REFUSAL_INSUFFICIENT_SECTOR_PEERS,)
        for item in technology
        for outcome in item.outcomes
    )
    healthcare = tuple(
        item
        for item in _current(scores)
        if item.current.readiness.sector_code == "HEALTHCARE"
    )
    assert all(outcome.score is not None for item in healthcare for outcome in item.outcomes)


def test_non_common_stock_is_named_and_cannot_supply_a_peer():
    specs = tuple(
        replace(item, security_type="PREFERRED_STOCK")
        if item.index == 0
        else item
        for item in _base_specs()
    )
    scores = _scores(specs)
    excluded = _by_security(scores, "sec-si3c-000")[0]
    assert all(
        outcome.refusal_reasons == (REFUSAL_NON_COMMON_STOCK_SECURITY,)
        for outcome in excluded.outcomes
    )
    technology = tuple(
        item
        for item in _current(scores)
        if item.current.readiness.sector_code == "TECHNOLOGY"
        and item.current.readiness.security_id != "sec-si3c-000"
    )
    assert len(technology) == 19
    assert all(
        outcome.refusal_reasons == (REFUSAL_INSUFFICIENT_SECTOR_PEERS,)
        for item in technology
        for outcome in item.outcomes
    )


def test_same_ticker_distinct_stable_ids_and_share_classes_count_separately():
    specs = tuple(
        replace(
            item,
            ticker="DUP",
            share_class="A" if position == 0 else "B",
        )
        if position < 2
        else item
        for position, item in enumerate(
            tuple(spec for spec in _base_specs() if spec.sector == "TECHNOLOGY")
        )
    )
    current = _current(_scores(specs))
    assert len(current) == 20
    cohort = current[0].cohort
    duplicate_ticker_members = tuple(
        item for item in cohort.candidate_members if item.ticker == "DUP"
    )
    assert len(duplicate_ticker_members) == 2
    assert len({item.security_id for item in duplicate_ticker_members}) == 2
    assert {item.share_class for item in duplicate_ticker_members} == {"A", "B"}
    assert all(outcome.score is not None for item in current for outcome in item.outcomes)


def test_pre_cutoff_correction_wins_once_and_binds_supersession_identity():
    scores = _scores(correction=(0, "2024-02-13T13:00:00Z"))
    rows = _by_security(scores, "sec-si3c-000")
    assert len(rows) == 2
    selected = next(
        item
        for item in rows
        if item.outcomes[0].revision_selection_state is RevisionSelectionState.SELECTED
    )
    superseded = next(item for item in rows if item is not selected)
    assert all(outcome.score is not None for outcome in selected.outcomes)
    assert all(
        outcome.refusal_reasons == (REFUSAL_SUPERSEDED_AT_RELEASE_CUTOFF,)
        for outcome in superseded.outcomes
    )
    member = next(
        item
        for item in selected.cohort.candidate_members
        if item.security_id == "sec-si3c-000"
    )
    assert member.event_id == selected.current.readiness.event_id
    assert member.supersedes_event_id == superseded.current.readiness.event_id
    assert len(selected.cohort.candidate_members) == 40
    assert all(outcome.peer_count == 20 for outcome in selected.outcomes)
    assert len(
        {
            (item.current.readiness.security_id, outcome.model)
            for item in rows
            for outcome in item.outcomes
            if outcome.score is not None
        }
    ) == 2


def test_post_cutoff_correction_is_retained_without_retroactive_second_score():
    baseline = _by_security(_scores(), "sec-si3c-000")[0]
    scores = _scores(correction=(0, "2024-02-13T16:00:00Z"))
    rows = _by_security(scores, "sec-si3c-000")
    assert len(rows) == 2
    selected = next(
        item
        for item in rows
        if item.outcomes[0].revision_selection_state is RevisionSelectionState.SELECTED
    )
    late = next(item for item in rows if item is not selected)
    assert all(outcome.score is not None for outcome in selected.outcomes)
    assert all(
        outcome.refusal_reasons == (REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF,)
        and outcome.score is None
        for outcome in late.outcomes
    )
    assert sum(
        outcome.score is not None
        for item in rows
        for outcome in item.outcomes
    ) == 2
    for baseline_outcome, selected_outcome in zip(
        baseline.outcomes, selected.outcomes, strict=True
    ):
        assert selected_outcome.normalization_slot_id == (
            baseline_outcome.normalization_slot_id
        )
        assert selected_outcome.raw_value == baseline_outcome.raw_value
        assert selected_outcome.winsor_lower == baseline_outcome.winsor_lower
        assert selected_outcome.winsor_upper == baseline_outcome.winsor_upper
        assert selected_outcome.score == baseline_outcome.score
    assert tuple(
        (item.security_id, item.event_id, item.s0_value, item.s1_value)
        for item in selected.cohort.candidate_members
    ) == tuple(
        (item.security_id, item.event_id, item.s0_value, item.s1_value)
        for item in baseline.cohort.candidate_members
    )


def test_correction_published_exactly_at_decision_open_is_not_visible_at_that_open():
    decision_at = _current(_scores())[0].cohort.decision_at
    scores = _scores(correction=(0, decision_at))
    rows = _by_security(scores, "sec-si3c-000")
    assert len(rows) == 2
    correction = next(
        item for item in rows if item.current.feature.current_snapshot.revision_id == "r2"
    )
    assert all(
        outcome.revision_selection_state is RevisionSelectionState.NOT_VISIBLE
        and outcome.refusal_reasons == (REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF,)
        for outcome in correction.outcomes
    )


def test_input_reordering_is_byte_identical_and_incomplete_or_duplicate_batches_fail():
    raw = _raw_batch(_base_specs())
    expected = build_pit_stock_normalized_scores(raw)
    reordered = build_pit_stock_normalized_scores(tuple(reversed(raw)))
    assert [item.to_payload() for item in reordered] == [
        item.to_payload() for item in expected
    ]
    assert [item.sha256 for item in reordered] == [item.sha256 for item in expected]
    with pytest.raises(StockNormalizationError, match="incomplete"):
        build_pit_stock_normalized_scores(raw[:-1])
    with pytest.raises(StockNormalizationError, match="duplicate readiness event_id"):
        build_pit_stock_normalized_scores(raw + (raw[0],))
    with pytest.raises(StockNormalizationError, match="exact tuple"):
        build_pit_stock_normalized_scores(list(raw))

    class TupleSubclass(tuple):
        pass

    with pytest.raises(StockNormalizationError, match="exact tuple"):
        build_pit_stock_normalized_scores(TupleSubclass(raw))


def test_contract_rejects_peer_injection_revision_recast_and_underfill_bounds():
    disposition = _current(_scores())[0]
    cohort = disposition.cohort
    forged_member = replace(
        cohort.candidate_members[1],
        s0_value=ExactRational(999, 1),
    )
    forged_members = (
        cohort.candidate_members[:1]
        + (forged_member,)
        + cohort.candidate_members[2:]
    )
    with pytest.raises((TypeError, ValueError), match="init=False"):
        replace(cohort, candidate_members=forged_members)

    s0 = disposition.outcomes[0]
    with pytest.raises(StockNormalizationError, match="revision state"):
        replace(
            s0,
            revision_selection_state=RevisionSelectionState.NOT_VISIBLE,
            selected_event_id=None,
            sector_code=None,
            sector_members=(),
            winsor_lower=None,
            winsor_upper=None,
            winsorized_value=None,
            sector_median=None,
            sector_mad=None,
            scaled_mad=None,
            score=None,
            refusal_reasons=(REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF,),
        )

    extras = tuple(
        _Spec(
            index=index,
            sector="ENERGY",
            current_shares=20000 + index,
            prior_shares=100 + index,
        )
        for index in range(40, 59)
    )
    energy = _by_security(_scores(_base_specs() + extras), "sec-si3c-040")[0]
    with pytest.raises(StockNormalizationError, match="winsor witness"):
        replace(
            energy.outcomes[0],
            winsor_lower=ExactRational(0, 1),
            winsor_upper=ExactRational(1, 1),
        )


@pytest.mark.parametrize(
    "case",
    ["duplicate_s0", "duplicate_s1", "missing_s1", "reversed_order", "empty"],
)
def test_disposition_requires_exactly_one_s0_then_one_s1_outcome(case):
    """Policy v1 allows one result per policy/release/security/model.

    The builder always emits S0 then S1, so only a hand-constructed or
    rehydrated disposition can violate this. Nothing downstream re-derives the
    model tuple: removing this guard admits a duplicated S0 that double-counts
    one model while silently dropping S1.
    """
    disposition = _current(_scores())[0]
    s0, s1 = disposition.outcomes
    assert (s0.model, s1.model) == (
        StockScoreModel.S0_LEVEL,
        StockScoreModel.S1_DELTA,
    )
    outcomes = {
        "duplicate_s0": (s0, s0),
        "duplicate_s1": (s1, s1),
        "missing_s1": (s0,),
        "reversed_order": (s1, s0),
        "empty": (),
    }[case]

    with pytest.raises(StockNormalizationError, match="exactly S0 then S1"):
        StockScoreDisposition(
            current=disposition.current,
            cohort=disposition.cohort,
            outcomes=outcomes,
        )


def test_mixed_release_calendar_lineages_for_one_settlement_fail_closed():
    with pytest.raises(StockNormalizationError, match="settlement cycle mixes"):
        build_pit_stock_normalized_scores(
            _raw_batch_with_two_release_keys_for_one_settlement()
        )


def test_score_contract_recomputes_tampered_statistics_and_policy_exact_type():
    disposition = _current(_scores())[0]
    s0, _ = disposition.outcomes
    with pytest.raises(StockNormalizationError, match="normalized score"):
        replace(s0, score=ExactRational(0, 1))

    class PolicySubclass(type(STOCK_NORMALIZATION_POLICY)):
        pass

    forged = object.__new__(PolicySubclass)
    for field in STOCK_NORMALIZATION_POLICY.__dataclass_fields__:
        object.__setattr__(forged, field, getattr(STOCK_NORMALIZATION_POLICY, field))
    with pytest.raises(StockNormalizationError, match="exact StockNormalizationPolicy"):
        require_stock_normalization_policy(forged)

    class IntSubclass(int):
        pass

    forged_exact_class = object.__new__(type(STOCK_NORMALIZATION_POLICY))
    for field in STOCK_NORMALIZATION_POLICY.__dataclass_fields__:
        object.__setattr__(
            forged_exact_class,
            field,
            getattr(STOCK_NORMALIZATION_POLICY, field),
        )
    object.__setattr__(
        forged_exact_class,
        "minimum_sector_peers",
        IntSubclass(20),
    )
    with pytest.raises(StockNormalizationError, match="minimum sector peers"):
        require_stock_normalization_policy(forged_exact_class)

    forged_rational = object.__new__(ExactRational)
    object.__setattr__(forged_rational, "numerator", IntSubclass(0))
    object.__setattr__(forged_rational, "denominator", IntSubclass(1))
    forged_nested = object.__new__(type(STOCK_NORMALIZATION_POLICY))
    for field in STOCK_NORMALIZATION_POLICY.__dataclass_fields__:
        object.__setattr__(
            forged_nested,
            field,
            getattr(STOCK_NORMALIZATION_POLICY, field),
        )
    object.__setattr__(forged_nested, "epsilon", forged_rational)
    with pytest.raises(StockNormalizationError, match="epsilon is not canonical"):
        require_stock_normalization_policy(forged_nested)

    class ModelSpoof:
        def __init__(self, value):
            self.value = value

        def __eq__(self, other):
            return True

    forged_models = object.__new__(type(STOCK_NORMALIZATION_POLICY))
    for field in STOCK_NORMALIZATION_POLICY.__dataclass_fields__:
        object.__setattr__(
            forged_models,
            field,
            getattr(STOCK_NORMALIZATION_POLICY, field),
        )
    object.__setattr__(
        forged_models,
        "models",
        (ModelSpoof("S0_level"), ModelSpoof("S1_delta")),
    )
    with pytest.raises(StockNormalizationError, match="frozen S0/S1 pair"):
        require_stock_normalization_policy(forged_models)

    class StrSubclass(str):
        pass

    with pytest.raises(StockNormalizationError, match="schema_version"):
        replace(disposition, schema_version=StrSubclass("1.0"))


def test_payloads_are_content_hashed_immutable_and_import_firewall_stays_local():
    scores = _scores()
    policy_payload = STOCK_NORMALIZATION_POLICY.to_payload()
    assert policy_payload["authority"] == "synthetic_structural_score_only"
    assert policy_payload["production_authoritative"] is False
    for disposition in scores:
        assert disposition.sha256 == hash_payload(disposition.to_payload())
        for outcome in disposition.outcomes:
            assert outcome.sha256 == hash_payload(outcome.to_payload())
            assert not _contains_float(outcome.to_payload())
            payload = outcome.to_payload()
            assert payload["authority"] == "synthetic_structural_score_only"
            assert payload["production_authoritative"] is False
            assert "market_cap_eligible" not in payload
            assert "liquidity_eligible" not in payload
            assert "trading_authorized" not in payload
    first = scores[0]
    before = first.sha256
    payload = first.to_payload()
    payload["outcomes"][0]["refusal_reasons"].append("caller_mutation")
    assert first.sha256 == before
    assert "caller_mutation" not in first.outcomes[0].refusal_reasons

    module_path = (
        Path(__file__).parents[1]
        / "research"
        / "short_interest_etf"
        / "stock_normalization.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "research.short_interest_etf.normalize" not in imported
    assert not {"numpy", "pandas", "statistics", "math"} & imported


def test_current_row_payload_scale_is_no_go_for_provider_scale():
    """Measure current row-list witness growth without a wall-clock benchmark."""
    samples = {}
    for count in (20, 40):
        scores = _scores(_single_sector_specs(count))
        current = _current(scores)
        assert len(current) == count
        assert all(
            outcome.score is not None and not outcome.refusal_reasons
            for disposition in current
            for outcome in disposition.outcomes
        )
        assert {
            disposition.cohort.normalization_policy_sha256
            for disposition in scores
        } == {STOCK_NORMALIZATION_POLICY.sha256}
        assert all(
            outcome.to_payload()["authority"] == STRUCTURAL_SCORE_AUTHORITY
            and outcome.to_payload()["production_authoritative"] is False
            for disposition in scores
            for outcome in disposition.outcomes
        )

        metrics = _scale_metrics(scores)
        assert metrics.disposition_count == 2 * count
        assert metrics.unique_cohort_count == 2
        assert metrics.cohort_payload_occurrences == 2 * count
        assert metrics.outcome_count == 4 * count
        assert metrics.raw_inventory_embeddings == 4 * count**2
        assert metrics.candidate_member_embeddings == count**2
        assert metrics.eligible_member_embeddings == count**2
        assert metrics.sector_member_embeddings == 2 * count**2
        assert metrics.total_repeated_witnesses == 8 * count**2
        assert metrics.canonical_payload_bytes > 0
        assert len(metrics.payload_sha256) == 64
        samples[count] = metrics

    small = samples[20]
    large = samples[40]
    for field in (
        "raw_inventory_embeddings",
        "candidate_member_embeddings",
        "eligible_member_embeddings",
        "sector_member_embeddings",
        "total_repeated_witnesses",
    ):
        assert getattr(large, field) == 4 * getattr(small, field)
    assert large.unique_cohort_count == small.unique_cohort_count
    assert large.canonical_payload_bytes > 3 * small.canonical_payload_bytes
