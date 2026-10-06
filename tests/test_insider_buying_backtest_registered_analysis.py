"""Invented pure-byte registered stock study; no real outcomes or QC runs."""
from __future__ import annotations

import copy
import hashlib
import json
import random
import gc
import weakref
from datetime import date, timedelta
from decimal import Decimal, localcontext
from dataclasses import replace
from pathlib import Path

import pytest

from research.insider_buying import backtest_registered_analysis as mod


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def business_days(count: int = 460) -> list[str]:
    result, day = [], date(2020, 1, 2)
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day.isoformat())
        day += timedelta(days=1)
    return result


def utc(day: str, time: str = "14:30:00") -> str:
    return day + "T" + time + "Z"


def price(dates: list[str], entry: int, horizon: int, exit_price: str) -> dict:
    return {"entry_session": dates[entry], "exit_session": dates[entry + horizon],
            "entry_price": "100", "exit_price": exit_price,
            "split_multiplier": "1", "cash_per_initial_share": "0"}


def instrument(dates: list[str], entry: int, sid: str, issuer: str, *, cap: str = "100",
               exits: tuple[str, str, str] = ("105", "110", "130")) -> dict:
    rng = random.Random(19)
    xs, ys = [], []
    for _ in range(252):
        row = [Decimal(rng.randrange(-50, 51)) / 10_000 for _ in mod.FACTORS]
        xs.append([format(x, "f") for x in row])
        y = Decimal("0.0001") + sum((x * Decimal(i + 1) / 10 for i, x in enumerate(row)), Decimal(0))
        ys.append(format(y, "f"))
    return {"security_id": sid, "issuer_id": issuer, "industry": "industrial",
            "features": {"market_cap": cap, "momentum_12_1": "0.1", "book_to_market": "0.3",
                         "adv": "1000000", "spread_bps": "5"},
            "features_available_at_utc": utc(dates[entry - 1], "21:00:00"),
            "factor_training": {"sessions": dates[entry - 252:entry], "stock_excess_returns": ys,
                                "factor_returns": xs, "available_at_utc": utc(dates[entry - 1], "21:00:00"),
                                "return_clock": "regular-open-to-regular-open-end-session-labelled"},
            "future_factors": [{"session": dates[entry + k], "interval_end_session": dates[entry + k + 1],
                               "riskfree": "0", "returns": ["0"] * 6}
                               for k in range(60)],
            "horizons": {str(h): price(dates, entry, h, x) for h, x in zip(mod.HORIZONS, exits)}}


def fixture() -> dict[str, dict]:
    dates, entry = business_days(), 270
    sessions = [{"session": day, "open_utc": utc(day), "close_utc": utc(day, "21:00:00")} for day in dates]
    registration = {"schema": "insider-stock-analysis-registration-v1", "trust_scope": "fixture",
                    "registered_look_id": "synthetic-stock-look", "candidate_id": "synthetic-stock-candidate",
                    "policy": mod.frozen_analysis_policy(), "registered_at_utc": "2019-12-01T00:00:00Z",
                    "first_outcome_access_utc": "2022-01-01T00:00:00Z", "implementation_sha256": "a" * 64,
                    "analysis_plan": mod.analysis_plan_descriptors(implementation_sha256="a" * 64),
                    "source_manifest_sha256": "b" * 64, "security_master_sha256": "c" * 64,
                    "calendar_sha256": sha(mod.canonical_bytes(sessions)), "outcome_vintage_sha256": "d" * 64,
                    "rights_sha256": "e" * 64, "prior_variance_calibration_sha256": "f" * 64}
    register_sha = sha(mod.canonical_bytes(registration))
    event = {"signal_id": "event-1", "issuer_id": "issuer-1", "security_id": "stock-1",
             "available_at_utc": utc(dates[entry - 1], "21:00:00"), "entry_session": dates[entry],
             "exit_session": dates[entry + 20], "source_event_sha256": "1" * 64,
             "buyer_ids": ["buyer-1"], "score": "1.25", "earnings_distance_sessions": 10, "regime": "bull"}
    manifest = {"schema": "insider-stock-event-study-manifest-v1", "trust_scope": "fixture",
                "registration_sha256": register_sha, "source_manifest_sha256": "b" * 64,
                "security_master_sha256": "c" * 64, "calendar_sha256": registration["calendar_sha256"],
                "outcome_vintage_sha256": "d" * 64, "sessions": sessions,
                "eligible_control_security_ids": ["control-1", "control-2", "control-3", "control-4", "control-5"],
                "events": [event]}
    manifest_sha = sha(mod.canonical_bytes(manifest))
    terminal = {"schema": "insider-stock-event-study-terminal-v1", "trust_scope": "fixture",
                "registration_sha256": register_sha, "manifest_sha256": manifest_sha,
                "candidate_id": registration["candidate_id"], "registered_look_id": registration["registered_look_id"],
                "outcome_vintage_sha256": "d" * 64, "status": "Completed", "errors": [], "final_positions": [],
                "fills": [{"signal_id": "event-1", "side": side, "security_id": "stock-1", "session": dates[index],
                           "filled_at_utc": utc(dates[index]), "quantity": quantity, "price": value,
                           "order_id": order} for side, index, quantity, value, order in
                          (("entry", entry, 10, "100", "order-1"), ("exit", entry + 20, -10, "110", "order-2"))]}
    panel = {"schema": "insider-stock-event-study-panel-v1", "trust_scope": "fixture",
             "registration_sha256": register_sha, "manifest_sha256": manifest_sha,
             "outcome_vintage_sha256": "d" * 64, "matched_control_coverage_sha256": "2" * 64,
             "events": [{"signal_id": "event-1", "stock": instrument(dates, entry, "stock-1", "issuer-1"),
                         "market": {str(h): price(dates, entry, h, "102") for h in mod.HORIZONS},
                         "sector": {str(h): price(dates, entry, h, "103") for h in mod.HORIZONS}}],
             "control_pools": {dates[entry]: [instrument(dates, entry, "control-" + str(i), "control-issuer-" + str(i),
                                                       cap=str(85 + 5 * i), exits=("101", "102", "103")) for i in range(1, 6)]}}
    return {"registration": registration, "manifest": manifest, "terminal": terminal, "panel": panel}


def encoded(values: dict, *, scope: str = "fixture", rebind: bool = True) -> tuple[dict, mod.RegisteredAnalysisTrustRoots]:
    values = copy.deepcopy(values)
    if rebind:
        registration_sha = sha(mod.canonical_bytes(values["registration"]))
        for role in ("manifest", "terminal", "panel"):
            values[role]["registration_sha256"] = registration_sha
        manifest_sha = sha(mod.canonical_bytes(values["manifest"]))
        for role in ("terminal", "panel"):
            values[role]["manifest_sha256"] = manifest_sha
    raw = {role: mod.canonical_bytes(values[role]) for role in mod.ROLES}
    roots = mod.RegisteredAnalysisTrustRoots(scope, tuple((role, sha(raw[role])) for role in mod.ROLES))
    return raw, roots


def evaluate(values: dict, *, scope: str = "fixture", rebind: bool = True) -> dict:
    raw, roots = encoded(values, scope=scope, rebind=rebind)
    return mod.analyze_registered_stock_study(registration_raw=raw["registration"], manifest_raw=raw["manifest"],
                                             terminal_raw=raw["terminal"], panel_raw=raw["panel"], trust_roots=roots,
                                             expected_implementation_sha256="a" * 64)


def test_complete_invented_order_calculation_is_not_market_evidence():
    result = evaluate(fixture())
    assert result["counts"] == {"events": 1, "issuers": 1, "entry_dates": 1, "unique_buyers": 1,
                                "confirmation_events": 1, "submitted_orders": 2, "missing_rows": 0}
    assert result["order_path_verified"] is True
    assert result["control_event_incidence_is_retrospective_source_census"] is False
    assert result["control_selection_is_tradeable_PIT"] is False
    assert result["control_matching_features_are_pre_entry"] is True
    assert result["control_selection_design_is_pre_entry_causal"] is True
    assert result["control_source_event_exclusion_window_sessions"] == [0, 0]
    assert result["software_statistical_disposition"] == "FIXTURE_INSUFFICIENT"
    assert result["primary_inference"] is None
    assert result["matched_control_ids"] == {"event-1": ["control-3", "control-2", "control-4"]}
    costs = result["horizon_cost_diagnostics"]
    assert costs["20"]["0"]["raw"]["mean"] == "0.1"
    assert costs["20"]["10"]["matched_factor_adjusted"]["mean"] == "0.0779"
    assert costs["20"]["20"]["market_adjusted"]["mean"] == "0.0758"
    assert costs["5"]["0"]["sector_adjusted"]["mean"] == "0.02"
    assert costs["60"]["0"]["matched_factor_adjusted"]["mean"] == "0.27"
    for field in ("ib5_pass", "backtesting_ready", "actual_outcome_access_performed", "qc_authority", "rights_authority", "broker_authority"):
        assert result[field] is False
    assert result["alpha_spent"] == [0, 1]
    assert result["registered_looks_consumed"] == result["qc_jobs_launched"] == 0
    assert result["unimplemented_required_diagnostics"] == []
    assert result["implemented_separate_diagnostics_not_integrated_here"]
    assert result["negative_control_schedules"]["source_event_count"] == 1
    assert result["negative_control_schedules"]["schedules"] == []
    assert len(result["negative_control_schedules"]["unavailable_groups"]) == 2
    assert result["order_notional_diagnostics"]["cost_fee_usd"]["10"] == "2.1"
    assert result["cross_section_diagnostics"]["mean_ic"] is None
    raw_report = dict(result)
    raw_report.pop("report_sha256")
    assert result["report_sha256"] == sha(mod.canonical_bytes(raw_report))


def test_result_is_deterministic_detached_and_input_untouched():
    value = fixture()
    before = copy.deepcopy(value)
    first, second = evaluate(value), evaluate(value)
    assert first == second and value == before
    first["counts"]["events"] = 999
    assert evaluate(value)["counts"]["events"] == 1


def test_default_policy_nontransfer_null_closure_and_preoutcome_count():
    policy = mod.frozen_analysis_policy()
    assert policy["stock_alpha"] == policy["etf_alpha_reserve"] == [1, 160]
    assert policy["valid_stock_null_closes_family"] is True
    assert policy["etf_reserve_transferable"] is policy["etf_can_rescue_stock_null"] is policy["qc_can_rescue_stock_null"] is False
    expected = ((Decimal(str(mod.NormalDist().inv_cdf(1 - 1 / 320)))
                 + Decimal(str(mod.NormalDist().inv_cdf(.8)))) ** 2 * Decimal(".0025") / Decimal(".01") ** 2)
    assert mod.required_independent_count() == int(expected.to_integral_value(rounding="ROUND_CEILING"))
    assert mod.required_independent_count() > 300
    policy["primary_horizon_sessions"] = 5
    assert mod.frozen_analysis_policy()["primary_horizon_sessions"] == 20


def test_preoutcome_seasoned_stock_candidate_registry_does_not_replace_actual_training():
    policy = mod.frozen_analysis_policy()
    assert policy["minimum_prior_regular_listing_sessions"] == 253
    assert policy["factor_model"] == "252-pre-entry-open-to-open-intervals-ols-intercept-six-factors-with-riskfree"
    plan = mod.analysis_plan_descriptors(implementation_sha256="a" * 64)
    assert "253 prior listed sessions" in plan["primary_statistic"]["definition"]
    assert "252 actual prior open intervals mandatory" in plan["primary_statistic"]["definition"]
    assert "253 prior listed sessions" in plan["controls"]["definition"]
    assert all(len(item["definition"]) <= 200 for item in plan.values())
    result = evaluate(fixture())
    assert result["software_statistical_disposition"] == "FIXTURE_INSUFFICIENT"
    assert result["backtesting_ready"] is result["ib5_pass"] is False
    value = fixture()
    value["panel"]["events"][0]["stock"]["factor_training"]["sessions"].pop()
    with pytest.raises(mod.RegisteredAnalysisError, match="252"):
        evaluate(value)


@pytest.mark.parametrize("lower_bound", [None, 60, 252, 254, True])
def test_seasoning_policy_drift_refuses_after_external_reanchoring(lower_bound):
    value = fixture()
    if lower_bound is None:
        value["registration"]["policy"].pop("minimum_prior_regular_listing_sessions")
    else:
        value["registration"]["policy"]["minimum_prior_regular_listing_sessions"] = lower_bound
    with pytest.raises(mod.RegisteredAnalysisError, match="policy drift"):
        evaluate(value)


def test_student_reference_known_values():
    assert mod._student_two_sided_p(1, 1) == pytest.approx(.5, abs=1e-12)
    assert mod._student_two_sided_p(0, 4) == 1
    assert mod._student_two_sided_p(2 ** .5, 2) == pytest.approx(1 - 2 ** -.5, abs=1e-12)
    for df in (1, 2, 5, 30, 300):
        critical = mod._student_critical(df)
        assert mod._student_two_sided_p(float(critical), df) == pytest.approx(1 / 160, abs=1e-12)
    assert mod._student_critical(1) > mod._student_critical(300)


def test_two_way_cluster_variance_known_four_cell_example():
    rows = (("a", "2021-01-04", Decimal(".1")), ("a", "2021-01-05", Decimal(".2")),
            ("b", "2021-01-04", Decimal(".3")), ("b", "2021-01-05", Decimal(".4")))
    result = mod.clustered_inference(rows)
    assert Decimal(result["mean"]) == Decimal(".25")
    assert abs(Decimal(result["variance"]) - Decimal(1) / 120) < Decimal("1e-28")
    assert result["reference_degrees_of_freedom"] == 1
    assert result["planning_sufficient"] is False
    assert result["inferentially_available"] is True
    assert result["overlapping_cross_date_dependence_fully_resolved"] is False


def test_negative_two_way_variance_unavailable_not_floored():
    rows = (("a", "2021-01-04", Decimal("1")), ("a", "2021-01-05", Decimal("-1")),
            ("b", "2021-01-04", Decimal("-1")), ("b", "2021-01-05", Decimal("1")))
    result = mod.clustered_inference(rows)
    assert result["variance"] is None and result["confidence_interval"] is None
    assert result["unavailable_reason"] == "nonpositive-two-way-inclusion-exclusion-variance"


def test_zero_variance_unavailable_not_infinite_significance():
    rows = tuple((str(i), "2021-01-" + f"{i+1:02d}", Decimal(".1")) for i in range(10))
    result = mod.clustered_inference(rows)
    assert result["inferentially_available"] is False


def test_power_sufficiency_counts_issuers_and_dates_not_rows():
    required = mod.required_independent_count()
    dates = business_days(required + 10)
    rows = tuple(("issuer-" + str(i), dates[i], Decimal(".05") + Decimal(i % 5) / 10000) for i in range(required))
    result = mod.clustered_inference(rows)
    assert result["planning_sufficient"] is True and result["inferentially_available"] is True
    one_day = tuple((row[0], dates[0], row[2]) for row in rows)
    result = mod.clustered_inference(one_day)
    assert result["observation_count"] == required and result["planning_sufficient"] is False
    one_issuer = tuple(("same-issuer", row[1], row[2]) for row in rows)
    assert mod.clustered_inference(one_issuer)["planning_sufficient"] is False


@pytest.mark.parametrize("mean, expected", [(".05", "FIXTURE_POSITIVE"), ("-.01", "FIXTURE_VALID_NULL"), ("0", "FIXTURE_VALID_NULL")])
def test_actual_primary_positive_and_null_calculations_never_spend_alpha(mean, expected):
    required = mod.required_independent_count()
    dates = business_days(required + 10)
    rows = tuple(("issuer-" + str(i), dates[i], Decimal(mean) + Decimal((i % 5) - 2) / 10000)
                 for i in range(required))
    result = mod.fixture_primary_disposition(rows)
    assert result["software_statistical_disposition"] == expected
    assert result["software_valid_stock_null_closes_family"] is (expected == "FIXTURE_VALID_NULL")
    assert result["ib5_pass"] is result["data_validity_established_here"] is result["etf_reserve_transferable"] is False
    assert result["etf_can_rescue_stock_null"] is result["qc_can_rescue_stock_null"] is False
    assert result["alpha_spent"] == [0, 1] and result["etf_alpha_reserve"] == [1, 160]


def test_factor_ols_exact_coefficients_and_intercept():
    dates, entry = business_days(), 270
    training = instrument(dates, entry, "s", "i")["factor_training"]
    result = mod._ols(training, before=mod._utc(utc(dates[entry])))
    assert abs(result[0] - Decimal(".0001")) < Decimal("1e-24")
    for i, coefficient in enumerate(result[1:]):
        assert abs(coefficient - Decimal(i + 1) / 10) < Decimal("1e-24")


def test_split_dividend_return_arithmetic():
    value = price(business_days(), 270, 5, "55")
    value["split_multiplier"], value["cash_per_initial_share"] = "2", "3"
    assert mod._price_return(value) == Decimal(".13")


def test_block_bootstrap_deterministic_and_keeps_sparse_calendar():
    dates = tuple(business_days())
    rows = [(dates[270 + i * 10], Decimal(i % 3) / 100 - Decimal(".01")) for i in range(14)]
    first, second = mod._block_bootstrap(rows, dates), mod._block_bootstrap(rows, dates)
    assert first == second and first["available"] is True
    assert first["draws"] == 999 and first["block_sessions"] == 60
    assert first["confirmatory"] is first["issuer_dependence_resampled"] is first["cross_date_overlap_fully_resolved"] is False
    assert mod._block_bootstrap(rows[:2], dates)["available"] is False


@pytest.mark.parametrize("role", mod.ROLES)
def test_external_anchor_mismatch_refuses(role):
    values = fixture()
    raw, roots = encoded(values)
    raw[role] += b" "
    with pytest.raises(mod.RegisteredAnalysisError, match="hash mismatch"):
        mod.analyze_registered_stock_study(registration_raw=raw["registration"], manifest_raw=raw["manifest"],
                                           terminal_raw=raw["terminal"], panel_raw=raw["panel"], trust_roots=roots,
                                           expected_implementation_sha256="a" * 64)


def test_production_refuses_before_outcome_decode(monkeypatch):
    values = fixture()
    values["registration"]["trust_scope"] = "production"
    raw, roots = encoded(values, scope="production")
    original, seen = mod._decode, []
    def spy(data, digest):
        seen.append(digest)
        return original(data, digest)
    monkeypatch.setattr(mod, "_decode", spy)
    with pytest.raises(mod.RegisteredAnalysisError, match="zero-look"):
        mod.analyze_registered_stock_study(registration_raw=raw["registration"], manifest_raw=b"not read",
                                           terminal_raw=b"not read", panel_raw=b"not read", trust_roots=roots,
                                           expected_implementation_sha256="a" * 64)
    assert seen == [roots.hashes()["registration"]]


def modify(values, key):
    event, stock = values["manifest"]["events"][0], values["panel"]["events"][0]["stock"]
    if key == "after-open": event["available_at_utc"] = event["entry_session"] + "T14:30:01Z"
    elif key == "at-open": event["available_at_utc"] = event["entry_session"] + "T14:30:00Z"
    elif key == "delayed-open": event["available_at_utc"] = values["manifest"]["sessions"][260]["close_utc"]
    elif key == "quantity": values["terminal"]["fills"][1]["quantity"] = -9
    elif key == "price": values["terminal"]["fills"][1]["price"] = "109"
    elif key == "late-fill": values["terminal"]["fills"][1]["filled_at_utc"] = event["exit_session"] + "T14:31:00Z"
    elif key == "same-order": values["terminal"]["fills"][1]["order_id"] = "order-1"
    elif key == "partial": values["terminal"]["fills"].pop()
    elif key == "positions": values["terminal"]["final_positions"] = ["stock-1"]
    elif key == "error": values["terminal"]["errors"] = ["runtime issue"]
    elif key == "future-feature": stock["features_available_at_utc"] = event["entry_session"] + "T15:00:00Z"
    elif key == "future-training": stock["factor_training"]["available_at_utc"] = event["entry_session"] + "T15:00:00Z"
    elif key == "factor-clock": stock["factor_training"]["return_clock"] = "regular-close-to-close"
    elif key == "factor-interval-end": stock["future_factors"][0]["interval_end_session"] = event["entry_session"]
    elif key == "none-training": stock["factor_training"] = None
    elif key == "wrong-training": stock["factor_training"]["sessions"][0] = "2010-01-04"
    elif key == "singular": stock["factor_training"]["factor_returns"] = [["0"] * 6 for _ in range(252)]
    elif key == "short-training": stock["factor_training"]["stock_excess_returns"].pop()
    elif key == "short-future-factor": stock["future_factors"].pop()
    elif key == "wrong-future-factor": stock["future_factors"][0]["session"] = event["exit_session"]
    elif key == "unknown-factor": stock["future_factors"][0]["returns"].append("0")
    elif key == "wrong-horizon": stock["horizons"]["20"]["exit_session"] = event["entry_session"]
    elif key == "short-control": next(iter(values["panel"]["control_pools"].values())).pop()
    elif key == "control-subject": next(iter(values["panel"]["control_pools"].values()))[0]["security_id"] = "foreign"
    elif key == "duplicate-control":
        for item in next(iter(values["panel"]["control_pools"].values())): item["issuer_id"] = "same-control-issuer"
    elif key == "other-industry": stock["industry"] = "unknown"
    elif key == "zero-mad": stock["features"]["adv"] = "9000000"
    elif key == "policy-alpha": values["registration"]["policy"]["stock_alpha"] = [1, 80]
    elif key == "policy-mde": values["registration"]["policy"]["minimum_detectable_effect"] = "0.1"
    elif key == "policy-bool": values["registration"]["policy"]["valid_stock_null_closes_family"] = 1
    elif key == "post-outcome-register": values["registration"]["registered_at_utc"] = "2023-01-01T00:00:00Z"
    elif key == "look-drift": values["terminal"]["registered_look_id"] = "foreign"
    elif key == "epoch-drift": values["panel"]["outcome_vintage_sha256"] = "9" * 64
    elif key == "subject-drift": stock["security_id"] = "foreign"
    elif key == "split-order": stock["horizons"]["20"]["split_multiplier"] = "2"
    elif key == "cash-order": stock["horizons"]["20"]["cash_per_initial_share"] = "1"
    elif key == "unknown-fields": stock["authority"] = True
    elif key == "duplicate-buyer": event["buyer_ids"] = ["same", "same"]
    elif key == "zero-cap": stock["features"]["market_cap"] = "0"
    elif key == "zero-price": stock["horizons"]["5"]["entry_price"] = "0"
    elif key == "negative-cash": stock["horizons"]["5"]["cash_per_initial_share"] = "-1"
    elif key == "bool-quantity": values["terminal"]["fills"][0]["quantity"] = True
    elif key == "bool-distance": event["earnings_distance_sessions"] = True
    elif key == "invalid-score": event["score"] = "NaN"
    elif key == "bad-regime": event["regime"] = "optimized"
    else: raise AssertionError(key)


@pytest.mark.parametrize("key", ["after-open", "at-open", "delayed-open", "quantity", "price", "late-fill", "same-order", "partial",
                                 "positions", "error", "future-feature", "future-training", "factor-clock", "factor-interval-end", "none-training", "wrong-training", "singular", "short-training",
                                 "short-future-factor", "wrong-future-factor", "unknown-factor", "wrong-horizon", "short-control", "control-subject",
                                 "duplicate-control", "other-industry", "zero-mad", "policy-alpha", "policy-mde", "policy-bool", "post-outcome-register",
                                 "look-drift", "epoch-drift", "subject-drift", "split-order", "cash-order", "unknown-fields", "duplicate-buyer", "zero-cap",
                                 "zero-price", "negative-cash", "bool-quantity", "bool-distance", "invalid-score", "bad-regime"])
def test_danger_direction_refuses_with_complete_rehashed_fixture(key):
    values = fixture()
    modify(values, key)
    with pytest.raises(mod.RegisteredAnalysisError):
        evaluate(values)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e2", " 1", "1 ", "01", ".5", "+1", 1, True, 1.0, None])
def test_noncanonical_money_and_return_text_refuses(value):
    with pytest.raises(mod.RegisteredAnalysisError): mod._decimal(value)


def test_decimal_domain_limit_is_not_rounded_by_ambient_context():
    with localcontext() as ctx:
        ctx.prec = 5
        with pytest.raises(mod.RegisteredAnalysisError):
            mod._decimal("1000000000000000000000000000000.1")


def test_public_study_calculation_is_ambient_decimal_context_independent():
    value = fixture()
    baseline = evaluate(value)
    with localcontext() as ctx:
        ctx.prec = 5
        assert evaluate(value) == baseline


def dynamic_fixture():
    value = fixture()
    manifest, panel = value["manifest"], value["panel"]
    manifest["schema"] = "insider-stock-event-study-manifest-v2"
    day = manifest["events"][0]["entry_session"]
    manifest["eligible_control_security_ids_by_entry_session"] = {day: manifest["eligible_control_security_ids"][:]}
    panel["schema"] = "insider-stock-event-study-panel-v2"
    full = panel["control_pools"][day]
    # These are selected independently using the complete feature population;
    # no future returns participated in determining these three identities.
    panel["selected_control_outcomes"] = {day: [copy.deepcopy(full[i]) for i in (2, 1, 3)]}
    panel["control_pools"][day] = [{key: item[key] for key in ("security_id", "issuer_id", "industry", "features", "features_available_at_utc")}
                                  for item in full]
    return value


def test_dynamic_feature_only_control_pool_matches_fixed_candidate_without_unused_outcomes():
    result = evaluate(dynamic_fixture())
    previous = evaluate(fixture())
    assert result["control_inventory_profile"] == "dynamic-per-entry-v2"
    assert result["matched_control_ids"] == previous["matched_control_ids"]
    assert result["horizon_cost_diagnostics"] == previous["horizon_cost_diagnostics"]


def test_dual_class_universe_chooses_nearest_distinct_issuer_not_three_sids():
    event = {"issuer_id": "event", "industry": "same", "features": {key: Decimal(100) for key in mod.FEATURES}}
    pool = []
    for sid, issuer, size in (("class-A", "issuer-A", 99), ("class-B", "issuer-A", 100),
                              ("class-C", "issuer-C", 101), ("class-D", "issuer-D", 102)):
        features = {key: Decimal(100) for key in mod.FEATURES}; features["market_cap"] = Decimal(size)
        pool.append({"security_id": sid, "issuer_id": issuer, "industry": "same", "features": features})
    result = mod._matched(event, pool)
    assert [row["security_id"] for row in result] == ["class-B", "class-C", "class-D"]
    assert len({row["issuer_id"] for row in result}) == 3
    pool[-1]["issuer_id"] = "issuer-C"
    with pytest.raises(mod.RegisteredAnalysisError, match="control issuers"): mod._matched(event, pool)


@pytest.mark.parametrize("edit", ["missing-date", "foreign-date", "union-drift", "pool-union-not-date", "missing-selected", "foreign-selected", "changed-features", "future-feature", "unused-outcomes"])
def test_dynamic_control_inventory_and_selected_outcomes_refuse_future_or_selection_drift(edit):
    value = dynamic_fixture()
    day = value["manifest"]["events"][0]["entry_session"]
    if edit == "missing-date": value["manifest"]["eligible_control_security_ids_by_entry_session"] = {}
    elif edit == "foreign-date": value["manifest"]["eligible_control_security_ids_by_entry_session"]["2021-01-01"] = ["control-1", "control-2", "control-3"]
    elif edit == "union-drift": value["manifest"]["eligible_control_security_ids"].append("future-control")
    elif edit == "pool-union-not-date": value["manifest"]["eligible_control_security_ids_by_entry_session"][day] = ["control-1", "control-2", "control-3"]; value["manifest"]["eligible_control_security_ids"] = ["control-1", "control-2", "control-3"]
    elif edit == "missing-selected": value["panel"]["selected_control_outcomes"][day].pop()
    elif edit == "foreign-selected": value["panel"]["selected_control_outcomes"][day][0]["security_id"] = "foreign"
    elif edit == "changed-features": value["panel"]["selected_control_outcomes"][day][0]["features"]["market_cap"] = "1000"
    elif edit == "future-feature": value["panel"]["control_pools"][day][0]["features_available_at_utc"] = day + "T15:00:00Z"
    elif edit == "unused-outcomes":
        dates, entry = business_days(), 270
        value["panel"]["selected_control_outcomes"][day].append(instrument(dates, entry, "control-1", "control-issuer-1", cap="90", exits=("101", "102", "103")))
    with pytest.raises(mod.RegisteredAnalysisError): evaluate(value)


def test_large_6000_stock_feature_universe_has_no_6000_outcome_requirement():
    value = dynamic_fixture()
    day = value["manifest"]["events"][0]["entry_session"]
    pool = value["panel"]["control_pools"][day]
    prototype = copy.deepcopy(pool[0])
    for i in range(5995):
        row = copy.deepcopy(prototype)
        row["security_id"], row["issuer_id"] = "extra-control-" + str(i), "extra-issuer-" + str(i)
        row["features"]["market_cap"] = str(1_000_000 + i)
        row["industry"] = "other-industry"
        pool.append(row)
    identities = sorted(row["security_id"] for row in pool)
    value["manifest"]["eligible_control_security_ids"] = identities
    value["manifest"]["eligible_control_security_ids_by_entry_session"][day] = identities
    # Robust-scaling now has different MAD; the three nearest industry-exact
    # controls remain the same because only their size differs in that group.
    result = evaluate(value)
    assert len(pool) == 6000 and len(value["panel"]["selected_control_outcomes"][day]) == 3
    assert result["counts"]["events"] == 1 and result["control_inventory_profile"] == "dynamic-per-entry-v2"


def test_unknown_registration_field_and_stale_bindings_refuse():
    value = fixture()
    value["registration"]["outcome_access_authorized"] = True
    with pytest.raises(mod.RegisteredAnalysisError, match="fields"):
        evaluate(value)
    value = fixture()
    value["manifest"]["registration_sha256"] = "0" * 64
    with pytest.raises(mod.RegisteredAnalysisError, match="epoch"):
        evaluate(value, rebind=False)


def test_duplicate_signal_and_issuer_day_refuse_before_row_drop():
    for same_signal in (True, False):
        value = fixture()
        event = copy.deepcopy(value["manifest"]["events"][0])
        if not same_signal: event["signal_id"] = "new-signal"
        value["manifest"]["events"].append(event)
        with pytest.raises(mod.RegisteredAnalysisError, match="duplicate"):
            evaluate(value)


def test_empty_completed_is_not_statistical_success():
    value = fixture()
    value["manifest"]["events"] = []
    value["terminal"]["fills"] = []
    value["panel"]["events"] = []
    with pytest.raises(mod.RegisteredAnalysisError, match="population empty"):
        evaluate(value)


def test_duplicate_json_keys_and_noncanonical_encoding_refuse():
    raw = b'{"a":1,"a":2}'
    with pytest.raises(mod.RegisteredAnalysisError): mod._decode(raw, sha(raw))
    raw = b'{"a": 1}'
    with pytest.raises(mod.RegisteredAnalysisError): mod._decode(raw, sha(raw))


def test_invalid_trust_roots_refuse():
    with pytest.raises(mod.RegisteredAnalysisError): mod.RegisteredAnalysisTrustRoots("fixture", (("manifest", "1" * 64),)).hashes()
    with pytest.raises(mod.RegisteredAnalysisError): mod.RegisteredAnalysisTrustRoots("anything", tuple((x, "1" * 64) for x in mod.ROLES)).hashes()


def test_exact_executable_analysis_registry_not_arbitrary_method_strings():
    value = fixture()
    plan = mod.analysis_plan_descriptors(implementation_sha256="a" * 64)
    assert set(plan) == {"primary_statistic", "inference", "controls", "split", "error_policy"}
    for item in plan.values():
        assert item["implementation_sha256"] == "a" * 64
        assert len(item["definition"]) <= 200
    value["registration"]["analysis_plan"]["inference"]["method_id"] = "invented-acceptable-method"
    with pytest.raises(mod.RegisteredAnalysisError, match="exact registry"):
        evaluate(value)
    value = fixture()
    value["registration"]["implementation_sha256"] = "9" * 64
    with pytest.raises(mod.RegisteredAnalysisError, match="implementation mismatch"):
        evaluate(value)


def test_metadata_validator_shared_with_bridge_no_source_or_look_authority():
    value = fixture()
    raw, _ = encoded(value)
    result = mod.verify_registered_analysis_manifest(registration_raw=raw["registration"], manifest_raw=raw["manifest"],
                expected_registration_sha256=sha(raw["registration"]), expected_manifest_sha256=sha(raw["manifest"]),
                expected_implementation_sha256="a" * 64)
    assert result["canonical_event_clock_verified"] is True
    assert result["source_authentication_performed"] is result["look_authority"] is False
    assert result["implementation_execution_identity_verified_here"] is False


def negative_fixture():
    sessions = tuple(business_days())
    descriptors = tuple({"signal_id": "event-" + str(i), "issuer_id": "issuer-" + str(i // 2),
                         "security_id": "security-" + str(i), "industry": "industrial", "size_bucket": "small",
                         "entry_session": sessions[270 + i * 3], "source_event_sha256": format(i, "064x"),
                         "pit_context_available_at_utc": "2019-12-01T00:00:00Z"} for i in range(4))
    return descriptors, sessions


def negative_schedules():
    descriptors, sessions = negative_fixture()
    return mod.build_negative_control_schedules(descriptors=descriptors, sessions=sessions,
        session_open_utc=tuple(utc(day) for day in sessions), source_inventory_sha256="3" * 64)


def test_negative_control_schedules_preserve_source_counts_and_group_inventory():
    first, second = negative_schedules(), negative_schedules()
    assert first == second and first["source_event_count"] == 4 and len(first["schedules"]) == 8
    descriptors, sessions = negative_fixture()
    source = {row["signal_id"]: row for row in descriptors}
    for row in first["schedules"]:
        event = source[row["source_signal_id"]]
        assert row["source_event_sha256"] == event["source_event_sha256"]
        assert row["new_price_query_required"] is row["new_pit_reference_required"] is True
        assert row["original_return_reuse_permitted"] is row["original_pit_context_reuse_permitted"] is False
        assert row["exit_session"] == sessions[sessions.index(row["entry_session"]) + 20]
        if row["recipe"] == "filing-date-within-issuer":
            assert row["target_issuer_id"] == event["issuer_id"]
            assert row["entry_session"] != event["entry_session"]
        else:
            assert row["entry_session"] == event["entry_session"]
            assert row["target_security_id"] != event["security_id"]
            assert row["source_industry"] == event["industry"] and row["source_size_bucket"] == event["size_bucket"]
    assert first["returns_evaluated"] is first["outcome_access_authority"] is False


def negative_prices(schedules):
    sessions = business_days()
    return tuple({"control_id": row["control_id"], "target_security_id": row["target_security_id"],
                  "price": price(sessions, sessions.index(row["entry_session"]), 20, str(101 + i)),
                  "pit_reference_sha256": "4" * 64, "reference_available_at_utc": "2019-12-01T00:00:00Z",
                  "entry_open_utc": row["entry_open_utc"]} for i, row in enumerate(schedules["schedules"]))


def test_new_negative_price_calculations_not_original_return_relabeling():
    schedules = negative_schedules()
    result = mod.evaluate_negative_control_prices(schedules=schedules, price_rows=negative_prices(schedules))
    assert result["count"] == 8
    assert set(result["recipes"]) == {"filing-date-within-issuer", "security-within-industry-size"}
    assert result["confirmatory"] is result["ib5_pass"] is result["outcome_provenance_verified_here"] is False
    assert result["alpha_spent"] == [0, 1]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign-security", "original-date", "future-reference", "invented-open", "reuse-price"])
def test_negative_controls_danger_directions_refuse(mutation):
    schedules = negative_schedules()
    prices = list(negative_prices(schedules))
    if mutation == "missing": prices.pop()
    elif mutation == "duplicate": prices[1] = copy.deepcopy(prices[0])
    elif mutation == "foreign-security": prices[0]["target_security_id"] = "foreign"
    elif mutation == "original-date": prices[0]["price"]["entry_session"] = business_days()[270]
    elif mutation == "future-reference": prices[0]["reference_available_at_utc"] = prices[0]["entry_open_utc"]
    elif mutation == "invented-open": prices[0]["entry_open_utc"] = schedules["schedules"][0]["entry_session"] + "T23:59:00Z"
    elif mutation == "reuse-price": schedules["schedules"][0]["original_return_reuse_permitted"] = True
    with pytest.raises(mod.RegisteredAnalysisError):
        mod.evaluate_negative_control_prices(schedules=schedules, price_rows=tuple(prices))


@pytest.mark.parametrize("family", ["code-A-grants", "stale-public-filings"])
def test_grant_and_stale_placebos_require_separate_source_inventory(family):
    with pytest.raises(mod.RegisteredAnalysisError, match="family missing"):
        mod.require_source_bound_placebo_family(family=family, source_inventory_raw=None, expected_source_inventory_sha256="5" * 64)
    value = {"schema": "insider-source-placebo-family-v1", "family": family,
             "source_manifest_sha256": "1" * 64, "factory_source_sha256": "2" * 64,
             "source_event_sha256s": ["3" * 64]}
    raw = mod.canonical_bytes(value)
    result = mod.require_source_bound_placebo_family(family=family, source_inventory_raw=raw, expected_source_inventory_sha256=sha(raw))
    assert result["source_event_count"] == 1
    assert result["source_authentication_performed"] is result["source_factory_execution_verified_here"] is result["outcomes_evaluated"] is False


def test_cross_section_ic_rank_ic_ties_quintiles():
    rows = [{"event": {"entry_session": "2021-01-04", "score": str(i)},
             "returns": {20: {"matched_factor_adjusted": Decimal(i) / 100}}} for i in range(1, 6)]
    result = mod._cross_section_diagnostics(rows)
    assert result["mean_ic"] == result["mean_rank_ic"] == "1"
    assert result["mean_quintile_returns"] == ["0.01", "0.02", "0.03", "0.04", "0.05"]
    assert result["top_minus_bottom_mean"] == "0.04" and result["quintile_monotonic_date_rate"] == "1"
    assert mod._rank([Decimal(3), Decimal(1), Decimal(3)]) == [Decimal("2.5"), Decimal(1), Decimal("2.5")]
    for row in rows: row["event"]["score"] = "1"
    result = mod._cross_section_diagnostics(rows)
    assert result["mean_ic"] is None and result["mean_quintile_returns"] is None


def test_parent_to_scored_package_native_bridge_to_registered_analysis_is_executable(monkeypatch):
    """Entire chain is genuine invented factories, not a claimed downloaded run."""
    from test_insider_buying_backtest_qc_export_adapter import _registered_inputs, _bridge_kwargs
    from research.insider_buying import backtest_qc_export_adapter as native
    inputs, registration, manifest, implementation = _registered_inputs(monkeypatch)
    sealed_export = native.adapt_qc_export(**inputs)
    terminal_raw = sealed_export.registered_terminal_bytes(**_bridge_kwargs(registration, manifest, implementation))
    terminal = json.loads(terminal_raw)
    dates = [row["session"] for row in manifest["sessions"]]
    indexed_fills = {(row["signal_id"], row["side"]): row for row in terminal["fills"]}
    rows, pools = [], {}
    for event in manifest["events"]:
        entry = dates.index(event["entry_session"])
        stock = instrument(dates, entry, event["security_id"], event["issuer_id"], exits=("105", "100", "130"))
        stock["horizons"]["20"]["entry_price"] = indexed_fills[(event["signal_id"], "entry")]["price"]
        stock["horizons"]["20"]["exit_price"] = indexed_fills[(event["signal_id"], "exit")]["price"]
        rows.append({"signal_id": event["signal_id"], "stock": stock,
                     "market": {str(h): price(dates, entry, h, "102") for h in mod.HORIZONS},
                     "sector": {str(h): price(dates, entry, h, "103") for h in mod.HORIZONS}})
        pools[event["entry_session"]] = [instrument(dates, entry, sid, "nonevent-issuer-" + str(i),
                                        cap=str(95 + 5 * i), exits=("101", "102", "103"))
                                        for i, sid in enumerate(manifest["eligible_control_security_ids"])]
    registration_raw, manifest_raw = mod.canonical_bytes(registration), mod.canonical_bytes(manifest)
    panel = {"schema": "insider-stock-event-study-panel-v1", "trust_scope": "fixture",
             "registration_sha256": sha(registration_raw), "manifest_sha256": sha(manifest_raw),
             "outcome_vintage_sha256": registration["outcome_vintage_sha256"],
             "matched_control_coverage_sha256": "2" * 64, "events": rows, "control_pools": pools}
    panel_raw = mod.canonical_bytes(panel)
    raw = {"registration": registration_raw, "manifest": manifest_raw, "terminal": terminal_raw, "panel": panel_raw}
    result = mod.analyze_registered_stock_study(registration_raw=registration_raw, manifest_raw=manifest_raw,
        terminal_raw=terminal_raw, panel_raw=panel_raw,
        trust_roots=mod.RegisteredAnalysisTrustRoots("fixture", tuple((role, sha(raw[role])) for role in mod.ROLES)),
        expected_implementation_sha256=implementation)
    assert result["counts"]["events"] == 20 and result["counts"]["submitted_orders"] == 40
    assert result["horizon_cost_diagnostics"]["20"]["0"]["raw"]["mean"] == "0"
    assert result["order_path_verified"] is True and result["software_statistical_disposition"] == "FIXTURE_INSUFFICIENT"
    assert result["ib5_pass"] is result["backtesting_ready"] is result["actual_outcome_access_performed"] is False


def make_panel_for_manifest_terminal(registration, manifest, terminal, issuer_by_security=None):
    """Invented factor/price/control reference, actual supplied native20fills."""
    dates = [row["session"] for row in manifest["sessions"]]
    fills = {(row["signal_id"], row["side"]): row for row in terminal["fills"]}
    event_issuers = {row["security_id"]: row["issuer_id"] for row in manifest["events"]}
    known = dict(issuer_by_security or {}); known.update(event_issuers)
    inventories = mod._control_inventories(manifest)
    rows, pools, selected = [], {}, {}
    for event in manifest["events"]:
        entry, day = dates.index(event["entry_session"]), event["entry_session"]
        stock = instrument(dates, entry, event["security_id"], event["issuer_id"], exits=("105", "100", "130"))
        stock["horizons"]["20"]["entry_price"] = fills[(event["signal_id"], "entry")]["price"]
        stock["horizons"]["20"]["exit_price"] = fills[(event["signal_id"], "exit")]["price"]
        rows.append({"signal_id": event["signal_id"], "stock": stock,
                     "market": {str(h): price(dates, entry, h, "102") for h in mod.HORIZONS},
                     "sector": {str(h): price(dates, entry, h, "103") for h in mod.HORIZONS}})
        full = [instrument(dates, entry, sid, known.get(sid, "invented-nonevent-" + str(i)),
                           cap=str(95 + 5 * i), exits=("101", "102", "103")) for i, sid in enumerate(inventories[day])]
        features = [{key: item[key] for key in ("security_id", "issuer_id", "industry", "features", "features_available_at_utc")} for item in full]
        eligible = [item for item in full if item["issuer_id"] not in {row["issuer_id"] for row in manifest["events"] if row["entry_session"] == day}]
        choices = mod._matched(mod._control_features({key: stock[key] for key in
                                   ("security_id", "issuer_id", "industry", "features", "features_available_at_utc")}, opening=mod._utc(manifest["sessions"][entry]["open_utc"])),
                               [mod._control_features({key: item[key] for key in
                                   ("security_id", "issuer_id", "industry", "features", "features_available_at_utc")}, opening=mod._utc(manifest["sessions"][entry]["open_utc"])) for item in eligible])
        wanted = {item["security_id"] for item in choices}
        pools[day] = features
        selected.setdefault(day, {})
        selected[day].update({item["security_id"]: item for item in full if item["security_id"] in wanted})
    panel = {"schema": "insider-stock-event-study-panel-v2", "trust_scope": "fixture",
             "registration_sha256": sha(mod.canonical_bytes(registration)), "manifest_sha256": sha(mod.canonical_bytes(manifest)),
             "outcome_vintage_sha256": registration["outcome_vintage_sha256"], "matched_control_coverage_sha256": "2" * 64,
             "events": rows, "control_pools": pools, "selected_control_outcomes": {day: list(items.values()) for day, items in selected.items()}}
    return panel


def test_causal_manifest_to_generated_child_native_completion_and_registered_analysis():
    from test_insider_buying_backtest_event_study_manifest import make_causal_fixture
    from test_insider_buying_backtest_qc_canonical_candidate import build, native_inputs
    from research.insider_buying import backtest_qc_canonical_candidate as native
    from research.insider_buying import backtest_event_study_manifest as producer
    kwargs = make_causal_fixture()
    # The application captures code bytes outside the pure product. This is
    # exact current candidate source identity, not real look/rights evidence.
    source_raw = (Path(__file__).resolve().parents[1] / "research/insider_buying/backtest_registered_analysis.py").read_bytes()
    implementation = sha(source_raw)
    registered = json.loads(kwargs["registration"])
    registered["implementation_sha256"] = implementation
    registered["analysis_plan"] = mod.analysis_plan_descriptors(implementation_sha256=implementation)
    kwargs["registration"] = mod.canonical_bytes(registered)
    kwargs["trust_roots"] = replace(kwargs["trust_roots"], registration_sha256=sha(kwargs["registration"]),
                                    analysis_implementation_sha256=implementation)
    source_manifest = producer.build_source_event_study_manifest(**kwargs)
    plan = build(kwargs)
    native_result = native.adapt_canonical_qc_export(**native_inputs(plan))
    terminal_raw = plan.verify_native_completion_set((native_result,))
    registration, manifest, terminal = json.loads(kwargs["registration"]), json.loads(source_manifest.manifest_bytes()), json.loads(terminal_raw)
    issuers = {row["qc_symbol_id"]: row["issuer_cik"] for row in json.loads(kwargs["security_master"])["mappings"]}
    panel = make_panel_for_manifest_terminal(registration, manifest, terminal, issuers)
    raw = {"registration": kwargs["registration"], "manifest": source_manifest.manifest_bytes(), "terminal": terminal_raw,
           "panel": mod.canonical_bytes(panel)}
    result = mod.analyze_registered_stock_study(registration_raw=raw["registration"], manifest_raw=raw["manifest"],
        terminal_raw=raw["terminal"], panel_raw=raw["panel"], expected_implementation_sha256=implementation,
        trust_roots=mod.RegisteredAnalysisTrustRoots("fixture", tuple((role, sha(raw[role])) for role in mod.ROLES)))
    assert result["counts"]["events"] == 1 and result["counts"]["submitted_orders"] == 2
    assert result["control_inventory_profile"] == "dynamic-per-entry-v2"
    assert result["registered_implementation_sha256"] == implementation
    assert result["implementation_execution_identity_verified_here"] is False
    assert result["software_statistical_disposition"] == "FIXTURE_INSUFFICIENT"
    assert result["ib5_pass"] is result["backtesting_ready"] is result["actual_outcome_access_performed"] is False


def ledger_fixture():
    dates = business_days(22)
    calendar = {"schema": "insider-backtest-calendar-v1", "trust_scope": "fixture",
                "sessions": [{"session": day, "open_utc": utc(day), "close_utc": utc(day, "21:00:00")} for day in dates]}
    rows = []
    for i, day in enumerate(dates):
        opening_positions = [{**item} for item in rows[-1]["positions"]] if rows else []
        opening_cash = Decimal(rows[-1]["cash_usd"]) if rows else Decimal(10000)
        opening_equity = opening_cash + sum((Decimal(item["mark_price_usd"]) * item["quantity"] for item in opening_positions), Decimal(0))
        price_mark = "90" if i == 5 else "100"
        positions = [{"security_id": "stock", "quantity": 10, "mark_price_usd": price_mark}] if 1 <= i < 21 else []
        cash = "8999" if 1 <= i < 21 else "10098" if i == 21 else "10000"
        equity = str(Decimal(cash) + (Decimal(price_mark) * 10 if positions else 0))
        fills = []
        if i in (1, 21):
            fills = [{"order_id": "entry" if i == 1 else "exit", "signal_id": "signal", "security_id": "stock",
                      "side": "entry" if i == 1 else "exit", "quantity": 10 if i == 1 else -10,
                      "price_usd": "100" if i == 1 else "110", "fee_usd": "1", "filled_at_utc": utc(day),
                      "adv20_usd": "1000000", "adv_available_at_utc": utc(dates[i - 1], "21:00:00")}]
        rows.append({"session": day, "marked_at_utc": utc(day, "21:00:00"), "external_cashflow_usd": "0",
                     "opening_marked_at_utc": utc(day), "opening_positions": opening_positions,
                     "opening_equity_before_cashflow_usd": str(opening_equity),
                     "cash_usd": cash, "equity_usd": equity, "market_total_return_index": str(Decimal(100) + Decimal(i + 1) / 10),
                     "positions": positions, "fills": fills})
    return {"schema": "insider-order-cash-ledger-v1", "trust_scope": "fixture", "registered_look_id": "look",
            "candidate_id": "candidate", "registration_sha256": "1" * 64, "source_manifest_sha256": "2" * 64,
            "outcome_vintage_sha256": "3" * 64, "capital_experiment_id": "ONE-experiment-not-pooled", "calendar": calendar,
            "initial_cash_usd": "10000", "initial_market_total_return_index": "100", "cashflow_timing": "session-open-before-fills", "rows": rows}


def ledger_result(value):
    raw = mod.canonical_bytes(value)
    return mod.analyze_supplied_order_cash_ledger(ledger_raw=raw, expected_ledger_sha256=sha(raw))


def test_full_cash_ledger_real_arithmetic_risk_turnover_capacity_without_pooled_capital():
    result = ledger_result(ledger_fixture())
    assert result["ending_cash_usd"] == "10098" and result["actual_fees_usd"] == "2"
    assert abs(Decimal(result["time_weighted_return"]) - Decimal(".0098")) < Decimal("1e-45")
    assert result["completed_roundtrips"] == 1 and result["average_holding_sessions"] == "20"
    assert result["maximum_trade_participation_of_pit_adv"] == "0.0011"
    assert Decimal(result["max_drawdown"]) > Decimal(".01")
    assert result["beta_to_supplied_market_total_return_index"] is not None and result["annualized_volatility"] is not None
    assert result["pooled_child_capital_inferred"] is result["confirmatory"] is result["ib5_pass"] is result["outcome_access_authority"] is False
    with localcontext() as ctx:
        ctx.prec = 5
        assert ledger_result(ledger_fixture()) == result


def test_open_cashflow_must_not_capture_prior_overnight_position_return():
    value = ledger_fixture()
    for i, row in enumerate(value["rows"]):
        if i >= 2:
            row["cash_usd"] = str(Decimal(row["cash_usd"]) + 1000)
            row["equity_usd"] = str(Decimal(row["equity_usd"]) + 1000)
        if i > 2:
            row["opening_equity_before_cashflow_usd"] = str(Decimal(row["opening_equity_before_cashflow_usd"]) + 1000)
    value["rows"][2]["external_cashflow_usd"] = "1000"
    value["rows"][2]["positions"][0]["mark_price_usd"] = "200"
    value["rows"][2]["opening_positions"][0]["mark_price_usd"] = "200"
    value["rows"][2]["opening_equity_before_cashflow_usd"] = "10999"
    value["rows"][2]["equity_usd"] = "11999"
    result = ledger_result(value)
    with localcontext() as ctx:
        ctx.prec = 50
        # Cash+position before the open deposit:8999+10*200=10999.
        # Return through the close(11999) after deposit(1000) is zero.
        expected = Decimal(10999) / 10000 * Decimal(11098) / 11999 - 1
        assert abs(Decimal(result["time_weighted_return"]) - expected) < Decimal("1e-45")


def test_expected_shortfall_uses_exact_five_percent_probability_mass():
    value = ledger_fixture()
    result = ledger_result(value)
    with localcontext() as ctx:
        ctx.prec = 50
        previous, returned = Decimal(10000), []
        for row in value["rows"]:
            current = Decimal(row["equity_usd"])
            returned.append(current / previous - 1); previous = current
        ordered = sorted(returned)
        expected = (ordered[0] + Decimal(".1") * ordered[1]) / Decimal("1.1")
        assert abs(Decimal(result["expected_shortfall_5pct_daily_return"]) - expected) < Decimal("1e-45")


def test_shared_stock_entry_open_price_cannot_drift_across_horizons():
    value = fixture()
    value["panel"]["events"][0]["stock"]["horizons"]["5"]["entry_price"] = "101"
    with pytest.raises(mod.RegisteredAnalysisError): evaluate(value)


def test_native_price_parity_compares_exact_decimal_value_without_rewriting_byte_roots():
    value = fixture()
    value["panel"]["events"][0]["stock"]["horizons"]["20"].update(entry_price="100.00", exit_price="110.000")
    result = evaluate(value)
    assert result["order_path_verified"] is True
    assert result["horizon_cost_diagnostics"]["20"]["0"]["raw"]["mean"] == "0.1"
    raw, roots = encoded(value)
    assert result["artifact_sha256s"] == roots.hashes()
    assert b'"entry_price":"100.00"' in raw["panel"]
    value["panel"]["events"][0]["stock"]["horizons"]["20"]["exit_price"] = "110.0001"
    with pytest.raises(mod.RegisteredAnalysisError, match="prices differ"):
        evaluate(value)


def test_ledger_preserves_supported_small_fee_under_low_ambient_precision():
    value = ledger_fixture()
    with localcontext() as ctx:
        ctx.prec = 100
        epsilon = Decimal(".0000000000000000000000000001")
        value["rows"][1]["fills"][0]["fee_usd"] = format(Decimal(1) + epsilon, "f")
        for i, row in enumerate(value["rows"]):
            if i >= 1:
                for field in ("cash_usd", "equity_usd"):
                    row[field] = format(Decimal(row[field]) - epsilon, "f")
            if i >= 2:
                row["opening_equity_before_cashflow_usd"] = format(Decimal(row["opening_equity_before_cashflow_usd"]) - epsilon, "f")
    result = ledger_result(value)
    assert result["actual_fees_usd"] == "2.0000000000000000000000000001"
    assert result["ending_cash_usd"] == "10097.9999999999999999999999999999"
    with localcontext() as ctx:
        ctx.prec = 3
        assert ledger_result(value) == result


def test_supported_scale28_fee_survives_large_bounded_cash_balance():
    value = ledger_fixture()
    with localcontext() as ctx:
        ctx.prec = 100
        initial, epsilon = Decimal("1e29"), Decimal("1e-28")
        value["initial_cash_usd"] = format(initial, "f")
        value["rows"][1]["fills"][0]["fee_usd"] = format(Decimal(1) + epsilon, "f")
        for i, row in enumerate(value["rows"]):
            for field in ("cash_usd", "equity_usd"):
                row[field] = format(Decimal(row[field]) + initial - 10000 - (epsilon if i >= 1 else 0), "f")
            row["opening_equity_before_cashflow_usd"] = format(Decimal(row["opening_equity_before_cashflow_usd"]) + initial - 10000 - (epsilon if i >= 2 else 0), "f")
        expected = format(initial + 98 - epsilon, "f")
    result = ledger_result(value)
    assert result["ending_cash_usd"] == expected
    assert result["actual_fees_usd"] == "2.0000000000000000000000000001"
    with localcontext() as ctx:
        ctx.prec = 3
        assert ledger_result(value) == result


@pytest.mark.parametrize("value", ["0." + "0" * 69 + "1", "1000000000000000000000000000001"])
def test_ledger_refuses_unsupported_money_scale_or_magnitude(value):
    ledger = ledger_fixture()
    ledger["rows"][1]["fills"][0]["fee_usd"] = value
    with pytest.raises(mod.RegisteredAnalysisError, match="scale|bound"):
        ledger_result(ledger)


def test_source_signal_cannot_repeat_a_later_flat_roundtrip():
    value = ledger_fixture()
    dates = business_days(24)
    for index in (22, 23):
        day = dates[index]
        value["calendar"]["sessions"].append({"session": day, "open_utc": utc(day), "close_utc": utc(day, "21:00:00")})
        opening = [] if index == 22 else [{"security_id": "stock", "quantity": 10, "mark_price_usd": "100"}]
        value["rows"].append({"session": day, "marked_at_utc": utc(day, "21:00:00"), "external_cashflow_usd": "0",
            "opening_marked_at_utc": utc(day), "opening_positions": opening,
            "opening_equity_before_cashflow_usd": "10098" if index == 22 else "10097",
            "cash_usd": "9097" if index == 22 else "10196", "equity_usd": "10097" if index == 22 else "10196",
            "market_total_return_index": str(Decimal(100) + Decimal(index + 1) / 10),
            "positions": [{"security_id": "stock", "quantity": 10, "mark_price_usd": "100"}] if index == 22 else [],
            "fills": [{"order_id": "new-" + str(index), "signal_id": "second-signal", "security_id": "stock",
                "side": "entry" if index == 22 else "exit", "quantity": 10 if index == 22 else -10,
                "price_usd": "100" if index == 22 else "110", "fee_usd": "1", "filled_at_utc": utc(day),
                "adv20_usd": "1000000", "adv_available_at_utc": utc(dates[index - 1], "21:00:00")}]})
    assert ledger_result(value)["completed_roundtrips"] == 2
    for row in value["rows"][-2:]:
        row["fills"][0]["signal_id"] = "signal"
    with pytest.raises(mod.RegisteredAnalysisError, match="repeats"):
        ledger_result(value)


@pytest.mark.parametrize("field", ["opening-time", "opening-quantity", "opening-value", "opening-missing", "share-bound"])
def test_exact_opening_cashflow_profile_refuses_mismatch(field):
    value = ledger_fixture()
    if field == "opening-time": value["rows"][2]["opening_marked_at_utc"] = utc(value["rows"][2]["session"], "14:31:00")
    elif field == "opening-quantity": value["rows"][2]["opening_positions"][0]["quantity"] = 9
    elif field == "opening-value": value["rows"][2]["opening_equity_before_cashflow_usd"] = "9998"
    elif field == "opening-missing": value["rows"][2]["opening_positions"] = []
    elif field == "share-bound": value["rows"][1]["fills"][0]["quantity"] = 10 ** 12 + 1
    with pytest.raises(mod.RegisteredAnalysisError): ledger_result(value)


@pytest.mark.parametrize("field", ["cash", "equity", "missing-mark", "partial-exit", "negative-fee", "future-adv", "late-fill", "missing-session", "short", "duplicate-order"])
def test_cash_ledger_danger_direction_refuses(field):
    value = ledger_fixture()
    if field == "cash": value["rows"][1]["cash_usd"] = "9000"
    elif field == "equity": value["rows"][1]["equity_usd"] = "9998"
    elif field == "missing-mark": value["rows"][1]["positions"] = []
    elif field == "partial-exit": value["rows"][-1]["fills"][0]["quantity"] = -9
    elif field == "negative-fee": value["rows"][1]["fills"][0]["fee_usd"] = "-1"
    elif field == "future-adv": value["rows"][1]["fills"][0]["adv_available_at_utc"] = value["rows"][1]["fills"][0]["filled_at_utc"]
    elif field == "late-fill": value["rows"][1]["fills"][0]["filled_at_utc"] = value["rows"][1]["session"] + "T14:31:00Z"
    elif field == "missing-session": value["rows"].pop()
    elif field == "short": value["rows"][1]["fills"][0].update(side="exit", quantity=-10)
    elif field == "duplicate-order": value["rows"][-1]["fills"][0]["order_id"] = "entry"
    with pytest.raises(mod.RegisteredAnalysisError): ledger_result(value)


def variant_fixture():
    calendar = ledger_fixture()["calendar"]
    # More calendar sessions provide the full delayed20 horizon.
    calendar["sessions"] = [{"session": day, "open_utc": utc(day), "close_utc": utc(day, "21:00:00")} for day in business_days(30)]
    dates = [row["session"] for row in calendar["sessions"]]
    variants = {}
    for name, entry, time, enter_price, exit_price in (("next-open", 1, "14:30:00", "100", "110"),
                                                     ("next-close", 0, "21:00:00", "101", "112"),
                                                     ("one-session-delayed-open", 2, "14:30:00", "102", "113")):
        if name == "next-close": entry = 1
        variants[name] = [{"signal_id": "signal", "security_id": "stock", "side": side, "quantity": quantity,
                           "price_usd": price_value, "fee_usd": "1", "filled_at_utc": utc(dates[index], time),
                           "order_id": name + "-" + side} for side, quantity, price_value, index in
                          (("entry", 10, enter_price, entry), ("exit", -10, exit_price, entry + 20))]
    return {"schema": "insider-stock-execution-variant-exports-v1", "trust_scope": "fixture",
            "registration_sha256": "1" * 64, "source_manifest_sha256": "2" * 64, "outcome_vintage_sha256": "3" * 64,
            "registered_look_id": "look", "candidate_id": "candidate", "calendar": calendar,
            "events": [{"signal_id": "signal", "security_id": "stock", "source_event_sha256": "4" * 64,
                        "available_at_utc": utc(dates[0], "22:00:00")}], "variants": variants}


def variant_result(value):
    raw = mod.canonical_bytes(value)
    return mod.compare_supplied_execution_variants(variants_raw=raw, expected_variants_sha256=sha(raw))


def test_exact_supplied_nextclose_and_delayed_orders_compare_without_inferred_prices():
    result = variant_result(variant_fixture())
    assert result["event_count"] == 1 and set(result["variants"]) == {"next-open", "next-close", "one-session-delayed-open"}
    assert result["variants"]["next-open"]["actual_fee_net_return"]["mean"] == "0.098"
    assert result["variants"]["next-open"]["actual_fees_usd"] == "2"
    assert result["price_reuse_inferred"] is result["confirmatory"] is result["ib5_pass"] is False


@pytest.mark.parametrize("field", ["missing-variant", "missing-fill", "delay-time", "close-time", "partial", "resize", "price-float", "negative-fee"])
def test_alternate_execution_actual_export_guards_refuse(field):
    value = variant_fixture()
    if field == "missing-variant": value["variants"].pop("next-close")
    elif field == "missing-fill": value["variants"]["next-close"].pop()
    elif field == "delay-time": value["variants"]["one-session-delayed-open"][0]["filled_at_utc"] = value["variants"]["next-open"][0]["filled_at_utc"]
    elif field == "close-time": value["variants"]["next-close"][0]["filled_at_utc"] = value["variants"]["next-open"][0]["filled_at_utc"]
    elif field == "partial": value["variants"]["next-close"][1]["quantity"] = -9
    elif field == "resize":
        value["variants"]["next-close"][0]["quantity"] = 20
        value["variants"]["next-close"][1]["quantity"] = -20
    elif field == "price-float": value["variants"]["next-close"][0]["price_usd"] = 100.0
    elif field == "negative-fee": value["variants"]["next-close"][0]["fee_usd"] = "-1"
    with pytest.raises(mod.RegisteredAnalysisError): variant_result(value)


def test_nonfinite_cluster_values_and_invalid_probabilities_refuse():
    for value in (Decimal("NaN"), Decimal("Infinity"), 1.0):
        with pytest.raises(mod.RegisteredAnalysisError): mod.clustered_inference((("a", "2021-01-04", value), ("b", "2021-01-05", Decimal(0))))
    for t, df in ((float("inf"), 1), (float("nan"), 1), (1, 0), (1, True)):
        with pytest.raises(mod.RegisteredAnalysisError): mod._student_two_sided_p(t, df)


def stream_fixture(*, count=3, pool_size=5):
    """External synthetic application captures each byte digest, no real data.

    The application regenerates deterministic invented rows for supply; the
    product receives and consumes exactly one iterator once. No record list or
    full feature panel is retained by this test application or the product.
    """
    values = fixture()
    dates = business_days(max(460, 270 + count + 61))
    sessions = [{"session": day, "open_utc": utc(day), "close_utc": utc(day, "21:00:00")} for day in dates]
    registration = values["registration"]
    registration["calendar_sha256"] = sha(mod.canonical_bytes(sessions))
    registration["first_outcome_access_utc"] = "2026-01-01T00:00:00Z"
    register_raw = mod.canonical_bytes(registration)
    register_sha = sha(register_raw)
    pool_ids = ["control-" + str(i).zfill(5) for i in range(pool_size)]
    events, fills = [], []
    for i in range(count):
        entry = 270 + i
        event = {**values["manifest"]["events"][0], "signal_id": "signal-" + str(i).zfill(5),
            "issuer_id": "issuer-" + str(i).zfill(5), "security_id": "stock-" + str(i).zfill(5),
            "available_at_utc": utc(dates[entry - 1], "21:00:00"), "entry_session": dates[entry],
            "exit_session": dates[entry + 20], "buyer_ids": ["buyer-" + str(i)]}
        events.append(event)
        for side, index, quantity, price_value in (("entry", entry, 10, "100"), ("exit", entry + 20, -10, str(110 + i % 7))):
            fills.append({"signal_id": event["signal_id"], "side": side, "security_id": event["security_id"],
                "session": dates[index], "filled_at_utc": utc(dates[index]), "quantity": quantity,
                "price": price_value, "order_id": event["signal_id"] + "-" + side})
    manifest = {**values["manifest"], "schema": "insider-stock-event-study-manifest-v2",
        "registration_sha256": register_sha, "calendar_sha256": registration["calendar_sha256"], "sessions": sessions,
        "events": events, "eligible_control_security_ids": pool_ids,
        "eligible_control_security_ids_by_entry_session": {event["entry_session"]: pool_ids for event in events}}
    manifest_raw = mod.canonical_bytes(manifest)
    manifest_sha = sha(manifest_raw)
    terminal = {**values["terminal"], "registration_sha256": register_sha, "manifest_sha256": manifest_sha, "fills": fills}
    terminal_raw = mod.canonical_bytes(terminal)
    common = {"trust_scope": "fixture", "registration_sha256": register_sha, "manifest_sha256": manifest_sha,
              "outcome_vintage_sha256": registration["outcome_vintage_sha256"], "matched_control_coverage_sha256": "2" * 64}
    template = instrument(dates, 270, "template", "template")
    def full(entry, sid, issuer, exits):
        value = copy.deepcopy(template)
        value.update(security_id=sid, issuer_id=issuer, features_available_at_utc=utc(dates[entry - 1], "21:00:00"))
        value["factor_training"].update(sessions=dates[entry - 252:entry], available_at_utc=utc(dates[entry - 1], "21:00:00"))
        value["future_factors"] = [{**item, "session": dates[entry + j], "interval_end_session": dates[entry + j + 1]}
                                   for j, item in enumerate(value["future_factors"])]
        value["horizons"] = {str(h): price(dates, entry, h, exit_price) for h, exit_price in zip(mod.HORIZONS, exits)}
        return value
    def record(index):
        entry, event = 270 + index, events[index]
        features = [{"security_id": sid, "issuer_id": "control-issuer-" + str(j), "industry": "industrial",
            "features": dict(template["features"]), "features_available_at_utc": utc(dates[entry - 1], "21:00:00")}
                    for j, sid in enumerate(pool_ids)]
        body = {**common, "schema": "insider-stock-event-study-panel-record-v1", "entry_session": event["entry_session"],
            "events": [{"signal_id": event["signal_id"], "stock": full(entry, event["security_id"], event["issuer_id"], ("105", str(110 + index % 7), "130")),
                "market": {str(h): price(dates, entry, h, "102") for h in mod.HORIZONS},
                "sector": {str(h): price(dates, entry, h, "103") for h in mod.HORIZONS}}],
            "control_pool": features,
            "selected_control_outcomes": [full(entry, sid, "control-issuer-" + str(j), ("101", "102", "103"))
                                          for j, sid in enumerate(pool_ids[:3])]}
        return mod.canonical_bytes(body)
    inventory = []
    for i, event in enumerate(events):
        raw = record(i)
        inventory.append({"entry_session": event["entry_session"], "signal_ids": [event["signal_id"]],
                          "sha256": sha(raw), "byte_length": len(raw)})
    descriptor = {**common, "schema": "insider-stock-event-study-panel-stream-v1", "records": inventory}
    raw = {"registration": register_raw, "manifest": manifest_raw, "terminal": terminal_raw,
           "panel": mod.canonical_bytes(descriptor)}
    return raw, record


def stream_evaluate(raw, records, *, scope="fixture"):
    return mod.analyze_registered_stock_study_stream(registration_raw=raw["registration"], manifest_raw=raw["manifest"],
        terminal_raw=raw["terminal"], panel_descriptor_raw=raw["panel"], panel_records=records,
        trust_roots=mod.RegisteredAnalysisTrustRoots(scope, tuple((role, sha(raw[role])) for role in mod.ROLES)),
        expected_implementation_sha256="a" * 64)


def test_one_pass_stream_releases_records_before_next_and_matches_flat_calculations():
    raw, record = stream_fixture()
    refs, iter_calls = [], []
    class Once:
        def __init__(self): self.generator = self.generate()
        def __iter__(self):
            iter_calls.append(1)
            assert len(iter_calls) == 1
            return self
        def __next__(self): return next(self.generator)
        def generate(self):
            for i in range(3):
                holder = mod.SuppliedPanelRecord(record(i))
                refs.append(weakref.ref(holder))
                yield holder
                del holder
                gc.collect()
                assert refs[-1]() is None
    streamed = stream_evaluate(raw, Once())
    assert len(iter_calls) == 1 and all(ref() is None for ref in refs)
    assert streamed["panel_stream"]["full_raw_records_retained"] == 0
    assert streamed["panel_stream"]["cross_date_control_or_outcome_cache_retained"] is False
    bodies = [json.loads(record(i)) for i in range(3)]
    descriptor = json.loads(raw["panel"])
    flat = {key: descriptor[key] for key in descriptor if key != "records"}
    flat.update(schema="insider-stock-event-study-panel-v2", events=[event for body in bodies for event in body["events"]],
        control_pools={body["entry_session"]: body["control_pool"] for body in bodies},
        selected_control_outcomes={body["entry_session"]: body["selected_control_outcomes"] for body in bodies})
    flat_raw = {**raw, "panel": mod.canonical_bytes(flat)}
    result = mod.analyze_registered_stock_study(registration_raw=raw["registration"], manifest_raw=raw["manifest"],
        terminal_raw=raw["terminal"], panel_raw=flat_raw["panel"], expected_implementation_sha256="a" * 64,
        trust_roots=mod.RegisteredAnalysisTrustRoots("fixture", tuple((role, sha(flat_raw[role])) for role in mod.ROLES)))
    for key in result:
        if key not in {"report_sha256", "artifact_sha256s"}: assert streamed[key] == result[key]
    assert streamed["alpha_spent"] == [0, 1] and streamed["registered_looks_consumed"] == 0


def test_stream_production_refuses_before_iterator_creation():
    raw, _ = stream_fixture(count=1)
    registration = json.loads(raw["registration"]); registration["trust_scope"] = "production"
    raw["registration"] = mod.canonical_bytes(registration)
    class Explodes:
        def __iter__(self): raise AssertionError("production consumed outcome iterator")
    with pytest.raises(mod.RegisteredAnalysisError, match="zero-look"):
        stream_evaluate(raw, Explodes(), scope="production")


@pytest.mark.parametrize("collection", [list, tuple])
def test_stream_refuses_materialized_record_collection(collection):
    raw, record = stream_fixture(count=1)
    with pytest.raises(mod.RegisteredAnalysisError, match="one-pass iterator"):
        stream_evaluate(raw, collection((record(0),)))


@pytest.mark.parametrize("edit", ["missing-record", "extra-record", "reordered-record", "tampered-record", "coherent-tamper", "record-vintage", "event-drop", "future-feature", "extra-outcome"])
def test_stream_record_exact_inventory_and_bytes_refuse(edit):
    raw, record = stream_fixture()
    records = [record(i) for i in range(3)]
    if edit == "missing-record": records.pop()
    elif edit == "extra-record": records.append(records[-1])
    elif edit == "reordered-record": records.reverse()
    elif edit == "tampered-record": records[0] = records[0] + b" "
    elif edit == "coherent-tamper":
        body = json.loads(records[0]); body["events"][0]["market"]["20"]["exit_price"] = "103"
        records[0] = mod.canonical_bytes(body)
    else:
        body = json.loads(records[0])
        if edit == "record-vintage": body["outcome_vintage_sha256"] = "9" * 64
        elif edit == "event-drop": body["events"] = []
        elif edit == "future-feature": body["control_pool"][0]["features_available_at_utc"] = body["entry_session"] + "T14:30:00Z"
        elif edit == "extra-outcome": body["selected_control_outcomes"].append(copy.deepcopy(body["selected_control_outcomes"][0]))
        records[0] = mod.canonical_bytes(body)
        descriptor = json.loads(raw["panel"])
        descriptor["records"][0].update(sha256=sha(records[0]), byte_length=len(records[0]))
        raw["panel"] = mod.canonical_bytes(descriptor)
    with pytest.raises(mod.RegisteredAnalysisError): stream_evaluate(raw, iter(records))


@pytest.mark.parametrize("edit", ["missing-date", "extra-date", "reordered-date", "missing-event", "extra-event", "length", "aggregate", "schema", "vintage"])
def test_stream_descriptor_refuses_before_record_iterator(edit):
    raw, _ = stream_fixture()
    descriptor = json.loads(raw["panel"])
    if edit == "missing-date": descriptor["records"].pop()
    elif edit == "extra-date": descriptor["records"].append(descriptor["records"][-1])
    elif edit == "reordered-date": descriptor["records"].reverse()
    elif edit == "missing-event": descriptor["records"][0]["signal_ids"] = []
    elif edit == "extra-event": descriptor["records"][0]["signal_ids"].append("foreign")
    elif edit == "length": descriptor["records"][0]["byte_length"] = mod.MAX_STREAM_RECORD_BYTES + 1
    elif edit == "aggregate": descriptor["records"][0]["byte_length"] = True
    elif edit == "schema": descriptor["schema"] = "unregistered-stream-v9"
    elif edit == "vintage": descriptor["outcome_vintage_sha256"] = "9" * 64
    raw["panel"] = mod.canonical_bytes(descriptor)
    class Explodes:
        def __iter__(self): raise AssertionError("invalid inventory consumed iterator")
    with pytest.raises(mod.RegisteredAnalysisError): stream_evaluate(raw, Explodes())


def test_stream_321_independent_dates_and_6000_feature_controls_exceeds_flat_limit_without_new_look():
    raw, record = stream_fixture(count=321, pool_size=6000)
    descriptor = json.loads(raw["panel"])
    assert sum(item["byte_length"] for item in descriptor["records"]) > mod.MAX_BYTES
    result = stream_evaluate(raw, (record(i) for i in range(321)))
    assert result["counts"]["entry_dates"] == result["counts"]["issuers"] == result["counts"]["events"] == 321
    assert result["primary_inference"]["entry_date_count"] == 321
    assert result["software_statistical_disposition"] == "FIXTURE_POSITIVE"
    assert result["panel_stream"]["records"] == 321 and result["panel_stream"]["one_parent_look_no_per_record_alpha"] is True
    assert result["registered_looks_consumed"] == 0 and result["alpha_spent"] == [0, 1]
    assert result["ib5_pass"] is result["backtesting_ready"] is result["actual_outcome_access_performed"] is False


def test_stream_total_128gib_byte_bound_refuses_before_record_iteration():
    raw, _ = stream_fixture(count=1025, pool_size=3)
    descriptor = json.loads(raw["panel"])
    for row in descriptor["records"]: row["byte_length"] = mod.MAX_STREAM_RECORD_BYTES
    assert sum(row["byte_length"] for row in descriptor["records"]) > mod.MAX_STREAM_AGGREGATE_BYTES
    raw["panel"] = mod.canonical_bytes(descriptor)
    class Explodes:
        def __iter__(self): raise AssertionError("unbounded aggregate consumed iterator")
    with pytest.raises(mod.RegisteredAnalysisError, match="aggregate"):
        stream_evaluate(raw, Explodes())


def test_stream_rejects_reanchored_source_event_order_before_outcome_iterator():
    raw, _ = stream_fixture()
    manifest = json.loads(raw["manifest"])
    manifest["events"].reverse()
    raw["manifest"] = mod.canonical_bytes(manifest)
    for role in ("terminal", "panel"):
        body = json.loads(raw[role]); body["manifest_sha256"] = sha(raw["manifest"])
        raw[role] = mod.canonical_bytes(body)
    class Explodes:
        def __iter__(self): raise AssertionError("reordered source population consumed outcomes")
    with pytest.raises(mod.RegisteredAnalysisError, match="source event inventory"):
        stream_evaluate(raw, Explodes())
