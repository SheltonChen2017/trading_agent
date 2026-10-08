"""Advisory end-to-end proofs using invented native-schema source values."""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Inexact, ROUND_DOWN, ROUND_UP, localcontext
from fractions import Fraction
import hashlib
import json
from zoneinfo import ZoneInfo

import pytest

from research.target_price_revisions_development import raw_candidate as candidate


def inputs(count=1):
    """Explicit illustrative NYSE-shaped calendar; no provider or price I/O."""
    eastern = ZoneInfo("America/New_York")
    holidays = {date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17)}
    days, day = [], date(2024, 12, 27)
    while day <= date(2025, 3, 31):
        if day.weekday() < 5 and day not in holidays:
            days.append(day)
        day += timedelta(days=1)
    axis = [{"session_date": day.isoformat(),
             "open_utc": datetime.combine(day, time(9, 30), eastern).astimezone(timezone.utc).isoformat(),
             "close_utc": datetime.combine(day, time(16), eastern).astimezone(timezone.utc).isoformat()} for day in days]
    ratings, identities = [], []
    for number in range(count):
        ticker = f"ZZTEST{number}"
        identities.append({"ticker": ticker, "security_id": f"SHARADAR:{1000 + number}",
                           "permaticker": 1000 + number, "figi": f"BBG{number:09d}",
                           "category": "Domestic Common Stock", "exchange": "NYSE", "isdelisted": False})
        ratings.append({"benzinga_id": f"fixture-event-{number:02d}", "benzinga_firm_id": 12,
                        "ticker": ticker, "date": "2024-12-27", "last_updated": "2024-12-27T15:00:00Z",
                        "currency": "USD", "price_target_action": "raises",
                        "price_target": "110", "previous_price_target": "100"})
    structure = {"schema": "tpr-raw-structure-v1", "capture_utc": "2026-10-07T10:00:00Z",
                 "calendar": axis, "ratings": ratings, "identities": identities,
                 "actions": [], "action_inventory_complete": True}
    outcomes = {"schema": "tpr-raw-outcomes-v1", "sessions": []}
    for index, session in enumerate(axis):
        volume_at = axis[index - 1]["close_utc"] if index else "2024-12-26T21:00:00Z"
        bars = [{"security_id": identity["security_id"], "open": "10", "close": "10",
                 "lagged_volume": 100000, "volume_available_at_utc": volume_at,
                 "open_available_at_utc": session["open_utc"],
                 "close_available_at_utc": session["close_utc"], "tradable": True} for identity in identities]
        outcomes["sessions"].append({"session_id": session["session_date"],
                                     "open_utc": session["open_utc"], "close_utc": session["close_utc"], "bars": bars})
    return structure, outcomes


def target_map(frame):
    return {row["security_id"]: row["weight"] for row in frame["weights"]}


def first_execution(outcomes):
    return next(session for session in outcomes["sessions"] if session["session_id"] == "2025-01-02")


def first_prior(outcomes):
    return next(session for session in outcomes["sessions"] if session["session_id"] == "2024-12-31")


def accounted_inputs():
    structure, outcomes = inputs()
    structure["actions"] = [{"ticker": "ZZTEST0", "date": "2025-01-03", "action": "dividend"}]
    digest = hashlib.sha256((json.dumps(structure, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                             + "\n").encode("ascii")).hexdigest()
    prepared = {"schema": "tpr-raw-market-inputs-v1", "structure_sha256": digest, "outcomes": outcomes,
        "corporate_actions": ({"action_id": "fixture-dividend", "session_id": "2025-01-03",
            "security_id": "SHARADAR:1000", "kind": "cash_dividend", "value": "0.1"},),
        "evidence": {"action_inventory_reconciled": True, "observed_provider_availability": False}}
    return structure, prepared


def test_separate_accounted_executor_forwards_entitlements_without_weakening_old_gate():
    structure, prepared = accounted_inputs()
    with pytest.raises(ValueError, match="action accounting"):
        candidate.run_raw_candidate(structure, prepared["outcomes"])
    result = candidate.run_accounted_raw_candidate(structure, prepared)
    assert result["backtest"]["final_dividend_receivable"] == "99.8"
    assert result["backtest"]["corporate_actions"][0]["kind"] == "cash_dividend"
    assert result["accounting_model"]["observed_provider_availability"] is False
    assert result["canonical_admission"] is False


@pytest.mark.parametrize("change", [
    lambda p: p.update(structure_sha256="a"*64),
    lambda p: p["evidence"].update(action_inventory_reconciled=False),
    lambda p: p.update(corporate_actions=list(p["corporate_actions"])),
    lambda p: p.update(schema="unbound"),
])
def test_accounted_executor_rejects_unbound_or_unreconciled_accounting(change):
    structure, prepared = accounted_inputs()
    change(prepared)
    with pytest.raises(ValueError, match="unbound or unreconciled"):
        candidate.run_accounted_raw_candidate(structure, prepared)


def test_connected_native_schema_candidate_builds_weekly_targets_and_actual_hypothetical_orders():
    structure, outcomes = inputs()
    targets = candidate.build_target_frames(structure)
    assert targets["frames"][0]["session_id"] == "2025-01-02"
    assert targets["frames"][0]["cutoff_utc"] == "2024-12-31T23:00:00+00:00"
    assert target_map(targets["frames"][0]) == {"SHARADAR:1000": "0.1"}
    result = candidate.run_raw_candidate(structure, outcomes)
    execution = result["backtest"]
    assert execution["complete"] is True and execution["orders"] and execution["fills"]
    assert execution["orders"][0]["requested_quantity"] == 998
    assert execution["fills"][0]["side"] == "buy"
    assert execution["fills"][0]["execution_price"] == "10.01"
    assert len(execution["sessions"]) == sum(row["session_date"] >= "2025-01-02" for row in structure["calendar"])
    assert result["canonical_admission"] is False and result["horizon_comparable"] is False
    assert result["historical_identity_proven"] is False and result["confirmatory_alpha"] == "0"
    assert result["quantconnect_attempts"] == 0 and result["trading_authority"] is False
    assert execution["costs_calibrated"] is False and execution["point_in_time_data"] is False
    assert all(value is False for _, value in execution["authority"])


def test_positive_top_ten_native_ties_do_not_add_an_eleventh_name_or_negative_name():
    structure, _ = inputs(12)
    structure["ratings"][-1].update(price_target="90", price_target_action="lowers")
    frame = candidate.build_target_frames(structure)["frames"][0]
    weights = target_map(frame)
    assert sorted(sid for sid, weight in weights.items() if weight == "0.1") == [f"SHARADAR:{1000 + i}" for i in range(10)]
    assert weights["SHARADAR:1010"] == weights["SHARADAR:1011"] == "0"
    assert sum(Fraction(value) for value in weights.values()) == 1


def test_distinct_native_lineages_collapse_to_unit_median_before_firm_median():
    structure, _ = inputs()
    first = structure["ratings"][0]
    structure["ratings"] = [dict(first, benzinga_id=f"fixture-event-{i}", price_target=value)
                             for i, value in enumerate(("110", "110", "190"))]
    structure["ratings"].append(dict(first, benzinga_id="fixture-other-firm", benzinga_firm_id=13,
                                      price_target="70", price_target_action="lowers"))
    targets = candidate.build_target_frames(structure)
    assert target_map(targets["frames"][0]) == {"SHARADAR:1000": "0"}
    assert Fraction(targets["normalization"][0]["scores"][0]["score"]) == Fraction(-1, 10)


def test_native_duplicates_permutation_and_outcome_bar_order_cannot_change_the_candidate():
    structure, outcomes = inputs(3)
    first = candidate.run_raw_candidate(structure, outcomes)
    permuted = deepcopy(structure)
    permuted["ratings"].reverse(); permuted["identities"].reverse()
    changed_outcomes = deepcopy(outcomes)
    for session in changed_outcomes["sessions"]:
        session["bars"].reverse()
    assert candidate.run_raw_candidate(permuted, changed_outcomes) == first
    duplicated = deepcopy(structure)
    duplicated["ratings"].append(dict(duplicated["ratings"][0]))
    assert candidate.build_target_frames(duplicated)["frames"] == candidate.build_target_frames(structure)["frames"]


def test_fixed_candidate_explicitly_selects_snapshot_permaticker_policy_and_discloses_missing_figi():
    structure, outcomes = inputs()
    structure["identities"][0]["figi"] = None
    targets = candidate.build_target_frames(structure)
    assert targets["policy"]["identity_policy"] == "sharadar_permaticker_snapshot_v1"
    assert targets["policy"]["current_snapshot_survivorship_bias_possible"] is True
    assert targets["normalization"][0]["missing_figi_input_rows"] == 1
    assert target_map(targets["frames"][0]) == {"SHARADAR:1000": "0.1"}
    report = candidate.run_raw_candidate(structure, outcomes)
    assert report["backtest"]["orders"] and report["backtest"]["complete"] is True
    assert report["historical_symbol_match_verified"] is False
    assert report["canonical_admission"] is False and report["quantconnect_attempts"] == 0


@pytest.mark.parametrize("changes", [{"figi": ""}, {"figi": "MISSING"}, {"security_id": "invented-security"}])
def test_candidate_snapshot_policy_does_not_convert_invalid_identity_to_positive_target(changes):
    structure, _ = inputs()
    structure["identities"][0].update(changes)
    targets = candidate.build_target_frames(structure)
    assert all(row["weight"] == "0" for frame in targets["frames"] for row in frame["weights"])
    assert targets["normalization"][0]["refusal_counts"]["invalid_snapshot_identity"] == 1


def test_censored_touch_changes_only_later_admitted_frames_and_retains_named_exclusion():
    structure, _ = inputs()
    source = dict(structure["ratings"][0], benzinga_id="fixture-later-touch",
                  last_updated="2025-01-07T15:00:00Z", price_target="120")
    baseline = candidate.build_target_frames(structure)
    structure["ratings"].append(source)
    changed = candidate.build_target_frames(structure)
    assert changed["frames"][:2] == baseline["frames"][:2]
    assert changed["normalization"][0]["refusal_counts"]["later_touch_censored"] == 1
    assert changed["normalization"][2]["accepted_events"] == 2
    assert "later_touch_censored" not in changed["normalization"][2]["refusal_counts"]


def test_changed_execution_outcomes_cannot_rewrite_decision_evidence_or_requested_quantity():
    structure, outcomes = inputs()
    first = candidate.run_raw_candidate(structure, outcomes)
    changed = deepcopy(outcomes)
    first_execution(changed)["bars"][0]["open"] = "20"
    later = candidate.run_raw_candidate(structure, changed)
    assert later["target_evidence"] == first["target_evidence"]
    assert later["backtest"]["orders"][0]["requested_quantity"] == first["backtest"]["orders"][0]["requested_quantity"]
    assert later["backtest"]["fills"][0]["quantity"] < first["backtest"]["fills"][0]["quantity"]


@pytest.mark.parametrize("problem", ["missing_execution", "missing_prior", "late_prior", "future_capacity"])
def test_missing_or_not_cutoff_known_marks_and_capacity_do_not_become_success(problem):
    structure, outcomes = inputs()
    if problem == "missing_execution":
        first_execution(outcomes)["bars"] = []
    elif problem == "missing_prior":
        first_prior(outcomes)["bars"] = []
    elif problem == "late_prior":
        first_prior(outcomes)["bars"][0]["close_available_at_utc"] = "2025-01-02T14:30:00Z"
    else:
        first_execution(outcomes)["bars"][0]["volume_available_at_utc"] = "2025-01-02T14:30:00Z"
    result = candidate.run_raw_candidate(structure, outcomes)["backtest"]
    assert result["complete"] is False and result["exclusions"]
    assert not any(fill["session_id"] == "2025-01-02" for fill in result["fills"])


@pytest.mark.parametrize("where", ["execution", "prior"])
def test_duplicate_native_bars_are_not_silently_deduplicated(where):
    structure, outcomes = inputs()
    session = first_execution(outcomes) if where == "execution" else first_prior(outcomes)
    session["bars"].append(dict(session["bars"][0]))
    with pytest.raises(ValueError):
        candidate.run_raw_candidate(structure, outcomes)


def test_buffer_close_cannot_become_known_before_its_actual_market_close():
    structure, outcomes = inputs()
    first_prior(outcomes)["bars"][0]["close_available_at_utc"] = "2024-12-31T14:30:00Z"
    with pytest.raises(ValueError, match="availability|clock|market"):
        candidate.run_raw_candidate(structure, outcomes)


@pytest.mark.parametrize("boundary", ["start", "end"])
def test_frozen_study_window_cannot_silently_drop_its_endpoint_session(boundary):
    structure, _ = inputs()
    missing = "2025-01-02" if boundary == "start" else "2025-03-31"
    structure["calendar"] = [session for session in structure["calendar"] if session["session_date"] != missing]
    with pytest.raises(ValueError, match="window|coverage|endpoint"):
        candidate.build_target_frames(structure)


@pytest.mark.parametrize("mutation", ["missing", "reordered", "wrong_clock", "wrong_id"])
def test_outcome_axis_must_match_source_calendar_exactly(mutation):
    structure, outcomes = inputs()
    if mutation == "missing":
        outcomes["sessions"].pop()
    elif mutation == "reordered":
        outcomes["sessions"].reverse()
    elif mutation == "wrong_clock":
        outcomes["sessions"][-1]["open_utc"] = "2025-03-31T14:30:00Z"
    else:
        outcomes["sessions"][-1]["session_id"] = "2025-03-30"
    with pytest.raises(ValueError, match="coverage|identity"):
        candidate.run_raw_candidate(structure, outcomes)


@pytest.mark.parametrize("date_string", ["2025-01-02", "2025-03-31", "2025-02-03"])
def test_any_in_window_action_refuses_the_whole_candidate_not_just_a_name(date_string):
    structure, _ = inputs(2)
    structure["actions"] = [{"ticker": "ZZTEST0", "date": date_string, "action": "split"}]
    with pytest.raises(ValueError, match="whole|corporate action"):
        candidate.build_target_frames(structure)


def test_unselected_name_action_also_refuses_the_whole_run():
    structure, _ = inputs(12)
    structure["actions"] = [{"ticker": "ZZTEST11", "date": "2025-03-01", "action": "dividend"}]
    with pytest.raises(ValueError, match="corporate action"):
        candidate.build_target_frames(structure)


def test_outcome_free_planner_keeps_actions_and_does_not_grant_execution_admission():
    structure, outcomes = inputs()
    baseline = candidate.build_target_frames(structure)
    structure["actions"] = [{"ticker": "ZZTEST0", "date": "2025-01-10", "action": kind}
        for kind in ("dividend", "sicchangefrom", "sicchangeto")]
    original = deepcopy(structure)
    plan = candidate.plan_target_frames(structure)
    assert plan["frames"] == baseline["frames"]
    assert plan["proposed_security_ids"] == ["SHARADAR:1000"]
    assert plan["action_accounting_admitted"] is plan["real_backtest_ready"] is False
    assert plan["policy"]["signal_action_policy"] == "nominal_pair_nonshare_actions_v1"
    assert plan["policy"]["nominal_dividend_effects_possible"] is True
    assert plan["policy"]["target_pair_like_for_like_proven"] is False
    assert plan["normalization"][2]["nonshare_action_counts"] == {"dividend": 1, "sicchangefrom": 1, "sicchangeto": 1}
    assert structure == original
    with pytest.raises(ValueError, match="corporate action"):
        candidate.build_target_frames(structure)
    with pytest.raises(ValueError, match="corporate action"):
        candidate.run_raw_candidate(structure, outcomes)


def test_planner_preserves_future_action_until_as_of_cutoff_not_hindsight_name_removal():
    structure, _ = inputs()
    baseline = candidate.build_target_frames(structure)
    structure["actions"] = [{"ticker": "ZZTEST0", "date": "2025-01-07", "action": "split"}]
    plan = candidate.plan_target_frames(structure)
    assert plan["frames"][:2] == baseline["frames"][:2]
    assert target_map(plan["frames"][2]) == {"SHARADAR:1000": "0"}
    assert plan["normalization"][2]["refusal_counts"]["corporate_action_ambiguity"] == 1
    assert plan["proposed_security_ids"] == ["SHARADAR:1000"]


def test_planner_cannot_override_source_inventory_calendar_or_identity_limits():
    structure, _ = inputs()
    structure["action_inventory_complete"] = False
    with pytest.raises(ValueError, match="source structure"):
        candidate.plan_target_frames(structure)
    structure["action_inventory_complete"] = True
    structure["identities"] *= 4097
    with pytest.raises(ValueError, match="scope"):
        candidate.plan_target_frames(structure)


def test_action_bound_is_independent_of_smaller_identity_bound_before_outcomes():
    structure, _ = inputs()
    action = {"ticker": "ZZTEST0", "date": "2025-01-10", "action": "dividend"}
    structure["actions"] = [action] * 100000
    assert candidate.validate_structure(structure, require_action_accounting=False)
    structure["actions"].append(action)
    with pytest.raises(ValueError, match="scope"):
        candidate.validate_structure(structure, require_action_accounting=False)


@pytest.mark.parametrize("flag", [None, 0, 1, "no"])
def test_action_accounting_selector_cannot_be_coerced(flag):
    structure, _ = inputs()
    with pytest.raises(ValueError, match="accounting"):
        candidate.validate_structure(structure, require_action_accounting=flag)


@pytest.mark.parametrize("mutation", ["holdout", "no_buffer", "order", "same_clock", "no_actions"])
def test_calendar_scope_order_and_inventory_gates_refuse(mutation):
    structure, _ = inputs()
    if mutation == "holdout":
        structure["calendar"][-1]["session_date"] = "2027-09-01"
    elif mutation == "no_buffer":
        structure["calendar"] = [session for session in structure["calendar"] if session["session_date"] >= "2025-01-02"]
    elif mutation == "order":
        structure["calendar"].reverse()
    elif mutation == "same_clock":
        structure["calendar"][0]["close_utc"] = structure["calendar"][0]["open_utc"]
    else:
        structure["action_inventory_complete"] = False
    with pytest.raises(ValueError):
        candidate.build_target_frames(structure)


def test_raw_score_and_targets_are_independent_of_callers_decimal_rounding():
    structure, _ = inputs()
    with localcontext() as context:
        context.rounding = ROUND_DOWN
        first = candidate.build_target_frames(structure)
    with localcontext() as context:
        context.rounding = ROUND_UP
        second = candidate.build_target_frames(structure)
    assert first == second


@pytest.mark.parametrize("alteration", ["bounds", "trap"])
def test_candidate_freezes_decimal_exponent_bounds_and_traps_not_just_precision(alteration):
    structure, _ = inputs()
    expected = candidate.build_target_frames(structure)
    with localcontext() as context:
        if alteration == "bounds":
            context.Emax = 0
            context.Emin = 0
        else:
            context.traps[Inexact] = True
        assert candidate.build_target_frames(structure) == expected


def test_buffer_sessions_are_validated_but_never_counted_as_study_marks_or_orders():
    structure, outcomes = inputs()
    result = candidate.run_raw_candidate(structure, outcomes)
    assert result["buffer_sessions_validated"] == 3
    assert result["backtest"]["sessions"][0]["session_id"] == "2025-01-02"
    assert all(row["session_id"] >= "2025-01-02" for name in ("orders", "fills", "sessions")
               for row in result["backtest"][name])


@pytest.mark.parametrize("malformed", [None, {"security_id": "fixture-security-00"}])
def test_malformed_buffer_bars_refuse_framing_before_native_indexing(malformed):
    structure, outcomes = inputs()
    first_prior(outcomes)["bars"] = [malformed]
    with pytest.raises(ValueError):
        candidate.run_raw_candidate(structure, outcomes)


@pytest.mark.parametrize("issued", ["2024-07-31", "2025-04-01", "2027-09-01"])
def test_frozen_source_window_cannot_process_out_of_scope_ratings(issued):
    structure, _ = inputs()
    structure["ratings"][0]["date"] = issued
    with pytest.raises(ValueError, match="source.*window|scope"):
        candidate.build_target_frames(structure)


@pytest.mark.parametrize("field", ["structure", "outcome"])
def test_custom_schema_literals_never_execute_equality_callbacks(field):
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("source schema callback executed")
        def __ne__(self, other):
            pytest.fail("source schema callback executed")
    structure, outcomes = inputs()
    if field == "structure":
        structure["schema"] = Evil("tpr-raw-structure-v1")
    else:
        outcomes["schema"] = Evil("tpr-raw-outcomes-v1")
    with pytest.raises(ValueError):
        candidate.run_raw_candidate(structure, outcomes)


def test_custom_outcome_session_identity_is_rejected_before_equality():
    class Evil(str):
        def __eq__(self, other):
            pytest.fail("outcome session identity callback executed")
        def __ne__(self, other):
            pytest.fail("outcome session identity callback executed")
    structure, outcomes = inputs()
    outcomes["sessions"][0]["session_id"] = Evil("2024-12-27")
    with pytest.raises(ValueError):
        candidate.run_raw_candidate(structure, outcomes)


def test_connected_candidate_is_pure_after_calendar_fixture_construction(monkeypatch):
    import builtins
    import io
    import os
    import socket
    structure, outcomes = inputs()
    expected = candidate.run_raw_candidate(structure, outcomes)
    def refuse(*args, **kwargs):
        pytest.fail("raw candidate attempted I/O")
    for module, name in ((builtins, "open"), (io, "open"), (os, "open"), (os, "getenv"), (socket, "socket")):
        monkeypatch.setattr(module, name, refuse)
    assert candidate.run_raw_candidate(structure, outcomes) == expected
