"""Synthetic population/cutoff binding, never eligible scores or authority."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from functools import lru_cache

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.dataset import build_vintage
from research.short_interest_etf.stock_eligible_population import (
    StockEligiblePopulationInventory,
    build_stock_eligible_population_inventory,
)
from research.short_interest_etf.stock_features import build_pit_stock_raw_features
from research.short_interest_etf.stock_investability import (
    SyntheticMarketHistory,
    build_stock_investability,
)
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
    RevisionSelectionState,
    build_pit_stock_normalized_scores,
)
from research.short_interest_etf.stock_population_binding import (
    StockPopulationBindingError,
    StockPopulationBindingInventory,
    build_stock_population_binding_inventory,
)
from tests.test_short_interest_stock_investability import _history, _inputs
from tests.test_short_interest_stock_normalization import (
    _raw_batch,
    _single_sector_specs,
)


LOOKBACKS = (20, 60, 120, 252)
MODELS = tuple(model.value for model in STOCK_NORMALIZATION_POLICY.models)
AUTHORITY_FLAGS = (
    "production_authoritative", "ranking_authorized", "seed_authorized",
    "outcome_authorized",
)


@lru_cache(maxsize=1)
def _population():
    return build_stock_eligible_population_inventory(build_stock_investability(*_inputs()))


@lru_cache(maxsize=1)
def _binding():
    return build_stock_population_binding_inventory(_population())


@lru_cache(maxsize=1)
def _canonical_scores():
    evidence = _population().evidence
    return build_pit_stock_normalized_scores(
        build_pit_stock_raw_features(evidence.vintage, evidence.references)
    )


def _current_bindings(inventory, *, cutoff="2024-02-13T14:30:00Z"):
    return {
        row["lookback_sessions"]: row
        for row in inventory.to_payload()["bindings"]
        if row["settlement_date"] == "2024-01-31"
        and row["eligibility_cutoff_at"] == cutoff
    }


@lru_cache(maxsize=4)
def _multi_security_population(count, correction=None, refused_index=None, specs=None):
    """Build canonical SI-3C fixtures with real SI-2B price/identity lineage.

    ``specs`` overrides the default single-sector specs so a caller can shape
    authentic share deltas, for example to create an exact S1 tie group. The
    default stays ``_single_sector_specs(count)``.
    """
    raw = _raw_batch(_single_sector_specs(count) if specs is None else specs, correction)
    context = raw[0].source_context
    vintage = context.source_vintage
    references = context.reference_bundle
    template = _inputs()[2]
    daily_templates = template.daily
    cap_templates = template.capitalizations
    if correction is not None and correction[1] == "2024-02-14T15:00:00Z":
        daily_templates = (*daily_templates, *(replace(
            template.daily[-1], session=session,
            available_at=f"{session}T23:00:00Z",
            observed_at=f"{session}T23:00:00Z",
            raw_record_sha256=hash_payload({"extended_daily": session}),
        ) for session in ("2024-02-13", "2024-02-14")))
        cap_templates = (*cap_templates, replace(
            template.capitalizations[-1], session="2024-02-14",
            available_at="2024-02-14T23:00:00Z",
            observed_at="2024-02-14T23:00:00Z",
            raw_record_sha256=hash_payload({"extended_cap": "2024-02-14"}),
        ))
    identities = {
        snapshot.security.security_id: snapshot.security
        for snapshot in vintage.snapshots
    }
    daily = []
    caps = []
    refused_security = None if refused_index is None else f"sec-si3c-{refused_index:03d}"
    for security_id, security in sorted(identities.items()):
        identity = hash_payload(security.to_payload())
        daily.extend(replace(
            row, security_id=security_id, security_identity_sha256=identity,
            raw_record_sha256=hash_payload({"daily_security": security_id, "session": row.session}),
        ) for row in daily_templates)
        caps.extend(replace(
            row, security_id=security_id, security_identity_sha256=identity,
            market_cap_usd="299999999" if security_id == refused_security else "300000000",
            raw_record_sha256=hash_payload({"cap_security": security_id, "session": row.session}),
        ) for row in cap_templates)
    evidence = build_stock_investability(
        vintage, references, SyntheticMarketHistory(tuple(daily), tuple(caps)),
    )
    return build_stock_eligible_population_inventory(evidence)


def test_public_binding_api_exists_without_changing_the_package_root():
    assert issubclass(StockPopulationBindingError, ValueError)
    assert callable(build_stock_population_binding_inventory)
    assert hasattr(StockPopulationBindingInventory, "to_payload")
    assert hasattr(StockPopulationBindingInventory, "sha256")


def test_each_candidate_cohort_is_bound_without_merging_cutoffs_or_members():
    payload = _binding().to_payload()
    source = _population().to_payload()
    assert payload["schema_version"] == "1.0"
    assert payload["binding_id"] == "si2b-offline-population-normalization-binding-v1"
    assert payload["policy"]["candidate_lookbacks"] == list(LOOKBACKS)
    assert len(payload["bindings"]) == len(source["cohorts"]) == 8
    assert len(payload["normalization_cohorts"]) == 2
    by_hash = {cohort["cohort_sha256"]: cohort for cohort in source["cohorts"]}
    for row in payload["bindings"]:
        original = by_hash[row["source_cohort_sha256"]]
        assert row["settlement_date"] == original["settlement_date"]
        assert row["lookback_sessions"] == original["lookback_sessions"]
        assert row["eligibility_cutoff_at"] == original["evidence_cutoff_at"]
        assert row["cutoff_equal"] is True
        assert row["cutoff_relation"] == "same_open"
        for name in ("eligible_event_ids", "refused_event_ids"):
            assert row[name] == original[name]
        assert set(row["eligible_event_ids"]).isdisjoint(row["refused_event_ids"])
        assert set(row["eligible_event_ids"] + row["refused_event_ids"]) == {
            member["event_id"] for member in row["members"]
        }
        for member, source_member in zip(row["members"], original["members"], strict=True):
            assert {key: member[key] for key in source_member} == source_member


def test_hashes_bind_sources_policies_summary_and_each_complete_binding():
    payload = _binding().to_payload()
    source = _population().to_payload()
    assert payload["source_population_sha256"] == source["inventory_sha256"]
    for key in (
        "source_evidence_sha256", "source_vintage_sha256", "reference_bundle_sha256",
        "market_history_sha256",
    ):
        assert payload[key] == source[key]
    assert payload["normalization_policy_sha256"] == STOCK_NORMALIZATION_POLICY.sha256
    assert payload["policy_sha256"] == hash_payload(payload["policy"])
    assert payload["inventory_sha256"] == hash_payload({
        key: value for key, value in payload.items() if key != "inventory_sha256"
    })
    assert _binding().sha256 == payload["inventory_sha256"]
    canonical = {item.cohort.settlement_date: item.cohort for item in _canonical_scores()}
    for summary in payload["normalization_cohorts"]:
        cohort = canonical[summary["settlement_date"]]
        assert summary["normalization_cohort_sha256"] == hash_payload(cohort.to_payload())
        assert summary["decision_at"] == cohort.decision_at
        assert summary["release_calendar_key"] == cohort.release_calendar_key
        assert summary["release_sha256"] == cohort.release_sha256
        assert summary["candidate_event_ids"] == sorted(x.event_id for x in cohort.candidate_members)
        assert summary["structural_peer_event_ids"] == sorted(x.event_id for x in cohort.eligible_members)
        for model in MODELS:
            assert summary["scoreable_event_ids_by_model"][model] == sorted(
                item.current.readiness.event_id for item in _canonical_scores()
                if item.cohort.settlement_date == summary["settlement_date"]
                and any(outcome.model.value == model and outcome.score is not None for outcome in item.outcomes)
            )
    for row in payload["bindings"]:
        assert row["binding_sha256"] == hash_payload({
            key: value for key, value in row.items() if key != "binding_sha256"
        })
        assert row["normalization_cohort_sha256"] == hash_payload(canonical[row["settlement_date"]].to_payload())


def test_liquidity_eligibility_is_not_sector_peer_or_seed_qualification():
    assert STOCK_NORMALIZATION_POLICY.minimum_sector_peers == 20
    for row in _current_bindings(_binding()).values():
        event = row["eligible_event_ids"][0]
        assert row["eligible_selected_event_ids"] == [event]
        assert row["eligible_candidate_event_ids"] == [event]
        assert row["eligible_structural_peer_event_ids"] == []
        assert row["eligible_outside_structural_peer_event_ids"] == [event]
        assert row["eligible_scoreable_event_ids_by_model"] == {model: [] for model in MODELS}
        assert row["binding_observations"] == ["eligible_events_outside_structural_peer_population"]
        member = row["members"][0]
        assert member["structural_candidate"] is True
        assert member["structural_peer"] is False
        assert member["scoreable_models"] == []
    payload = _binding().to_payload()
    warmup = next(row for row in payload["bindings"] if row["settlement_date"] == "2024-01-12")
    assert warmup["eligible_event_ids"] == []
    assert len(warmup["refused_event_ids"]) == 1
    assert warmup["members"][0]["refusal_reasons"] == ["missing_authenticated_prior_cycle"]
    assert warmup["members"][0]["revision_selection_state"] == RevisionSelectionState.SELECTED.value
    assert warmup["members"][0]["structural_candidate"] is False


def test_true_twenty_peer_cohort_reports_intersections_not_filtered_ranks():
    population = _multi_security_population(20, refused_index=19)
    inventory = build_stock_population_binding_inventory(population)
    payload = inventory.to_payload()
    summary = next(row for row in payload["normalization_cohorts"] if row["settlement_date"] == "2024-01-31")
    assert len(summary["candidate_event_ids"]) == len(summary["structural_peer_event_ids"]) == 20
    assert all(len(summary["scoreable_event_ids_by_model"][model]) == 20 for model in MODELS)
    for row in _current_bindings(inventory).values():
        assert len(row["members"]) == 20
        assert len(row["eligible_event_ids"]) == 19
        assert len(row["refused_event_ids"]) == 1
        assert row["eligible_candidate_event_ids"] == row["eligible_event_ids"]
        assert row["eligible_structural_peer_event_ids"] == row["eligible_event_ids"]
        assert row["eligible_scoreable_event_ids_by_model"] == {
            model: row["eligible_event_ids"] for model in MODELS
        }
        assert row["eligible_outside_structural_peer_event_ids"] == []
        assert row["binding_observations"] == []
        refused = next(member for member in row["members"] if not member["eligible"])
        assert refused["structural_peer"] is True
        assert refused["scoreable_models"] == sorted(MODELS)
        assert refused["refusal_reasons"] == ["below_market_cap_floor"]


def test_delayed_revision_keeps_its_own_later_cutoff_and_original_selected_event():
    population = _multi_security_population(1, (0, "2024-02-14T15:00:00Z"), -1)
    inventory = build_stock_population_binding_inventory(population)
    original = _current_bindings(inventory)
    delayed = _current_bindings(inventory, cutoff="2024-02-15T14:30:00Z")
    assert set(original) == set(delayed) == set(LOOKBACKS)
    assert len(inventory.to_payload()["bindings"]) == 12
    for lookback, row in delayed.items():
        assert row["cutoff_equal"] is False
        assert row["cutoff_relation"] == "eligibility_after_normalization"
        assert row["normalization_cutoff_at"] == "2024-02-13T14:30:00Z"
        member = row["members"][0]
        assert member["revision_selection_state"] == RevisionSelectionState.NOT_VISIBLE.value
        assert member["selected_event_id"] == original[lookback]["members"][0]["event_id"]
        assert member["selected_event_id"] != member["event_id"]
        assert member["eligible"] is True
        assert member["structural_candidate"] is False
        assert member["structural_peer"] is False
        assert row["eligible_event_ids"] == [member["event_id"]]
        assert row["eligible_selected_event_ids"] == row["eligible_candidate_event_ids"] == []
        assert row["eligible_outside_structural_peer_event_ids"] == [member["event_id"]]
        assert row["binding_observations"] == [
            "different_evidence_cutoff",
            "eligible_events_not_selected_at_normalization_cutoff",
            "eligible_events_outside_structural_candidate_population",
            "eligible_events_outside_structural_peer_population",
        ]


def test_revision_selected_before_first_open_retains_superseded_member_refusal():
    population = _multi_security_population(1, (0, "2024-02-13T13:00:00Z"), -1)
    rows = _current_bindings(build_stock_population_binding_inventory(population))
    for row in rows.values():
        assert len(row["members"]) == 2
        selected = next(member for member in row["members"] if member["eligible"])
        superseded = next(member for member in row["members"] if not member["eligible"])
        assert selected["revision_selection_state"] == RevisionSelectionState.SELECTED.value
        assert superseded["revision_selection_state"] == RevisionSelectionState.SUPERSEDED.value
        assert selected["selected_event_id"] == superseded["selected_event_id"] == selected["event_id"]
        assert superseded["structural_candidate"] is False
        assert "superseded_before_execution" in superseded["refusal_reasons"]
        assert row["refused_event_ids"] == [superseded["event_id"]]


def test_missing_thirtieth_session_binds_different_candidate_memberships():
    vintage, references, history = _inputs()
    missing = history.daily[-30].session
    changed = _history(daily=tuple(row for row in history.daily if row.session != missing))
    population = build_stock_eligible_population_inventory(build_stock_investability(vintage, references, changed))
    rows = _current_bindings(build_stock_population_binding_inventory(population))
    assert len(rows[20]["eligible_event_ids"]) == 1
    assert rows[20]["refused_event_ids"] == []
    for lookback in (60, 120, 252):
        assert rows[lookback]["eligible_event_ids"] == []
        assert len(rows[lookback]["refused_event_ids"]) == 1
        assert "daily_history_missing" in rows[lookback]["members"][0]["refusal_reasons"]
        assert all(events == [] for events in rows[lookback]["eligible_scoreable_event_ids_by_model"].values())


def test_reordered_authentic_sources_preserve_binding_identity():
    vintage, references, history = _inputs()
    reordered = build_vintage(vintage.manifest, vintage.release_calendar, tuple(reversed(vintage.snapshots)), vintage.refusals)
    evidence = build_stock_investability(reordered, references, _history(daily=tuple(reversed(history.daily)), caps=tuple(reversed(history.capitalizations))))
    population = build_stock_eligible_population_inventory(evidence)
    assert build_stock_population_binding_inventory(population).to_payload() == _binding().to_payload()


def test_returned_binding_payload_is_recursively_detached():
    inventory = _binding()
    before = inventory.to_payload()
    changed = inventory.to_payload()
    changed["bindings"][0]["members"][0]["refusal_reasons"].clear()
    changed["bindings"][0]["eligible_event_ids"].append("forged")
    changed["normalization_cohorts"][0]["candidate_event_ids"].append("forged")
    changed["policy"]["candidate_lookbacks"].append(1)
    assert inventory.to_payload() == before
    assert inventory.to_payload() != changed


def test_frozen_contract_prevents_normal_attribute_reassignment():
    inventory = _binding()
    with pytest.raises(FrozenInstanceError):
        inventory.population = _population()


def test_caller_history_mutation_cannot_change_captured_binding():
    population = StockEligiblePopulationInventory(_population().evidence)
    inventory = build_stock_population_binding_inventory(population)
    before = inventory.to_payload()
    object.__setattr__(population.evidence.history.daily[-1], "volume_shares", 999999)
    assert inventory.to_payload() == before


def test_captured_history_mutation_fails_closed_for_payload_and_digest():
    inventory = StockPopulationBindingInventory(_population())
    object.__setattr__(inventory.population.evidence.history.daily[-1], "volume_shares", 999999)
    with pytest.raises(StockPopulationBindingError):
        inventory.to_payload()
    with pytest.raises(StockPopulationBindingError):
        _ = inventory.sha256


@pytest.mark.parametrize("forged", ["00" * 32, None, 1, True])
def test_pinned_population_hash_rejects_forgery_and_wrong_types(forged):
    inventory = StockPopulationBindingInventory(_population())
    object.__setattr__(inventory, "_source_population_sha256", forged)
    with pytest.raises(StockPopulationBindingError):
        inventory.to_payload()


def test_forged_upstream_source_binding_cannot_enter_inventory():
    population = StockEligiblePopulationInventory(_population().evidence)
    object.__setattr__(population, "_source_evidence_sha256", "00" * 32)
    with pytest.raises(StockPopulationBindingError):
        build_stock_population_binding_inventory(population)


def test_replacing_captured_source_cannot_rewrite_binding_identity():
    inventory = StockPopulationBindingInventory(_population())
    history = _history(daily=tuple(replace(row, close_usd="99") for row in _inputs()[2].daily))
    changed = build_stock_eligible_population_inventory(build_stock_investability(_inputs()[0], _inputs()[1], history))
    object.__setattr__(inventory, "population", changed)
    with pytest.raises(StockPopulationBindingError):
        inventory.to_payload()


@pytest.mark.parametrize("value", [None, {}, [], True, "synthetic", 1])
def test_builder_rejects_noncanonical_source_types(value):
    with pytest.raises(StockPopulationBindingError):
        build_stock_population_binding_inventory(value)


def test_population_subclass_serializer_is_not_dispatched():
    calls = []

    class ForgedPopulation(StockEligiblePopulationInventory):
        def to_payload(self):
            calls.append("forged_serializer")
            return _population().to_payload()

    population = ForgedPopulation(_population().evidence)
    with pytest.raises(StockPopulationBindingError):
        build_stock_population_binding_inventory(population)
    assert calls == []


def test_binding_subclass_is_not_a_canonical_public_inventory():
    class ForgedBinding(StockPopulationBindingInventory):
        pass

    inventory = ForgedBinding(_population())
    with pytest.raises(StockPopulationBindingError):
        StockPopulationBindingInventory.to_payload(inventory)


def test_security_callback_cannot_forge_population_capture():
    population = StockEligiblePopulationInventory(_population().evidence)
    calls = []

    def callback():
        calls.append("security_serializer")
        raise AssertionError("caller callback must not run")

    object.__setattr__(population.evidence.vintage.snapshots[0].security, "to_payload", callback)
    try:
        inventory = build_stock_population_binding_inventory(population)
        assert inventory.to_payload() == _binding().to_payload()
    except StockPopulationBindingError:
        pass
    assert calls == []


def test_binding_keeps_financial_policy_unresolved_and_emits_no_authority_or_scores():
    payload = _binding().to_payload()
    assert payload["selected_lookback"] is None
    assert payload["financial_population_policy_required"] is True
    assert payload["policy"]["financial_population_policy_required"] is True
    for name in AUTHORITY_FLAGS:
        assert payload[name] is False
    forbidden = {
        "score", "scores", "rank", "ranks", "percentile", "percentiles",
        "pressure_percentile", "covering_percentile", "pressure_seed", "covering_seed",
        "orders", "winsor_lower", "winsor_upper", "winsorized_value", "sector_median",
        "sector_mad", "seed_qualified", "ranking_population_selected",
    }

    def check(value):
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value)
            for nested in value.values():
                check(nested)
        elif isinstance(value, list):
            for nested in value:
                check(nested)

    check(payload)
    import research.short_interest_etf as package

    assert not hasattr(package, "build_stock_population_binding_inventory")
    assert not hasattr(package, "StockPopulationBindingInventory")
