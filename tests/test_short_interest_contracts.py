"""Strict SI-0 source, identity, denominator, and volume contracts."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from research.short_interest_etf.contracts import (
    CollectionManifest,
    DenominatorObservation,
    ShortInterestContractError,
    ShortInterestSnapshot,
    VolumeBasis,
    recompute_days_to_cover,
)
from research.short_interest_etf.dataset import load_synthetic_fixture
from research.short_interest_etf.preregistration import PREREGISTRATION

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "short_interest_etf"
    / "official_style_v1.json"
)


def _fixture_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _snapshot_payload(index: int = 0) -> dict:
    return copy.deepcopy(_fixture_payload()["snapshot_rows"][index])


def test_synthetic_fixture_round_trips_all_pinned_contracts():
    vintage = load_synthetic_fixture(FIXTURE)
    assert vintage.manifest.source_dataset_id == "synthetic-si-vintage-2024-02-14"
    assert vintage.manifest.accepted_record_count == 2
    assert len(vintage.release_calendar) == 2
    assert len(vintage.snapshots) == 2
    assert vintage.refusals == ()
    assert all(
        ShortInterestSnapshot.from_payload(item.to_payload()) == item
        for item in vintage.snapshots
    )


def test_preregistration_pins_zero_look_fixture_scope_and_canonical_choices():
    assert PREREGISTRATION.source_semantic == "official_open_short_position_snapshot"
    assert PREREGISTRATION.canonical_score == "S1_delta"
    assert PREREGISTRATION.primary_horizon_sessions == 20
    assert PREREGISTRATION.primary_cost_bps == 10
    assert PREREGISTRATION.cost_sensitivity_bps == (0, 5, 20)
    assert PREREGISTRATION.canonical_leverage == 1
    assert PREREGISTRATION.milestone_outcome_look_budget == 0
    assert PREREGISTRATION.outcome_looks_used == 0
    assert PREREGISTRATION.production_authoritative is False
    assert len(PREREGISTRATION.sha256) == 64


@pytest.mark.parametrize(
    ("contract", "payload"),
    [
        (
            CollectionManifest,
            lambda: _fixture_payload()["manifest"],
        ),
        (
            ShortInterestSnapshot,
            _snapshot_payload,
        ),
    ],
)
def test_contract_loaders_refuse_missing_and_unknown_fields(contract, payload):
    original = payload()
    missing = copy.deepcopy(original)
    missing.pop(next(iter(missing)))
    with pytest.raises(ShortInterestContractError, match="fields mismatch"):
        contract.from_payload(missing)
    unknown = copy.deepcopy(original)
    unknown["future_unreviewed_field"] = "unsafe"
    with pytest.raises(ShortInterestContractError, match="unknown"):
        contract.from_payload(unknown)


def test_nested_source_payload_mutation_cannot_change_validated_snapshot():
    payload = _snapshot_payload()
    snapshot = ShortInterestSnapshot.from_payload(payload)
    payload["security"]["ticker"] = "MUTATED"
    payload["denominator"]["value"] = "1"
    assert snapshot.security.ticker == "SYN"
    assert snapshot.denominator.value == "10000"


def test_event_id_binds_normalized_facts_not_only_caller_supplied_raw_hash():
    snapshot = ShortInterestSnapshot.from_payload(_snapshot_payload())
    changed_position = replace(
        snapshot,
        current_short_shares=900,
        recomputed_days_to_cover="9",
    )
    changed_denominator = replace(
        snapshot,
        denominator=replace(snapshot.denominator, value="10001"),
    )
    changed_availability = replace(
        snapshot,
        revision_published_at="2024-01-25T21:00:00.100000Z",
    )
    for changed in (changed_position, changed_denominator, changed_availability):
        assert changed.raw_record_sha256 == snapshot.raw_record_sha256
        assert changed.event_id != snapshot.event_id


@pytest.mark.parametrize("value", [0, -1, "0", "-1"])
def test_zero_or_negative_denominators_fail_closed(value):
    payload = _snapshot_payload()
    payload["denominator"]["value"] = value
    with pytest.raises(ShortInterestContractError, match="denominator.value"):
        ShortInterestSnapshot.from_payload(payload)


def test_shares_outstanding_denominator_refuses_fractional_share_counts():
    payload = _snapshot_payload()
    payload["denominator"]["value"] = "10000.5"
    with pytest.raises(ShortInterestContractError, match="whole shares"):
        ShortInterestSnapshot.from_payload(payload)


@pytest.mark.parametrize("value", [0, -1, "0", "-1"])
def test_zero_or_negative_average_daily_volume_fails_closed(value):
    payload = _snapshot_payload()
    payload["volume_basis"]["average_daily_share_volume"] = value
    with pytest.raises(
        ShortInterestContractError, match="average_daily_share_volume"
    ):
        ShortInterestSnapshot.from_payload(payload)


@pytest.mark.parametrize(
    ("section", "field"),
    [("denominator", "value"), ("volume_basis", "average_daily_share_volume")],
)
def test_exact_financial_quantities_refuse_json_floats(section, field):
    payload = _snapshot_payload()
    payload[section][field] = 100.0
    with pytest.raises(ShortInterestContractError, match="JSON numbers are refused"):
        ShortInterestSnapshot.from_payload(payload)


def test_zero_short_positions_are_valid_but_negative_positions_are_not():
    payload = _snapshot_payload()
    payload["current_short_shares"] = 0
    payload["recomputed_days_to_cover"] = "0"
    assert ShortInterestSnapshot.from_payload(payload).current_short_shares == 0
    payload["current_short_shares"] = -1
    with pytest.raises(ShortInterestContractError, match="current_short_shares"):
        ShortInterestSnapshot.from_payload(payload)


def test_recomputed_days_to_cover_is_independent_and_bound_to_exact_inputs():
    assert recompute_days_to_cover(5, "3") == "1.666666666667"
    payload = _snapshot_payload()
    payload["recomputed_days_to_cover"] = payload["reported_days_to_cover"]
    with pytest.raises(ShortInterestContractError, match="recomputed_days_to_cover"):
        ShortInterestSnapshot.from_payload(payload)


def test_extreme_finite_days_to_cover_inputs_never_escape_decimal_errors():
    tiny_volume = "0." + ("0" * 39) + "1"
    result = recompute_days_to_cover(10**100, tiny_volume)
    assert result == "1" + ("0" * 140)


def test_ticker_is_auditable_metadata_not_the_stable_security_identity():
    snapshot = ShortInterestSnapshot.from_payload(_snapshot_payload())
    renamed = replace(snapshot.security, ticker="NEW")
    assert renamed.security_id == snapshot.security.security_id
    assert renamed.ticker != snapshot.security.ticker
    assert snapshot.logical_id == replace(snapshot, security=renamed).logical_id


@pytest.mark.parametrize("nested_name", ["volume_basis", "denominator"])
def test_nested_financial_inputs_must_match_stable_security_id(nested_name):
    payload = _snapshot_payload()
    payload[nested_name]["security_id"] = "sec-synth-wrong"
    with pytest.raises(ShortInterestContractError, match="security_id must match"):
        ShortInterestSnapshot.from_payload(payload)


def test_security_identity_requires_canonical_ticker_and_valid_settlement_window():
    payload = _snapshot_payload()
    payload["security"]["ticker"] = "syn"
    with pytest.raises(ShortInterestContractError, match="canonical uppercase"):
        ShortInterestSnapshot.from_payload(payload)
    payload = _snapshot_payload()
    payload["security"]["valid_to"] = "2024-01-11"
    with pytest.raises(ShortInterestContractError, match="not valid"):
        ShortInterestSnapshot.from_payload(payload)


@pytest.mark.parametrize(
    ("contract_factory", "available", "observed"),
    [
        (
            lambda snapshot: snapshot.denominator,
            "2024-01-25T22:00:00Z",
            "2024-01-25T21:00:00Z",
        ),
        (
            lambda snapshot: snapshot.volume_basis,
            "2024-01-25T22:00:00Z",
            "2024-01-25T21:00:00Z",
        ),
    ],
)
def test_observation_time_cannot_manufacture_earlier_availability(
    contract_factory, available, observed
):
    snapshot = ShortInterestSnapshot.from_payload(_snapshot_payload())
    contract = contract_factory(snapshot)
    with pytest.raises(ShortInterestContractError, match="observed_at"):
        replace(contract, available_at=available, observed_at=observed)


def test_source_manifest_counts_and_retrieval_timestamp_are_strict():
    payload = _fixture_payload()["manifest"]
    payload["accepted_record_count"] = 1
    with pytest.raises(ShortInterestContractError, match="must equal"):
        CollectionManifest.from_payload(payload)
    payload = _fixture_payload()["manifest"]
    payload["retrieved_at"] = "2024-02-14T14:00:00"
    with pytest.raises(ShortInterestContractError, match="UTC timestamp"):
        CollectionManifest.from_payload(payload)


def test_direct_nested_contracts_round_trip_strictly():
    snapshot = ShortInterestSnapshot.from_payload(_snapshot_payload())
    assert VolumeBasis.from_payload(snapshot.volume_basis.to_payload()) == snapshot.volume_basis
    assert (
        DenominatorObservation.from_payload(snapshot.denominator.to_payload())
        == snapshot.denominator
    )
