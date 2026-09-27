"""Synthetic next-open eligible reranking; never a selected seed or outcome look."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from functools import lru_cache

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.dataset import build_vintage
from research.short_interest_etf.stock_covering import build_pit_stock_covering_scores
from research.short_interest_etf.stock_eligible_ranking import (
    StockEligibleRankingError,
    StockEligibleRankingInventory,
    build_stock_eligible_ranking_inventory,
)
from research.short_interest_etf.stock_eligible_population import (
    build_stock_eligible_population_inventory,
)
from research.short_interest_etf.stock_features import build_pit_stock_raw_features
from research.short_interest_etf.stock_investability import (
    SyntheticMarketHistory,
    build_stock_investability,
)
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
    build_pit_stock_normalized_scores,
)
from research.short_interest_etf.stock_population_binding import (
    StockPopulationBindingInventory,
    build_stock_population_binding_inventory,
)
from tests.test_short_interest_stock_normalization import (
    _raw_batch,
    _single_sector_specs,
)
from tests.test_short_interest_stock_population_binding import (
    _multi_security_population,
)
from tests.test_short_interest_stock_investability import _inputs


LOOKBACKS = (20, 60, 120, 252)
NEXT_OPEN = "2024-02-13T14:30:00Z"
SETTLEMENT = "2024-01-31"


def _rational(value: dict[str, int]) -> Fraction:
    assert type(value) is dict
    assert set(value) == {"numerator", "denominator"}
    assert all(type(part) is int for part in value.values())
    return Fraction(value["numerator"], value["denominator"])


def _current_rankings(payload: dict) -> dict[int, dict]:
    return {
        row["lookback_sessions"]: row
        for row in payload["rankings"]
        if row["settlement_date"] == SETTLEMENT
        and row["decision_at"] == NEXT_OPEN
    }


@lru_cache(maxsize=1)
def _nineteen_population():
    return _multi_security_population(20, refused_index=19)


@lru_cache(maxsize=1)
def _nineteen_binding():
    return build_stock_population_binding_inventory(_nineteen_population())


@lru_cache(maxsize=1)
def _nineteen_ranking():
    return build_stock_eligible_ranking_inventory(_nineteen_binding())


@lru_cache(maxsize=1)
def _nineteen_payload():
    return _nineteen_ranking().to_payload()


@lru_cache(maxsize=1)
def _small_ranking():
    return build_stock_eligible_ranking_inventory(
        build_stock_population_binding_inventory(_multi_security_population(1))
    )


@lru_cache(maxsize=1)
def _nine_ranking():
    source = _multi_security_population(20).evidence
    caps = tuple(replace(
        row,
        market_cap_usd="299999999",
        raw_record_sha256=hash_payload({"below_floor": row.security_id, "session": row.session}),
    ) if int(row.security_id[-3:]) >= 9 else row
        for row in source.history.capitalizations)
    history = SyntheticMarketHistory(source.history.daily, caps)
    population = build_stock_eligible_population_inventory(
        build_stock_investability(source.vintage, source.references, history)
    )
    return build_stock_eligible_ranking_inventory(
        build_stock_population_binding_inventory(population)
    )


@lru_cache(maxsize=1)
def _late_ranking():
    population = _multi_security_population(
        20, (0, "2024-02-14T15:00:00Z"), -1,
    )
    binding = build_stock_population_binding_inventory(population)
    return binding, build_stock_eligible_ranking_inventory(binding)


@lru_cache(maxsize=1)
def _lookback_split_ranking():
    source = _multi_security_population(20).evidence
    target = "sec-si3c-019"
    target_sessions = sorted(
        row.session for row in source.history.daily if row.security_id == target
    )
    missing = target_sessions[-30]
    daily = tuple(
        row for row in source.history.daily
        if (row.security_id, row.session) != (target, missing)
    )
    population = build_stock_eligible_population_inventory(
        build_stock_investability(
            source.vintage,
            source.references,
            SyntheticMarketHistory(daily, source.history.capitalizations),
        )
    )
    return build_stock_eligible_ranking_inventory(
        build_stock_population_binding_inventory(population)
    )


@lru_cache(maxsize=1)
def _later_only_binding():
    """A legitimate release can have no evidence visible at its canonical open."""
    vintage, references, history = _inputs()
    published = "2024-02-14T15:00:00Z"
    snapshots = tuple(
        replace(
            snapshot,
            revision_published_at=published,
            observed_at=published,
            raw_record_sha256=hash_payload({"all_late": snapshot.event_id}),
        ) if snapshot.settlement_date == SETTLEMENT else snapshot
        for snapshot in vintage.snapshots
    )
    manifest = replace(
        vintage.manifest,
        raw_artifact_sha256=hash_payload([item.to_payload() for item in snapshots]),
    )
    source = build_vintage(manifest, vintage.release_calendar, snapshots)
    extra_daily = tuple(
        replace(
            history.daily[-1],
            session=session,
            available_at=f"{session}T23:00:00Z",
            observed_at=f"{session}T23:00:00Z",
            raw_record_sha256=hash_payload({"all_late_daily": session}),
        ) for session in ("2024-02-13", "2024-02-14")
    )
    extra_cap = replace(
        history.capitalizations[-1],
        session="2024-02-14",
        available_at="2024-02-14T23:00:00Z",
        observed_at="2024-02-14T23:00:00Z",
        raw_record_sha256=hash_payload({"all_late_cap": "2024-02-14"}),
    )
    evidence = build_stock_investability(
        source,
        references,
        SyntheticMarketHistory(
            (*history.daily, *extra_daily),
            (*history.capitalizations, extra_cap),
        ),
    )
    return build_stock_population_binding_inventory(
        build_stock_eligible_population_inventory(evidence)
    )


@lru_cache(maxsize=1)
def _tie_ranking():
    specs = list(_single_sector_specs(20))
    specs[1] = replace(
        specs[1],
        current_shares=specs[0].current_shares,
        prior_shares=specs[0].prior_shares,
    )
    raw = _raw_batch(tuple(specs))
    source = _multi_security_population(20).evidence
    context = raw[0].source_context
    population = build_stock_eligible_population_inventory(
        build_stock_investability(
            context.source_vintage,
            context.reference_bundle,
            source.history,
        )
    )
    return build_stock_eligible_ranking_inventory(
        build_stock_population_binding_inventory(population)
    )


def test_owner_frozen_offline_ranking_api_exists():
    assert issubclass(StockEligibleRankingError, ValueError)
    assert hasattr(StockEligibleRankingInventory, "to_payload")
    assert callable(build_stock_eligible_ranking_inventory)


def test_four_candidate_rankings_keep_existing_normalization_and_hashes():
    binding = _nineteen_binding().to_payload()
    payload = _nineteen_payload()
    assert payload["source_binding_sha256"] == binding["inventory_sha256"]
    assert payload["policy"]["candidate_lookbacks"] == list(LOOKBACKS)
    assert payload["policy_sha256"] == hash_payload(payload["policy"])
    assert payload["inventory_sha256"] == hash_payload({
        key: value for key, value in payload.items() if key != "inventory_sha256"
    })
    assert payload["selected_lookback"] is None
    for name in ("seed_authorized", "outcome_authorized", "production_authoritative"):
        assert payload[name] is False

    canonical = {
        item["settlement_date"]: item["normalization_cohort_sha256"]
        for item in binding["normalization_cohorts"]
    }
    rankings = _current_rankings(payload)
    assert set(rankings) == set(LOOKBACKS)
    assert STOCK_NORMALIZATION_POLICY.minimum_sector_peers == 20
    for row in rankings.values():
        assert row["decision_at"] == NEXT_OPEN
        assert row["normalization_cohort_sha256"] == canonical[SETTLEMENT]
        assert len(row["eligible_event_ids"]) == 19
        assert row["ranked_event_ids"] == row["eligible_event_ids"]
        assert row["ranking_sha256"] == hash_payload({
            key: value for key, value in row.items() if key != "ranking_sha256"
        })


def test_ranks_are_recomputed_on_nineteen_eligible_scores_not_filtered_structural_percentiles():
    population = _nineteen_population()
    rankings = _current_rankings(_nineteen_payload())
    reference = rankings[20]
    eligible = set(reference["ranked_event_ids"])
    evidence = population.evidence
    normalized = build_pit_stock_normalized_scores(
        build_pit_stock_raw_features(evidence.vintage, evidence.references)
    )
    covering = build_pit_stock_covering_scores(normalized)
    expected = {}
    for source in covering.projections:
        if source.settlement_date != SETTLEMENT or source.event_id not in eligible:
            continue
        assert source.decision_at == NEXT_OPEN
        assert source.source_s1_score is not None
        assert source.covering_score is not None
        expected[source.event_id, "pressure"] = source.source_s1_score.to_fraction()
        expected[source.event_id, "covering"] = source.covering_score.to_fraction()
    assert len(expected) == 38

    for lookback, ranking in rankings.items():
        assert lookback in LOOKBACKS
        rows = ranking["rows"]
        assert len(rows) == 38
        assert {(row["event_id"], row["role"]) for row in rows} == set(expected)
        for row in rows:
            key = row["event_id"], row["role"]
            score = expected[key]
            values = [value for (event, role), value in expected.items() if role == row["role"]]
            lower = sum(value < score for value in values)
            equal = sum(value == score for value in values)
            higher = sum(value > score for value in values)
            exact_percentile = Fraction(2 * lower + equal, 2 * len(values))
            assert _rational(row["score"]) == score
            assert (
                row["strictly_lower_count"], row["equal_count"],
                row["strictly_higher_count"], row["scoreable_count"],
            ) == (lower, equal, higher, 19)
            assert _rational(row["role_percentile"]) == exact_percentile
            assert row["threshold_candidate"] is (exact_percentile >= Fraction(9, 10))


def test_nine_eligible_scores_have_percentiles_but_no_threshold_or_seed_classification():
    rankings = _current_rankings(_nine_ranking().to_payload())
    assert set(rankings) == set(LOOKBACKS)
    for ranking in rankings.values():
        assert len(ranking["eligible_event_ids"]) == 9
        assert len(ranking["ranked_event_ids"]) == 9
        assert len(ranking["rows"]) == 18
        assert ranking["underfill_reasons"]
        for row in ranking["rows"]:
            assert row["scoreable_count"] == 9
            assert row["threshold_candidate"] is None
            assert _rational(row["role_percentile"]) > 0


def test_missing_history_affects_only_its_lookback_denominators():
    rankings = _current_rankings(_lookback_split_ranking().to_payload())
    assert set(rankings) == set(LOOKBACKS)
    assert len(rankings[20]["ranked_event_ids"]) == 20
    assert len(rankings[20]["rows"]) == 40
    assert {row["scoreable_count"] for row in rankings[20]["rows"]} == {20}
    for lookback in (60, 120, 252):
        row = rankings[lookback]
        assert len(row["ranked_event_ids"]) == 19
        assert len(row["rows"]) == 38
        assert {item["scoreable_count"] for item in row["rows"]} == {19}
        assert set(row["ranked_event_ids"]).issubset(rankings[20]["ranked_event_ids"])


def test_later_arriving_eligible_revision_is_explicitly_excluded_from_next_open_ranks():
    binding, inventory = _late_ranking()
    late = {
        row["lookback_sessions"]: row
        for row in binding.to_payload()["bindings"]
        if row["settlement_date"] == SETTLEMENT
        and row["eligibility_cutoff_at"] == "2024-02-15T14:30:00Z"
    }
    rankings = _current_rankings(inventory.to_payload())
    assert set(late) == set(rankings) == set(LOOKBACKS)
    for lookback, ranking in rankings.items():
        late_event = late[lookback]["eligible_event_ids"][0]
        original_event = late[lookback]["members"][0]["selected_event_id"]
        assert late_event != original_event
        assert late_event in ranking["excluded_later_event_ids"]
        assert late_event not in ranking["ranked_event_ids"]
        assert all(row["event_id"] != late_event for row in ranking["rows"])
        assert original_event in ranking["ranked_event_ids"]
        assert ranking["decision_at"] == NEXT_OPEN
        assert len(ranking["ranked_event_ids"]) == 20


def test_later_only_release_gets_empty_next_open_cohorts_not_whole_inventory_refusal():
    binding = _later_only_binding()
    later = {
        row["lookback_sessions"]: row
        for row in binding.to_payload()["bindings"]
        if row["settlement_date"] == SETTLEMENT
        and row["eligibility_cutoff_at"] == "2024-02-15T14:30:00Z"
    }
    assert set(later) == set(LOOKBACKS)
    payload = build_stock_eligible_ranking_inventory(binding).to_payload()
    rankings = _current_rankings(payload)
    assert set(rankings) == set(LOOKBACKS)
    assert len(payload["rankings"]) == 2 * len(LOOKBACKS)
    for lookback, ranking in rankings.items():
        assert ranking["decision_at"] == NEXT_OPEN
        assert ranking["eligible_event_ids"] == []
        assert ranking["ranked_event_ids"] == []
        assert ranking["rows"] == []
        assert ranking["underfill_reasons"]
        assert ranking["excluded_later_event_ids"] == later[lookback]["eligible_event_ids"]


def test_exact_equal_scores_remain_one_indivisible_tie_group():
    ranking = _current_rankings(_tie_ranking().to_payload())[20]
    by_security_role = {
        (row["security_id"], row["role"]): row
        for row in ranking["rows"]
    }
    assert len(ranking["ranked_event_ids"]) == 20
    for role in ("pressure", "covering"):
        first = by_security_role["sec-si3c-000", role]
        second = by_security_role["sec-si3c-001", role]
        assert _rational(first["score"]) == _rational(second["score"])
        assert first["equal_count"] >= 2
        assert (
            first["strictly_lower_count"], first["equal_count"],
            first["strictly_higher_count"], first["role_percentile"],
            first["threshold_candidate"],
        ) == (
            second["strictly_lower_count"], second["equal_count"],
            second["strictly_higher_count"], second["role_percentile"],
            second["threshold_candidate"],
        )


def test_invalid_or_forged_binding_refuses_before_ranking():
    with pytest.raises(StockEligibleRankingError):
        build_stock_eligible_ranking_inventory(None)
    forged = StockPopulationBindingInventory(_multi_security_population(1))
    object.__setattr__(forged, "_source_population_sha256", "00" * 32)
    with pytest.raises(StockEligibleRankingError):
        build_stock_eligible_ranking_inventory(forged)


def test_returned_ranking_payload_is_detached_and_all_authorities_remain_false():
    inventory = _small_ranking()
    before = inventory.to_payload()
    changed = inventory.to_payload()
    current = next(row for row in changed["rankings"] if row["settlement_date"] == SETTLEMENT)
    current["excluded_members"][0]["reasons"].append("forged")
    current["ranked_event_ids"].append("forged")
    changed["policy"]["candidate_lookbacks"].append(1)
    assert inventory.to_payload() == before
    assert inventory.to_payload() != changed

    def assert_no_authority(value):
        if type(value) is dict:
            for key, nested in value.items():
                if key.endswith("_authorized") or key.endswith("_authoritative"):
                    assert nested is False
                assert_no_authority(nested)
        elif type(value) is list:
            for nested in value:
                assert_no_authority(nested)

    assert_no_authority(before)
