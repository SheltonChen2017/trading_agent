"""Synthetic D2 software only; no source, outcome, calendar or trading proof."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from research.target_price_revisions_development.scoring import (
    FixtureScoringError, StockScore, StockResult, build_fixture_targets,
    project_fixture_etf, residualize_fixture_scores, score_fixture_stocks,
)
from research.target_price_revisions_development import scoring

CUTOFF = "2026-10-05T22:00:00Z"
CONTROLS = ("prior_total_return_5_sessions", "prior_total_return_20_sessions",
            "prior_total_return_60_sessions", "log_point_in_time_market_cap",
            "log_point_in_time_adv_20_sessions", "realized_volatility_20_sessions")
CONFIG = {"clip_absolute": "2", "industry_min_total": 3, "industry_min_active": 2,
          "sector_min_total": 3, "sector_min_active": 2, "min_price": "1", "min_adv": "100",
          "max_spread_fraction": "0.02", "max_capacity_fraction": "0.1"}


def universe(name="A", **changes):
    row = {"security_id": "SYNTHETIC-SEC-" + name, "instrument_type": "common_stock",
           "venue": "XNYS", "primary_listing": True, "basis_id": "SYNTHETIC-BASIS",
           "adr_ratio": None, "underlying_id": None, "industry_id": "SYNTHETIC-INDUSTRY",
           "sector_id": "SYNTHETIC-SECTOR", "available_at_utc": "2026-10-01T20:00:00Z",
           "effective_session_index": 99,
           "controls": {"values": dict.fromkeys(CONTROLS, "1"), "available_at_utc": "2026-10-01T20:00:00Z",
                        "effective_session_index": 99, "complete": True, "evidence_id": "SYNTHETIC-CONTROLS",
                        "price": "10", "adv": "1000", "spread_fraction": "0.01", "capacity_fraction": "0.01",
                        "rating_state": "SYNTHETIC-NO-ACCEPTED-RATING-EVENT", "catalyst_state": "SYNTHETIC-NO-COMMON-CATALYST",
                        "rating_inventory_complete": True, "catalyst_inventory_complete": True}}
    row.update(changes)
    return row


def event(name="A", delta="1", *, institution="1", lineage="1", session=100, catalyst="1"):
    new = str(Decimal("100") + Decimal(delta) * Decimal("10"))
    return {"lineage_id": "SYNTHETIC-LINEAGE-" + name + "-" + lineage,
            "version_id": "SYNTHETIC-VERSION-1", "security_id": "SYNTHETIC-SEC-" + name,
            "institution_id": "SYNTHETIC-INST-" + institution,
            "catalyst_id": None if catalyst is None else "SYNTHETIC-CATALYST-" + catalyst,
            "eligible_session_index": session, "available_at_utc": "2026-10-01T16:00:00Z",
            "payload": {"new_target": new, "prior_target": "100", "pre_event_price": "10",
                        "target_basis_id": "SYNTHETIC-BASIS", "price_basis_id": "SYNTHETIC-BASIS",
                        "price_available_at_utc": "2026-09-30T20:00:00Z",
                        "information_at_utc": "2026-10-01T15:00:00Z",
                        "price_session_index": session - 2, "information_session_index": session - 1}}


def stocks(*events, rows=None, decision=100, config=CONFIG, complete=True):
    if rows is None:
        rows = (universe("A"), universe("B"), universe("C"))
        for row in rows:
            row["controls"]["effective_session_index"] = decision - 1
    return score_fixture_stocks(rows, events,
                                cutoff_utc=CUTOFF, decision_session_index=decision,
                                config=config, inventory_complete=complete)


def triad(decision=100):
    return stocks(event("A", "-1"), event("B", "0"), event("C", "1"), decision=decision)


def lookup(result, name="A"):
    return next(row for row in result.rows if row.security_id == "SYNTHETIC-SEC-" + name)


def test_price_scaled_stock_strength_valid_zero_and_robust_scores():
    result = triad()
    assert [r.strength for r in result.rows] == ["-1", "0", "1"]
    assert lookup(result, "B").state == "VALID_ZERO"
    assert lookup(result, "B").normalized_score == "0"
    assert Decimal(lookup(result, "C").normalized_score) * Decimal("1.4826") == pytest.approx(Decimal("1"))
    assert all(flag is False for _, flag in result.authority)


@pytest.mark.parametrize("age,expected", [(0, "1"), (20, "0.5"), (40, "0.25"), (80, "0.0625"), (81, "0")])
def test_fixed_half_life_and_original_eligible_session_age(age, expected):
    result = triad(100 + age)
    assert lookup(result, "C").strength == expected
    assert next(v for v in result.versions if v.security_id == "SYNTHETIC-SEC-C").age_sessions == age
    if age == 81:
        assert all(v.contribution == "0" for v in result.versions)
        assert all(v.state in ("VALID_ZERO", "VALID_NONZERO") for v in result.versions)


def test_fixed_context_does_not_depend_on_caller_decimal_precision():
    with localcontext() as ctx:
        ctx.prec = 3
        low = triad()
    with localcontext() as ctx:
        ctx.prec = 60
        high = triad()
    assert low == high


def test_clipping_is_fixture_config_not_source_repair():
    result = stocks(event("A", "-3"), event("B", "0"), event("C", "3"))
    assert [r.strength for r in result.rows] == ["-2", "0", "2"]


def test_repeated_lineages_in_one_unit_do_not_create_institution_breadth():
    result = stocks(*(event("A", "1", lineage=str(i)) for i in range(10)), event("B", "0"), event("C", "-1"))
    a = lookup(result)
    assert a.strength == "1" and (a.n_inst, a.n_cat, a.n_ind) == ("1", "1", "1")


def test_common_catalyst_and_unknown_cluster_collapse_effective_breadth():
    for catalyst in ("1", None):
        result = stocks(*(event("A", "1", institution=str(i), lineage=str(i), catalyst=catalyst) for i in range(3)), event("B", "0"), event("C", "-1"))
        a = lookup(result)
        assert (a.n_inst, a.n_cat, a.n_ind) == ("3", "1", "1")


def test_multi_session_unit_sum_preserves_cancellation_and_zero_effective_counts():
    a = event("A", "2", session=80)
    b = event("A", "-1", lineage="2", session=100, catalyst="2")
    result = stocks(a, b, event("B", "1"), event("C", "-1"))
    row = lookup(result)
    assert row.strength == "0" and row.n_inst == "0" and row.n_ind == "0"


def test_missing_control_is_refused_before_group_population_and_never_imputed():
    row = universe("B")
    row["controls"]["values"].pop(CONTROLS[0])
    result = stocks(event("A", "-1"), event("B", "0"), event("C", "1"), rows=(universe("A"), row, universe("C")))
    assert lookup(result, "B").state == "REFUSED"
    assert lookup(result, "B").normalized_score is None
    assert "missing_control" in lookup(result, "B").reasons
    assert all(r.normalized_score is None for r in result.rows)


def test_industry_then_sector_fallback_and_no_market_or_epsilon_fallback():
    rows = (universe("A", industry_id="SYNTHETIC-I-A"), universe("B", industry_id="SYNTHETIC-I-B"), universe("C", industry_id="SYNTHETIC-I-C"))
    result = stocks(event("A", "-1"), event("B", "0"), event("C", "1"), rows=rows)
    assert all(r.group_id == "sector:SYNTHETIC-SECTOR" for r in result.rows)
    zero = stocks(event("A", "0"), event("B", "0"), event("C", "0"))
    assert all(r.normalized_score is None and "normalization_unavailable" in r.reasons for r in zero.rows)


@pytest.mark.parametrize("field,value", [("instrument_type", "reit"), ("venue", "XLON"), ("primary_listing", False), ("available_at_utc", "2026-10-06T00:00:00Z")])
def test_invalid_universe_metadata_is_visible_refusal(field, value):
    result = stocks(event(), event("B", "0"), event("C", "-1"), rows=(universe("A", **{field: value}), universe("B"), universe("C")))
    assert lookup(result).state == "REFUSED"


def test_bad_latest_version_never_falls_back_and_future_payload_is_not_read():
    good = event()
    bad = copy.deepcopy(good)
    bad.update(version_id="SYNTHETIC-VERSION-2", available_at_utc="2026-10-02T16:00:00Z")
    bad["payload"]["pre_event_price"] = "0"
    refused = stocks(good, bad, event("B", "0"), event("C", "-1"))
    assert lookup(refused).strength is None
    future = copy.deepcopy(bad)
    future.update(available_at_utc="2026-10-06T00:00:00Z", payload=object())
    assert lookup(stocks(good, future, event("B", "0"), event("C", "-1"))).strength == "1"


@pytest.mark.parametrize("value", [None, True, 1.0, "NaN", "Infinity", "0", "-1"])
def test_missing_or_invalid_pre_event_price_is_not_repaired(value):
    row = event()
    row["payload"]["pre_event_price"] = value
    assert lookup(stocks(row, event("B", "0"), event("C", "-1"))).strength is None


def design(*, singular=False, zero_mad=False):
    rows = []
    for index in range(64):
        values = [1 if index & (1 << bit) else -1 for bit in range(6)]
        if singular:
            values[1] = values[0]
        if zero_mad:
            values[0] = 1
        response = 2 * values[0] + 3 * values[1] + values[0] * values[1]
        values[5] += 2  # explicit nonnegative volatility fixture: 1 or 3
        rows.append(StockScore("SYNTHETIC-SEC-" + str(index), "VALID_NONZERO", (), str(response), str(response),
                               "industry:SYNTHETIC-I", tuple((name, str(value)) for name, value in zip(CONTROLS, values)),
                               "SYNTHETIC-RATING", "SYNTHETIC-CATALYST", "1", "1", "1"))
    return StockResult(tuple(rows), (), "2026-10-05T22:00:00+00:00", 100)


def test_exact_rational_ols_and_average_tie_fractional_ranks():
    result = residualize_fixture_scores(design())
    assert set(r.score for r in result.rows) == {"-1", "1"}
    assert set(r.percentile for r in result.rows) == {"1/4", "3/4"}
    assert result.columns == ("intercept", *CONTROLS)
    assert all(r.state == "VALID_NONZERO" for r in result.rows)


@pytest.mark.parametrize("case,reason", [("singular", "singular_control_design"), ("zero_mad", "zero_control_mad")])
def test_ols_singular_and_zero_mad_are_named_refusals(case, reason):
    result = residualize_fixture_scores(design(**{case: True}))
    assert all(r.score is None and reason in r.reasons for r in result.rows)


def ranks():
    return residualize_fixture_scores(design())


def book(weight="0.99", **changes):
    row = {"etf_id": "SYNTHETIC-ETF-A", "product_type": "unlevered_equity_etf",
           "complete": True, "available_at_utc": "2026-10-01T20:00:00Z", "captured_at_utc": "2026-10-01T20:01:00Z",
           "effective_session_index": 99, "cash_weight": "0", "residual_weight": "0",
           "cash_evidence_id": "SYNTHETIC-CASH", "residual_evidence_id": "SYNTHETIC-RESIDUAL",
           "holdings": ({"security_id": "SYNTHETIC-SEC-0", "weight": weight, "mapped": True,
                         "mapping_evidence_id": "SYNTHETIC-MAPPING"},
                        {"security_id": None, "weight": str(Decimal(1) - Decimal(weight)), "mapped": False,
                         "mapping_evidence_id": None})}
    row.update(changes)
    return row


def project(snapshot, result=None):
    return project_fixture_etf(snapshot, result or ranks(), cutoff_utc=CUTOFF,
                               decision_session_index=100, max_age_sessions=5)


def test_hard_mapping_gate_and_no_covered_weight_amplification():
    result = project(book())
    assert result.mapped_weight == "0.99" and result.observed_weight == "0.99"
    assert result.raw_score == "0.99"  # row zero's interaction residual is +1
    assert project(book("0.9899")).state == "REFUSED"
    assert "mapping_below_99_percent" in project(book("0.9899")).reasons


@pytest.mark.parametrize("change", [{"complete": False}, {"product_type": "leveraged_etf"},
                                     {"effective_session_index": 90}, {"available_at_utc": "2026-10-06T00:00:00Z"},
                                     {"cash_weight": "0.01"}])
def test_stale_incomplete_future_or_nonaccounting_etf_is_refused(change):
    assert project(book(**change)).state == "REFUSED"


def test_complete_zero_exit_target_map_and_caps_do_not_renormalize():
    candidates = ({"etf_id": "SYNTHETIC-ETF-A", "state": "VALID_NONZERO", "desired_weight": "0.8", "sector_id": "SYNTHETIC-SECTOR", "peer_id": "SYNTHETIC-PEER"},)
    prior = ({"etf_id": "SYNTHETIC-ETF-OLD", "weight": "1"},)
    result = build_fixture_targets(candidates, prior, cutoff_utc=CUTOFF, decision_session_index=100,
                                   max_names=2, name_cap="0.3", sector_cap="0.5", peer_cap="0.5", additions_cap="0.2")
    assert dict((r.etf_id, r.weight) for r in result.targets) == {"SYNTHETIC-ETF-A": "0.2", "SYNTHETIC-ETF-OLD": "0"}
    assert result.cash_weight == "0.8" and result.reduction_weight == "1"
    assert all(flag is False for _, flag in result.authority)


def test_caller_mutation_does_not_change_frozen_score_results():
    event_row = event()
    result = stocks(event_row, event("B", "0"), event("C", "-1"))
    event_row["payload"]["new_target"] = "999"
    assert lookup(result).strength == "1"
    with pytest.raises(FrozenInstanceError):
        lookup(result).strength = "999"


def test_incomplete_inventory_is_not_empty_valid_zero():
    with pytest.raises(FixtureScoringError, match="incomplete_fixture_inventory"):
        stocks(complete=False)


def test_full_score_output_round_trips_into_exact_residualizer():
    rows, events = [], []
    for index in range(64):
        values = [1 if index & (1 << bit) else -1 for bit in range(6)]
        response = 2 * values[0] + 3 * values[1] + values[0] * values[1]
        values[5] += 2
        row = universe(str(index))
        row["controls"]["values"] = dict((name, str(value)) for name, value in zip(CONTROLS, values))
        rows.append(row)
        events.append(event(str(index), str(response)))
    configured = dict(CONFIG, clip_absolute="10")
    scored = stocks(*events, rows=rows, config=configured)
    result = residualize_fixture_scores(scored)
    assert len(result.rows) == 64 and all(r.score is not None for r in result.rows)
    assert set(r.percentile for r in result.rows) == {"1/4", "3/4"}


def test_malformed_universe_with_events_returns_named_refusal():
    row = universe("A")
    row.pop("basis_id")
    result = stocks(event(), event("B", "0"), event("C", "-1"), rows=(row, universe("B"), universe("C")))
    assert lookup(result).state == "REFUSED"
    assert lookup(result).reasons == ("invalid_fixture_schema",)


def test_local_decimal_bound_check_is_not_caller_contextual():
    with localcontext() as ctx:
        ctx.prec = 3
        with pytest.raises(FixtureScoringError, match="invalid_fixture_decimal"):
            scoring._num("1000000000000000000000000.1")


def test_own_bounded_rational_text_can_round_trip_beyond_256_characters():
    value = Fraction(2 ** 1000, 3 ** 1000)
    encoded = scoring._ftext(value)
    assert len(encoded) > 256
    assert scoring._fraction(encoded) == value


@pytest.mark.parametrize("value", ["-0.1", "-1"])
def test_negative_volatility_control_is_not_admitted(value):
    row = universe("A")
    row["controls"]["values"][CONTROLS[-1]] = value
    assert lookup(stocks(event(), rows=(row, universe("B"), universe("C")))).strength is None


def test_missing_mapped_feature_is_refused_but_known_raw_diagnostic_is_preserved():
    snapshot = book()
    snapshot["holdings"] = (snapshot["holdings"][0], {"security_id": "SYNTHETIC-SEC-MISSING", "weight": "0.01", "mapped": True, "mapping_evidence_id": "SYNTHETIC-MAP"})
    result = project(snapshot)
    assert result.state == "REFUSED" and result.raw_score is None
    assert result.mapped_weight == "1" and result.observed_weight == "0.99"
    assert result.known_raw_score == "0.99"


def test_forged_custom_stock_state_cannot_execute_caller_equality():
    class CustomState:
        def __eq__(self, other):
            raise AssertionError("caller state equality executed")

    result = design()
    first = result.rows[0]
    object.__setattr__(first, "state", CustomState())
    with pytest.raises(FixtureScoringError, match="invalid_fixture_stock_row"):
        residualize_fixture_scores(result)


@pytest.mark.parametrize("value", ["-1.0000001", "-2"])
def test_total_return_control_cannot_be_below_negative_one(value):
    row = universe("A")
    row["controls"]["values"][CONTROLS[0]] = value
    result = stocks(event(), event("B", "0"), event("C", "-1"), rows=(row, universe("B"), universe("C")))
    assert lookup(result).reasons == ("invalid_fixture_control_value",)


def test_control_physical_endpoints_and_strict_cutoff():
    row = universe("A")
    row["controls"]["values"][CONTROLS[0]] = "-1"
    row["controls"]["values"][CONTROLS[-1]] = "0"
    assert lookup(stocks(event(), event("B", "0"), event("C", "-1"), rows=(row, universe("B"), universe("C")))).state == "VALID_NONZERO"
    row["controls"]["available_at_utc"] = CUTOFF
    assert lookup(stocks(event(), rows=(row, universe("B"), universe("C")))).reasons == ("unavailable_fixture_controls",)


def test_refused_feature_and_valid_zero_have_distinct_projection_coverage():
    zero = scoring.RankRow("SYNTHETIC-SEC-0", "VALID_ZERO", (), "0", "1/2", "0")
    zero_result = scoring.RankResult((zero,), (), (), "2026-10-05T22:00:00+00:00", 100)
    projection = project(book("1"), zero_result)
    assert (projection.state, projection.raw_score, projection.observed_weight, projection.active_weight) == ("VALID_ZERO", "0", "1", "0")
    refused = scoring.RankRow("SYNTHETIC-SEC-0", "REFUSED", ("missing_control",), None, None, None)
    refused_result = scoring.RankResult((refused,), (), (), "2026-10-05T22:00:00+00:00", 100)
    projection = project(book("1"), refused_result)
    assert projection.state == "REFUSED" and projection.raw_score is None
    assert projection.observed_weight == "0" and projection.active_weight == "0"
    assert projection.missing_security_ids == ("SYNTHETIC-SEC-0",)


def test_incompatible_price_basis_is_refused_not_repaired():
    row = event()
    row["payload"]["price_basis_id"] = "SYNTHETIC-OTHER-BASIS"
    assert lookup(stocks(row)).reasons == ("incompatible_fixture_price_basis",)


def test_unit_uses_median_distinct_lineages_not_sum():
    result = stocks(event(delta="-1", lineage="1"), event(delta="1", lineage="2"), event(delta="2", lineage="3"), event("B", "0"), event("C", "-1"))
    assert lookup(result).strength == "1"


def test_visible_lineage_collision_is_named_refusal():
    original = event()
    conflicting = copy.deepcopy(original)
    conflicting["payload"]["new_target"] = "120"
    assert lookup(stocks(original, conflicting)).reasons == ("fixture_lineage_collision",)


def test_normalization_and_allocator_use_no_runtime_io(monkeypatch):
    import builtins
    import os
    from pathlib import Path
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("fixture runtime I/O attempted")

    # Modules are already imported: this is a Python-call regression, not an OS sandbox.
    with monkeypatch.context() as scoped:
        for owner, name in ((builtins, "open"), (os, "open"), (Path, "open"), (Path, "read_bytes"), (Path, "read_text"), (socket, "socket")):
            scoped.setattr(owner, name, forbidden)
        result = triad()
        assert lookup(result).state == "VALID_NONZERO"
        target = build_fixture_targets((), (), cutoff_utc=CUTOFF, decision_session_index=100,
                                       max_names=1, name_cap="0.2", sector_cap="0.2", peer_cap="0.2", additions_cap="0.2")
        assert target.cash_weight == "1" and len(scoring.fixture_target_sha256(target)) == 64


def test_complete_universe_resource_bound_matches_residualizer():
    rows = tuple(universe(str(index)) for index in range(1024))
    bounded = stocks(rows=rows)
    assert len(bounded.rows) == 1024
    assert len(residualize_fixture_scores(bounded).rows) == 1024
    with pytest.raises(FixtureScoringError, match="invalid_fixture_collection"):
        stocks(rows=(*rows, universe("1024")))


def test_surrogate_group_category_is_named_refusal_before_utf8_sort():
    result = design()
    object.__setattr__(result.rows[0], "group_id", "\ud800")
    with pytest.raises(FixtureScoringError, match="invalid_fixture_category"):
        residualize_fixture_scores(result)
