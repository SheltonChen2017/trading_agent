"""Dangerous-direction tests for exact SI-3C S0/S1 normalization."""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import lru_cache
from fractions import Fraction
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_payload
import research.short_interest_etf.stock_score_batch as stock_score_batch_module
from research.short_interest_etf.contracts import (
    ReleasePrecision,
    parse_utc_timestamp,
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
    StockModelOutcome,
    StockScoreDisposition,
    StockScoreModel,
    build_pit_stock_normalized_scores,
    require_stock_normalization_policy,
)
from research.short_interest_etf.stock_score_batch import (
    STOCK_SCORE_BATCH_AUTHORITY,
    STOCK_SCORE_BATCH_SCHEMA_VERSION,
    STOCK_SCORE_BATCH_V2_SCHEMA_VERSION,
    STOCK_SCORE_BATCH_V2_VERIFICATION_SCHEMA_VERSION,
    STOCK_SCORE_BATCH_VERIFICATION_SCHEMA_VERSION,
    StockScoreBatchEnvelope,
    StockScoreBatchEnvelopeV2,
    StockScoreBatchError,
    StockScoreBatchVerification,
    StockScoreBatchVerificationV2,
    build_stock_score_batch_envelope,
    build_stock_score_batch_envelope_v2,
    verify_compact_stock_score_batch_payload,
    verify_compact_stock_score_batch_payload_v2,
    verify_stock_score_batch_payload,
    verify_stock_score_batch_payload_v2,
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
def _single_sector_scores(count: int) -> tuple[StockScoreDisposition, ...]:
    return _scores(_single_sector_specs(count))


@lru_cache(maxsize=None)
def _multi_cycle_scores(
    cycle_count: int,
    security_count: int = 20,
) -> tuple[StockScoreDisposition, ...]:
    """Extend the tracked two-cycle fixture deterministically in memory."""
    if cycle_count not in (2, 4):
        raise ValueError("synthetic scale characterization supports 2 or 4 cycles")

    specs = _single_sector_specs(security_count)
    base = _raw_batch(specs)
    if cycle_count == 2:
        return build_pit_stock_normalized_scores(base)

    source_context = base[0].source_context
    vintage = source_context.source_vintage
    exact_release_template = next(
        item
        for item in vintage.release_calendar
        if item.precision is ReleasePrecision.EXACT_TIMESTAMP
    )
    appended_cycle_specs = (
        (
            "2024-02-15",
            "2024-01-16",
            "2024-02-22",
            "2024-02-27",
            "2024-02-27T20:00:00Z",
            "2024-02-27T21:00:00Z",
            "2024-02-27T22:00:00Z",
        ),
        (
            "2024-02-29",
            "2024-01-30",
            "2024-03-07",
            "2024-03-11",
            "2024-03-11T20:00:00Z",
            "2024-03-11T21:00:00Z",
            "2024-03-11T22:00:00Z",
        ),
    )
    snapshots = list(vintage.snapshots)
    releases = list(vintage.release_calendar)
    previous_by_security = {
        item.security.security_id: item
        for item in vintage.snapshots
        if item.settlement_date == CURRENT_SETTLEMENT
    }

    for cycle_offset, (
        settlement_date,
        volume_window_start,
        filing_deadline_date,
        public_release_date,
        available_at,
        published_at,
        observed_at,
    ) in enumerate(appended_cycle_specs, start=2):
        release = replace(
            exact_release_template,
            settlement_date=settlement_date,
            filing_deadline_date=filing_deadline_date,
            public_release_date=public_release_date,
            public_release_at=published_at,
            precision=ReleasePrecision.EXACT_TIMESTAMP,
            evidence_sha256=_sha(f"multi-cycle-release-{settlement_date}"),
            observed_at=observed_at,
        )
        releases.append(release)

        for spec in specs:
            security_id = f"sec-si3c-{spec.index:03d}"
            previous = previous_by_security[security_id]
            current_shares = (
                previous.current_short_shares + cycle_offset + spec.index + 3
            )
            volume = replace(
                previous.volume_basis,
                window_start_date=volume_window_start,
                window_end_date=settlement_date,
                available_at=available_at,
                observed_at=observed_at,
                raw_record_sha256=_sha(
                    f"multi-cycle-volume-{settlement_date}-{security_id}"
                ),
            )
            denominator = replace(
                previous.denominator,
                effective_date=settlement_date,
                available_at=available_at,
                observed_at=observed_at,
                raw_record_sha256=_sha(
                    f"multi-cycle-denominator-{settlement_date}-{security_id}"
                ),
            )
            days_to_cover = recompute_days_to_cover(
                current_shares,
                volume.average_daily_share_volume,
            )
            current = replace(
                previous,
                source_record_id=(
                    f"synthetic-si3c-{spec.index:03d}-{settlement_date}-r1"
                ),
                settlement_date=settlement_date,
                current_short_shares=current_shares,
                previous_settlement_date=previous.settlement_date,
                previous_short_shares=previous.current_short_shares,
                release_calendar_key=release.key,
                volume_basis=volume,
                reported_days_to_cover=days_to_cover,
                recomputed_days_to_cover=days_to_cover,
                denominator=denominator,
                revision_id="r1",
                revision_published_at=published_at,
                observed_at=observed_at,
                supersedes_event_id=None,
                raw_record_sha256=_sha(
                    f"multi-cycle-snapshot-{settlement_date}-{security_id}"
                ),
            )
            snapshots.append(current)
            previous_by_security[security_id] = current

    manifest = replace(
        vintage.manifest,
        source_dataset_id="synthetic-si3c-normalization-4-cycle-v1",
        snapshot_name="synthetic-si3c-four-cycle-scale-characterization",
        retrieved_at=appended_cycle_specs[-1][-1],
        settlement_end=appended_cycle_specs[-1][0],
        requested_record_count=len(snapshots),
        input_row_count=len(snapshots),
        accepted_record_count=len(snapshots),
        raw_artifact_sha256=hash_payload(
            [item.to_payload() for item in snapshots]
        ),
    )
    extended_vintage = build_vintage(
        manifest,
        tuple(releases),
        tuple(snapshots),
    )
    reference_bundle = source_context.reference_bundle
    extended_references = PitReferenceBundle(
        manifest=replace(
            reference_bundle.manifest,
            reference_dataset_id="synthetic-si3c-pit-reference-4-cycle-v1",
            retrieved_at="2024-03-12T22:00:00Z",
        ),
        lifecycles=reference_bundle.lifecycles,
        classifications=reference_bundle.classifications,
    )
    raw_features = build_pit_stock_raw_features(
        extended_vintage,
        extended_references,
    )
    return build_pit_stock_normalized_scores(raw_features)


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


def _compact_witness_count(payload: dict) -> int:
    return sum(
        len(record["cohort"]["raw_disposition_inventory"])
        for record in payload["cohorts"]
    ) + sum(len(record["members"]) for record in payload["member_sets"])


def _tamper_score_batch(payload: dict, case: str) -> dict:
    tampered = deepcopy(payload)
    if case == "unknown_envelope_field":
        tampered["unexpected"] = True
    elif case == "missing_cohort":
        tampered["cohorts"].pop()
        tampered["cohort_count"] -= 1
    elif case == "substituted_member_reference":
        outcome = tampered["rows"][0]["outcomes"][0]
        original = outcome["sector_members_sha256"]
        outcome["sector_members_sha256"] = next(
            record["members_sha256"]
            for record in tampered["member_sets"]
            if record["members_sha256"] != original
        )
    elif case == "omitted_row":
        tampered["rows"].pop()
        tampered["row_count"] -= 1
    elif case == "duplicate_member_record":
        tampered["member_sets"].append(deepcopy(tampered["member_sets"][0]))
        tampered["member_set_count"] += 1
    elif case == "orphan_member_record":
        members = [{"synthetic_orphan": True}]
        tampered["member_sets"].append(
            {"members": members, "members_sha256": hash_payload(members)}
        )
        tampered["member_sets"].sort(key=lambda item: item["members_sha256"])
        tampered["member_set_count"] += 1
    else:
        raise AssertionError(f"unknown tamper case: {case}")
    return tampered


def _tamper_v2_score_batch(payload: dict, case: str) -> dict:
    tampered = deepcopy(payload)
    inventory_record = tampered["raw_inventory_sets"][0]
    inventory = inventory_record["raw_disposition_inventory"]
    if case == "unknown_envelope_field":
        tampered["unexpected"] = True
    elif case == "inventory_count_mismatch":
        tampered["raw_inventory_set_count"] = 2
    elif case == "stale_inventory_item":
        inventory[0]["sha256"] = "0" * 64
    elif case == "reordered_inventory":
        inventory.reverse()
    elif case == "missing_inventory_record":
        tampered["raw_inventory_sets"].clear()
        tampered["raw_inventory_set_count"] = 0
    elif case == "missing_inventory_reference":
        tampered["cohorts"][0]["cohort"]["raw_dispositions_sha256"] = "0" * 64
    elif case == "duplicate_inventory_record":
        tampered["raw_inventory_sets"].append(deepcopy(inventory_record))
        tampered["raw_inventory_set_count"] = 2
    elif case == "orphan_inventory_record":
        orphan_inventory = [{"event_id": "synthetic-orphan", "sha256": "0" * 64}]
        tampered["raw_inventory_sets"].append(
            {
                "raw_disposition_inventory": orphan_inventory,
                "raw_dispositions_sha256": hash_payload(orphan_inventory),
            }
        )
        tampered["raw_inventory_sets"].sort(
            key=lambda item: item["raw_dispositions_sha256"]
        )
        tampered["raw_inventory_set_count"] = 2
    elif case == "duplicate_inventory_pair":
        inventory.append(deepcopy(inventory[0]))
        replacement = hash_payload(inventory)
        inventory_record["raw_dispositions_sha256"] = replacement
        for record in tampered["cohorts"]:
            record["cohort"]["raw_dispositions_sha256"] = replacement
    elif case == "rehash_substituted_inventory":
        inventory[0]["sha256"] = "0" * 64
        replacement = hash_payload(inventory)
        inventory_record["raw_dispositions_sha256"] = replacement
        for record in tampered["cohorts"]:
            record["cohort"]["raw_dispositions_sha256"] = replacement
    elif case == "omitted_row":
        tampered["rows"].pop()
        tampered["row_count"] -= 1
    else:
        raise AssertionError(f"unknown V2 tamper case: {case}")
    return tampered


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
    [
        "duplicate_s0",
        "duplicate_s1",
        "missing_s0",
        "missing_s1",
        "reversed_order",
        "extra_s0",
        "extra_s1",
        "empty",
    ],
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
        "missing_s0": (s1,),
        "missing_s1": (s0,),
        "reversed_order": (s1, s0),
        "extra_s0": (s0, s1, s0),
        "extra_s1": (s0, s1, s1),
        "empty": (),
    }[case]

    with pytest.raises(StockNormalizationError, match="exactly S0 then S1"):
        StockScoreDisposition(
            current=disposition.current,
            cohort=disposition.cohort,
            outcomes=outcomes,
        )


@pytest.mark.parametrize("case", ["list", "tuple_subclass", "outcome_subclass"])
def test_disposition_requires_exact_tuple_of_exact_outcome_types(case):
    disposition = _current(_scores())[0]
    s0, s1 = disposition.outcomes

    if case == "list":
        outcomes = [s0, s1]
    elif case == "tuple_subclass":
        class TupleSubclass(tuple):
            pass

        outcomes = TupleSubclass((s0, s1))
    else:
        class OutcomeSubclass(StockModelOutcome):
            pass

        forged_s0 = object.__new__(OutcomeSubclass)
        for field_name in s0.__dataclass_fields__:
            object.__setattr__(forged_s0, field_name, getattr(s0, field_name))
        outcomes = (forged_s0, s1)

    with pytest.raises(
        StockNormalizationError,
        match="exact tuple of exact model outcomes",
    ):
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


@pytest.mark.parametrize(
    ("count", "legacy_digest", "envelope_digest"),
    [
        (
            20,
            "efe0ef91822a20d3dda680269d792644157058a5a4e7660a7cf7143f3cbf1299",
            "82f579b6b91e9ed6917fb4da24509e4d7fd0a6fb0de18367c807b4242fc5637a",
        ),
        (
            40,
            "b4701c5040dbec2151adec42d1f9dca4436b6f900d9d8676be842faee0a2c9df",
            "6eae0887c46daf401ae8a2b5acd0aa4bec1693da5c9625d4841c7649324a3f0d",
        ),
    ],
)
def test_compact_score_batch_is_lossless_canonical_and_non_authoritative(
    count,
    legacy_digest,
    envelope_digest,
):
    scores = _single_sector_scores(count)
    envelope = build_stock_score_batch_envelope(scores)
    payload = envelope.to_payload()
    legacy_rows = tuple(item.to_payload() for item in scores)

    assert type(envelope) is StockScoreBatchEnvelope
    assert payload["schema_version"] == STOCK_SCORE_BATCH_SCHEMA_VERSION
    assert payload["authority"] == STOCK_SCORE_BATCH_AUTHORITY
    assert payload["production_authoritative"] is False
    assert payload["normalization_policy_sha256"] == STOCK_NORMALIZATION_POLICY.sha256
    assert payload["preregistration_sha256"] == (
        STOCK_NORMALIZATION_POLICY.preregistration_sha256
    )
    assert payload["row_count"] == 2 * count
    assert payload["cohort_count"] == 2
    assert payload["canonical_row_list_sha256"] == legacy_digest
    assert envelope.canonical_row_list_sha256 == legacy_digest
    assert envelope.sha256 == envelope_digest
    assert envelope.expanded_row_payloads() == legacy_rows
    assert verify_stock_score_batch_payload(
        payload,
        dispositions=scores,
    ) == legacy_rows
    assert not _contains_float(payload)
    assert any(
        outcome["refusal_reasons"]
        for row in legacy_rows
        for outcome in row["outcomes"]
    )
    assert any(
        not outcome["refusal_reasons"]
        for row in legacy_rows
        for outcome in row["outcomes"]
    )
    assert all(
        "candidate_members" not in record["cohort"]
        and "eligible_members" not in record["cohort"]
        for record in payload["cohorts"]
    )
    assert all(
        "sector_members" not in outcome
        for row in payload["rows"]
        for outcome in row["outcomes"]
    )

    before = envelope.sha256
    payload["rows"][0]["current"]["refusal_reasons"].append("caller_mutation")
    assert envelope.sha256 == before
    assert "caller_mutation" not in envelope.to_payload()["rows"][0]["current"][
        "refusal_reasons"
    ]


def test_compact_score_batch_streams_legacy_digest_and_native_verification(
    monkeypatch,
):
    scores = _single_sector_scores(20)
    expected_legacy_digest = hash_payload([item.to_payload() for item in scores])
    original_hash_payload = stock_score_batch_module.hash_payload
    original_validate_payload = stock_score_batch_module._validate_payload
    original_array_sha256 = stock_score_batch_module._canonical_json_array_sha256

    def refuse_full_legacy_row_list(payload):
        if (
            type(payload) is list
            and payload
            and type(payload[0]) is dict
            and frozenset(payload[0])
            == frozenset({"cohort", "current", "outcomes", "schema_version"})
        ):
            raise AssertionError("full legacy row list must not be hashed at once")
        return original_hash_payload(payload)

    def refuse_legacy_expansion(_payload):
        raise AssertionError("compact path must not call legacy expansion")

    def require_non_materializing_validation(payload, *, materialize_rows):
        if materialize_rows is not False:
            raise AssertionError("compact path must validate without legacy rows")
        return original_validate_payload(payload, materialize_rows=False)

    def require_lazy_row_iterable(values):
        if type(values) in (list, tuple):
            raise AssertionError("legacy rows must enter the hasher lazily")
        return original_array_sha256(values)

    monkeypatch.setattr(
        stock_score_batch_module,
        "hash_payload",
        refuse_full_legacy_row_list,
    )
    monkeypatch.setattr(
        stock_score_batch_module,
        "_expand_payload",
        refuse_legacy_expansion,
    )
    monkeypatch.setattr(
        stock_score_batch_module,
        "_validate_payload",
        require_non_materializing_validation,
    )
    monkeypatch.setattr(
        stock_score_batch_module,
        "_canonical_json_array_sha256",
        require_lazy_row_iterable,
    )

    envelope = build_stock_score_batch_envelope(scores)
    payload = envelope.to_payload()
    receipt = verify_compact_stock_score_batch_payload(
        payload,
        dispositions=scores,
    )

    assert type(receipt) is StockScoreBatchVerification
    assert receipt.schema_version == STOCK_SCORE_BATCH_VERIFICATION_SCHEMA_VERSION
    assert receipt.authority == STOCK_SCORE_BATCH_AUTHORITY
    assert receipt.production_authoritative is False
    assert receipt.row_count == len(scores)
    assert receipt.canonical_row_list_sha256 == expected_legacy_digest
    assert receipt.envelope_sha256 == envelope.sha256
    assert receipt.to_payload()["envelope_sha256"] == envelope.sha256
    assert receipt.sha256 == hash_payload(receipt.to_payload())


def test_compact_verification_receipt_is_exact_typed_and_non_authoritative():
    scores = _single_sector_scores(20)
    envelope = build_stock_score_batch_envelope(scores)
    receipt = verify_compact_stock_score_batch_payload(
        envelope.to_payload(),
        dispositions=scores,
    )

    class StrSubclass(str):
        pass

    invalid_replacements = (
        ({"row_count": True}, "positive exact int"),
        (
            {"canonical_row_list_sha256": StrSubclass("0" * 64)},
            "exact str",
        ),
        ({"envelope_sha256": "not-a-digest"}, "SHA-256"),
        (
            {
                "schema_version": StrSubclass(
                    STOCK_SCORE_BATCH_VERIFICATION_SCHEMA_VERSION
                )
            },
            "schema_version",
        ),
        ({"authority": StrSubclass(STOCK_SCORE_BATCH_AUTHORITY)}, "authority"),
        ({"production_authoritative": 0}, "non-production"),
    )
    for changes, message in invalid_replacements:
        with pytest.raises(StockScoreBatchError, match=message):
            replace(receipt, **changes)


def test_compact_verification_receipt_hashes_the_authenticated_snapshot(
    monkeypatch,
):
    scores = _single_sector_scores(20)
    envelope = build_stock_score_batch_envelope(scores)
    payload = envelope.to_payload()
    original_canonical_json = stock_score_batch_module.canonical_json
    mutated = False

    def mutate_caller_after_serialization(value):
        nonlocal mutated
        serialized = original_canonical_json(value)
        if value is payload and not mutated:
            payload["authority"] = "mutated-after-authentication"
            mutated = True
        return serialized

    monkeypatch.setattr(
        stock_score_batch_module,
        "canonical_json",
        mutate_caller_after_serialization,
    )
    receipt = verify_compact_stock_score_batch_payload(
        payload,
        dispositions=scores,
    )

    assert mutated is True
    assert payload["authority"] == "mutated-after-authentication"
    assert receipt.envelope_sha256 == envelope.sha256
    assert receipt.envelope_sha256 != hash_payload(payload)


def test_streamed_canonical_array_digest_matches_canonical_json_oracle(monkeypatch):
    values = (
        {"nested": [1, True, None, {"unicode": "雪"}]},
        {"ordered_by_encoder": {"z": 0, "a": "é"}},
    )
    original_canonical_json = stock_score_batch_module.canonical_json
    yielded_count = 0
    encoded_count = 0

    def one_at_a_time():
        nonlocal yielded_count
        for value in values:
            if yielded_count != encoded_count:
                raise AssertionError(
                    "array helper consumed another item before encoding the prior item"
                )
            yielded_count += 1
            yield value

    def count_canonical_encoding(value):
        nonlocal encoded_count
        result = original_canonical_json(value)
        encoded_count += 1
        return result

    monkeypatch.setattr(
        stock_score_batch_module,
        "canonical_json",
        count_canonical_encoding,
    )
    assert stock_score_batch_module._canonical_json_array_sha256(one_at_a_time()) == (
        hash_payload(list(values))
    )
    assert yielded_count == encoded_count == len(values)


def test_compact_score_batch_is_input_order_independent_and_strictly_typed():
    scores = _single_sector_scores(20)
    expected = build_stock_score_batch_envelope(scores)
    reordered = build_stock_score_batch_envelope(tuple(reversed(scores)))
    assert reordered.to_payload() == expected.to_payload()
    assert reordered.sha256 == expected.sha256

    class TupleSubclass(tuple):
        pass

    class DispositionSubclass(StockScoreDisposition):
        pass

    forged = object.__new__(DispositionSubclass)
    for field_name in scores[0].__dataclass_fields__:
        object.__setattr__(forged, field_name, getattr(scores[0], field_name))

    for invalid in (list(scores), TupleSubclass(scores), (forged,)):
        with pytest.raises(StockScoreBatchError, match="exact tuple of exact"):
            build_stock_score_batch_envelope(invalid)
    with pytest.raises(StockScoreBatchError, match="cannot be empty"):
        build_stock_score_batch_envelope(())
    with pytest.raises(StockScoreBatchError, match="incomplete"):
        build_stock_score_batch_envelope(scores[:-1])
    with pytest.raises(StockScoreBatchError, match="duplicate disposition"):
        build_stock_score_batch_envelope(scores + (scores[0],))

    alternate_specs = tuple(
        _Spec(
            index=100 + index,
            sector="TECHNOLOGY",
            current_shares=200 + index,
            prior_shares=230 - index,
        )
        for index in range(20)
    )
    alternate = _scores(alternate_specs)
    with pytest.raises(StockScoreBatchError, match="mixes authenticated lineage"):
        build_stock_score_batch_envelope(scores + alternate)


@pytest.mark.parametrize(
    "case",
    [
        "unknown_envelope_field",
        "missing_cohort",
        "substituted_member_reference",
        "omitted_row",
        "duplicate_member_record",
        "orphan_member_record",
    ],
)
def test_compact_score_batch_refuses_tampering(case):
    scores = _single_sector_scores(20)
    payload = build_stock_score_batch_envelope(scores).to_payload()
    tampered = _tamper_score_batch(payload, case)
    with pytest.raises(StockScoreBatchError):
        verify_compact_stock_score_batch_payload(
            tampered,
            dispositions=scores,
        )
    with pytest.raises(StockScoreBatchError):
        verify_stock_score_batch_payload(
            tampered,
            dispositions=scores,
        )


def test_compact_score_batch_refuses_subclassed_payload_containers():
    scores = _single_sector_scores(20)
    canonical = build_stock_score_batch_envelope(scores).to_payload()

    class DictSubclass(dict):
        pass

    class ListSubclass(list):
        pass

    class StrSubclass(str):
        pass

    class IntSubclass(int):
        pass

    with pytest.raises(StockScoreBatchError, match="exact dict"):
        verify_stock_score_batch_payload(
            DictSubclass(canonical),
            dispositions=scores,
        )
    payload = deepcopy(canonical)
    payload["rows"] = ListSubclass(payload["rows"])
    with pytest.raises(StockScoreBatchError, match="exact non-float JSON"):
        verify_stock_score_batch_payload(payload, dispositions=scores)

    nested_attacks = []
    payload = deepcopy(canonical)
    payload["schema_version"] = StrSubclass(payload["schema_version"])
    nested_attacks.append(payload)
    payload = deepcopy(canonical)
    payload["rows"][0]["schema_version"] = StrSubclass(
        payload["rows"][0]["schema_version"]
    )
    nested_attacks.append(payload)
    payload = deepcopy(canonical)
    payload["rows"][0]["current"]["refusal_reasons"] = ListSubclass(
        payload["rows"][0]["current"]["refusal_reasons"]
    )
    nested_attacks.append(payload)
    payload = deepcopy(canonical)
    payload["rows"][0]["outcomes"][0]["authority"] = StrSubclass(
        payload["rows"][0]["outcomes"][0]["authority"]
    )
    nested_attacks.append(payload)
    payload = deepcopy(canonical)
    payload["rows"][0]["outcomes"][0]["peer_count"] = IntSubclass(
        payload["rows"][0]["outcomes"][0]["peer_count"]
    )
    nested_attacks.append(payload)
    payload = deepcopy(canonical)
    nonempty = next(
        record for record in payload["member_sets"] if record["members"]
    )
    nonempty["members"][0] = DictSubclass(nonempty["members"][0])
    nested_attacks.append(payload)
    payload = deepcopy(canonical)
    outcome = payload["rows"][0]["outcomes"][0]
    authority = outcome.pop("authority")
    outcome[StrSubclass("authority")] = authority
    nested_attacks.append(payload)

    for payload in nested_attacks:
        with pytest.raises(
            StockScoreBatchError,
            match="exact non-float JSON|keys must be exact str",
        ):
            verify_stock_score_batch_payload(payload, dispositions=scores)


def test_compact_score_batch_refuses_recursive_payload_containers():
    scores = _single_sector_scores(20)
    payload = build_stock_score_batch_envelope(scores).to_payload()
    reasons = payload["rows"][0]["current"]["refusal_reasons"]
    reasons.append(reasons)
    with pytest.raises(StockScoreBatchError, match="recursive container"):
        verify_stock_score_batch_payload(payload, dispositions=scores)


def test_compact_score_batch_requires_the_exact_authenticated_rows():
    scores = _single_sector_scores(20)
    alternate = _single_sector_scores(40)
    payload = build_stock_score_batch_envelope(alternate).to_payload()
    with pytest.raises(StockScoreBatchError, match="authenticated dispositions"):
        verify_stock_score_batch_payload(payload, dispositions=scores)


def test_compact_score_batch_preserves_role_specific_multisector_witnesses():
    scores = _scores()
    envelope = build_stock_score_batch_envelope(scores)
    payload = envelope.to_payload()
    assert envelope.expanded_row_payloads() == tuple(
        item.to_payload() for item in scores
    )
    assert payload["row_count"] == 80
    assert payload["cohort_count"] == 2
    assert payload["member_set_count"] == 4

    member_sizes = {
        record["members_sha256"]: len(record["members"])
        for record in payload["member_sets"]
    }
    assert sorted(member_sizes.values()) == [0, 20, 20, 40]
    cohorts = {
        record["cohort_sha256"]: record["cohort"]
        for record in payload["cohorts"]
    }
    scored_rows = [
        row
        for row in payload["rows"]
        if all(outcome["score"] is not None for outcome in row["outcomes"])
    ]
    assert len(scored_rows) == 40
    candidate_digests = {
        cohorts[row["cohort_sha256"]]["candidate_members_sha256"]
        for row in scored_rows
    }
    sector_digests = {
        outcome["sector_members_sha256"]
        for row in scored_rows
        for outcome in row["outcomes"]
    }
    assert len(candidate_digests) == 1
    assert {member_sizes[digest] for digest in candidate_digests} == {40}
    assert len(sector_digests) == 2
    assert {member_sizes[digest] for digest in sector_digests} == {20}
    assert candidate_digests.isdisjoint(sector_digests)


@pytest.mark.parametrize(
    ("builder", "builder_name"),
    [
        (build_stock_score_batch_envelope, "_build_payload"),
        (build_stock_score_batch_envelope_v2, "_build_payload_v2"),
    ],
    ids=("v1", "v2"),
)
def test_compact_score_batch_distinguishes_candidate_eligible_and_sector_roles(
    monkeypatch,
    builder,
    builder_name,
):
    import research.short_interest_etf.stock_score_batch as score_batch_module

    sectors = (
        ("TECHNOLOGY", 20),
        ("HEALTHCARE", 20),
        ("ENERGY", 19),
    )
    specs = []
    for sector, count in sectors:
        for _ in range(count):
            index = len(specs)
            specs.append(
                _Spec(
                    index=index,
                    sector=sector,
                    current_shares=200 + index,
                    prior_shares=300 - index,
                )
            )

    scores = _scores(tuple(specs))
    envelope = builder(scores)
    payload = envelope.to_payload()
    member_sizes = {
        record["members_sha256"]: len(record["members"])
        for record in payload["member_sets"]
    }
    cohorts = [record["cohort"] for record in payload["cohorts"]]
    candidate_digests = {
        cohort["candidate_members_sha256"] for cohort in cohorts
        if member_sizes[cohort["candidate_members_sha256"]] > 0
    }
    eligible_digests = {
        cohort["eligible_members_sha256"] for cohort in cohorts
        if member_sizes[cohort["eligible_members_sha256"]] > 0
    }
    sector_digests = {
        outcome["sector_members_sha256"]
        for row in payload["rows"]
        for outcome in row["outcomes"]
        if outcome["score"] is not None
    }

    assert {member_sizes[digest] for digest in candidate_digests} == {59}
    assert {member_sizes[digest] for digest in eligible_digests} == {40}
    assert {member_sizes[digest] for digest in sector_digests} == {20}
    assert candidate_digests.isdisjoint(eligible_digests)
    assert candidate_digests.isdisjoint(sector_digests)
    assert eligible_digests.isdisjoint(sector_digests)
    assert envelope.expanded_row_payloads() == tuple(
        item.to_payload() for item in scores
    )

    original_build_payload = getattr(score_batch_module, builder_name)

    def alias_candidate_as_eligible(dispositions):
        mutated = original_build_payload(dispositions)
        for record in mutated["cohorts"]:
            cohort = record["cohort"]
            if (
                cohort["candidate_members_sha256"]
                != cohort["eligible_members_sha256"]
            ):
                cohort["eligible_members_sha256"] = cohort[
                    "candidate_members_sha256"
                ]
        return mutated

    monkeypatch.setattr(
        score_batch_module,
        builder_name,
        alias_candidate_as_eligible,
    )
    with pytest.raises(StockScoreBatchError, match="expanded.*cohort"):
        builder(scores)


def test_compact_score_batch_stores_repeated_witnesses_linearly():
    samples = {}
    for count in (20, 40):
        scores = _single_sector_scores(count)
        legacy = _scale_metrics(scores)
        payload = build_stock_score_batch_envelope(scores).to_payload()
        compact_bytes = len(canonical_json(payload).encode("utf-8"))
        compact_witnesses = _compact_witness_count(payload)
        assert compact_witnesses > 0
        assert compact_bytes < legacy.canonical_payload_bytes
        assert payload["cohort_count"] == 2
        assert payload["member_set_count"] == len(payload["member_sets"])
        assert [record["cohort_sha256"] for record in payload["cohorts"]] == sorted(
            record["cohort_sha256"] for record in payload["cohorts"]
        )
        assert [
            record["members_sha256"] for record in payload["member_sets"]
        ] == sorted(record["members_sha256"] for record in payload["member_sets"])
        samples[count] = (compact_witnesses, compact_bytes)

    small_witnesses, small_bytes = samples[20]
    large_witnesses, large_bytes = samples[40]
    assert large_witnesses == 2 * small_witnesses
    assert large_bytes < 3 * small_bytes


def test_compact_score_batch_characterizes_multi_cycle_inventory_growth():
    """Pin the remaining C-squared inventory term without timing thresholds."""
    security_count = 20
    samples = {}
    for cycle_count in (2, 4):
        scores = _multi_cycle_scores(cycle_count, security_count)
        expected_security_ids = {
            f"sec-si3c-{index:03d}" for index in range(security_count)
        }
        security_ids_by_settlement = {}
        for disposition in scores:
            readiness = disposition.current.readiness
            security_ids_by_settlement.setdefault(
                readiness.settlement_date,
                set(),
            ).add(readiness.security_id)
        envelope = build_stock_score_batch_envelope(scores)
        payload = envelope.to_payload()
        inventories = [
            record["cohort"]["raw_disposition_inventory"]
            for record in payload["cohorts"]
        ]
        inventory_digests = {
            record["cohort"]["raw_dispositions_sha256"]
            for record in payload["cohorts"]
        }
        stored_inventory_entries = sum(len(items) for items in inventories)
        unique_inventory_entries = len(inventories[0])
        member_entries = sum(
            len(record["members"]) for record in payload["member_sets"]
        )

        assert len(scores) == cycle_count * security_count
        assert len(security_ids_by_settlement) == cycle_count
        assert all(
            security_ids == expected_security_ids
            for security_ids in security_ids_by_settlement.values()
        )
        reference_retrieved_at = parse_utc_timestamp(
            scores[0].current.source_context.reference_bundle.manifest.retrieved_at,
            "reference_manifest.retrieved_at",
        )
        assert all(
            parse_utc_timestamp(
                disposition.cohort.decision_at,
                "cohort.decision_at",
            )
            <= reference_retrieved_at
            for disposition in scores
        )
        assert payload["row_count"] == cycle_count * security_count
        assert payload["cohort_count"] == cycle_count
        assert payload["member_set_count"] == cycle_count
        assert len(inventories) == cycle_count
        assert all(
            len(items) == cycle_count * security_count
            for items in inventories
        )
        assert len(inventory_digests) == 1
        assert all(
            hash_payload(items) in inventory_digests for items in inventories
        )
        assert stored_inventory_entries == cycle_count**2 * security_count
        assert unique_inventory_entries == cycle_count * security_count
        assert stored_inventory_entries // unique_inventory_entries == cycle_count
        assert member_entries == (cycle_count - 1) * security_count
        assert payload["normalization_policy_sha256"] == (
            STOCK_NORMALIZATION_POLICY.sha256
        )
        assert payload["preregistration_sha256"] == (
            STOCK_NORMALIZATION_POLICY.preregistration_sha256
        )
        assert payload["authority"] == STOCK_SCORE_BATCH_AUTHORITY
        assert payload["production_authoritative"] is False

        receipt = verify_compact_stock_score_batch_payload(
            payload,
            dispositions=scores,
        )
        assert receipt.row_count == cycle_count * security_count
        assert receipt.canonical_row_list_sha256 == (
            envelope.canonical_row_list_sha256
        )
        assert receipt.envelope_sha256 == envelope.sha256
        samples[cycle_count] = (
            stored_inventory_entries,
            len(canonical_json(payload).encode("utf-8")),
            envelope.canonical_row_list_sha256,
            envelope.sha256,
        )

    assert samples[4][0] == 4 * samples[2][0]


def test_compact_score_batch_stays_out_of_the_canonical_package_exports():
    package_path = (
        Path(__file__).parents[1]
        / "research"
        / "short_interest_etf"
        / "__init__.py"
    )
    tree = ast.parse(package_path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "research.short_interest_etf.stock_score_batch" not in imported


@pytest.mark.parametrize(
    (
        "cycle_count",
        "legacy_digest",
        "v1_envelope_digest",
        "v2_envelope_digest",
        "v2_canonical_bytes",
    ),
    [
        (
            2,
            "efe0ef91822a20d3dda680269d792644157058a5a4e7660a7cf7143f3cbf1299",
            "82f579b6b91e9ed6917fb4da24509e4d7fd0a6fb0de18367c807b4242fc5637a",
            "0089de9bf817ae8f37eb0d6c4ea79ccc4bdfa4ddc38015d06a08053546f9fb8b",
            352841,
        ),
        (
            4,
            "19f3b85aa3c601ca6f66253042a64799592b946624b940ed83012d6218fb6fd0",
            "cbf25e6f67a6e9e545644a3233876bf600ab996c2cbe842750d06620fb539901",
            "de12ce1bf1c85cb63608a9b8ed99fc7e5666959dd2886d5bb836c1fd8da87678",
            892667,
        ),
    ],
)
def test_v2_score_batch_is_lossless_content_addressed_and_non_authoritative(
    cycle_count,
    legacy_digest,
    v1_envelope_digest,
    v2_envelope_digest,
    v2_canonical_bytes,
):
    security_count = 20
    scores = _multi_cycle_scores(cycle_count, security_count)
    legacy_rows = tuple(item.to_payload() for item in scores)
    v1 = build_stock_score_batch_envelope(scores)
    v2 = build_stock_score_batch_envelope_v2(scores)
    payload = v2.to_payload()

    assert type(v2) is StockScoreBatchEnvelopeV2
    assert payload["schema_version"] == STOCK_SCORE_BATCH_V2_SCHEMA_VERSION
    assert payload["authority"] == STOCK_SCORE_BATCH_AUTHORITY
    assert payload["production_authoritative"] is False
    assert payload["normalization_policy_sha256"] == STOCK_NORMALIZATION_POLICY.sha256
    assert payload["preregistration_sha256"] == (
        STOCK_NORMALIZATION_POLICY.preregistration_sha256
    )
    assert payload["row_count"] == cycle_count * security_count
    assert payload["cohort_count"] == cycle_count
    assert payload["raw_inventory_set_count"] == 1
    assert len(payload["raw_inventory_sets"]) == 1
    inventory_record = payload["raw_inventory_sets"][0]
    inventory = inventory_record["raw_disposition_inventory"]
    assert len(inventory) == cycle_count * security_count
    assert hash_payload(inventory) == inventory_record["raw_dispositions_sha256"]
    assert {
        record["cohort"]["raw_dispositions_sha256"]
        for record in payload["cohorts"]
    } == {inventory_record["raw_dispositions_sha256"]}
    assert all(
        "raw_disposition_inventory" not in record["cohort"]
        for record in payload["cohorts"]
    )
    assert payload["canonical_row_list_sha256"] == legacy_digest
    assert v2.canonical_row_list_sha256 == legacy_digest
    assert v1.canonical_row_list_sha256 == legacy_digest
    assert v1.sha256 == v1_envelope_digest
    assert v2.sha256 == v2_envelope_digest
    assert len(canonical_json(payload).encode("utf-8")) == v2_canonical_bytes
    assert v2_canonical_bytes < len(
        canonical_json(v1.to_payload()).encode("utf-8")
    )
    assert v2.expanded_row_payloads() == legacy_rows
    assert verify_stock_score_batch_payload_v2(
        payload,
        dispositions=scores,
    ) == legacy_rows
    receipt = verify_compact_stock_score_batch_payload_v2(
        payload,
        dispositions=scores,
    )
    assert type(receipt) is StockScoreBatchVerificationV2
    assert receipt.schema_version == STOCK_SCORE_BATCH_V2_VERIFICATION_SCHEMA_VERSION
    assert receipt.row_count == len(scores)
    assert receipt.canonical_row_list_sha256 == legacy_digest
    assert receipt.envelope_sha256 == v2.sha256
    assert not _contains_float(payload)


def test_v2_serialized_inventory_scales_with_rows_not_cohorts_times_rows():
    samples = {}
    for cycle_count in (2, 4):
        scores = _multi_cycle_scores(cycle_count, 20)
        v1_payload = build_stock_score_batch_envelope(scores).to_payload()
        v2_payload = build_stock_score_batch_envelope_v2(scores).to_payload()
        v1_entries = sum(
            len(record["cohort"]["raw_disposition_inventory"])
            for record in v1_payload["cohorts"]
        )
        v2_entries = sum(
            len(record["raw_disposition_inventory"])
            for record in v2_payload["raw_inventory_sets"]
        )
        assert v1_entries == cycle_count**2 * 20
        assert v2_entries == cycle_count * 20
        assert v2_payload["raw_inventory_set_count"] == 1
        samples[cycle_count] = (v1_entries, v2_entries)

    assert samples[4][0] == 4 * samples[2][0]
    assert samples[4][1] == 2 * samples[2][1]


def test_v1_and_v2_score_batch_schemas_are_strictly_separate():
    scores = _single_sector_scores(20)
    v1 = build_stock_score_batch_envelope(scores)
    v2 = build_stock_score_batch_envelope_v2(scores)

    assert v1.schema_version == STOCK_SCORE_BATCH_SCHEMA_VERSION
    assert v2.schema_version == STOCK_SCORE_BATCH_V2_SCHEMA_VERSION
    assert v1.sha256 == (
        "82f579b6b91e9ed6917fb4da24509e4d7fd0a6fb0de18367c807b4242fc5637a"
    )
    with pytest.raises(StockScoreBatchError, match="frozen schema"):
        verify_compact_stock_score_batch_payload(
            v2.to_payload(),
            dispositions=scores,
        )
    with pytest.raises(StockScoreBatchError, match="frozen schema"):
        verify_stock_score_batch_payload(
            v2.to_payload(),
            dispositions=scores,
        )
    with pytest.raises(StockScoreBatchError, match="frozen schema"):
        verify_compact_stock_score_batch_payload_v2(
            v1.to_payload(),
            dispositions=scores,
        )
    with pytest.raises(StockScoreBatchError, match="frozen schema"):
        verify_stock_score_batch_payload_v2(
            v1.to_payload(),
            dispositions=scores,
        )


def test_v2_score_batch_is_input_order_independent_and_cache_is_immutable():
    scores = _single_sector_scores(20)
    expected = build_stock_score_batch_envelope_v2(scores)
    reordered = build_stock_score_batch_envelope_v2(tuple(reversed(scores)))
    assert reordered.to_payload() == expected.to_payload()
    assert reordered.sha256 == expected.sha256

    payload = expected.to_payload()
    original_sha256 = expected.sha256
    payload["raw_inventory_sets"][0]["raw_disposition_inventory"][0][
        "sha256"
    ] = "0" * 64
    assert expected.sha256 == original_sha256
    assert expected.to_payload()["raw_inventory_sets"][0][
        "raw_disposition_inventory"
    ][0]["sha256"] != "0" * 64

    with pytest.raises(StockScoreBatchError, match="exact tuple of exact"):
        build_stock_score_batch_envelope_v2(list(scores))
    with pytest.raises(StockScoreBatchError, match="cannot be empty"):
        build_stock_score_batch_envelope_v2(())
    with pytest.raises(StockScoreBatchError, match="incomplete"):
        build_stock_score_batch_envelope_v2(scores[:-1])
    with pytest.raises(StockScoreBatchError, match="duplicate disposition"):
        build_stock_score_batch_envelope_v2(scores + (scores[0],))


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unknown_envelope_field", "frozen schema"),
        ("inventory_count_mismatch", "count does not match"),
        ("stale_inventory_item", "content digest"),
        ("reordered_inventory", "content digest"),
        ("missing_inventory_record", "positive exact int"),
        ("missing_inventory_reference", "missing raw inventory set"),
        ("duplicate_inventory_record", "duplicate digest"),
        ("orphan_inventory_record", "orphan record"),
        ("duplicate_inventory_pair", "duplicate references"),
        ("rehash_substituted_inventory", "expanded V2 cohort"),
        ("omitted_row", "incomplete for its shared raw inventory"),
    ],
)
def test_v2_score_batch_refuses_inventory_and_envelope_tampering(case, message):
    scores = _single_sector_scores(20)
    payload = build_stock_score_batch_envelope_v2(scores).to_payload()
    tampered = _tamper_v2_score_batch(payload, case)
    with pytest.raises(StockScoreBatchError, match=message):
        verify_compact_stock_score_batch_payload_v2(
            tampered,
            dispositions=scores,
        )
    with pytest.raises(StockScoreBatchError, match=message):
        verify_stock_score_batch_payload_v2(
            tampered,
            dispositions=scores,
        )


def test_v2_score_batch_refuses_exact_type_and_recursive_payload_attacks():
    scores = _single_sector_scores(20)
    canonical = build_stock_score_batch_envelope_v2(scores).to_payload()

    class DictSubclass(dict):
        pass

    class ListSubclass(list):
        pass

    class StrSubclass(str):
        pass

    class IntSubclass(int):
        pass

    with pytest.raises(StockScoreBatchError, match="exact dict"):
        verify_compact_stock_score_batch_payload_v2(
            DictSubclass(canonical),
            dispositions=scores,
        )

    attacks = []
    payload = deepcopy(canonical)
    payload["raw_inventory_sets"] = ListSubclass(payload["raw_inventory_sets"])
    attacks.append(payload)
    payload = deepcopy(canonical)
    payload["raw_inventory_set_count"] = IntSubclass(1)
    attacks.append(payload)
    payload = deepcopy(canonical)
    payload["raw_inventory_sets"][0]["raw_dispositions_sha256"] = StrSubclass(
        payload["raw_inventory_sets"][0]["raw_dispositions_sha256"]
    )
    attacks.append(payload)
    payload = deepcopy(canonical)
    payload["raw_inventory_sets"][0]["raw_disposition_inventory"][0][
        "unexpected_float"
    ] = 1.0
    attacks.append(payload)
    for payload in attacks:
        with pytest.raises(StockScoreBatchError, match="exact non-float JSON"):
            verify_compact_stock_score_batch_payload_v2(
                payload,
                dispositions=scores,
            )

    payload = deepcopy(canonical)
    inventory = payload["raw_inventory_sets"][0]["raw_disposition_inventory"]
    inventory.append(inventory)
    with pytest.raises(StockScoreBatchError, match="recursive container"):
        verify_compact_stock_score_batch_payload_v2(
            payload,
            dispositions=scores,
        )


def test_v2_compact_paths_stream_and_do_not_retain_legacy_expansions(monkeypatch):
    scores = _single_sector_scores(20)
    expected_legacy_digest = hash_payload([item.to_payload() for item in scores])
    original_hash_payload = stock_score_batch_module.hash_payload
    original_validate_v2 = stock_score_batch_module._validate_payload_v2
    original_array_sha256 = stock_score_batch_module._canonical_json_array_sha256
    original_deepcopy = stock_score_batch_module.deepcopy

    def refuse_v1_builder(_dispositions):
        raise AssertionError("V2 must be built directly rather than through V1")

    def refuse_full_legacy_row_list(value):
        if (
            type(value) is list
            and value
            and type(value[0]) is dict
            and frozenset(value[0])
            == frozenset({"cohort", "current", "outcomes", "schema_version"})
        ):
            raise AssertionError("full legacy row list must not be hashed at once")
        return original_hash_payload(value)

    def refuse_legacy_expansion(_payload):
        raise AssertionError("compact V2 path must not call legacy expansion")

    def require_non_materializing_validation(payload, *, materialize_rows):
        if materialize_rows is not False:
            raise AssertionError("compact V2 validation must not retain legacy rows")
        validated = original_validate_v2(payload, materialize_rows=False)
        assert validated.expanded_rows is None
        return validated

    def require_lazy_row_iterable(values):
        if type(values) in (list, tuple):
            raise AssertionError("legacy V2 rows must enter the hasher lazily")
        return original_array_sha256(values)

    def refuse_raw_inventory_deepcopy(value, memo=None):
        if (
            type(value) is list
            and value
            and type(value[0]) is dict
            and frozenset(value[0]) == frozenset({"event_id", "sha256"})
        ):
            raise AssertionError("compact V2 validation copied a raw inventory")
        if memo is None:
            return original_deepcopy(value)
        return original_deepcopy(value, memo)

    monkeypatch.setattr(stock_score_batch_module, "_build_payload", refuse_v1_builder)
    monkeypatch.setattr(
        stock_score_batch_module,
        "hash_payload",
        refuse_full_legacy_row_list,
    )
    monkeypatch.setattr(
        stock_score_batch_module,
        "_expand_payload_v2",
        refuse_legacy_expansion,
    )
    monkeypatch.setattr(
        stock_score_batch_module,
        "_validate_payload_v2",
        require_non_materializing_validation,
    )
    monkeypatch.setattr(
        stock_score_batch_module,
        "_canonical_json_array_sha256",
        require_lazy_row_iterable,
    )
    monkeypatch.setattr(
        stock_score_batch_module,
        "deepcopy",
        refuse_raw_inventory_deepcopy,
    )

    envelope = build_stock_score_batch_envelope_v2(scores)
    receipt = verify_compact_stock_score_batch_payload_v2(
        envelope.to_payload(),
        dispositions=scores,
    )
    assert receipt.canonical_row_list_sha256 == expected_legacy_digest
    assert receipt.envelope_sha256 == envelope.sha256


def test_v2_verification_receipt_is_exact_typed_and_non_authoritative():
    scores = _single_sector_scores(20)
    envelope = build_stock_score_batch_envelope_v2(scores)
    receipt = verify_compact_stock_score_batch_payload_v2(
        envelope.to_payload(),
        dispositions=scores,
    )
    assert receipt.to_payload() == {
        "authority": STOCK_SCORE_BATCH_AUTHORITY,
        "canonical_row_list_sha256": envelope.canonical_row_list_sha256,
        "envelope_sha256": envelope.sha256,
        "production_authoritative": False,
        "row_count": len(scores),
        "schema_version": STOCK_SCORE_BATCH_V2_VERIFICATION_SCHEMA_VERSION,
    }
    assert receipt.sha256 == hash_payload(receipt.to_payload())

    class StrSubclass(str):
        pass

    invalid_replacements = (
        ({"row_count": True}, "positive exact int"),
        (
            {"canonical_row_list_sha256": StrSubclass("0" * 64)},
            "exact str",
        ),
        ({"envelope_sha256": "not-a-digest"}, "SHA-256"),
        (
            {
                "schema_version": StrSubclass(
                    STOCK_SCORE_BATCH_V2_VERIFICATION_SCHEMA_VERSION
                )
            },
            "schema_version",
        ),
        ({"schema_version": "wrong-schema"}, "schema_version"),
        ({"authority": StrSubclass(STOCK_SCORE_BATCH_AUTHORITY)}, "authority"),
        ({"authority": "wrong-authority"}, "authority"),
        ({"production_authoritative": 0}, "non-production"),
    )
    for changes, message in invalid_replacements:
        with pytest.raises(StockScoreBatchError, match=message):
            replace(receipt, **changes)


def test_v2_envelope_metadata_is_exact_typed_and_non_authoritative():
    scores = _single_sector_scores(20)
    envelope = build_stock_score_batch_envelope_v2(scores)

    class StrSubclass(str):
        pass

    invalid_replacements = (
        (
            {"schema_version": StrSubclass(STOCK_SCORE_BATCH_V2_SCHEMA_VERSION)},
            "schema_version",
        ),
        ({"schema_version": "wrong-schema"}, "schema_version"),
        (
            {"authority": StrSubclass(STOCK_SCORE_BATCH_AUTHORITY)},
            "authority",
        ),
        ({"authority": "wrong-authority"}, "authority"),
        ({"production_authoritative": 0}, "non-production"),
        ({"production_authoritative": True}, "non-production"),
    )
    for changes, message in invalid_replacements:
        with pytest.raises(StockScoreBatchError, match=message):
            replace(envelope, **changes)


def test_v2_verification_receipt_hashes_the_authenticated_snapshot(monkeypatch):
    scores = _single_sector_scores(20)
    envelope = build_stock_score_batch_envelope_v2(scores)
    payload = envelope.to_payload()
    original_canonical_json = stock_score_batch_module.canonical_json
    mutated = False

    def mutate_caller_after_serialization(value):
        nonlocal mutated
        serialized = original_canonical_json(value)
        if value is payload and not mutated:
            payload["authority"] = "mutated-after-authentication"
            mutated = True
        return serialized

    monkeypatch.setattr(
        stock_score_batch_module,
        "canonical_json",
        mutate_caller_after_serialization,
    )
    receipt = verify_compact_stock_score_batch_payload_v2(
        payload,
        dispositions=scores,
    )

    assert mutated is True
    assert payload["authority"] == "mutated-after-authentication"
    assert receipt.envelope_sha256 == envelope.sha256
    assert receipt.envelope_sha256 != hash_payload(payload)


def test_v2_score_batch_requires_the_exact_authenticated_rows():
    scores = _single_sector_scores(20)
    alternate = _single_sector_scores(40)
    payload = build_stock_score_batch_envelope_v2(alternate).to_payload()
    with pytest.raises(StockScoreBatchError, match="authenticated dispositions"):
        verify_compact_stock_score_batch_payload_v2(
            payload,
            dispositions=scores,
        )


@pytest.mark.parametrize(
    ("builder", "verifier"),
    [
        (build_stock_score_batch_envelope, verify_stock_score_batch_payload),
        (build_stock_score_batch_envelope_v2, verify_stock_score_batch_payload_v2),
    ],
    ids=("v1", "v2"),
)
def test_expanding_score_batch_verifier_returns_only_authenticated_rows(
    monkeypatch,
    builder,
    verifier,
):
    scores = _single_sector_scores(20)
    alternate = _single_sector_scores(40)
    expected_rows = tuple(item.to_payload() for item in scores)
    payload = builder(scores).to_payload()
    alternate_payload = builder(alternate).to_payload()
    original_canonical_json = stock_score_batch_module.canonical_json
    swapped = False

    def swap_caller_after_authenticated_serialization(value):
        nonlocal swapped
        serialized = original_canonical_json(value)
        if value is payload and not swapped:
            payload.clear()
            payload.update(deepcopy(alternate_payload))
            swapped = True
        return serialized

    monkeypatch.setattr(
        stock_score_batch_module,
        "canonical_json",
        swap_caller_after_authenticated_serialization,
    )
    returned_rows = verifier(payload, dispositions=scores)

    assert swapped is True
    assert payload == alternate_payload
    assert returned_rows == expected_rows
    assert len(returned_rows) == len(scores)


@pytest.mark.parametrize(
    ("builder", "verifier", "validator_name"),
    [
        (
            build_stock_score_batch_envelope,
            verify_compact_stock_score_batch_payload,
            "_validate_compact_payload",
        ),
        (
            build_stock_score_batch_envelope_v2,
            verify_compact_stock_score_batch_payload_v2,
            "_validate_compact_payload_v2",
        ),
    ],
    ids=("v1", "v2"),
)
def test_compact_score_batch_receipt_uses_one_authenticated_snapshot(
    monkeypatch,
    builder,
    verifier,
    validator_name,
):
    scores = _single_sector_scores(20)
    alternate = _single_sector_scores(40)
    payload = builder(alternate).to_payload()
    expected_payload = builder(scores).to_payload()
    original_validator = getattr(stock_score_batch_module, validator_name)
    swapped = False

    def validate_then_swap(candidate):
        nonlocal swapped
        validated = original_validator(candidate)
        payload.clear()
        payload.update(deepcopy(expected_payload))
        swapped = True
        return validated

    monkeypatch.setattr(
        stock_score_batch_module,
        validator_name,
        validate_then_swap,
    )
    with pytest.raises(StockScoreBatchError, match="authenticated dispositions"):
        verifier(payload, dispositions=scores)
    assert swapped is True
