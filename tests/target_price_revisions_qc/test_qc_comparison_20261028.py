"""Synthetic-only new-study policy/selection/transfer behavior, no native proof."""
import ast
from copy import deepcopy
from decimal import Decimal, Inexact, localcontext
from fractions import Fraction
import hashlib
from itertools import product
import json
from pathlib import Path

import pytest

from research.target_price_revisions_qc import comparison_20261028 as c
from research.target_price_revisions_qc import cap_tilt as old


def members(*ids):
    return [{"sid": sid, "ticker": "T-" + sid} for sid in ids]


def universe(**rows):
    return {sleeve: rows.get(sleeve, []) for sleeve in c.SLEEVES}


def off(rows, caps, **kwargs):
    return c.construct_off(rows, caps, finance_insurance_by_sid=kwargs.pop("finance", {}), **kwargs)


def tilt(rows, caps, scores, arm="cap_tilt_200", **kwargs):
    return c.construct_tilt(rows, caps, scores, arm=arm,
        finance_insurance_by_sid=kwargs.pop("finance", {}), **kwargs)


def pure(rows, scores, **kwargs):
    return c.construct_pure_tpr(rows, scores, finance_insurance_by_sid=kwargs.pop("finance", {}), **kwargs)


def test_policy_file_matches_exact_canonical_candidate_and_has_no_input_hashes():
    raw = Path(c.__file__).with_name("comparison_20261028_policy.json").read_bytes()
    assert raw == c.policy_bytes()
    assert c.validate_policy(raw) == hashlib.sha256(raw).hexdigest()
    policy = json.loads(raw)
    assert policy["status"] == "CANDIDATE_ONLY"
    assert policy["study_id"] == "TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1"
    assert [row["sleeve"] for row in policy["universes"]] == list(c.SLEEVES)
    assert [row["capacity"] for row in policy["arms"]] == ["0", "0.5", "1", "2", "0"]
    assert policy["construction"]["ar_enabled"] is False
    assert all(policy[key] is False for key in ("source_inputs_admitted", "native_setup_complete",
        "backtesting_ready", "canonical_admission", "trading_authority"))
    assert policy["limits"]["new_attempts"] == policy["limits"]["new_observed_looks"] == 0
    assert policy["limits"]["accepted_performance"] is None
    assert "input_hashes" not in policy
    assert policy["unchanged_execution_contract"]["buy_cash_fraction"] == "0.97"
    assert policy["dates"] == {"first_session": "2021-01-04", "end": "2026-10-09",
        "signal_warmup_start": "2020-09-01", "valuations": 1449, "decisions": 301}


@pytest.mark.parametrize("raw", [b"{}", b"", "{}", b"NaN", b"{\"x\":1,\"x\":2}"])
def test_noncanonical_policy_refuses(raw):
    with pytest.raises(c.ComparisonError): c.validate_policy(raw)


def test_policy_return_is_fresh_and_does_not_change_constants():
    policy = c.policy()
    policy["construction"]["sleeve_order"].append("QQQ")
    policy["arms"][0]["capacity"] = "999"
    assert c.policy()["arms"][0]["capacity"] == "0"
    assert c.SLEEVES == ("SPY", "XLE", "REMX", "KIE", "XLF", "IWM")
    assert old.ETFS == ("SPY", "XLV", "XLE", "QQQ", "SOXX", "REMX")


@pytest.mark.parametrize("arm,capacity", [("cap_off", "0"), ("cap_tilt_50", "0.5"), ("cap_tilt_100", "1")])
def test_zero_50_100_match_legacy_numeric_allocation_with_test_only_logical_renaming(arm, capacity):
    # Test logical sleeve slots only: production never aliases new universes.
    rows, caps, scores, old_selected = {}, {}, {}, {}
    for index, (new_sleeve, old_sleeve) in enumerate(zip(c.SLEEVES, old.ETFS)):
        ids = ["X", *(f"S{index}-{n}" for n in range(11))]
        rows[new_sleeve] = members(*ids)
        for n, sid in enumerate(ids):
            caps[sid] = str(1000 - n)
            scores[sid] = (None, "-9", "0", "2", "2", "7")[n % 6]
        old_selected[old_sleeve] = old.rank_cap_members(rows[new_sleeve], caps)[0]
    finance = {row["sid"]: "noninsurance" for row in rows["XLF"]}
    expected, previous = old.tilt_sleeves(old_selected, {} if arm == "cap_off" else scores, capacity=capacity)
    actual, report = (off(rows, caps, finance=finance) if arm == "cap_off"
                      else tilt(rows, caps, scores, arm=arm, finance=finance))
    assert actual == expected
    assert report["baseline_weights"] == previous["baseline_weights"]
    assert report["cash_weight"] == previous["cash_weight"]
    assert report["transferred_weight"] == previous["transferred_weight"]
    for new_sleeve, old_sleeve in zip(c.SLEEVES, old.ETFS):
        for key in ("target_weights", "rank_tilts", "target_weight", "cash_weight", "recipient_capacity",
                    "donor_capacity", "transferred_weight", "recipient_underfill", "aggregate_cap_blocked_capacity"):
            assert report["per_sleeve"][new_sleeve][key] == previous["per_sleeve"][old_sleeve][key]


def test_200_spends_only_actual_donor_to_zero_and_retains_unfunded_demand():
    target, report = tilt(universe(SPY=members("L", "H")), {"L": "2", "H": "1"}, {"L": "-2", "H": "7"})
    assert target == {"H": Fraction(1, 30), "L": 0}
    row = report["per_sleeve"]["SPY"]
    assert row["rank_tilts"] == {"L": -1, "H": 1}
    assert row["transferred_weight"] == Fraction(1, 60)
    assert row["recipient_underfill"] == row["recipient_capacity"] - Fraction(1, 60) > 0
    assert row["zero_weight_count"] == 1
    assert report["target_gross_weight"] == Fraction(1, 30)
    # A final rational residual permits exactly zero without independent clipping.
    assert (row["transferred_weight"] / c.QUANTUM).denominator != 1


def test_200_ten_distinct_scores_never_creates_the_zero_floor_leverage():
    rows = universe(**{sleeve: members(*(f"{sleeve}-{n}" for n in range(10))) for sleeve in c.SLEEVES})
    caps = {row["sid"]: str(20 - n) for records in rows.values() for n, row in enumerate(records)}
    scores = {row["sid"]: str(n + 1) for records in rows.values() for n, row in enumerate(records)}
    finance = {row["sid"]: "noninsurance" for row in rows["XLF"]}
    target, report = tilt(rows, caps, scores, finance=finance)
    assert sum(target.values()) == report["target_gross_weight"] == 1
    assert report["cash_weight"] == 0
    assert all(0 <= weight <= Fraction(1, 10) for weight in target.values())
    assert all(row["target_weight"] == Fraction(1, 6) for row in report["per_sleeve"].values())
    assert all(row["recipient_underfill"] > 0 for row in report["per_sleeve"].values())


def test_200_overlap_and_aggregate_cap_block_actual_donation():
    rows = universe(**{sleeve: members("X", "D-" + sleeve) for sleeve in c.SLEEVES})
    caps = {"X": "100", **{"D-" + sleeve: "1" for sleeve in c.SLEEVES}}
    scores = {"X": "8", **{"D-" + sleeve: "-4" for sleeve in c.SLEEVES}}
    target, report = tilt(rows, caps, scores, finance={"X": "noninsurance", "D-XLF": "noninsurance"})
    assert target["X"] == Fraction(1, 10)
    assert target == report["baseline_weights"]
    assert report["transferred_weight"] == 0
    assert all(row["aggregate_cap_blocked_capacity"] == row["recipient_capacity"] > 0
               for row in report["per_sleeve"].values())


def test_200_prior_sleeve_donation_creates_only_actual_name_cap_headroom():
    rows = universe(**{sleeve: members("X") for sleeve in c.SLEEVES})
    rows["SPY"].extend(members("H"))
    rows["XLE"].extend(members("L"))
    target, report = tilt(rows, {"X": "9", "H": "8", "L": "7"},
        {"X": "1", "H": "9", "L": "-9"}, finance={"X": "noninsurance"})
    assert target["X"] == Fraction(1, 10)
    assert target["H"] == Fraction(1, 30)
    assert target["L"] == 0
    assert report["transferred_weight"] == Fraction(1, 30)


@pytest.mark.parametrize("arm", ["cap_tilt_50", "cap_tilt_100", "cap_tilt_200"])
def test_missing_invalid_zero_single_scored_and_tied_only_remain_neutral(arm):
    ids = ("M", "U", "I", "Z", "A", "B")
    scores = {"U": {"state": "unknown", "value": "999"}, "I": float("nan"), "Z": "0", "A": "4", "B": "4"}
    target, report = tilt(universe(SPY=members(*ids)), dict.fromkeys(ids, "1"), scores, arm=arm)
    assert target == dict.fromkeys(ids, Fraction(1, 60))
    assert report["per_sleeve"]["SPY"]["score_state_counts"] == {
        "missing": 1, "unknown": 1, "invalid": 1, "zero": 1, "nonzero": 2}
    assert report["transferred_weight"] == 0


def test_off_has_no_signal_parameter_and_tilt_never_reads_nonselected_values():
    class SelectedOnly(dict):
        def get(self, key, default=None):
            if key == "UNSELECTED": raise AssertionError("unselected score was read")
            return super().get(key, default)
    ids = [*(f"A{n}" for n in range(10)), "UNSELECTED"]
    rows = universe(SPY=members(*ids))
    caps = {sid: str(100 - n) for n, sid in enumerate(ids)}
    scores = SelectedOnly({sid: str(n + 1) for n, sid in enumerate(ids)})
    target, _ = tilt(rows, caps, scores)
    assert "UNSELECTED" not in target
    with pytest.raises(TypeError): c.construct_off(rows, caps, scores=scores, finance_insurance_by_sid={})


def test_pure_signed_ranking_includes_zero_above_negative_and_excludes_all_unavailable():
    ids = ("P", "Z", "N", "M", "U", "I", "J", "K")
    scores = {"P": "2", "Z": "0", "N": "-3", "U": {"state": "unknown", "value": "900"},
              "I": {"state": "invalid", "value": "900"}, "J": None, "K": "NaN", "OUTSIDE": "9999"}
    target, report = pure(universe(SPY=members(*ids)), scores)
    row = report["per_sleeve"]["SPY"]
    assert row["ranked_ids"] == ("P", "Z", "N")
    assert target == {sid: Fraction(1, 60) for sid in ("P", "Z", "N")}
    assert row["selection_coverage"]["score_state_counts"] == {
        "nonzero": 2, "zero": 1, "missing": 2, "unknown": 1, "invalid": 2}
    assert row["unfilled_slots"] == 7
    assert report["cash_weight"] == Fraction(19, 20)


def test_pure_ties_by_permanent_sid_caps_are_not_an_input_or_called(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("cap selection was called")
    monkeypatch.setattr(old, "rank_cap_members", forbidden)
    ids = [f"S{n:02}" for n in reversed(range(12))]
    rows = universe(SPY=members(*ids))
    target, report = pure(rows, dict.fromkeys(ids, "0"))
    assert report["per_sleeve"]["SPY"]["ranked_ids"] == tuple(sorted(ids)[:10])
    assert len(target) == 10
    with pytest.raises(TypeError): c.construct_pure_tpr(rows, {}, caps={}, finance_insurance_by_sid={})


@pytest.mark.parametrize("constructor", ["cap_off", "cap_tilt_200", "pure_tpr"])
def test_warning_final_removal_happens_after_top10_and_never_refills(constructor):
    ids = [f"S{n:02}" for n in range(12)]
    rows = universe(SPY=members(*ids))
    values = {sid: str(100 - n) for n, sid in enumerate(ids)}
    kwargs = {"warning_ids": ("S00",), "final_ids": ("S01", "S00")}
    target, report = (off(rows, values, **kwargs) if constructor == "cap_off" else
        pure(rows, values, **kwargs) if constructor == "pure_tpr" else tilt(rows, values, values, **kwargs))
    row = report["per_sleeve"]["SPY"]
    assert row["ranked_count"] == 10
    assert row["executable_count"] == 8
    assert row["unfilled_slots"] == 2
    assert "S10" not in target and "S11" not in target
    assert row["removed_unusable"] == ({"security_id": "S00", "state": "final"}, {"security_id": "S01", "state": "final"})
    assert sum(target.values()) == Fraction(2, 15)


@pytest.mark.parametrize("constructor", ["off", "tilt", "pure"])
def test_finance_insurance_filter_precedes_all_rankings_and_retains_census(constructor):
    rows = universe(XLF=members("INS", "FIN"), KIE=members("INS"))
    values = {"INS": "100000", "FIN": "-2" if constructor == "pure" else "1"}
    finance = {"INS": "insurance", "FIN": "noninsurance"}
    target, report = (off(rows, values, finance=finance) if constructor == "off" else
        pure(rows, values, finance=finance) if constructor == "pure" else tilt(rows, values, values, finance=finance))
    assert report["per_sleeve"]["XLF"]["ranked_ids"] == ("FIN",)
    assert report["per_sleeve"]["KIE"]["ranked_ids"] == ("INS",)
    assert target == {"INS": Fraction(1, 60), "FIN": Fraction(1, 60)}
    assert report["finance_classification"] == {"supplied_finance_members": 2,
        "insurance_excluded": 1, "noninsurance_retained": 1, "missing_or_unknown": 0,
        "historical_classification_authenticated": False}


@pytest.mark.parametrize("classification", [{}, {"X": "unknown"}, {"X": None}, {"X": "Insurance"}, {"X": True}, {"X": "noninsurance", "EXTRA": "insurance"}])
def test_missing_unknown_invalid_or_unbound_finance_classification_refuses(classification):
    with pytest.raises(c.ComparisonError):
        pure(universe(XLF=members("X")), {"X": "1"}, finance=classification)


@pytest.mark.parametrize("value", ["1e9999999", "9" * 129, Decimal("1e9999"), 2**513, Fraction(1, 2**513),
    {"state": "nonzero", "value": "0"}, {"state": "zero", "value": "1"}, {"state": "available", "value": "3", "future": True}, True, 1.0])
def test_pure_numeric_bounds_and_inconsistent_states_become_invalid_not_zero(value):
    target, report = pure(universe(SPY=members("X")), {"X": value})
    assert target == {}
    assert report["per_sleeve"]["SPY"]["selection_coverage"]["score_state_counts"]["invalid"] == 1


@pytest.mark.parametrize("value", ["-1", "0", "NaN", "1e9999999", "9" * 129, 2**513])
def test_bad_caps_never_enter_any_cap_selected_arm(value):
    target, report = off(universe(SPY=members("X")), {"X": value})
    assert target == {}
    assert report["cash_weight"] == 1
    assert report["per_sleeve"]["SPY"]["selection_coverage"]["selected_count"] == 0


@pytest.mark.parametrize("rows", [{}, universe(SPY=[None]), universe(SPY=members("X", "X")),
    universe(SPY=[{"sid": "X", "ticker": "T"}], XLE=[{"sid": "X", "ticker": "OTHER"}]),
    universe(SPY=[{"sid": "X", "ticker": "T"}], XLE=[{"sid": "Y", "ticker": "T"}]),
    universe(SPY=[{"sid": "X\n", "ticker": "T"}]), universe(SPY=[{"sid": "X", "ticker": "T" * 33}])])
def test_invalid_or_ambiguous_members_refuse(rows):
    with pytest.raises(c.ComparisonError): pure(rows, {})


@pytest.mark.parametrize("arm", ["cap_off", "pure_tpr", "cap_tilt_20", "cap_tilt_150", "2", None, True])
def test_only_predeclared_tilt_arm_ids_accepted(arm):
    with pytest.raises(c.ComparisonError): tilt(universe(), {}, {}, arm=arm)


def test_inputs_are_not_mutated_and_decimal_context_cannot_change_exact_allocation():
    rows, caps, scores = universe(SPY=members("L", "H")), {"L": "100", "H": "90"}, {"L": "-9", "H": "2"}
    before = deepcopy((rows, caps, scores))
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        actual = tilt(rows, caps, scores)
    assert (rows, caps, scores) == before
    assert actual == tilt(rows, caps, scores)


def test_all_three_name_synthetic_score_states_200_conserve_identity_budget_and_caps():
    rows, caps = universe(SPY=members("A", "B", "C")), dict.fromkeys(("A", "B", "C"), "1")
    for values in product((None, "-2", "-1", "0", "1", "2"), repeat=3):
        target, report = tilt(rows, caps, dict(zip(("A", "B", "C"), values)))
        assert set(target) == {"A", "B", "C"}
        assert sum(target.values()) == Fraction(1, 20)
        assert all(0 <= value <= Fraction(1, 10) for value in target.values())
        assert report["cash_weight"] == Fraction(19, 20)
        assert report["per_sleeve"]["SPY"]["recipient_underfill"] >= 0


def test_every_report_keeps_acceptance_and_source_custody_false():
    for _, report in (off(universe(), {}), tilt(universe(), {}, {}), pure(universe(), {})):
        assert all(report[key] is False for key in ("source_inputs_admitted", "native_basis_authenticated",
            "runtime_integration_complete", "backtesting_ready", "canonical_admission"))
        assert report["accepted_performance"] is None


def test_import_closure_has_only_pure_legacy_and_stdlib_no_io_or_effect():
    tree = ast.parse(Path(c.__file__).read_text())
    imports = [(node.module, node.level) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert (None, 1) in imports
    assert all(level or module in ("__future__", "collections.abc", "decimal", "fractions") for module, level in imports)
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {"open", "eval", "exec", "compile", "__import__"}


def _mutated_function(name, before, after):
    source = Path(c.__file__).read_text()
    assert source.count(before) == 1
    mutated = ast.parse(source.replace(before, after))
    node = next(node for node in mutated.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = dict(c.__dict__)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<in-memory-comparison-mutant>", "exec"), namespace)
    return namespace[name]


def test_in_memory_donor_zero_stop_mutant_is_killed_and_restored(monkeypatch):
    real = c._allocate
    mutant = _mutated_function("_allocate", "available = min(demand[donor] - spent, updated[donor])",
        "available = demand[donor] - spent")
    try:
        monkeypatch.setattr(c, "_allocate", mutant)
        with pytest.raises((AssertionError, c.ComparisonError)):
            test_200_spends_only_actual_donor_to_zero_and_retains_unfunded_demand()
    finally:
        monkeypatch.setattr(c, "_allocate", real)
    test_200_spends_only_actual_donor_to_zero_and_retains_unfunded_demand()


def test_in_memory_pure_zero_exclusion_mutant_is_killed_and_restored(monkeypatch):
    real = c.construct_pure_tpr
    mutant = _mutated_function("construct_pure_tpr", 'if state in ("nonzero", "zero"):', 'if state == "nonzero":')
    try:
        monkeypatch.setattr(c, "construct_pure_tpr", mutant)
        with pytest.raises(AssertionError):
            test_pure_signed_ranking_includes_zero_above_negative_and_excludes_all_unavailable()
    finally:
        monkeypatch.setattr(c, "construct_pure_tpr", real)
    test_pure_signed_ranking_includes_zero_above_negative_and_excludes_all_unavailable()


def test_in_memory_finance_filter_mutant_is_killed_and_restored(monkeypatch):
    real = c._members
    before = 'inventory["XLF"] = [row for row in finance if finance_insurance_by_sid[row["sid"]] == "noninsurance"]'
    mutant = _mutated_function("_members", before, 'inventory["XLF"] = finance')
    try:
        monkeypatch.setattr(c, "_members", mutant)
        with pytest.raises(AssertionError):
            test_finance_insurance_filter_precedes_all_rankings_and_retains_census("pure")
    finally:
        monkeypatch.setattr(c, "_members", real)
    test_finance_insurance_filter_precedes_all_rankings_and_retains_census("pure")


@pytest.mark.parametrize("state", ["missing", "unknown", "invalid"])
def test_explicit_unavailable_state_ignores_retained_value_and_preserves_census(state):
    cell = {"state": state, "value": "9" * 1000}
    target, report = pure(universe(SPY=members("X")), {"X": cell})
    assert target == {}
    counts = report["per_sleeve"]["SPY"]["selection_coverage"]["score_state_counts"]
    assert counts[state] == 1 and sum(counts.values()) == 1
    target, report = off(universe(SPY=members("X")), {"X": cell})
    counts = report["per_sleeve"]["SPY"]["selection_coverage"]["cap_state_counts"]
    assert target == {} and counts[state] == 1 and sum(counts.values()) == 1


@pytest.mark.parametrize("key", ["", "X\n", " X", "X" * 129, 1, None])
def test_source_mapping_keys_are_bounded_permanent_identity_strings(key):
    with pytest.raises(c.ComparisonError): pure(universe(), {key: "1"})
    with pytest.raises(c.ComparisonError): off(universe(), {key: "1"})


@pytest.mark.parametrize("score", ["+.25", "1e2", Decimal("1.1"), Fraction(1, 7), 2, {"state": "zero", "value": None}])
def test_pure_supports_exact_representations_and_explicit_measured_zero(score):
    target, report = pure(universe(SPY=members("X")), {"X": score})
    assert target == {"X": Fraction(1, 60)}
    assert report["per_sleeve"]["SPY"]["selection_coverage"]["eligible_count"] == 1


def test_native_identity_inventory_and_input_row_limits_are_enforced():
    with pytest.raises(c.ComparisonError):
        pure(universe(SPY=members(*(f"S{n}" for n in range(c.MAX_IDENTITIES + 1)))), {})
    with pytest.raises(c.ComparisonError):
        pure(universe(), {f"S{n}": "1" for n in range(c.MAX_IDENTITIES + 1)})


def test_member_and_mapping_order_do_not_change_deterministic_reports():
    rows = universe(SPY=members("L", "H", "Z"), XLE=members("X", "H"))
    caps, scores = {"L": "9", "H": "7", "Z": "1", "X": "8"}, {"L": "-2", "H": "1", "Z": "0", "X": "9"}
    expected = tilt(rows, caps, scores)
    reordered = {key: list(reversed(value)) for key, value in reversed(tuple(rows.items()))}
    assert tilt(reordered, dict(reversed(tuple(caps.items()))), dict(reversed(tuple(scores.items())))) == expected
    assert pure(reordered, dict(reversed(tuple(scores.items())))) == pure(rows, scores)
