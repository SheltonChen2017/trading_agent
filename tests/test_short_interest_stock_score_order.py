"""Dangerous-direction tests for parameter-free SI-3E-P0 score ordering."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from functools import lru_cache
import inspect
import json

import pytest

from data.hashing import canonical_json, hash_payload
import research.short_interest_etf as canonical_short_interest_package
import research.short_interest_etf.stock_score_order as stock_score_order_module
from research.short_interest_etf.stock_covering import (
    StockCoveringBatch,
    build_pit_stock_covering_scores,
)
from research.short_interest_etf.stock_features import ExactRational
from research.short_interest_etf.stock_normalization import RevisionSelectionState
from research.short_interest_etf.stock_score_order import (
    SCORE_ORDER_INVENTORY_ID,
    StockScoreOrderBatch,
    StockScoreOrderDisposition,
    StockScoreOrderError,
    StockScoreOrderRole,
    build_stock_score_order_inventory,
)
from tests.test_short_interest_stock_normalization import (
    _fresh_non_affine_scores,
    _multi_cycle_scores,
    _non_affine_scores,
    _scores,
    _single_sector_scores,
    _tampered_covering,
    _tampered_covering_batch,
)


@lru_cache(maxsize=1)
def _covering() -> StockCoveringBatch:
    return build_pit_stock_covering_scores(_non_affine_scores())


@lru_cache(maxsize=1)
def _inventory() -> StockScoreOrderBatch:
    return build_stock_score_order_inventory(_covering())


@lru_cache(maxsize=1)
def _four_cycle_inventory() -> StockScoreOrderBatch:
    return build_stock_score_order_inventory(
        build_pit_stock_covering_scores(_multi_cycle_scores(4, 20))
    )


def _clone_disposition(
    disposition: StockScoreOrderDisposition,
    **changes,
) -> StockScoreOrderDisposition:
    clone = object.__new__(StockScoreOrderDisposition)
    for name in disposition.__dataclass_fields__:
        object.__setattr__(clone, name, getattr(disposition, name))
    for name, value in changes.items():
        object.__setattr__(clone, name, value)
    return clone


def _clone_batch(batch: StockScoreOrderBatch, **changes) -> StockScoreOrderBatch:
    clone = object.__new__(StockScoreOrderBatch)
    for name in batch.__dataclass_fields__:
        object.__setattr__(clone, name, getattr(batch, name))
    for name, value in changes.items():
        if name == "dispositions" and "_dispositions" in batch.__dataclass_fields__:
            name = "_dispositions"
        object.__setattr__(clone, name, value)
    return clone


def _contains_float(value) -> bool:
    if type(value) is float:
        return True
    if type(value) is dict:
        return any(_contains_float(item) for item in value.values())
    if type(value) is list:
        return any(_contains_float(item) for item in value)
    return False


def _source_by_event(batch: StockCoveringBatch):
    return {item.event_id: item for item in batch.projections}


def _role_rows(
    batch: StockScoreOrderBatch,
    role: StockScoreOrderRole,
) -> tuple[StockScoreOrderDisposition, ...]:
    return tuple(item for item in batch.dispositions if item.role is role)


def test_score_order_inventory_has_two_canonical_roles_per_source_projection():
    covering = _covering()
    inventory = _inventory()
    actual = tuple((item.event_id, item.role) for item in inventory.dispositions)
    expected = tuple(
        (source.event_id, role)
        for source in covering.projections
        for role in (
            StockScoreOrderRole.PRESSURE,
            StockScoreOrderRole.COVERING,
        )
    )

    assert type(inventory) is StockScoreOrderBatch
    assert type(inventory.dispositions) is tuple
    assert actual == expected
    assert len(inventory.dispositions) == 2 * len(covering.projections)
    assert all(
        type(item) is StockScoreOrderDisposition
        for item in inventory.dispositions
    )
    assert len({item.score_order_slot_id for item in inventory.dispositions}) == (
        len(inventory.dispositions)
    )
    assert len({item.score_order_record_id for item in inventory.dispositions}) == (
        len(inventory.dispositions)
    )


def test_score_order_counts_match_independent_exact_release_local_oracle():
    inventory = _inventory()
    for role in StockScoreOrderRole:
        role_rows = _role_rows(inventory, role)
        release_keys = {
            (item.settlement_date, item.decision_session) for item in role_rows
        }
        for release_key in release_keys:
            release_rows = tuple(
                item
                for item in role_rows
                if (item.settlement_date, item.decision_session) == release_key
            )
            scores = tuple(
                item.score.to_fraction()
                for item in release_rows
                if item.score is not None
            )
            for item in release_rows:
                if item.score is None:
                    assert item.strictly_lower_count is None
                    assert item.equal_count is None
                    assert item.strictly_higher_count is None
                    continue
                score = item.score.to_fraction()
                assert type(item.score) is ExactRational
                assert type(item.strictly_lower_count) is int
                assert type(item.equal_count) is int
                assert type(item.strictly_higher_count) is int
                assert item.strictly_lower_count == sum(
                    value < score for value in scores
                )
                assert item.equal_count == sum(value == score for value in scores)
                assert item.strictly_higher_count == sum(
                    value > score for value in scores
                )
                assert (
                    item.strictly_lower_count
                    + item.equal_count
                    + item.strictly_higher_count
                    == len(scores)
                )


def test_score_order_golden_non_affine_identities_are_exact():
    rows = {
        (item.security_id, item.role): item
        for item in _inventory().dispositions
        if item.score is not None
    }
    expected = {
        ("sec-si3c-000", StockScoreOrderRole.PRESSURE): (
            ExactRational(-98050, 66717),
            0,
            1,
            39,
        ),
        ("sec-si3c-002", StockScoreOrderRole.PRESSURE): (
            ExactRational(-10000, 7413),
            1,
            1,
            38,
        ),
        ("sec-si3c-010", StockScoreOrderRole.PRESSURE): (
            ExactRational(0, 1),
            19,
            2,
            19,
        ),
        ("sec-si3c-038", StockScoreOrderRole.PRESSURE): (
            ExactRational(10000, 7413),
            39,
            1,
            0,
        ),
        ("sec-si3c-000", StockScoreOrderRole.COVERING): (
            ExactRational(98050, 66717),
            39,
            1,
            0,
        ),
        ("sec-si3c-038", StockScoreOrderRole.COVERING): (
            ExactRational(-10000, 7413),
            0,
            1,
            39,
        ),
    }
    assert {
        key: (
            rows[key].score,
            rows[key].strictly_lower_count,
            rows[key].equal_count,
            rows[key].strictly_higher_count,
        )
        for key in expected
    } == expected


def test_exact_ties_are_indivisible_equivalence_groups():
    inventory = _inventory()
    pressure_zero = tuple(
        item
        for item in inventory.dispositions
        if item.role is StockScoreOrderRole.PRESSURE
        and item.score == ExactRational(0, 1)
    )
    assert len(pressure_zero) == 2
    assert len({item.event_id for item in pressure_zero}) == 2
    assert {
        (
            item.strictly_lower_count,
            item.equal_count,
            item.strictly_higher_count,
        )
        for item in pressure_zero
    } == {(19, 2, 19)}
    source_by_event = _source_by_event(_covering())
    expected_group_sha256 = hash_payload(
        {
            "covering_record_ids": sorted(
                source_by_event[item.event_id].covering_record_id
                for item in pressure_zero
            ),
            "decision_at": pressure_zero[0].decision_at,
            "decision_session": pressure_zero[0].decision_session,
            "role": StockScoreOrderRole.PRESSURE.value,
            "score": {"denominator": 1, "numerator": 0},
            "settlement_date": pressure_zero[0].settlement_date,
        }
    )
    assert {
        item.equivalence_group_sha256 for item in pressure_zero
    } == {expected_group_sha256}
    nonzero = next(
        item
        for item in inventory.dispositions
        if item.role is StockScoreOrderRole.PRESSURE
        and item.score is not None
        and item.score != ExactRational(0, 1)
    )
    assert nonzero.equivalence_group_sha256 != expected_group_sha256


def test_score_order_identity_hashes_have_an_independent_oracle():
    source_by_event = _source_by_event(_covering())
    row = _inventory().dispositions[0]
    source = source_by_event[row.event_id]
    expected_slot_id = hash_payload(
        {
            "inventory_id": SCORE_ORDER_INVENTORY_ID,
            "role": row.role.value,
            "source_covering_slot_id": source.covering_slot_id,
        }
    )
    expected_record_id = hash_payload(
        {
            "score_order_slot_id": expected_slot_id,
            "source_covering_record_id": source.covering_record_id,
        }
    )
    assert row.score_order_slot_id == expected_slot_id
    assert row.score_order_record_id == expected_record_id


def test_covering_order_is_the_exact_inverse_of_pressure_order():
    inventory = _inventory()
    pressure = {
        item.event_id: item
        for item in inventory.dispositions
        if item.role is StockScoreOrderRole.PRESSURE
    }
    covering = {
        item.event_id: item
        for item in inventory.dispositions
        if item.role is StockScoreOrderRole.COVERING
    }
    assert pressure.keys() == covering.keys()
    for event_id, pressure_row in pressure.items():
        covering_row = covering[event_id]
        if pressure_row.score is None:
            assert covering_row.score is None
            assert covering_row.strictly_lower_count is None
            assert covering_row.equal_count is None
            assert covering_row.strictly_higher_count is None
        else:
            assert covering_row.score == ExactRational.from_fraction(
                -pressure_row.score.to_fraction()
            )
            assert covering_row.strictly_lower_count == (
                pressure_row.strictly_higher_count
            )
            assert covering_row.equal_count == pressure_row.equal_count
            assert covering_row.strictly_higher_count == (
                pressure_row.strictly_lower_count
            )


def test_score_order_partitions_four_cycles_without_cross_release_counts():
    inventory = _four_cycle_inventory()
    release_keys = {
        (item.settlement_date, item.decision_session)
        for item in inventory.dispositions
    }
    assert len(release_keys) == 4
    assert len(inventory.dispositions) == 160
    for role in StockScoreOrderRole:
        for release_key in release_keys:
            rows = tuple(
                item
                for item in inventory.dispositions
                if item.role is role
                and (item.settlement_date, item.decision_session) == release_key
            )
            assert len(rows) == 20
            scored = tuple(item for item in rows if item.score is not None)
            assert len(scored) in (0, 20)
            for item in scored:
                assert (
                    item.strictly_lower_count
                    + item.equal_count
                    + item.strictly_higher_count
                    == 20
                )


def test_score_order_retains_every_terminal_source_row_for_both_roles():
    covering = _covering()
    inventory = _inventory()
    source_by_event = _source_by_event(covering)
    output_events = [item.event_id for item in inventory.dispositions]
    assert set(output_events) == set(source_by_event)
    assert all(output_events.count(event_id) == 2 for event_id in source_by_event)

    for item in inventory.dispositions:
        source = source_by_event[item.event_id]
        assert item.refusal_reasons == source.refusal_reasons
        expected_score = (
            source.source_s1_score
            if item.role is StockScoreOrderRole.PRESSURE
            else source.covering_score
        )
        assert item.score == expected_score
        if expected_score is None:
            assert item.strictly_lower_count is None
            assert item.equal_count is None
            assert item.strictly_higher_count is None


def test_score_order_empty_batch_is_exact_and_non_authoritative():
    inventory = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(())
    )
    payload = inventory.to_payload()
    assert inventory.dispositions == ()
    assert inventory.source_projection_count == 0
    assert inventory.disposition_count == 0
    assert inventory.release_count == 0
    assert inventory.source_score_batch_sha256 is None
    assert payload["source_covering_batch"]["projections"] == []
    assert payload["source_batch_verification_required"] is False
    assert payload["standalone_source_authenticated"] is False
    assert payload["production_authoritative"] is False


def test_score_order_all_refused_release_retains_rows_outside_denominator():
    covering = build_pit_stock_covering_scores(_single_sector_scores(19))
    inventory = build_stock_score_order_inventory(covering)
    release_keys = {
        (
            item.settlement_date,
            item.decision_session,
            item.decision_at,
        )
        for item in covering.projections
    }
    assert len(inventory.dispositions) == 2 * len(covering.projections)
    assert inventory.release_count == len(release_keys)
    assert all(item.score is None for item in inventory.dispositions)
    assert all(item.scoreable_count is None for item in inventory.dispositions)
    assert all(item.strictly_lower_count is None for item in inventory.dispositions)
    assert all(item.equal_count is None for item in inventory.dispositions)
    assert all(item.strictly_higher_count is None for item in inventory.dispositions)


@pytest.mark.parametrize(
    ("published_at", "terminal_reason"),
    (
        ("2024-02-13T13:00:00Z", "superseded_at_release_cutoff"),
        ("2024-02-13T16:00:00Z", "not_visible_at_release_cutoff"),
    ),
)
def test_score_order_retains_corrected_revision_terminal_rows(
    published_at,
    terminal_reason,
):
    covering = build_pit_stock_covering_scores(
        _scores(correction=(0, published_at))
    )
    inventory = build_stock_score_order_inventory(covering)
    source_events = {item.event_id for item in covering.projections}
    assert {item.event_id for item in inventory.dispositions} == source_events
    target = tuple(
        item
        for item in inventory.dispositions
        if item.security_id == "sec-si3c-000"
        and item.refusal_reasons == (terminal_reason,)
    )
    assert len(target) == 2
    assert {item.role for item in target} == set(StockScoreOrderRole)
    for item in target:
        assert item.score is None
        assert item.strictly_lower_count is None
        assert item.equal_count is None
        assert item.strictly_higher_count is None
    release_key = (
        target[0].settlement_date,
        target[0].decision_session,
        target[0].decision_at,
    )
    for role in StockScoreOrderRole:
        release_rows = tuple(
            item
            for item in inventory.dispositions
            if item.role is role
            and (
                item.settlement_date,
                item.decision_session,
                item.decision_at,
            )
            == release_key
        )
        scored = tuple(item for item in release_rows if item.score is not None)
        assert len(release_rows) == 41
        assert len(scored) == 40
        for item in scored:
            assert item.scoreable_count == 40
            assert (
                item.strictly_lower_count
                + item.equal_count
                + item.strictly_higher_count
                == 40
            )


def test_score_order_is_input_order_invariant_and_canonically_serialized():
    scores = _non_affine_scores()
    expected = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(scores)
    )
    reordered = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(tuple(reversed(scores)))
    )
    assert reordered.to_payload() == expected.to_payload()
    assert reordered.sha256 == expected.sha256
    assert expected.sha256 == hash_payload(expected.to_payload())
    assert canonical_json(expected.to_payload()) == canonical_json(
        deepcopy(expected.to_payload())
    )
    assert not _contains_float(expected.to_payload())


def test_score_order_contract_exposes_no_percentile_seed_or_action_decision():
    payload = _inventory().to_payload()
    assert set(payload) == {
        "authority",
        "disposition_count",
        "dispositions",
        "independent_return_evaluation_required",
        "investability_screen_applied",
        "outcome_access_authorized",
        "percentile_policy_applied",
        "production_authoritative",
        "ranking_decision_authorized",
        "release_count",
        "research_gate_sha256",
        "return_effect_symmetry_assumed",
        "schema_version",
        "score_order_inventory_id",
        "seed_selection_authorized",
        "source_batch_verification_required",
        "source_covering_batch",
        "source_covering_batch_sha256",
        "source_projection_count",
        "source_score_batch_sha256",
        "standalone_source_authenticated",
    }
    assert payload["independent_return_evaluation_required"] is True
    assert payload["investability_screen_applied"] is False
    assert payload["percentile_policy_applied"] is False
    assert payload["ranking_decision_authorized"] is False
    assert payload["seed_selection_authorized"] is False
    assert payload["production_authoritative"] is False
    assert payload["outcome_access_authorized"] is False
    assert payload["return_effect_symmetry_assumed"] is False
    assert payload["source_batch_verification_required"] is True
    assert payload["standalone_source_authenticated"] is False
    for row in payload["dispositions"]:
        assert set(row) == {
            "authority",
            "decision_at",
            "decision_session",
            "equal_count",
            "equivalence_group_sha256",
            "event_id",
            "independent_return_evaluation_required",
            "investability_screen_applied",
            "normalization_cohort_sha256",
            "normalization_policy_sha256",
            "outcome_access_authorized",
            "percentile_policy_applied",
            "production_authoritative",
            "ranking_decision_authorized",
            "refusal_reasons",
            "research_gate_sha256",
            "return_effect_symmetry_assumed",
            "revision_selection_state",
            "role",
            "schema_version",
            "score",
            "score_order_inventory_id",
            "score_order_record_id",
            "score_order_slot_id",
            "scoreable_count",
            "security_id",
            "seed_selection_authorized",
            "selected_event_id",
            "settlement_date",
            "source_batch_verification_required",
            "source_covering_batch_sha256",
            "source_covering_disposition_sha256",
            "source_covering_record_id",
            "source_covering_score",
            "source_disposition_sha256",
            "source_normalization_slot_id",
            "source_s1_outcome_sha256",
            "source_s1_score",
            "source_score_batch_sha256",
            "standalone_source_authenticated",
            "strictly_higher_count",
            "strictly_lower_count",
        }
        assert row["independent_return_evaluation_required"] is True
        assert row["investability_screen_applied"] is False
        assert row["outcome_access_authorized"] is False
        assert row["percentile_policy_applied"] is False
        assert row["production_authoritative"] is False
        assert row["ranking_decision_authorized"] is False
        assert row["return_effect_symmetry_assumed"] is False
        assert row["seed_selection_authorized"] is False
        assert row["source_batch_verification_required"] is True
        assert row["standalone_source_authenticated"] is False

    forbidden_keys = {
        "action",
        "allocation",
        "buy",
        "decile",
        "eligibility",
        "eligible",
        "etf_id",
        "is_seed",
        "long",
        "order",
        "outcome",
        "percentile",
        "portfolio_weight",
        "position",
        "qc",
        "quantconnect",
        "rank",
        "sell",
        "seed_side",
        "short",
        "threshold",
        "trade",
        "underweight",
    }
    stack = [payload]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            assert forbidden_keys.isdisjoint(current)
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)


def test_score_order_package_root_remains_unexported():
    for name in (
        "StockScoreOrderBatch",
        "StockScoreOrderDisposition",
        "StockScoreOrderError",
        "StockScoreOrderRole",
        "build_stock_score_order_inventory",
    ):
        assert name not in canonical_short_interest_package.__all__
        assert not hasattr(canonical_short_interest_package, name)


def test_score_order_builder_is_parameter_free_by_signature():
    parameters = tuple(
        inspect.signature(build_stock_score_order_inventory).parameters.values()
    )
    assert len(parameters) == 1
    assert parameters[0].name == "covering_batch"
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[0].default is inspect.Parameter.empty


def test_score_order_builder_requires_an_exact_complete_covering_batch():
    covering = _covering()
    with pytest.raises(StockScoreOrderError, match="exact StockCoveringBatch"):
        build_stock_score_order_inventory(list(covering.projections))

    class BatchSubclass(StockCoveringBatch):
        pass

    forged_subclass = object.__new__(BatchSubclass)
    for name in covering.__dataclass_fields__:
        object.__setattr__(forged_subclass, name, getattr(covering, name))
    with pytest.raises(StockScoreOrderError, match="exact StockCoveringBatch"):
        build_stock_score_order_inventory(forged_subclass)

    missing = _tampered_covering_batch(
        covering,
        projections=covering.projections[:-1],
    )
    with pytest.raises(StockScoreOrderError, match="source covering batch"):
        build_stock_score_order_inventory(missing)

    duplicate = _tampered_covering_batch(
        covering,
        projections=covering.projections + (covering.projections[-1],),
    )
    with pytest.raises(StockScoreOrderError, match="source covering batch"):
        build_stock_score_order_inventory(duplicate)


def test_score_order_builder_refuses_instance_method_substitution():
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    alternate = build_pit_stock_covering_scores(_scores())
    callback_count = 0

    def substitute_payload():
        nonlocal callback_count
        callback_count += 1
        return StockCoveringBatch.to_payload(alternate)

    object.__setattr__(covering, "to_payload", substitute_payload)
    with pytest.raises(StockScoreOrderError, match="unexpected instance state"):
        build_stock_score_order_inventory(covering)
    assert callback_count == 0


def test_score_order_capture_does_not_dispatch_source_data_descriptor():
    covering = build_pit_stock_covering_scores(())
    original_authority = StockCoveringBatch.authority

    class AuthorityDescriptor:
        callback_count = 0

        def __get__(self, instance, owner):
            type(self).callback_count += 1
            if instance is None:
                return self
            state = object.__getattribute__(instance, "__dict__")
            return dict.__getitem__(state, "authority")

        def __set__(self, instance, value):
            state = object.__getattribute__(instance, "__dict__")
            dict.__setitem__(state, "authority", value)

    try:
        setattr(StockCoveringBatch, "authority", AuthorityDescriptor())
        inventory = build_stock_score_order_inventory(covering)
    finally:
        setattr(StockCoveringBatch, "authority", original_authority)
    assert AuthorityDescriptor.callback_count == 0
    assert inventory.authority.endswith("score_order_batch_only")


def test_score_order_builder_refuses_nested_source_method_callback():
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    target = covering._projections[0]
    callback_count = 0

    def injected_validation():
        nonlocal callback_count
        callback_count += 1

    object.__setattr__(target, "_validate_structure", injected_validation)
    with pytest.raises(StockScoreOrderError, match="unexpected instance state"):
        build_stock_score_order_inventory(covering)
    assert callback_count == 0


def test_score_order_builder_refuses_dynamic_instance_key_without_callback():
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    target = covering._projections[0]
    state = object.__getattribute__(target, "__dict__")
    value = dict.__getitem__(state, "source_s1_score")
    dict.__delitem__(state, "source_s1_score")

    class DynamicKey(str):
        called = False
        __hash__ = str.__hash__

        def __eq__(self, other):
            type(self).called = True
            return str.__eq__(self, other)

    dict.__setitem__(state, DynamicKey("source_s1_score"), value)
    DynamicKey.called = False
    with pytest.raises(StockScoreOrderError, match="unexpected instance state"):
        build_stock_score_order_inventory(covering)
    assert DynamicKey.called is False


def test_score_order_builder_refuses_dynamic_rational_key_without_callback():
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    score = next(
        item.source_s1_score
        for item in covering._projections
        if item.source_s1_score is not None
    )
    state = object.__getattribute__(score, "__dict__")
    value = dict.__getitem__(state, "numerator")
    dict.__delitem__(state, "numerator")

    class DynamicKey(str):
        called = False
        __hash__ = str.__hash__

        def __eq__(self, other):
            type(self).called = True
            return str.__eq__(self, other)

    dict.__setitem__(state, DynamicKey("numerator"), value)
    DynamicKey.called = False
    with pytest.raises(StockScoreOrderError, match="unexpected instance state"):
        build_stock_score_order_inventory(covering)
    assert DynamicKey.called is False


def test_score_order_builder_rejects_cross_release_and_mixed_source_rows():
    covering = _covering()
    first = covering.projections[0]
    cross_release = _tampered_covering(
        first,
        settlement_date=covering.projections[-1].settlement_date,
        decision_session=covering.projections[-1].decision_session,
        decision_at=covering.projections[-1].decision_at,
    )
    cross_release_batch = _tampered_covering_batch(
        covering,
        projections=(cross_release,) + covering.projections[1:],
    )
    with pytest.raises(StockScoreOrderError, match="source covering batch"):
        build_stock_score_order_inventory(cross_release_batch)

    alternate = build_pit_stock_covering_scores(_scores())
    replaced = next(
        item
        for item in covering.projections
        if item.security_id == "sec-si3c-010"
        and item.source_s1_score is not None
    )
    alien_source = next(
        item
        for item in alternate.projections
        if item.security_id == replaced.security_id
        and item.settlement_date == replaced.settlement_date
    )
    assert alien_source.event_id != replaced.event_id
    alien = _tampered_covering(
        alien_source,
        source_score_batch_sha256=covering.source_score_batch_sha256,
    )
    mixed = _tampered_covering_batch(
        covering,
        projections=tuple(
            alien if item is replaced else item
            for item in covering.projections
        ),
    )
    with pytest.raises(StockScoreOrderError, match="source covering batch"):
        build_stock_score_order_inventory(mixed)


def test_score_order_contracts_are_frozen_and_constructor_closed():
    inventory = _inventory()
    result = inventory.dispositions[-1]
    with pytest.raises(TypeError, match="constructed only"):
        StockScoreOrderDisposition()
    with pytest.raises(TypeError, match="constructed only"):
        StockScoreOrderBatch()
    with pytest.raises(FrozenInstanceError):
        result.score = ExactRational(0, 1)
    with pytest.raises(FrozenInstanceError):
        inventory.dispositions = ()


def test_score_order_contracts_reject_behavior_bearing_instance_methods():
    inventory = _inventory()
    row = inventory.dispositions[0]
    for target, name in (
        (row, "_validate_structure"),
        (row, "_to_payload_unchecked"),
        (row, "to_payload"),
        (inventory, "_validate_structure"),
        (inventory, "to_payload"),
    ):
        with pytest.raises(AttributeError):
            object.__setattr__(target, name, lambda: None)
    assert inventory.to_payload()["dispositions"][0][
        "ranking_decision_authorized"
    ] is False


def test_score_order_disposition_counts_and_roles_fail_closed():
    result = next(
        item for item in _inventory().dispositions if item.score is not None
    )
    cases = (
        ({"role": result.role.value}, "role"),
        ({"score": ExactRational(1, 1)}, "source score"),
        ({"strictly_lower_count": True}, "count"),
        ({"equal_count": result.equal_count + 1}, "count"),
        ({"strictly_higher_count": result.strictly_higher_count + 1}, "count"),
        ({"refusal_reasons": ("invented_refusal",)}, "refusal"),
    )
    for changes, message in cases:
        with pytest.raises(StockScoreOrderError, match=message):
            _clone_disposition(result, **changes).to_payload()


def test_score_order_role_singletons_refuse_mutated_internal_value():
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    role = StockScoreOrderRole.PRESSURE
    original_value = object.__getattribute__(role, "_value_")
    try:
        object.__setattr__(role, "_value_", "forged_seed_role")
        with pytest.raises(StockScoreOrderError, match="role singleton"):
            build_stock_score_order_inventory(covering)
    finally:
        object.__setattr__(role, "_value_", original_value)
    inventory = build_stock_score_order_inventory(covering)
    assert {
        item["role"] for item in inventory.to_payload()["dispositions"]
    } == {"pressure", "covering"}


def test_score_order_revision_state_refuses_mutated_internal_value():
    inventory = _inventory()
    state = RevisionSelectionState.SELECTED
    original_value = object.__getattribute__(state, "_value_")

    class ForgedValue(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            return other == "selected_at_release_cutoff"

    try:
        object.__setattr__(state, "_value_", ForgedValue("forged_selection"))
        with pytest.raises(StockScoreOrderError, match="state singleton"):
            inventory.to_payload()
    finally:
        object.__setattr__(state, "_value_", original_value)
    assert {
        item["revision_selection_state"]
        for item in inventory.to_payload()["dispositions"]
        if item["revision_selection_state"]
        == "selected_at_release_cutoff"
    } == {"selected_at_release_cutoff"}


def test_score_order_disposition_rejects_scalar_subclasses():
    class IntSubclass(int):
        pass

    class StrSubclass(str):
        pass

    class RationalSubclass(ExactRational):
        pass

    result = next(
        item for item in _inventory().dispositions if item.score is not None
    )
    cases = (
        (
            {"strictly_lower_count": IntSubclass(result.strictly_lower_count)},
            "exact non-negative integer",
        ),
        (
            {"score_order_record_id": StrSubclass(result.score_order_record_id)},
            "SHA-256",
        ),
        (
            {
                "_bound_source_covering_batch_sha256": StrSubclass(
                    result._bound_source_covering_batch_sha256
                )
            },
            "SHA-256",
        ),
        (
            {
                "source_s1_score": RationalSubclass(
                    result.source_s1_score.numerator,
                    result.source_s1_score.denominator,
                )
            },
            "exact ExactRational",
        ),
    )
    for changes, message in cases:
        with pytest.raises(StockScoreOrderError, match=message):
            _clone_disposition(result, **changes).to_payload()


def test_score_order_disposition_rejects_behavior_bearing_rational():
    result = next(
        item for item in _inventory().dispositions if item.score is not None
    )
    forged_score = ExactRational(
        result.score.numerator,
        result.score.denominator,
    )
    object.__setattr__(
        forged_score,
        "to_fraction",
        lambda: result.score.to_fraction(),
    )
    with pytest.raises(StockScoreOrderError, match="unexpected instance state"):
        _clone_disposition(result, score=forged_score).to_payload()


def test_terminal_score_refuses_dynamic_equality_without_callback():
    terminal = next(
        item for item in _inventory().dispositions if item.score is None
    )
    forged = _clone_disposition(terminal)

    class MutatingEquality:
        called = False

        def __eq__(self, other):
            type(self).called = True
            object.__setattr__(forged, "score", None)
            object.__setattr__(forged, "authority", "forged_after_check")
            return other is None

    object.__setattr__(forged, "score", MutatingEquality())
    with pytest.raises(StockScoreOrderError, match="terminal score-order"):
        forged.to_payload()
    assert MutatingEquality.called is False


def test_score_order_disposition_lineage_and_scope_values_fail_closed():
    result = next(
        item for item in _inventory().dispositions if item.score is not None
    )
    cases = (
        ({"score_order_slot_id": "0" * 64}, "slot identity"),
        ({"score_order_record_id": "0" * 64}, "record identity"),
        ({"source_covering_batch_sha256": "0" * 64}, "source covering batch"),
        ({"source_covering_disposition_sha256": "0" * 64}, "source covering"),
        ({"source_score_batch_sha256": "0" * 64}, "source score batch"),
        ({"normalization_policy_sha256": "0" * 64}, "normalization policy"),
        ({"research_gate_sha256": "0" * 64}, "SI-0M gate"),
        ({"schema_version": "2.0"}, "schema_version"),
        ({"authority": "production_score_order"}, "authority"),
        ({"production_authoritative": True}, "non-production"),
    )
    for changes, message in cases:
        with pytest.raises(StockScoreOrderError, match=message):
            _clone_disposition(result, **changes).to_payload()


def test_score_order_row_rejects_coherently_rehashed_hidden_source_scope():
    result = next(
        item for item in _inventory().dispositions if item.score is not None
    )
    source = json.loads(result._source_covering_projection_payload_json)
    source["production_authoritative"] = True
    forged = _clone_disposition(
        result,
        _source_covering_projection_payload_json=canonical_json(source),
        source_covering_disposition_sha256=hash_payload(source),
    )
    with pytest.raises(StockScoreOrderError, match="exact SI-3D contract"):
        forged.to_payload()


def test_score_order_batch_rejects_missing_duplicate_and_count_drift():
    inventory = _inventory()
    cases = (
        ({"dispositions": inventory.dispositions[:-1]}, "complete"),
        (
            {"dispositions": inventory.dispositions + (inventory.dispositions[-1],)},
            "duplicate",
        ),
        ({"source_projection_count": len(_covering()) + 1}, "projection count"),
        ({"disposition_count": len(inventory.dispositions) + 1}, "disposition count"),
        ({"release_count": 3}, "release count"),
        ({"release_count": True}, "release count"),
        ({"schema_version": "2.0"}, "schema_version"),
        ({"authority": "production_score_order_batch"}, "authority"),
        ({"production_authoritative": True}, "non-production"),
    )
    for changes, message in cases:
        with pytest.raises(StockScoreOrderError, match=message):
            _clone_batch(inventory, **changes).to_payload()


def test_score_order_batch_preflights_rows_before_hash_callbacks():
    inventory = _inventory()
    original = inventory.dispositions[0]
    forged_row = _clone_disposition(original)
    dispositions = (forged_row,) + inventory.dispositions[1:]
    forged_batch = _clone_batch(inventory, dispositions=dispositions)

    class MutatingDigest(str):
        called = False

        def __hash__(self):
            type(self).called = True
            object.__setattr__(
                forged_row,
                "source_covering_disposition_sha256",
                str(self),
            )
            object.__setattr__(
                forged_batch,
                "authority",
                "forged_after_check",
            )
            return super().__hash__()

    object.__setattr__(
        forged_row,
        "source_covering_disposition_sha256",
        MutatingDigest(original.source_covering_disposition_sha256),
    )
    with pytest.raises(StockScoreOrderError, match="SHA-256"):
        forged_batch.to_payload()
    assert MutatingDigest.called is False


@pytest.mark.parametrize("target_kind", ("row", "batch"))
def test_score_order_serialization_revalidates_after_gate_callback(
    monkeypatch,
    target_kind,
):
    inventory = _inventory()
    target = (
        _clone_disposition(inventory.dispositions[0])
        if target_kind == "row"
        else _clone_batch(inventory)
    )
    real_gate = stock_score_order_module.require_short_interest_research_gate
    callback_count = 0

    def mutate_during_gate(gate):
        nonlocal callback_count
        receipt = real_gate(gate)
        callback_count += 1
        object.__setattr__(target, "authority", "forged_after_gate")
        return receipt

    monkeypatch.setattr(
        stock_score_order_module,
        "require_short_interest_research_gate",
        mutate_during_gate,
    )
    with pytest.raises(StockScoreOrderError, match="authority"):
        target.to_payload()
    assert callback_count == 1


def test_score_order_batch_recomputes_counts_against_release_population():
    inventory = _inventory()
    target_index, target = next(
        (index, item)
        for index, item in enumerate(inventory.dispositions)
        if item.score is not None and item.strictly_higher_count > 0
    )
    forged = _clone_disposition(
        target,
        strictly_lower_count=target.strictly_lower_count + 1,
        strictly_higher_count=target.strictly_higher_count - 1,
    )
    dispositions = list(inventory.dispositions)
    dispositions[target_index] = forged
    with pytest.raises(StockScoreOrderError, match="incorrect exact counts"):
        _clone_batch(inventory, dispositions=tuple(dispositions)).to_payload()


def test_score_order_payload_is_detached_from_returned_and_caller_owned_state():
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    inventory = build_stock_score_order_inventory(covering)
    expected_payload = inventory.to_payload()
    expected_sha256 = inventory.sha256

    returned = inventory.to_payload()
    returned["dispositions"].clear()
    if type(returned.get("source_covering_batch")) is dict:
        returned["source_covering_batch"].clear()
    assert inventory.to_payload() == expected_payload
    assert inventory.sha256 == expected_sha256

    target = next(item for item in covering._projections if item.source_s1_score)
    object.__setattr__(target, "source_s1_score", ExactRational(1, 1))
    assert inventory.to_payload() == expected_payload
    assert inventory.sha256 == expected_sha256


def test_score_order_iterator_refuses_row_sabotage_before_next_yield():
    inventory = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(_fresh_non_affine_scores())
    )
    iterator = iter(inventory)
    assert next(iterator) is inventory._dispositions[0]
    object.__setattr__(inventory._dispositions[-1], "authority", "forged")
    with pytest.raises(StockScoreOrderError, match="authority"):
        next(iterator)


def test_score_order_capture_is_atomic_against_post_snapshot_source_mutation(
    monkeypatch,
):
    expected = build_stock_score_order_inventory(
        build_pit_stock_covering_scores(_fresh_non_affine_scores())
    )
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    target = next(
        item for item in covering._projections if item.source_s1_score is not None
    )
    real_canonical_json = stock_score_order_module.canonical_json
    mutated = False

    def mutate_live_source_after_capture(value):
        nonlocal mutated
        if (
            not mutated
            and type(value) is dict
            and "covering_projection_id" in value
            and "projections" in value
        ):
            object.__setattr__(
                target,
                "source_s1_score",
                ExactRational(123, 1),
            )
            mutated = True
        return real_canonical_json(value)

    monkeypatch.setattr(
        stock_score_order_module,
        "canonical_json",
        mutate_live_source_after_capture,
    )
    actual = build_stock_score_order_inventory(covering)
    assert mutated is True
    assert target.source_s1_score == ExactRational(123, 1)
    assert actual.to_payload() == expected.to_payload()


def test_score_order_builder_revalidates_gate_callback_source_mutation(
    monkeypatch,
):
    covering = build_pit_stock_covering_scores(_fresh_non_affine_scores())
    target = next(
        item for item in covering._projections if item.source_s1_score is not None
    )
    real_gate = stock_score_order_module.require_short_interest_research_gate
    mutated = False

    def mutate_during_gate(gate):
        nonlocal mutated
        receipt = real_gate(gate)
        if not mutated:
            object.__setattr__(
                target,
                "source_s1_score",
                ExactRational(123, 1),
            )
            mutated = True
        return receipt

    monkeypatch.setattr(
        stock_score_order_module,
        "require_short_interest_research_gate",
        mutate_during_gate,
    )
    with pytest.raises(StockScoreOrderError, match="source covering batch"):
        build_stock_score_order_inventory(covering)
    assert mutated is True


def test_score_order_rejects_coherently_rehashed_embedded_score_forgery():
    inventory = _inventory()
    source = json.loads(inventory._source_covering_batch_payload_json)
    target = next(
        item
        for item in source["projections"]
        if item["source_s1_score"] is not None
    )
    target["source_s1_score"] = {"denominator": 1, "numerator": 123}
    target["covering_score"] = {"denominator": 1, "numerator": -123}
    source_json = canonical_json(source)
    forged_batch = _clone_batch(
        inventory,
        _source_covering_batch_payload_json=source_json,
        source_covering_batch_sha256=hash_payload(source),
    )
    with pytest.raises(StockScoreOrderError, match="detached from score batch"):
        forged_batch.to_payload()


def test_score_order_row_refuses_a_negative_order_count():
    """A negative count must fail even when the count identity still sums."""
    scored = next(
        item for item in _inventory().dispositions if item.score is not None
    )
    negative = _clone_disposition(
        scored,
        strictly_lower_count=scored.strictly_lower_count - 1,
        equal_count=scored.equal_count + 1,
    )
    assert (
        negative.strictly_lower_count
        + negative.equal_count
        + negative.strictly_higher_count
        == negative.scoreable_count
    )
    assert negative.strictly_lower_count < 0
    with pytest.raises(StockScoreOrderError, match="non-negative integer"):
        negative.to_payload()


def test_score_order_batch_refuses_a_swapped_role_pair():
    """The two roles of one projection must stay in canonical order."""
    inventory = _inventory()
    rows = list(inventory.dispositions)
    assert rows[0].role is StockScoreOrderRole.PRESSURE
    assert rows[1].role is StockScoreOrderRole.COVERING
    assert (
        rows[0].source_covering_disposition_sha256
        == rows[1].source_covering_disposition_sha256
    )
    swapped = _clone_batch(
        inventory,
        dispositions=tuple([rows[1], rows[0]] + rows[2:]),
    )
    with pytest.raises(StockScoreOrderError, match="canonically ordered"):
        swapped.to_payload()
