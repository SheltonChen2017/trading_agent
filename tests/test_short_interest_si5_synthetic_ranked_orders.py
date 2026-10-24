"""The actual synthetic ranking chain reaches orders without admitting history."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import inspect
import json
from pathlib import Path
import subprocess

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    require_si5_offline_protocol,
)
from research.short_interest_etf.si5_synthetic_rehearsal import (
    run_si5_synthetic_rehearsal,
)
from research.short_interest_etf.si5_synthetic_orders import SI5SyntheticOrderError
import research.short_interest_etf.si5_synthetic_ranked_orders as bridge
from research.short_interest_etf.contracts import parse_utc_timestamp


LOOKBACKS = [20, 60, 120, 252]
COSTS = [0, 5, 10, 20]
RECORD_PATH = "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"
DECISION_COMMIT = "782e85ecd2867537f5f7e93abe4d9ab66eb9bddc"
DECISION_SHA256 = "a2c8e49681dd890583255f336c838b79b415dd70c8a078e221f41a9f05fde177"


@pytest.fixture(scope="module")
def canonical_payload():
    return bridge.run_si5_synthetic_ranked_order_scenario().to_payload()


@pytest.fixture(scope="module")
def independently_built_pipeline():
    sources = bridge._build_fixture_sources()
    evidence = bridge.build_stock_investability(sources.vintage, sources.references, sources.history)
    population = bridge.build_stock_eligible_population_inventory(evidence)
    binding = bridge.build_stock_population_binding_inventory(population)
    ranking = bridge.build_stock_eligible_ranking_inventory(binding)
    cohort = bridge.build_si5_stock_cohort_manifest(ranking)
    return sources, ranking.to_payload(), cohort.to_payload(), binding.to_payload()


def _executed_release(payload):
    executed = [row for row in payload["releases"] if row["executable"] is True]
    assert len(executed) == 1
    return executed[0]


def _fraction(payload):
    assert type(payload) is dict
    assert set(payload) == {"numerator", "denominator"}
    assert all(type(value) is int for value in payload.values())
    return Fraction(payload["numerator"], payload["denominator"])


def test_public_api_is_fixed_id_only_and_keeps_real_authority_closed(canonical_payload):
    assert bridge.SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID == (
        "si5-synthetic-ranked-order-routing-v1"
    )
    assert issubclass(bridge.SI5SyntheticRankedOrderError, ValueError)
    assert list(inspect.signature(bridge.run_si5_synthetic_ranked_order_scenario).parameters) == [
        "scenario_id"
    ]
    payload = canonical_payload
    assert payload["scenario_id"] == bridge.SI5_SYNTHETIC_RANKED_ORDER_SCENARIO_ID
    assert payload["synthetic_only"] is True
    for name in (
        "actual_source_admitted", "point_in_time_data_verified", "outcome_access_authorized",
        "qc_backtest_authorized", "trading_authority", "real_backtesting_ready",
    ):
        assert payload[name] is False
    assert payload["selected_lookback"] is None
    assert type(payload["authorized_real_outcome_looks"]) is int
    assert type(payload["consumed_real_outcome_looks"]) is int
    assert payload["authorized_real_outcome_looks"] == payload["consumed_real_outcome_looks"] == 0
    assert _fraction(payload["allocated_alpha"]) == 0
    assert payload["permanent_look_ids"] == []
    assert SI5_OFFLINE_PROTOCOL.terminal_value_rule is None
    assert SI5_OFFLINE_PROTOCOL.order_cashflow_rule is None


def test_receipt_binds_the_real_typed_pipeline_and_unchanged_protocol(canonical_payload):
    payload = canonical_payload
    hashes = (
        "fixture_recipe_sha256", "source_vintage_sha256", "reference_bundle_sha256",
        "market_history_sha256", "population_inventory_sha256", "binding_inventory_sha256",
        "ranking_inventory_sha256", "cohort_manifest_sha256", "routing_sha256",
        "bridge_policy_sha256", "demonstration_policy_sha256", "si5_offline_protocol_sha256",
    )
    for name in hashes:
        value = payload[name]
        assert type(value) is str and len(value) == 64
        assert all(char in "0123456789abcdef" for char in value)
    assert len({payload[name] for name in hashes[:8]}) == 8
    assert payload["si5_offline_protocol_sha256"] == require_si5_offline_protocol(
        SI5_OFFLINE_PROTOCOL
    ) == "bfa06b282132a0b5ceef4e9e4e3900f0dea6ffaadad8e00e22f5c8f837022972"
    assert payload["demonstration_policy_sha256"] == (
        "ab4a0e5c080324100143417469d845144c3417273e95bf5abf410db3c51e07eb"
    )
    assert payload["result_sha256"] == hash_payload({
        key: value for key, value in payload.items() if key != "result_sha256"
    })


def test_warmup_and_no_successor_releases_are_explicit_not_dropped(canonical_payload):
    releases = canonical_payload["releases"]
    assert [row["settlement_date"] for row in releases] == [
        "2024-01-12", "2024-01-31", "2024-02-15"
    ]
    assert [row["executable"] for row in releases] == [False, True, False]
    assert [row["cohort_comparable"] for row in releases] == [False, True, True]
    for release in releases:
        assert [row["lookback_sessions"] for row in release["windows"]] == LOOKBACKS
    assert releases[0]["refusal_reasons"]
    assert "no_authenticated_successor_release" in releases[-1]["refusal_reasons"]
    for release, status in ((releases[0], "cohort_refused"), (releases[-1], "no_successor_release")):
        for window in release["windows"]:
            assert window["routing_status"] == status
            assert window["cost_runs"] == []


@pytest.mark.parametrize("lookback", LOOKBACKS)
def test_each_candidate_keeps_entry_clock_and_authenticated_next_release_exit(
    canonical_payload, lookback,
):
    release = _executed_release(canonical_payload)
    window = next(row for row in release["windows"] if row["lookback_sessions"] == lookback)
    assert window["routing_status"] == "executed"
    assert release["decision_at"] == window["entry_open_at"] == "2024-02-13T14:30:00Z"
    assert window["instruction_at"] < window["entry_open_at"]
    assert window["exit_open_at"] == canonical_payload["releases"][-1]["decision_at"]
    assert window["successor_settlement_date"] == "2024-02-15"
    assert window["refusal_reasons"] == []
    assert [run["cost_bps_per_side"] for run in window["cost_runs"]] == COSTS


@pytest.mark.parametrize("lookback", LOOKBACKS)
def test_original_full_ranks_and_tail_lineage_reach_only_their_intended_orders(
    canonical_payload, independently_built_pipeline, lookback,
):
    sources, ranking, cohort, binding = independently_built_pipeline
    payload = canonical_payload
    assert payload["source_vintage_sha256"] == bridge.build_identity(sources.vintage)["content_hash"]
    assert payload["reference_bundle_sha256"] == sources.references.sha256
    assert payload["market_history_sha256"] == sources.history.sha256
    assert payload["ranking_inventory_sha256"] == ranking["inventory_sha256"]
    assert payload["cohort_manifest_sha256"] == cohort["manifest_sha256"]
    assert payload["binding_inventory_sha256"] == binding["inventory_sha256"]
    structural = next(row for row in binding["normalization_cohorts"] if row["settlement_date"] == "2024-01-31")
    assert len(structural["structural_peer_event_ids"]) == 20
    original_release = cohort["releases"][1]
    routed_release = _executed_release(payload)
    original = next(row for row in original_release["lookbacks"] if row["lookback_sessions"] == lookback)
    routed = next(row for row in routed_release["windows"] if row["lookback_sessions"] == lookback)
    assert routed["source_ranking_sha256"] == original["source_ranking"]["ranking_sha256"]
    assert routed_release["release_manifest_sha256"] == original_release["release_manifest_sha256"]
    assert routed["exit_open_at"] == cohort["releases"][2]["decision_at"]
    assert len(original["ranked_security_identity_sha256s"]) == 19
    assert set(row["security_identity_sha256"] for row in routed_release["price_pairs"]) == set(
        original_release["common_security_identity_sha256s"]
    )
    assert len(routed_release["price_pairs"]) == 19
    assert len(original["comparison_rows"]) == 19
    projection_fields = (
        "event_id", "security_id", "security_identity_sha256", "pressure_row_sha256",
        "covering_row_sha256", "high_pressure_tail", "low_pressure_tail",
    )
    for field, event_field in (("long_routes", "low_pressure_event_ids"), ("avoided_routes", "high_pressure_event_ids")):
        expected = {
            row["event_id"]: {key: row[key] for key in projection_fields}
            for row in original["comparison_rows"] if row["event_id"] in original[event_field]
        }
        actual = {
            row["event_id"]: {key: row[key] for key in projection_fields}
            for row in routed[field]
        }
        assert actual == expected
        assert len(actual) == len(routed[field])
    long_ids = {row["security_identity_sha256"] for row in routed["long_routes"]}
    avoided_ids = {row["security_identity_sha256"] for row in routed["avoided_routes"]}
    assert long_ids and avoided_ids and not long_ids & avoided_ids
    # Whole-common prices include stocks in neither order/avoidance tail.
    assert set(original_release["common_security_identity_sha256s"]) - long_ids - avoided_ids
    refused_identity = hash_payload(bridge._identity(19).to_payload())
    for run in routed["cost_runs"]:
        assert {row["security_identity_sha256"] for row in run["orders"]} == long_ids
        assert all(row["security_identity_sha256"] not in avoided_ids | {refused_identity} for row in run["orders"])
        assert {row["side"] for row in run["orders"]} == {"buy", "sell"}
        assert run["short_sales"] is run["leverage"] is False
        for name in ("actual_source_admitted", "outcome_access_authorized", "point_in_time_data_verified", "production_authoritative", "qc_backtest_authorized", "real_backtesting_ready", "trading_authority"):
            assert run[name] is False
    witness = routed_release["entry_fact_witness"]
    assert parse_utc_timestamp(witness["latest_entry_fact_observed_at"], "fact") < parse_utc_timestamp(
        routed["instruction_at"], "instruction"
    ) < parse_utc_timestamp(original_release["decision_at"], "entry")
    assert witness["entry_fact_witness_sha256"] == hash_payload({
        key: value for key, value in witness.items() if key != "entry_fact_witness_sha256"
    })


@pytest.mark.parametrize("lookback", LOOKBACKS)
@pytest.mark.parametrize("cost", COSTS)
def test_all_sixteen_order_books_complete_self_financing_without_short_orders(
    canonical_payload, lookback, cost,
):
    release = _executed_release(canonical_payload)
    window = next(row for row in release["windows"] if row["lookback_sessions"] == lookback)
    run = next(row for row in window["cost_runs"] if row["cost_bps_per_side"] == cost)
    assert run["complete"] is True
    assert run["refusal_reasons"] == []
    assert run["selected_lookback"] is None
    assert run["synthetic_only"] is True
    assert run["real_backtesting_ready"] is False
    assert run["authorized_real_outcome_looks"] == run["consumed_real_outcome_looks"] == 0
    assert run["final_positions"] == []
    assert _fraction(run["ending_cash"]) >= 0
    assert _fraction(run["gross_entry_notional"]) <= _fraction(run["initial_cash"])
    orders = run["orders"]
    assert orders
    buys = [order for order in orders if order["side"] == "buy"]
    sells = [order for order in orders if order["side"] == "sell"]
    assert buys and len(buys) == len(sells)
    assert {order["security_identity_sha256"] for order in buys} == {
        order["security_identity_sha256"] for order in sells
    }
    assert all(_fraction(order["quantity"]) > 0 for order in orders)
    assert all(_fraction(order["cash_after"]) >= 0 for order in orders)
    assert all(_fraction(order["position_quantity_after"]) >= 0 for order in orders)
    assert run["kernel_result_sha256"] == hash_payload({
        key: value for key, value in run.items() if key != "kernel_result_sha256"
    })


@pytest.mark.parametrize("value", [None, "", "caller-prices", True, 20, {}, [], "si5-synthetic-ranked-order-routing-v2"])
def test_unknown_or_noncanonical_scenario_cannot_open_an_input_boundary(value):
    with pytest.raises(bridge.SI5SyntheticRankedOrderError, match="REFUSED"):
        bridge.run_si5_synthetic_ranked_order_scenario(value)


def test_no_prices_source_memberships_or_asserted_pit_flag_can_be_injected():
    for kwargs in (
        {"prices": []}, {"source": {}}, {"memberships": []},
        {"synthetic_only": True}, {"point_in_time_data": True}, {"source_admitted": True},
    ):
        with pytest.raises(TypeError):
            bridge.run_si5_synthetic_ranked_order_scenario(**kwargs)


@pytest.mark.parametrize("name,value", [
    ("_COSTS_BPS", (0, 5, 10, 21)), ("_LOOKBACKS", (20, 60, 120)),
    ("_INITIAL_CASH_USD", "19001"), ("_INSTRUCTION_AT", "2024-02-13T13:01:00Z"),
    ("_DECISION_IDS", ("unapproved-choice",)),
])
def test_fixed_policy_or_recipe_drift_refuses_before_pipeline(monkeypatch, name, value):
    def unexpected_build():
        pytest.fail("changed policy/recipe reached the typed pipeline")
    monkeypatch.setattr(bridge, name, value)
    monkeypatch.setattr(bridge, "_build_fixture_sources", unexpected_build)
    with pytest.raises(bridge.SI5SyntheticRankedOrderError, match="REFUSED"):
        bridge.run_si5_synthetic_ranked_order_scenario()


def test_private_retained_state_is_not_silently_repaired(canonical_payload):
    # This independently tests the retained representation, not a second build.
    result = bridge._result_from_payload(deepcopy(canonical_payload))
    exported = result.to_payload()
    exported["releases"].clear()
    exported["actual_source_admitted"] = True
    assert result.to_payload() == canonical_payload
    corrupted = json.loads(result._payload_json)
    corrupted["actual_source_admitted"] = 0
    object.__setattr__(result, "_payload_json", json.dumps(corrupted, sort_keys=True, separators=(",", ":")))
    with pytest.raises(bridge.SI5SyntheticRankedOrderError, match="REFUSED"):
        result.to_payload()


def test_prior_public_rehearsal_identity_does_not_change():
    assert run_si5_synthetic_rehearsal().sha256 == (
        "f535597577caac1276949d1c1d01f0f99e4ae99dd4612c0347a1349b24f9667d"
    )


def _pricing_release():
    """Valid identity-price projection seam, including all nineteen common names."""
    comparisons = [
        {
            "event_id": f"synthetic-release-event-{index}",
            "security_id": f"sec-si5-ranked-{index:03d}",
            "security_identity_sha256": hash_payload(bridge._identity(index).to_payload()),
        }
        for index in range(19)
    ]
    return {
        "decision_at": "2024-02-13T14:30:00Z",
        "lookbacks": [{"comparison_rows": comparisons}],
        "common_security_identity_sha256s": sorted(
            row["security_identity_sha256"] for row in comparisons
        ),
    }


def test_complete_common_price_projection_has_a_valid_positive_control():
    release = _pricing_release()
    pairs = bridge._price_pairs(release, {"decision_at": "2024-02-28T14:30:00Z"})
    assert len(pairs) == 19
    assert {row["security_identity_sha256"] for row in pairs} == set(release["common_security_identity_sha256s"])
    for pair in pairs:
        assert pair["entry_open_at"] == release["decision_at"]
        assert pair["exit_open_at"] == "2024-02-28T14:30:00Z"
        assert pair["price_pair_sha256"] == hash_payload({
            key: value for key, value in pair.items() if key != "price_pair_sha256"
        })


@pytest.mark.parametrize("field", ["entry_raw_open_usd", "exit_raw_open_usd"])
@pytest.mark.parametrize("invalid", [None, "0", "-1", "NaN"])
def test_non_tail_common_price_is_validated_before_tail_orders(monkeypatch, field, invalid):
    rows = bridge._security_rows()
    # Index nine is neither original extreme; valid tail opens must not hide it.
    rows[9][field] = invalid
    monkeypatch.setattr(bridge, "_security_rows", lambda: rows)
    with pytest.raises((bridge.SI5SyntheticRankedOrderError, SI5SyntheticOrderError), match="REFUSED"):
        bridge._price_pairs(
            _pricing_release(), {"decision_at": "2024-02-28T14:30:00Z"}
        )


def test_price_mapping_cannot_join_a_different_stable_identity_by_security_id():
    release = _pricing_release()
    old_identity = release["lookbacks"][0]["comparison_rows"][9]["security_identity_sha256"]
    impostor = hash_payload(bridge._identity(19).to_payload())
    release["lookbacks"][0]["comparison_rows"][9]["security_identity_sha256"] = impostor
    release["common_security_identity_sha256s"] = sorted(
        impostor if identity == old_identity else identity
        for identity in release["common_security_identity_sha256s"]
    )
    with pytest.raises(bridge.SI5SyntheticRankedOrderError, match="REFUSED"):
        bridge._price_pairs(release, {"decision_at": "2024-02-28T14:30:00Z"})


def test_missing_middle_price_emits_no_partial_order_books(monkeypatch, independently_built_pipeline):
    sources, _, cohort, _ = independently_built_pipeline
    middle_identity = hash_payload(bridge._identity(9).to_payload())
    for window in cohort["releases"][1]["lookbacks"]:
        middle = next(row for row in window["comparison_rows"] if row["security_identity_sha256"] == middle_identity)
        assert middle["low_pressure_tail"] is middle["high_pressure_tail"] is False
    rows = bridge._security_rows()
    rows[9]["entry_raw_open_usd"] = None
    monkeypatch.setattr(bridge, "_security_rows", lambda: rows)
    def forbidden_kernel(*args, **kwargs):
        pytest.fail("missing non-tail price reached a partial order book")
    monkeypatch.setattr(bridge, "_run_synthetic_order_kernel", forbidden_kernel)
    with pytest.raises((bridge.SI5SyntheticRankedOrderError, SI5SyntheticOrderError), match="REFUSED"):
        bridge._routing_payload(sources, deepcopy(cohort))


@pytest.mark.parametrize("instruction", ["2024-02-12T22:00:00Z", "2024-02-13T14:30:00Z", "2024-02-13T14:30:00.000001Z"])
def test_selection_facts_instruction_and_canonical_entry_must_be_strictly_ordered(monkeypatch, instruction):
    sources = bridge._build_fixture_sources()
    monkeypatch.setattr(bridge, "_INSTRUCTION_AT", instruction)
    with pytest.raises(bridge.SI5SyntheticRankedOrderError, match="misordered"):
        bridge._entry_fact_witness(sources, settlement_date="2024-01-31", entry_open_at="2024-02-13T14:30:00Z")


def test_entry_evidence_after_instruction_is_refused_even_if_before_entry_open():
    sources = bridge._build_fixture_sources()
    target = next(row for row in sources.history.daily if row.session == "2024-02-12")
    late = replace(target, observed_at="2024-02-13T13:30:00Z")
    changed = replace(sources, history=replace(sources.history, daily=tuple(
        late if row is target else row for row in sources.history.daily
    )))
    with pytest.raises(bridge.SI5SyntheticRankedOrderError, match="misordered"):
        bridge._entry_fact_witness(changed, settlement_date="2024-01-31", entry_open_at="2024-02-13T14:30:00Z")


def test_owner_decisions_precede_build_and_are_bound_to_committed_bytes():
    root = Path(__file__).resolve().parents[1]
    committed = subprocess.run(
        ["git", "show", f"{DECISION_COMMIT}:{RECORD_PATH}"],
        cwd=root, check=True, capture_output=True,
    ).stdout
    assert sha256(committed).hexdigest() == DECISION_SHA256
    section = committed.decode().split("## 94.", 1)[1]
    assert "> why did you stop. i told you to build continuously" in section
    for decision in ("SI-DEC-20261006-09", "SI-DEC-20261006-10", "SI-DEC-20261006-11"):
        assert decision in section
    assert "three fabricated release cycles" in section
    assert "derive exit from the next authenticated synthetic release" in section
