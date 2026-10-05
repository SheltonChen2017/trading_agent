"""Candidate-specific synthetic membership, never eligible scores or seeds."""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.dataset import build_vintage
from research.short_interest_etf.normalize import SnapshotRefusal
from research.short_interest_etf.pit_eligibility import build_stock_data_readiness
from research.short_interest_etf.stock_investability import (
    StockInvestabilityEvidence,
    SyntheticMarketHistory,
    build_stock_investability,
)
from research.short_interest_etf.stock_eligible_population import (
    StockEligiblePopulationError,
    StockEligiblePopulationInventory,
    build_stock_eligible_population_inventory,
)
from tests.test_short_interest_pit_eligibility import (
    _vintage_and_references_with_second_security,
)
from tests.test_short_interest_stock_investability import _history, _inputs


LOOKBACKS = (20, 60, 120, 252)
AUTHORITY_FLAGS = (
    "production_authoritative", "seed_authorized", "outcome_authorized",
    "ranking_authorized",
)


@lru_cache(maxsize=1)
def _evidence():
    return build_stock_investability(*_inputs())


@lru_cache(maxsize=1)
def _inventory():
    return build_stock_eligible_population_inventory(_evidence())


def _cohorts(inventory, settlement="2024-01-31"):
    return {
        cohort["lookback_sessions"]: cohort
        for cohort in inventory.to_payload()["cohorts"]
        if cohort["settlement_date"] == settlement
    }


def test_all_four_candidates_keep_their_own_complete_membership():
    payload = _inventory().to_payload()
    assert payload["schema_version"] == "1.0"
    assert payload["inventory_id"] == "si2b-offline-eligible-population-v1"
    assert payload["policy"]["grouping"] == (
        "settlement_date_execution_open_and_candidate_lookback"
    )
    assert payload["policy"]["semantics"] == (
        "synthetic_membership_only_not_scores_or_seeds"
    )
    assert payload["policy"]["candidate_lookbacks"] == list(LOOKBACKS)
    assert len(payload["cohorts"]) == 2 * len(LOOKBACKS)
    assert set(_cohorts(_inventory())) == set(LOOKBACKS)
    for count, cohort in _cohorts(_inventory()).items():
        assert cohort["lookback_sessions"] == count
        assert cohort["evidence_cutoff_at"] == "2024-02-13T14:30:00Z"
        assert cohort["source_member_count"] == 1
        assert cohort["eligible_member_count"] == 1
        assert cohort["refused_member_count"] == 0
        assert cohort["underfill_reasons"] == []
        member = cohort["members"][0]
        assert member["eligible"] is True
        assert member["refusal_reasons"] == []
        assert cohort["eligible_event_ids"] == [member["event_id"]]
        assert cohort["refused_event_ids"] == []
        assert cohort["eligible_security_ids"] == [member["security_id"]]


def test_inventory_binds_each_source_and_its_own_exact_content():
    payload = _inventory().to_payload()
    source = _evidence().to_payload()
    assert payload["source_evidence_sha256"] == _evidence().sha256
    for key in (
        "source_vintage_sha256", "reference_bundle_sha256", "market_history_sha256"
    ):
        assert payload[key] == source[key]
    assert payload["eligibility_policy_sha256"] == source["policy_sha256"]
    assert payload["policy_sha256"] == hash_payload(payload["policy"])
    assert _inventory().sha256 == payload["inventory_sha256"]
    assert payload["inventory_sha256"] == hash_payload({
        key: value for key, value in payload.items() if key != "inventory_sha256"
    })
    rows = {
        (row["event_id"], row["lookback_sessions"]): row
        for row in source["rows"]
    }
    readiness = {
        row.event_id: row
        for row in build_stock_data_readiness(_evidence().vintage, _evidence().references)
    }
    for cohort in payload["cohorts"]:
        assert cohort["cohort_sha256"] == hash_payload({
            key: value for key, value in cohort.items() if key != "cohort_sha256"
        })
        for member in cohort["members"]:
            row = rows[member["event_id"], cohort["lookback_sessions"]]
            ready = readiness[member["event_id"]]
            assert member["eligibility_row_sha256"] == hash_payload(row)
            for key in ("security_id", "security_identity_sha256", "eligible", "refusal_reasons"):
                assert member[key] == row[key]
            for key in ("taxonomy_id", "sector_code", "industry_code"):
                assert member[key] == getattr(ready, key)
            assert cohort["settlement_date"] == ready.settlement_date
            assert cohort["evidence_cutoff_at"] == ready.execution_at


def test_refused_upstream_members_remain_in_every_candidate_cohort():
    first = _inputs()[0].snapshots[0]
    cohorts = _cohorts(_inventory(), settlement="2024-01-12")
    assert set(cohorts) == set(LOOKBACKS)
    for cohort in cohorts.values():
        assert cohort["source_member_count"] == 1
        assert cohort["eligible_member_count"] == 0
        assert cohort["refused_member_count"] == 1
        assert cohort["eligible_event_ids"] == []
        assert cohort["refused_event_ids"] == [first.event_id]
        assert cohort["eligible_security_ids"] == []
        assert cohort["underfill_reasons"] == ["no_eligible_members"]
        member = cohort["members"][0]
        assert member["eligible"] is False
        assert "missing_authenticated_prior_cycle" in member["refusal_reasons"]


def test_parser_refusal_is_source_bound_without_inventing_a_security_member():
    vintage, references, history = _inputs()
    refusal = SnapshotRefusal(
        source_record_id="synthetic-malformed-row", settlement_date=None,
        reason="invalid_snapshot_contract", detail="synthetic parser refusal",
    )
    source = build_vintage(
        replace(
            vintage.manifest,
            requested_record_count=vintage.manifest.requested_record_count + 1,
            input_row_count=vintage.manifest.input_row_count + 1,
            refusal_count=vintage.manifest.refusal_count + 1,
        ),
        vintage.release_calendar, vintage.snapshots, (*vintage.refusals, refusal),
    )
    evidence = build_stock_investability(source, references, history)
    payload = build_stock_eligible_population_inventory(evidence).to_payload()
    original = _inventory().to_payload()
    assert payload["source_vintage_sha256"] != original["source_vintage_sha256"]
    assert payload["source_evidence_sha256"] != original["source_evidence_sha256"]
    assert payload["inventory_sha256"] != original["inventory_sha256"]
    assert payload["cohorts"] == original["cohorts"]
    assert sum(row["source_member_count"] for row in payload["cohorts"]) == 8


def test_missing_history_changes_only_the_affected_candidate_memberships():
    original = _inputs()[2]
    missing = original.daily[-30].session
    history = _history(daily=tuple(row for row in original.daily if row.session != missing))
    evidence = build_stock_investability(_inputs()[0], _inputs()[1], history)
    cohorts = _cohorts(build_stock_eligible_population_inventory(evidence))
    assert cohorts[20]["eligible_member_count"] == 1
    for lookback in (60, 120, 252):
        cohort = cohorts[lookback]
        assert cohort["source_member_count"] == 1
        assert cohort["eligible_member_count"] == 0
        assert cohort["refused_member_count"] == 1
        assert cohort["members"][0]["refusal_reasons"]
        assert cohort["underfill_reasons"] == ["no_eligible_members"]


def test_two_authentic_securities_partition_one_cohort_without_dropping_refusals():
    vintage, references = _vintage_and_references_with_second_security()
    original = _inputs()[2]
    second = next(snapshot.security for snapshot in vintage.snapshots if snapshot.security.security_id == "sec-synth-002")
    identity = hash_payload(second.to_payload())
    daily = tuple(replace(
        row, security_id=second.security_id, security_identity_sha256=identity,
        raw_record_sha256=hash_payload({"second_daily": row.session}),
    ) for row in original.daily)
    caps = tuple(replace(
        row, security_id=second.security_id, security_identity_sha256=identity,
        market_cap_usd="299999999",
        raw_record_sha256=hash_payload({"second_cap": row.session}),
    ) for row in original.capitalizations)
    history = SyntheticMarketHistory(
        (*original.daily, *daily), (*original.capitalizations, *caps)
    )
    evidence = build_stock_investability(vintage, references, history)
    cohorts = _cohorts(build_stock_eligible_population_inventory(evidence))
    for cohort in cohorts.values():
        assert cohort["source_member_count"] == 2
        assert cohort["eligible_member_count"] == 1
        assert cohort["refused_member_count"] == 1
        assert len(cohort["members"]) == 2
        assert cohort["eligible_security_ids"] == ["sec-synth-001"]
        refused = next(row for row in cohort["members"] if not row["eligible"])
        assert refused["security_id"] == "sec-synth-002"
        assert "below_market_cap_floor" in refused["refusal_reasons"]
        assert set(cohort["eligible_event_ids"]).isdisjoint(cohort["refused_event_ids"])
        assert set(cohort["eligible_event_ids"] + cohort["refused_event_ids"]) == {
            row["event_id"] for row in cohort["members"]
        }


def test_permuted_authentic_inputs_have_the_same_inventory_identity():
    vintage, references, history = _inputs()
    reordered = build_vintage(
        vintage.manifest, vintage.release_calendar,
        tuple(reversed(vintage.snapshots)), vintage.refusals,
    )
    evidence = build_stock_investability(reordered, references, _history(
        daily=tuple(reversed(history.daily)), caps=tuple(reversed(history.capitalizations)),
    ))
    inventory = build_stock_eligible_population_inventory(evidence)
    assert inventory.to_payload() == _inventory().to_payload()
    assert inventory.sha256 == _inventory().sha256


def test_returned_payload_is_recursively_detached():
    inventory = _inventory()
    original = inventory.to_payload()
    modified = inventory.to_payload()
    modified["cohorts"][0]["members"][0]["eligible"] = True
    modified["cohorts"][0]["members"][0]["refusal_reasons"].clear()
    modified["policy"]["candidate_lookbacks"].append(1)
    modified["production_authoritative"] = True
    assert inventory.to_payload() == original
    assert inventory.to_payload() != modified


def test_mutating_caller_source_after_construction_cannot_change_inventory():
    evidence = replace(_evidence())
    inventory = build_stock_eligible_population_inventory(evidence)
    before = inventory.to_payload()
    object.__setattr__(evidence.history.daily[-1], "volume_shares", 999999)
    object.__setattr__(evidence.history.capitalizations[-1], "market_cap_usd", "299999999")
    assert inventory.to_payload() == before


def test_mutating_captured_history_fails_closed_at_serialization():
    inventory = build_stock_eligible_population_inventory(_evidence())
    object.__setattr__(inventory.evidence.history.daily[-1], "volume_shares", 999999)
    with pytest.raises(StockEligiblePopulationError):
        inventory.to_payload()
    with pytest.raises(StockEligiblePopulationError):
        _ = inventory.sha256


def test_forged_source_hash_cannot_authenticate_changed_history():
    evidence = replace(_evidence())
    object.__setattr__(evidence, "_market_history_sha256", "00" * 32)
    with pytest.raises(StockEligiblePopulationError):
        build_stock_eligible_population_inventory(evidence)


@pytest.mark.parametrize("forged", ["00" * 32, None, 1, True])
def test_inventory_captured_source_hash_rejects_forgery_and_wrong_types(forged):
    inventory = build_stock_eligible_population_inventory(_evidence())
    object.__setattr__(inventory, "_source_evidence_sha256", forged)
    with pytest.raises(StockEligiblePopulationError):
        inventory.to_payload()


def test_rebinding_captured_evidence_cannot_rewrite_the_inventory_source():
    inventory = build_stock_eligible_population_inventory(_evidence())
    changed = _history(daily=tuple(
        replace(row, close_usd="99") for row in _inputs()[2].daily
    ))
    alternate = build_stock_investability(_inputs()[0], _inputs()[1], changed)
    object.__setattr__(inventory, "evidence", alternate)
    with pytest.raises(StockEligiblePopulationError):
        inventory.to_payload()


@pytest.mark.parametrize("value", [None, {}, [], True, "synthetic", 1])
def test_builder_refuses_noncanonical_source_types(value):
    with pytest.raises(StockEligiblePopulationError):
        build_stock_eligible_population_inventory(value)


def test_evidence_subclass_cannot_dispatch_a_forged_serializer():
    calls = []

    class ForgedEvidence(StockInvestabilityEvidence):
        def to_payload(self):
            calls.append("to_payload")
            return _evidence().to_payload()

    source = ForgedEvidence(*_inputs())
    with pytest.raises(StockEligiblePopulationError):
        build_stock_eligible_population_inventory(source)
    assert calls == []


def test_inventory_subclass_is_not_a_canonical_public_result():
    class ForgedInventory(StockEligiblePopulationInventory):
        pass

    inventory = ForgedInventory(_evidence())
    with pytest.raises(StockEligiblePopulationError):
        StockEligiblePopulationInventory.to_payload(inventory)


def test_caller_security_serializer_callback_is_never_dispatched():
    evidence = replace(_evidence())
    calls = []
    security = evidence.vintage.snapshots[0].security

    def callback():
        calls.append("security_serializer")
        raise AssertionError("caller callback must not run")

    object.__setattr__(security, "to_payload", callback)
    try:
        inventory = build_stock_eligible_population_inventory(evidence)
        assert inventory.to_payload() == _inventory().to_payload()
    except StockEligiblePopulationError:
        pass
    assert calls == []


def test_inventory_never_grants_authority_or_relabels_membership_as_scores():
    payload = _inventory().to_payload()
    assert payload["selected_lookback"] is None
    for name in AUTHORITY_FLAGS:
        assert payload[name] is False
    assert all(payload["policy"][name] is False for name in AUTHORITY_FLAGS)
    forbidden = {
        "score", "rank", "percentile", "pressure_percentile", "covering_percentile",
        "pressure_seed", "covering_seed", "orders", "selected_lookback",
    }
    for cohort in payload["cohorts"]:
        assert forbidden.isdisjoint(cohort)
        for member in cohort["members"]:
            assert forbidden.isdisjoint(member)


def test_membership_adapter_is_not_exported_from_the_package_root():
    import research.short_interest_etf as package

    assert not hasattr(package, "build_stock_eligible_population_inventory")
    assert not hasattr(package, "StockEligiblePopulationInventory")
